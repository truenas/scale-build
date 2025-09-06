import glob
import itertools
import logging
import os
import textwrap
import shutil
import stat
import tempfile

from scale_build.config import SIGNING_KEY, SIGNING_PASSWORD
from scale_build.extensions import build_extensions as do_build_extensions
from scale_build.utils.manifest import get_manifest, get_apt_repos
from scale_build.utils.run import run
from scale_build.utils.paths import CHROOT_BASEDIR, RELEASE_DIR, UPDATE_DIR

from .bootstrap import umount_chroot_basedir
from .manifest import build_manifest, build_release_manifest, get_version, update_file_path, update_file_checksum_path
from .mtree import generate_mtree
from .utils import run_in_chroot


logger = logging.getLogger(__name__)


def build_rootfs_image():
    for f in glob.glob(os.path.join('./tmp/release', '*.update*')):
        os.unlink(f)

    if os.path.exists(UPDATE_DIR):
        shutil.rmtree(UPDATE_DIR)
    os.makedirs(RELEASE_DIR, exist_ok=True)
    os.makedirs(UPDATE_DIR)

    version = get_version()

    # Generate audit rules
    gencmd = os.path.join(CHROOT_BASEDIR, 'conf', 'audit_rules', 'privileged-rules.py')
    priv_rule_file = os.path.join(CHROOT_BASEDIR, 'conf', 'audit_rules', '31-privileged.rules')
    run([gencmd, '--target_dir', CHROOT_BASEDIR, '--privilege_file', priv_rule_file, '--prefix', CHROOT_BASEDIR])
    # Remove the audit file generation script
    os.unlink(gencmd)

    # Copy over audit plugins configuration
    conf_plugins_dir = os.path.join(CHROOT_BASEDIR, 'conf', 'audit_plugins')
    audit_plugins = os.path.join(CHROOT_BASEDIR, 'etc', 'audit', 'plugins.d')
    for plugin in os.listdir(conf_plugins_dir):
        src = os.path.join(conf_plugins_dir, plugin)
        dst = os.path.join(audit_plugins, plugin)
        shutil.copyfile(src, dst)

    # Generate mtree of relevant root filesystem directories
    mtree_file = generate_mtree(CHROOT_BASEDIR, version)
    shutil.copyfile(mtree_file, os.path.join(CHROOT_BASEDIR, 'conf', 'rootfs.mtree'))

    # We are going to build a nested squashfs image.

    # Why nested? So that during update we can easily RO mount the outer image
    # to read a MANIFEST and verify signatures of the real rootfs inner image
    #
    # This allows us to verify without ever extracting anything to disk

    # Create the inner image
    run(['mksquashfs', CHROOT_BASEDIR, os.path.join(UPDATE_DIR, 'rootfs.squashfs'), '-comp', 'xz'])

    # Build any MANIFEST information
    build_manifest()

    # Sign the image (if enabled)
    if SIGNING_KEY and SIGNING_PASSWORD:
        sign_manifest(SIGNING_KEY, SIGNING_PASSWORD)

    # Create the outer image now
    update_file = update_file_path(version)
    run(['mksquashfs', UPDATE_DIR, update_file, '-noD'])
    update_file_checksum = run(['sha256sum', update_file_path(version)], log=False).stdout.strip().split()[0]
    with open(update_file_checksum_path(version), 'w') as f:
        f.write(update_file_checksum)

    build_release_manifest(update_file, update_file_checksum)


def sign_manifest(signing_key, signing_pass):
    run(
        f'echo "{signing_pass}" | gpg -ab --batch --yes --no-use-agent --pinentry-mode loopback --passphrase-fd 0 '
        f'--default-key {signing_key} --output {os.path.join(UPDATE_DIR, "MANIFEST.sig")} '
        f'--sign {os.path.join(UPDATE_DIR, "MANIFEST")}', shell=True,
        exception_msg='Failed gpg signing with SIGNING_PASSWORD', log=False,
    )


