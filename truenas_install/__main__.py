# -*- coding=utf-8 -*-
import contextlib
import glob
import json
import logging
import os
import re
import subprocess
import sys
import tempfile

logger = logging.getLogger(__name__)

RE_UNSQUASHFS_PROGRESS = re.compile(r"\[.+\]\s+(?P<extracted>[0-9]+)/(?P<total>[0-9]+)\s+(?P<progress>[0-9]+)%")
run_kw = dict(check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", errors="ignore")

is_json_output = False


def write_progress(progress, message):
    if is_json_output:
        sys.stdout.write(json.dumps({"progress": progress, "message": message}) + "\n")
    else:
        sys.stdout.write(f"[{int(progress * 100)}%] {message}\n")
    sys.stdout.flush()


def write_error(error):
    if is_json_output:
        sys.stdout.write(json.dumps({"error": error}) + "\n")
    else:
        sys.stdout.write(f"Error: {error}\n")
    sys.stdout.flush()


@contextlib.contextmanager
def mount_update(path):
    with tempfile.TemporaryDirectory() as mounted:
        run_command(["mount", "-t", "squashfs", "-o", "loop", path, mounted])
        try:
            yield mounted
        finally:
            run_command(["umount", mounted])


def run_command(cmd, **kwargs):
    try:
        return subprocess.run(cmd, **run_kw, **kwargs)
    except subprocess.CalledProcessError as e:
        write_error(f"Command {cmd} failed with exit code {e.returncode}: {e.stderr}")
        raise


if __name__ == "__main__":
    input = json.loads(sys.stdin.read())

    disks = input["disks"]
    if input.get("json"):
        is_json_output = True
    old_root = input.get("old_root", None)
    password = input.get("password", None)
    pool_name = input["pool_name"]
    sql = input.get("sql", None)
    src = input["src"]

    with open(os.path.join(src, "manifest.json")) as f:
        manifest = json.load(f)

    dataset_name = f"{pool_name}/ROOT/{manifest['version']}"

    write_progress(0, "Creating dataset")
    run_command([
        "zfs", "create",
        "-o", "mountpoint=legacy",
        "-o", f"truenas:kernel_version={manifest['kernel_version']}",
        dataset_name,
    ])
    try:
        with tempfile.TemporaryDirectory() as root:
            run_command(["mount", "-t", "zfs", dataset_name, root])
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
                                int(m.group("extracted")) / int(m.group("total")) * 0.9,
                                "Extracting",
                            )

                            buffer = b""

                p.wait()
                if p.returncode != 0:
                    write_error({"error": f"unsquashfs failed with exit code {p.returncode}: {stdout}"})
                    raise subprocess.CalledProcessError(p.returncode, cmd, stdout)

                write_progress(0.9, "Performing post-install tasks")

                if old_root is not None:
                    run_command([
                        "rsync", "-aRx",
                        "--exclude", "data/factory-v1.db",
                        "--exclude", "data/manifest.json",
                        "etc/hostid",
                        "data",
                        "root",
                        f"{root}/",
                    ], cwd=old_root)

                    with open(f"{root}/data/need-update", "w"):
                        pass
                else:
                    run_command(["cp", "/etc/hostid", f"{root}/etc/"])

                    with open(f"{root}/data/first-boot", "w"):
                        pass
                    with open(f"{root}/data/truenas-eula-pending", "w"):
                        pass

                if password is not None:
                    run_command(["chroot", root, "/etc/netcli", "reset_root_pw", password])

                if sql is not None:
                    run_command(["chroot", root, "sqlite3", "/data/freenas-v1.db"], input=sql)

                undo = []
                try:
                    run_command(["mount", "-t", "proc", "none", f"{root}/proc"])
                    undo.append(["umount", f"{root}/proc"])

                    run_command(["mount", "-t", "sysfs", "none", f"{root}/sys"])
                    undo.append(["umount", f"{root}/sys"])

                    run_command(["mount", "-t", "zfs", f"{pool_name}/grub", f"{root}/boot/grub"])
                    undo.append(["umount", f"{root}/boot/grub"])

                    for device in sum([glob.glob(f"/dev/{disk}*") for disk in disks], []) + ["/dev/zfs"]:
                        run_command(["touch", f"{root}{device}"])
                        run_command(["mount", "-o", "bind", device, f"{root}{device}"])
                        undo.append(["umount", f"{root}{device}"])

                    # Set bootfs before running update-grub
                    run_command(["zpool", "set", f"bootfs={dataset_name}", pool_name])

                    run_command(["chroot", root, "/usr/local/bin/truenas-grub.py"])

                    run_command(["chroot", root, "update-initramfs", "-k", "all", "-u"])
                    run_command(["chroot", root, "update-grub"])

                    os.makedirs(f"{root}/boot/efi", exist_ok=True)
                    for disk in disks:
                        run_command(["chroot", root, "grub-install", "--target=i386-pc", f"/dev/{disk}"])

                        run_command(["chroot", root, "mkdosfs", "-F", "32", "-s", "1", "-n", "EFI", f"/dev/{disk}2"])
                        run_command(["chroot", root, "mount", "-t", "vfat", f"/dev/{disk}2", "/boot/efi"])
                        try:
                            run_command(["chroot", root, "grub-install", "--target=x86_64-efi",
                                         "--efi-directory=/boot/efi",
                                         "--bootloader-id=debian",
                                         "--recheck",
                                         "no-floppy"])
                            run_command(["chroot", root, "mkdir", "-p", "/boot/efi/EFI/boot"])
                            run_command(["chroot", root, "cp", "/boot/efi/EFI/debian/grubx64.efi",
                                         "/boot/efi/EFI/boot/bootx64.efi"])
                        finally:
                            run_command(["chroot", root, "umount", "/boot/efi"])
                finally:
                    for cmd in reversed(undo):
                        run_command(cmd)
            finally:
                run_command(["umount", root])
    except Exception:
        run_command(["zfs", "destroy", dataset_name])
        raise
