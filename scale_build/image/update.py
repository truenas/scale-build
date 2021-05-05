import contextlib
import glob
import itertools
import os
import textwrap
import shutil

from scale_build.config import SIGNING_KEY, SIGNING_PASSWORD
from scale_build.utils.manifest import get_manifest
from scale_build.utils.run import run
from scale_build.utils.paths import CHROOT_BASEDIR, CONF_SOURCES, RELEASE_DIR, UPDATE_DIR

from .bootstrap import umount_chroot_basedir
from .manifest import build_manifest, build_update_manifest, UPDATE_FILE, UPDATE_FILE_HASH
from .utils import run_in_chroot


def build_rootfs_image():
    for f in glob.glob(os.path.join('./tmp/release', '*.update*')):
        os.unlink(f)

    if os.path.exists(UPDATE_DIR):
        shutil.rmtree(UPDATE_DIR)
    os.makedirs(RELEASE_DIR, exist_ok=True)
    os.makedirs(UPDATE_DIR)

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
    run(['mksquashfs', UPDATE_DIR, UPDATE_FILE, '-noD'])
    update_hash = run(['sha256sum', UPDATE_FILE], log=False).stdout.strip().split()[0]
    with open(UPDATE_FILE_HASH, 'w') as f:
        f.write(update_hash)

    build_update_manifest(update_hash)


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
    for package in itertools.chain(
        manifest['base-packages'], map(lambda d: d['package'], manifest['additional-packages'])
    ):
        run_in_chroot(['apt', 'install', '-V', '-y', package])

    # Do any custom rootfs setup
    custom_rootfs_setup()

    # Do any pruning of rootfs
    clean_rootfs()

    # Copy the default sources.list file
    shutil.copy(CONF_SOURCES, os.path.join(CHROOT_BASEDIR, 'etc/apt/sources.list'))


def custom_rootfs_setup():
    # Any kind of custom mangling of the built rootfs image can exist here

    # If we are upgrading a FreeBSD installation on USB, there won't be no opportunity to run truenas-initrd.py
    # So we have to assume worse.
    # If rootfs image is used in a Linux installation, initrd will be re-generated with proper configuration,
    # so initrd we make now will only be used on the first boot after FreeBSD upgrade.
    with open(os.path.join(CHROOT_BASEDIR, 'etc/default/zfs'), 'a') as f:
        f.write('ZFS_INITRD_POST_MODPROBE_SLEEP=15')

    run_in_chroot(['update-initramfs', '-k', 'all', '-u'])

    # Generate native systemd unit files for SysV services that lack ones to prevent systemd-sysv-generator warnings
    tmp_systemd = os.path.join(CHROOT_BASEDIR, 'tmp/systemd')
    os.makedirs(tmp_systemd)
    run_in_chroot([
        '/usr/lib/systemd/system-generators/systemd-sysv-generator', '/tmp/systemd', '/tmp/systemd', '/tmp/systemd'
    ])
    for unit_file in filter(lambda f: f.endswith('.service'), os.listdir(tmp_systemd)):
        with open(os.path.join(tmp_systemd, unit_file), 'a') as f:
            f.write(textwrap.dedent('''\
                [Install]
                WantedBy=multi-user.target
            '''))

    for f in os.listdir(os.path.join(tmp_systemd, 'multi-user.target.wants')):
        file_path = os.path.join(tmp_systemd, f)
        if os.path.isfile(file_path) and not os.path.islink(file_path) and f != 'rrdcached.service':
            os.unlink(file_path)

    run_in_chroot(['rsync', '-av', '/tmp/systemd/', '/usr/lib/systemd/system/'])
    shutil.rmtree(tmp_systemd)
    run_in_chroot(['depmod'], check=False)


def clean_rootfs():
    to_remove = get_manifest()['base-prune']
    run_in_chroot(['apt', 'remove', '-y'] + to_remove)

    # Remove any temp build depends
    run_in_chroot(['apt', 'autoremove', '-y'])

    # We install the nvidia-kernel-dkms package which causes a modprobe file to be written
    # (i.e /etc/modprobe.d/nvidia.conf). This file tries to modprobe all the associated
    # nvidia drivers at boot whether or not your system has an nvidia card installed.
    # For all truenas certified and truenas enterprise hardware, we do not include nvidia GPUS.
    # So to prevent a bunch of systemd "Failed" messages to be barfed to the console during boot,
    # we remove this file because the linux kernel dynamically loads the modules based on whether
    # or not you have the actual hardware installed in the system.
    with contextlib.suppress(FileNotFoundError):
        os.unlink(os.path.join(CHROOT_BASEDIR, 'etc/modprobe.d/nvidia.conf'))

    for path in (
        os.path.join(CHROOT_BASEDIR, 'usr/share/doc'),
        os.path.join(CHROOT_BASEDIR, 'var/cache/apt'),
        os.path.join(CHROOT_BASEDIR, 'var/lib/apt/lists'),
    ):
        shutil.rmtree(path)
        os.makedirs(path, exist_ok=True)