def install_rootfs_packages():
    try:
        install_rootfs_packages_impl()
    finally:
        umount_chroot_basedir()


def install_rootfs_packages_impl():
    os.makedirs(os.path.join(CHROOT_BASEDIR, 'etc/dpkg/dpkg.cfg.d'), exist_ok=True)
    with open(os.path.join(CHROOT_BASEDIR, 'etc/dpkg/dpkg.cfg.d/force-unsafe-io'), 'w') as f:
        f.write('force-unsafe-io')

    run_in_chroot(['apt', 'update'])

    manifest = get_manifest()
    packages_to_install = {False: set(), True: set()}
    for package_entry in itertools.chain(manifest['base-packages'], manifest['additional-packages']):
        packages_to_install[package_entry['install_recommends']].add(package_entry['name'])

    for install_recommends, packages_names in packages_to_install.items():
        log_message = f'Installing {packages_names}'
        install_cmd = ['apt', 'install', '-V', '-y']
        if not install_recommends:
            install_cmd.append('--no-install-recommends')
            log_message += ' (no recommends)'
        install_cmd += list(packages_names)

        logger.debug(log_message)
        run_in_chroot(install_cmd)

    # Do any custom rootfs setup
    custom_rootfs_setup()

    # Do any pruning of rootfs
    clean_rootfs()

    build_extensions()

    with open(os.path.join(CHROOT_BASEDIR, 'etc/apt/sources.list'), 'w') as f:
        f.write('\n'.join(get_apt_sources()))

    post_rootfs_setup()


def get_apt_sources():
    # We want the final sources.list to be in the rootfs image
    apt_repos = get_apt_repos(check_custom=False)
    apt_sources = [f'deb {apt_repos["url"]} {apt_repos["distribution"]} {apt_repos["components"]}']
    for repo in apt_repos['additional']:
        apt_sources.append(f'deb {repo["url"]} {repo["distribution"]} {repo["component"]}')
    return apt_sources


def should_rem_execute_bit(binary):
    if binary.is_file() and any((binary.name in ('dpkg', 'apt'), binary.name.startswith('apt-'))):
        # disable apt related binaries so that users can avoid footshooting themselves
        # also disable dpkg since you can do the same type of footshooting
        return True

    return False


def post_rootfs_setup():
    no_executable_flag = ~stat.S_IXUSR & ~stat.S_IXGRP & ~stat.S_IXOTH
    with os.scandir(os.path.join(CHROOT_BASEDIR, 'usr/bin')) as binaries:
        for binary in filter(lambda x: should_rem_execute_bit(x), binaries):
            os.chmod(binary.path, stat.S_IMODE(binary.stat(follow_symlinks=False).st_mode) & no_executable_flag)
    # Make pkg_mgmt_disabled executable
    executable_flag = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    pkg_mgmt_disabled_path = os.path.join(CHROOT_BASEDIR, 'usr/local/bin/pkg_mgmt_disabled')
    if os.path.isfile(pkg_mgmt_disabled_path):
        old_mode = os.stat(pkg_mgmt_disabled_path).st_mode
        os.chmod(pkg_mgmt_disabled_path, old_mode | executable_flag)


