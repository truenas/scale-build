# -*- coding=utf-8 -*-
from collections import defaultdict
import contextlib
from datetime import datetime
import itertools
import json
import logging
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import textwrap

import psutil

from licenselib.license import ContractType, License
from .fhs import TRUENAS_DATASETS

logger = logging.getLogger(__name__)

EFI_SYSTEM_PARTITION_GUID = "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"
FREEBSD_BOOT_PARTITION_GUID = "83BD6B9D-7F41-11DC-BE0B-001560B84F0F"

CORE_BSD_LOADER_PATH = "/boot/efi/efi/boot/BOOTx64.efi"
SCALE_BSD_LOADER_PATH = "/boot/efi/efi/boot/FreeBSD.efi"

RE_UNSQUASHFS_PROGRESS = re.compile(r"\[.+\]\s+(?P<extracted>[0-9]+)/(?P<total>[0-9]+)\s+(?P<progress>[0-9]+)%")
run_kw = dict(check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", errors="ignore")

IS_FREEBSD = platform.system().upper() == "FREEBSD"
is_json_output = False


def write_progress(progress, message):
    if is_json_output:
        sys.stdout.write(json.dumps({"progress": progress, "message": message}) + "\n")
    else:
        sys.stdout.write(f"[{int(progress * 100)}%] {message}\n")
    sys.stdout.flush()


def write_error(error, raise_=False, prefix="Error: "):
    if is_json_output:
        sys.stdout.write(json.dumps({"error": error}) + "\n")
    else:
        sys.stdout.write(f"{prefix}{error}\n")
    sys.stdout.flush()

    if raise_:
        raise Exception(error)


def run_command(cmd, **kwargs):
    try:
        return subprocess.run(cmd, **dict(run_kw, **kwargs))
    except subprocess.CalledProcessError as e:
        write_error(f"Command {cmd} failed with exit code {e.returncode}: {e.stderr}")
        raise


def get_partition(disk, partition):
    paths = [f"/dev/{disk}{partition}", f"/dev/{disk}p{partition}"]
    for path in paths:
        if os.path.exists(path):
            return path
    raise Exception(f"Neither {' or '.join(paths)} exist")


def get_partition_guid(disk, partition):
    return dict(map(
        lambda s: s.split(": ", 1),
        run_command(["sgdisk", "-i", str(partition), f"/dev/{disk}"]).stdout.splitlines(),
    ))["Partition GUID code"].split()[0]


def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def query_row(query, database_path, prefix=None):
    database_path = database_path
    conn = sqlite3.connect(database_path)
    try:
        conn.row_factory = dict_factory
        c = conn.cursor()
        try:
            c.execute(query)
            result = c.fetchone()
        finally:
            c.close()
    finally:
        conn.close()
    if prefix:
        result = {k.replace(prefix, ""): v for k, v in result.items()}
    return result


def query_config_table(table, database_path, prefix=None):
    return query_row(f"SELECT * FROM {table}", database_path, prefix)


def configure_serial_port(root, db_path):
    if not os.path.exists(db_path):
        return

    # We would like to explicitly enable/disable serial-getty in the new BE based on db configuration
    advanced = query_config_table("system_advanced", db_path, prefix="adv_")
    if advanced["serialconsole"]:
        run_command(
            ["chroot", root, "systemctl", "enable", f"serial-getty@{advanced['serialport']}.service"], check=False
        )


def database_path(root):
    return os.path.join(root, "data/freenas-v1.db")


def enable_system_user_services(root, old_root):
    configure_serial_port(root, database_path(old_root))
    enable_user_services(root, old_root)


def enable_user_services(root, old_root):
    user_services_file = os.path.join(old_root, "data/user-services.json")
    if not os.path.exists(user_services_file):
        return

    with open(user_services_file, 'r') as f:
        systemd_units = [
            srv for srv, enabled in json.loads(f.read()).items() if enabled
        ]

    if systemd_units:
        run_command(["chroot", root, "systemctl", "enable"] + systemd_units, check=False)


def install_grub_freebsd(input, manifest, pool_name, dataset_name, disks):
    boot_partition_type = None
    for disk in disks:
        gpart_backup = run_command(["gpart", "backup", disk]).stdout.splitlines()
        partition_table_type = gpart_backup[0].split()[0]
        if partition_table_type == "GPT":
            boot_partition_type_probe = gpart_backup[1].split()[1]
            if boot_partition_type_probe not in ["bios-boot", "freebsd-boot", "efi"]:
                write_error(f"Invalid first partition type {boot_partition_type_probe} on {disk}", raise_=True)
            if boot_partition_type and boot_partition_type != boot_partition_type_probe:
                write_error("Non-matching first partition types across disks", raise_=True)
            boot_partition_type = boot_partition_type_probe
        else:
            write_error(f"Invalid partition table type {partition_table_type} on {disk}", raise_=True)

    run_command(["zpool", "set", f"bootfs={dataset_name}", pool_name])

    for f in ["/usr/local/etc/grub.d/10_kfreebsd", "/usr/local/etc/grub.d/30_os-prober"]:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(f)

    os.makedirs("/usr/local/etc/default", exist_ok=True)
    run_command(["truenas-grub.py"])

    cmdline = run_command(["sh", "-c", ". /usr/local/etc/default/grub; echo $GRUB_CMDLINE_LINUX"]).stdout.strip()

    for device in input["devices"]:
        fs_uuid = run_command(["grub-probe", "--device", f"/dev/{device}", "--target=fs_uuid"]).stdout.strip()
        if fs_uuid:
            break
    else:
        write_error(f"None of {input['devices']!r} has GRUB fs_uuid", raise_=True)

    grub_script_path = "/usr/local/etc/grub.d/10_truenas"
    with open(grub_script_path, "w") as f:
        freebsd_root_dataset = [p for p in psutil.disk_partitions() if p.mountpoint == "/"][0].device
        run_command(["zfs", "set", "truenas:12=1", freebsd_root_dataset])

        f.write(textwrap.dedent(f"""\
            #!/bin/sh
            cat << 'EOF'
            menuentry 'TrueNAS SCALE' --class truenas --class gnu-linux --class gnu --class os """
                                f"""$menuentry_id_option 'gnulinux-simple-{fs_uuid}' {{
                load_video
                insmod gzio
                if [ x$grub_platform = xxen ]; then insmod xzio; insmod lzopio; fi
                insmod part_gpt
                insmod zfs
                search --no-floppy --fs-uuid --set=root {fs_uuid}
                echo	'Loading Linux {manifest['kernel_version']} ...'
                linux	/ROOT/{manifest['version']}@/boot/vmlinuz-{manifest['kernel_version']} """
                                f"""root=ZFS={dataset_name} ro {cmdline} console=tty1 zfs_force=yes
                echo	'Loading initial ramdisk ...'
                initrd	/ROOT/{manifest['version']}@/boot/initrd.img-{manifest['kernel_version']}
            }}

            menuentry 'TrueNAS CORE' --class truenas --class gnu-linux --class gnu --class os """
                                f"""$menuentry_id_option 'gnulinux-simple-{fs_uuid}-core' {{
                load_video
                insmod gzio
                if [ x$grub_platform = xxen ]; then insmod xzio; insmod lzopio; fi
                insmod part_gpt
                insmod zfs
                search --no-floppy --fs-uuid --set=root {fs_uuid}
                echo	'Loading Linux {manifest['kernel_version']} ...'
                linux	/ROOT/{manifest['version']}@/boot/vmlinuz-{manifest['kernel_version']} """
                                f"""root=ZFS={dataset_name} ro {cmdline} console=tty1 zfs_force=yes """
                                f"""systemd.setenv=_BOOT_TRUENAS_CORE=1
                echo	'Loading initial ramdisk ...'
                initrd	/ROOT/{manifest['version']}@/boot/initrd.img-{manifest['kernel_version']}
            }}
        """))

    os.chmod(grub_script_path, 0o0755)

    os.makedirs("/boot/grub", exist_ok=True)
    run_command(["zfs", "destroy", "-r", f"{pool_name}/grub"], check=False)
    run_command(["zfs", "create", "-o", "mountpoint=legacy", f"{pool_name}/grub"])
    run_command(["mount", "-t", "zfs", f"{pool_name}/grub", "/boot/grub"])
    run_command(["grub-mkconfig", "-o", "/boot/grub/grub.cfg"])

    for disk in disks:
        if boot_partition_type in ["bios-boot", "freebsd-boot"]:
            if boot_partition_type != "bios-boot":
                run_command(["gpart", "modify", "-i", "1", "-t", "bios-boot", f"/dev/{disk}"])
            run_command(["grub-install", "--target=i386-pc", f"/dev/{disk}"])
        elif boot_partition_type == "efi":
            os.makedirs("/boot/efi", exist_ok=True)
            run_command(["umount", "/boot/efi"], check=False)
            run_command(["mount", "-t", "msdosfs", get_partition(disk, 1), "/boot/efi"])
            try:
                if not os.path.exists(SCALE_BSD_LOADER_PATH):
                    shutil.copyfile(CORE_BSD_LOADER_PATH, SCALE_BSD_LOADER_PATH)
                run_command(["grub-install", "--target=x86_64-efi", "--efi-directory=/boot/efi", "--removable"])
            finally:
                run_command(["umount", "/boot/efi"])


def configure_system_for_zectl(boot_pool):
    root_ds = os.path.join(boot_pool, "ROOT")
    set_prop = IS_FREEBSD or run_command([
        "zfs", "get", "-H", "-o", "value", "org.zectl:bootloader", root_ds
    ]).stdout.strip() != 'grub'
    if set_prop:
        run_command(["zfs", "set", "org.zectl:bootloader=grub", root_ds])


def read_license(root):
    license_path = os.path.join(root, "data/license")
    try:
        with open(license_path) as f:
            return License.load(f.read().strip('\n'))
    except Exception:
        return None


def andjoin(array, singular, plural):
    if len(array) == 1:
        return f"{array[0]} {singular}"

    if len(array) == 2:
        return f"{array[0]} and {array[1]} {plural}"

    return ", ".join(array[:-1]) + f" and {array[-1]} {plural}"


def precheck(old_root):
    services = [
        ("dynamicdns", "Dynamic DNS", "inadyn", None),
        ("openvpn_client", "OpenVPN Client", "openvpn", "client.conf"),
        ("openvpn_server", "OpenVPN Server", "openvpn", "server.conf"),
        ("rsync", "Rsync", "rsync", "--daemon"),
        ("s3", "S3", "minio", None),
        ("tftp", "TFTP", "in.tftpd", None),
        ("webdav", "WebDAV", "apache2", None),
    ]

    if old_root is not None:
        enabled_services = []
        db_path = database_path(old_root)
        if os.path.exists(db_path):
            for service, title, process_name, cmdline in services:
                try:
                    if query_row(
                        f"SELECT * FROM services_services WHERE srv_service = '{service}' AND srv_enable = 1",
                        db_path,
                    ) is not None:
                        enabled_services.append(title)
                except Exception:
                    pass

        processes = defaultdict(list)
        for p in psutil.process_iter():
            processes[p.name()].append(p.pid)
        running_services = []
        for service, title, process_name, cmdline in services:
            if process_name in processes:
                # If we report an enabled service, we don't want to report the same service running.
                if title not in enabled_services:
                    for pid in processes[process_name]:
                        if cmdline is not None:
                            try:
                                if cmdline not in psutil.Process(pid).cmdline():
                                    continue
                            except psutil.NoSuchProcess:
                                continue

                        try:
                            with open(f"/proc/{pid}/cgroup") as f:
                                cgroups = f.read()
                        except FileNotFoundError:
                            cgroups = ""

                        if "kubepods" in cgroups:
                            continue

                        running_services.append(title)
                        break

        if enabled_services or running_services:
            if (
                (licenseobj := read_license(old_root)) and
                ContractType(licenseobj.contract_type) in [ContractType.silver, ContractType.gold] and
                licenseobj.contract_end > datetime.utcnow().date()
            ):
                fatal = True
                text = (
                    "There are active configured services on this system that are not present in the new version. To "
                    "avoid any loss of system services, please contact iXsystems Support to schedule a guided upgrade. "
                    "Additional details are available from https://www.truenas.com/docs/scale/scaledeprecatedfeatures/."
                )
            else:
                fatal = False
                text = (
                    "There are active configured services on this system that are not present in the new version. "
                    "Upgrading this system deletes these services and saved settings: "
                    f"{andjoin(sorted(enabled_services + running_services), 'service', 'services')}. "
                    "This disrupts any system usage that relies on these active services."
                )

            return fatal, text


def main():
    global is_json_output

    input = json.loads(sys.stdin.read())

    if input.get("json"):
        is_json_output = True
    old_root = input.get("old_root", None)

    if input.get("precheck"):
        if precheck_result := precheck(old_root):
            fatal, text = precheck_result
            if fatal:
                write_error(text)
                sys.exit(2)
            else:
                write_error(text, prefix="")

        sys.exit(0)

    cleanup = input.get("cleanup", True)
    disks = input["disks"]
    force_grub_install = input.get("force_grub_install", False)
    authentication_method = input.get("authentication_method", None)
    pool_name = input["pool_name"]
    sql = input.get("sql", None)
    src = input["src"]

    with open(os.path.join(src, "manifest.json")) as f:
        manifest = json.load(f)

    old_bootfs_prop = run_command(["zpool", "get", "-H", "-o", "value", "bootfs", pool_name]).stdout.strip()

    write_progress(0, "Creating dataset")
    if input.get("dataset_name"):
        dataset_name = input["dataset_name"]
    else:
        dataset_name = f"{pool_name}/ROOT/{manifest['version']}"

        existing_datasets = set(filter(None, run_command(["zfs", "list", "-H", "-o", "name"]).stdout.split("\n")))
        if dataset_name in existing_datasets:
            for i in itertools.count(1):
                probe_dataset_name = f"{dataset_name}-{i}"
                if probe_dataset_name not in existing_datasets:
                    dataset_name = probe_dataset_name
                    break

    run_command([
        "zfs", "create",
        "-o", "mountpoint=legacy",
        "-o", f"truenas:kernel_version={manifest['kernel_version']}",
        "-o", "zectl:keep=False",
        dataset_name,
    ])

    for entry in TRUENAS_DATASETS:
        cmd = ["zfs", "create", "-u", "-o", "mountpoint=legacy", "-o", "canmount=noauto"]
        if "NOSUID" in entry["options"]:
            cmd.extend(["-o", "setuid=off", "-o", "devices=off"])
        if "NOEXEC" in entry["options"]:
            cmd.extend(["-o", "exec=off"])
        if "NODEV" in entry["options"]:
            cmd.extend(["-o", "devices=off"])
        if "NOACL" in entry['options']:
            cmd.extend(["-o", "acltype=off", "-o", "aclmode=discard"])
        if "NOATIME" in entry["options"]:
            cmd.extend(["-o", "atime=off"])

        cmd.append(f"{dataset_name}/{entry['name']}")
        run_command(cmd)

    try:
        with tempfile.TemporaryDirectory() as root:
            undo = []
            ds_info = []
            run_command(["mount", "-t", "zfs", dataset_name, root])
            for entry in TRUENAS_DATASETS:
                this_ds = entry['name']
                ds_name = f"{dataset_name}/{this_ds}"
                ds_path = entry.get("mountpoint") or f"/{entry['name']}"
                ds_guid = run_command(["zfs", "list", "-o", "guid", "-H", ds_name]).stdout.strip()

                mp = os.path.join(root, ds_path[1:])
                os.makedirs(mp, exist_ok=True)
                run_command(["mount", "-t", "zfs", f"{dataset_name}/{this_ds}", mp])
                ds_info.append({"ds": ds_name, "guid": ds_guid, "fhs_entry": entry})
                undo.append(["umount", mp])

            try:
                write_progress(0, "Extracting")
                cmd = [
                    "unsquashfs",
                    "-d", root,
                    "-f",
                    "-da", "16",
                    "-fr", "16",
                    os.path.join(src, "rootfs.squashfs"),
                ]
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                stdout = ""
                buffer = b""
                for char in iter(lambda: p.stdout.read(1), b""):
                    buffer += char
                    if char == b"\n":
                        stdout += buffer.decode("utf-8", "ignore")
                        buffer = b""

                    if buffer and buffer[0:1] == b"\r" and buffer[-1:] == b"%":
                        if m := RE_UNSQUASHFS_PROGRESS.match(buffer[1:].decode("utf-8", "ignore")):
                            write_progress(
                                int(m.group("extracted")) / int(m.group("total")) * 0.5,
                                "Extracting",
                            )
                            buffer = b""

                p.wait()
                if p.returncode != 0:
                    write_error({"error": f"unsquashfs failed with exit code {p.returncode}: {stdout}"})
                    raise subprocess.CalledProcessError(p.returncode, cmd, stdout)

                write_progress(0.5, "Performing post-install tasks")

                for entry in TRUENAS_DATASETS:
                    if not (force_mode := entry.get("mode")):
                        continue

                    os.chmod(f"{root}/{entry['name']}", force_mode)

                with open(f"{root}/conf/truenas_root_ds.json", "w") as f:
                    f.write(json.dumps(ds_info, indent=4))

                with contextlib.suppress(FileNotFoundError):
                    # We want to remove this for fresh installation + upgrade both
                    # In this case, /etc/machine-id would be treated as the valid
                    # machine-id which it will be otherwise as well if we use
                    # systemd-machine-id-setup --print to confirm but just to be cautious
                    # we remove this as it will be generated automatically by systemd then
                    # complying with /etc/machine-id contents
                    os.unlink(f"{root}/var/lib/dbus/machine-id")

                is_freebsd_upgrade = False
                setup_machine_id = False
                configure_serial = False
                if old_root is not None:
                    if os.path.exists(f"{old_root}/bin/freebsd-version"):
                        is_freebsd_upgrade = True

                    rsync = [
                        "etc/hostid",
                        "data",
                        "home",
                        "root",
                    ]
                    if is_freebsd_upgrade:
                        if not IS_FREEBSD:
                            setup_machine_id = True
                    else:
                        rsync.append("etc/machine-id")

                    run_command([
                        "rsync", "-aRx",
                        "--exclude", "data/factory-v1.db",
                        "--exclude", "data/manifest.json",
                        "--exclude", "data/sentinels",
                    ] + rsync + [
                        f"{root}/",
                    ], cwd=old_root)

                    with open(f"{root}/data/need-update", "w"):
                        pass

                    if is_freebsd_upgrade:
                        with open(f"{root}/data/freebsd-to-scale-update", "w"):
                            pass
                    else:
                        enable_system_user_services(root, old_root)
                else:
                    run_command(["cp", "/etc/hostid", f"{root}/etc/"])

                    with open(f"{root}/data/first-boot", "w"):
                        pass
                    with open(f"{root}/data/truenas-eula-pending", "w"):
                        pass

                    setup_machine_id = configure_serial = True

                is_freebsd_loader_upgrade = is_freebsd_upgrade
                if not is_freebsd_loader_upgrade and old_root is None and old_bootfs_prop != "-":
                    # Probably installing SCALE on CORE-formatted pool
                    with tempfile.TemporaryDirectory() as td:
                        try:
                            run_command(["mount", "-t", "zfs", old_bootfs_prop, td])
                        except Exception:
                            pass
                        else:
                            try:
                                if os.path.exists(f"{td}/bin/freebsd-version"):
                                    is_freebsd_loader_upgrade = True
                            finally:
                                run_command(["umount", td])

                # We do not want /data directory to be world readable
                # Doing this here is important so that we cover both fresh install and upgrade case
                run_command(["chmod", "-R", "u=rwX,g=,o=", f"{root}/data"])

                if setup_machine_id:
                    with contextlib.suppress(FileNotFoundError):
                        os.unlink(f"{root}/etc/machine-id")

                    run_command(["systemd-machine-id-setup", f"--root={root}"])

                if IS_FREEBSD:
                    install_grub_freebsd(input, manifest, pool_name, dataset_name, disks)
                else:
                    try:
                        run_command(["mount", "-t", "devtmpfs", "udev", f"{root}/dev"])
                        undo.append(["umount", f"{root}/dev"])

                        run_command(["mount", "-t", "proc", "none", f"{root}/proc"])
                        undo.append(["umount", f"{root}/proc"])

                        run_command(["mount", "-t", "sysfs", "none", f"{root}/sys"])
                        undo.append(["umount", f"{root}/sys"])

                        run_command(["mount", "-t", "zfs", f"{pool_name}/grub", f"{root}/boot/grub"])
                        undo.append(["umount", f"{root}/boot/grub"])

                        # It will legitimately exit with code 2 if initramfs must be updated (which we'll do anyway)
                        write_progress(0.55, "Running autotune")
                        run_command(["chroot", root, "/usr/local/bin/truenas-autotune.py", "--skip-unknown"],
                                    check=False)

                        if authentication_method is not None:
                            write_progress(0.56, "Setting up authentication")
                            run_command(["chroot", root, "/usr/local/bin/truenas-set-authentication-method.py"],
                                        input=json.dumps(authentication_method))

                        if sql is not None:
                            write_progress(0.57, "Upgrading database")
                            run_command(["chroot", root, "sqlite3", "/data/freenas-v1.db"], input=sql)

                        if configure_serial:
                            write_progress(0.58, "Configuring serial port")
                            configure_serial_port(root, os.path.join(root, "data/freenas-v1.db"))

                        # Set bootfs before running update-grub
                        run_command(["zpool", "set", f"bootfs={dataset_name}", pool_name])
                        if is_freebsd_loader_upgrade:
                            if old_bootfs_prop != "-":
                                run_command(["zfs", "set", "truenas:12=1", old_bootfs_prop])

                        cp = run_command([f"{root}/usr/local/bin/truenas-initrd.py", root], check=False)
                        if cp.returncode > 1:
                            raise subprocess.CalledProcessError(
                                cp.returncode, f'Failed to execute truenas-initrd: {cp.stderr}'
                            )

                        write_progress(0.7, "Preparing NVDIMM configuration")
                        run_command(["chroot", root, "/usr/local/bin/truenas-nvdimm.py"])
                        write_progress(0.71, "Preparing GRUB configuration")
                        run_command(["chroot", root, "/usr/local/bin/truenas-grub.py"])
                        write_progress(0.8, "Updating initramfs")
                        run_command(["chroot", root, "update-initramfs", "-k", "all", "-u"])
                        write_progress(0.9, "Updating GRUB")
                        run_command(["chroot", root, "update-grub"])

                        # We would like to configure fips bit as well here
                        write_progress(0.95, "Configuring FIPS")
                        run_command(["chroot", root, "/usr/bin/configure_fips"])

                        if old_root is None or force_grub_install:
                            write_progress(0.96, "Installing GRUB")

                            if os.path.exists("/sys/firmware/efi"):
                                run_command(["mount", "-t", "efivarfs", "efivarfs", f"{root}/sys/firmware/efi/efivars"])
                                undo.append(["umount", f"{root}/sys/firmware/efi/efivars"])

                                # Clean up dumps from NVRAM to prevent
                                # "failed to register the EFI boot entry: No space left on device"
                                for item in os.listdir("/sys/firmware/efi/efivars"):
                                    if item.startswith("dump-"):
                                        with contextlib.suppress(Exception):
                                            os.unlink(os.path.join("/sys/firmware/efi/efivars", item))

                            os.makedirs(f"{root}/boot/efi", exist_ok=True)
                            for i, disk in enumerate(disks):
                                install_grub_i386 = True
                                efi_partition_number = 2
                                format_efi_partition = True
                                copy_bsd_loader = False
                                if is_freebsd_loader_upgrade:
                                    first_partition_guid = get_partition_guid(disk, 1)
                                    if first_partition_guid == EFI_SYSTEM_PARTITION_GUID:
                                        install_grub_i386 = False
                                        efi_partition_number = 1
                                        format_efi_partition = False
                                        copy_bsd_loader = True
                                    if first_partition_guid == FREEBSD_BOOT_PARTITION_GUID:
                                        run_command([
                                            "sgdisk", "-t1:EF02", f"/dev/{disk}",
                                        ])

                                if install_grub_i386:
                                    run_command([
                                        "chroot", root, "grub-install", "--target=i386-pc", f"/dev/{disk}"
                                    ])

                                if get_partition_guid(disk, efi_partition_number) != EFI_SYSTEM_PARTITION_GUID:
                                    continue

                                partition = get_partition(disk, efi_partition_number)
                                if format_efi_partition:
                                    run_command(["chroot", root, "mkdosfs", "-F", "32", "-s", "1", "-n", "EFI",
                                                 partition])
                                run_command(["chroot", root, "mount", "-t", "vfat", partition, "/boot/efi"])

                                if copy_bsd_loader:
                                    if not os.path.exists(root + SCALE_BSD_LOADER_PATH):
                                        shutil.copyfile(root + CORE_BSD_LOADER_PATH, root + SCALE_BSD_LOADER_PATH)

                                try:
                                    grub_cmd = ["chroot", root, "grub-install", "--target=x86_64-efi",
                                                "--efi-directory=/boot/efi",
                                                "--bootloader-id=debian",
                                                "--recheck",
                                                "--no-floppy",
                                                "--no-nvram"]
                                    run_command(grub_cmd)

                                    run_command(["chroot", root, "mkdir", "-p", "/boot/efi/EFI/boot"])
                                    run_command(["chroot", root, "cp", "/boot/efi/EFI/debian/grubx64.efi",
                                                 "/boot/efi/EFI/boot/bootx64.efi"])

                                    if os.path.exists("/sys/firmware/efi"):
                                        run_command(["chroot", root, "efibootmgr", "-c",
                                                     "-d", f"/dev/{disk}",
                                                     "-p", f"{efi_partition_number}",
                                                     "-L", f"TrueNAS-{i}",
                                                     "-l", "/EFI/debian/grubx64.efi"])
                                finally:
                                    run_command(["chroot", root, "umount", "/boot/efi"])
                    finally:
                        for cmd in reversed(undo):
                            run_command(cmd)
            finally:
                run_command(["umount", root])

        for entry in TRUENAS_DATASETS:
            this_ds = f"{dataset_name}/{entry['name']}"
            mp = entry.get('mountpoint') or f"/{entry['name']}"
            ro = "on" if "RO" in entry["options"] else "off"
            run_command(["zfs", "set", f"readonly={ro}", this_ds])

            if entry.get("snap", False):
                run_command(["zfs", "snapshot", f"{this_ds}@pristine"])

            run_command(["zfs", "set", f"mountpoint={mp}", this_ds])
            run_command(["zfs", "set", 'org.zectl:bootloader=""', this_ds])

        run_command(["zfs", "set", "readonly=on", dataset_name])
        run_command(["zfs", "snapshot", f"{dataset_name}@pristine"])

    except Exception:
        if old_bootfs_prop != "-":
            run_command(["zpool", "set", f"bootfs={old_bootfs_prop}", pool_name])
        if cleanup:
            run_command(["zfs", "destroy", "-r", dataset_name])
        raise

    configure_system_for_zectl(pool_name)


if __name__ == "__main__":
    main()