def custom_rootfs_setup():
    # Any kind of custom mangling of the built rootfs image can exist here

    os.makedirs(os.path.join(CHROOT_BASEDIR, 'boot/grub'), exist_ok=True)

    # If we are upgrading a FreeBSD installation on USB, there won't be no opportunity to run truenas-initrd.py
    # So we have to assume worse.
    # If rootfs image is used in a Linux installation, initrd will be re-generated with proper configuration,
    # so initrd we make now will only be used on the first boot after FreeBSD upgrade.
    with open(os.path.join(CHROOT_BASEDIR, 'etc/default/zfs'), 'a') as f:
        f.write('ZFS_INITRD_POST_MODPROBE_SLEEP=15')

    for initrd in os.listdir(f"{CHROOT_BASEDIR}/boot"):
        if initrd.startswith("initrd.img-") and "debug" in initrd:
            os.unlink(f"{CHROOT_BASEDIR}/boot/{initrd}")

    for kernel in os.listdir(f"{CHROOT_BASEDIR}/boot"):
        if not kernel.startswith("vmlinuz-"):
            continue

        kernel_name = kernel.removeprefix("vmlinuz-")
        if "debug" in kernel_name:
            continue

        run_in_chroot(['update-initramfs', '-k', kernel_name, '-u'])

    run_in_chroot(['depmod'], check=False)

    # /usr will be readonly, and so we want the ca-certificates directory to
    # symlink to writeable location in /var/local
    local_cacerts = os.path.join(CHROOT_BASEDIR, "usr/local/share/ca-certificates")
    os.makedirs(os.path.join(CHROOT_BASEDIR, "usr/local/share"), exist_ok=True)
    shutil.rmtree(local_cacerts, ignore_errors=True)
    os.symlink("/var/local/ca-certificates", local_cacerts)


def clean_rootfs():
    to_remove = get_manifest()['base-prune']
    run_in_chroot(['apt', 'remove', '-y'] + to_remove)

    # Remove any temp build depends
    run_in_chroot(['apt', 'autoremove', '-y'])

    # OpenSSH generates its server keys on installation, we don't want all SCALE builds
    # of the same version to have the same keys. middleware will generate these keys on
    # specific installation first boot.
    ssh_keys = os.path.join(CHROOT_BASEDIR, 'etc/ssh')
    for f in os.listdir(ssh_keys):
        if f.startswith('ssh_host_') and (f.endswith('_key') or f.endswith('_key.pub') or f.endswith('key-cert.pub')):
            os.unlink(os.path.join(ssh_keys, f))

    for path in (
        os.path.join(CHROOT_BASEDIR, 'usr/share/doc'),
        os.path.join(CHROOT_BASEDIR, 'var/cache/apt'),
        os.path.join(CHROOT_BASEDIR, 'var/lib/apt/lists'),
        os.path.join(CHROOT_BASEDIR, 'var/trash'),
    ):
        shutil.rmtree(path)
        os.makedirs(path, exist_ok=True)


def build_extensions():
    # Build a systemd-sysext extension that, upon loading, will make `/usr/bin/dpkg` working.
    # It is necessary for `update-initramfs` to function properly.
    sysext_extensions_dir = os.path.join(CHROOT_BASEDIR, "usr/share/truenas/sysext-extensions")
    os.makedirs(sysext_extensions_dir, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        os.makedirs(f"{td}/usr/bin")
        shutil.copy2(f"{CHROOT_BASEDIR}/usr/bin/dpkg", f"{td}/usr/bin/dpkg")

        os.makedirs(f"{td}/usr/local/bin")
        with open(f"{td}/usr/local/bin/dpkg", "w") as f:
            f.write("#!/bin/bash\n")
            f.write("exec /usr/bin/dpkg \"$@\"")
        os.chmod(f"{td}/usr/local/bin/dpkg", 0o755)

        os.makedirs(f"{td}/usr/lib/extension-release.d")
        with open(f"{td}/usr/lib/extension-release.d/extension-release.functioning-dpkg", "w") as f:
            f.write("ID=_any\n")

        run(["mksquashfs", td, f"{sysext_extensions_dir}/functioning-dpkg.raw"])

    with tempfile.TemporaryDirectory() as td:
        rootfs_image = f"{td}/rootfs.squashfs"
        run(["mksquashfs", CHROOT_BASEDIR, rootfs_image, "-one-file-system"])
        do_build_extensions(rootfs_image, sysext_extensions_dir)

    external_extesions_dir = os.path.join(RELEASE_DIR, "extensions")
    os.makedirs(external_extesions_dir, exist_ok=True)
    for external_extension in ["dev-tools.raw"]:
        shutil.move(os.path.join(sysext_extensions_dir, external_extension),
                    os.path.join(external_extesions_dir, external_extension))
