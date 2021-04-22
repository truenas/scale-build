import contextlib
import glob
import itertools
import logging
import os
import textwrap
import shutil

from scale_build.config import SIGNING_KEY, SIGNING_PASSWORD
from scale_build.exceptions import CallError
from scale_build.utils.logger import get_logger
from scale_build.utils.manifest import get_manifest
from scale_build.utils.run import run
from scale_build.utils.paths import CHROOT_BASEDIR, CONF_SOURCES, RELEASE_DIR, UPDATE_DIR

from .manifest import build_manifest, build_update_manifest, UPDATE_FILE, UPDATE_FILE_HASH
from .utils import run_in_chroot


logger = logging.getLogger(__name__)


def build_rootfs_image():
    for f in glob.glob(os.path.join('./tmp/release', '*.update*')):
        os.unlink(f)

    shutil.rmtree(UPDATE_DIR, ignore_errors=True)
    os.makedirs(RELEASE_DIR, exist_ok=True)
    os.makedirs(UPDATE_DIR, exist_ok=True)

    # We are going to build a nested squashfs image.

    # Why nested? So that during update we can easily RO mount the outer image
    # to read a MANIFEST and verify signatures of the real rootfs inner image
    #
    # This allows us to verify without ever extracting anything to disk

    build_logger = get_logger('rootfs-image', 'rootfs-image.log', 'w')
    # Create the inner image
    run(
        ['mksquashfs', CHROOT_BASEDIR, os.path.join(UPDATE_DIR, 'rootfs.squashfs'), '-comp', 'xz'],
        logger=build_logger
    )
    # Build any MANIFEST information
    build_manifest()

    # Sign the image (if enabled)
    if SIGNING_KEY and SIGNING_PASSWORD:
        sign_manifest(SIGNING_KEY, SIGNING_PASSWORD)

    # Create the outer image now
    run(['mksquashfs', UPDATE_DIR, UPDATE_FILE, '-noD'], logger=build_logger)
    update_hash = run(['sha256sum', UPDATE_FILE]).stdout.decode(errors='ignore').strip()
    with open(UPDATE_FILE_HASH, 'w') as f:
        f.write(update_hash)

    build_update_manifest(update_hash)


def sign_manifest(signing_key, signing_pass):
    run(
        f'echo "{signing_pass}" | gpg -ab --batch --yes --no-use-agent --pinentry-mode loopback --passphrase-fd 0 '
        f'--default-key {signing_key} --output {os.path.join(UPDATE_DIR, "MANIFEST.sig")} '
        f'--sign {os.path.join(UPDATE_DIR, "MANIFEST")}', exception_msg='Failed gpg signing with SIGNING_PASSWORD',
        exception=CallError
    )


def install_rootfs_packages():
    rootfs_logger = get_logger('rootfs-packages', 'rootfs-packages', 'w')
    os.makedirs(os.path.join(CHROOT_BASEDIR, 'etc/dpkg/dpkg.cfg.d'), exist_ok=True)
    with open(os.path.join(CHROOT_BASEDIR, 'etc/dpkg/dpkg.cfg.d/force-unsafe-io'), 'w') as f:
        f.write('force-unsafe-io')

    run_in_chroot('apt update', rootfs_logger)

    manifest = get_manifest()
    for package in itertools.chain(
        manifest['base-packages'], map(lambda d: d['package'], manifest['additional-packages'])
    ):
        run_in_chroot(f'apt install -V -y {package}', rootfs_logger, f'Failed apt install {package}')

    # Do any custom rootfs setup
    custom_rootfs_setup(rootfs_logger)

    # Do any pruning of rootfs
    clean_rootfs(rootfs_logger)

    # Copy the default sources.list file
    shutil.copy(CONF_SOURCES, os.path.join(CHROOT_BASEDIR, 'etc/apt/sources.list'))

    run_in_chroot('depmod', rootfs_logger, check=False)


def custom_rootfs_setup(rootfs_logger):
    # Any kind of custom mangling of the built rootfs image can exist here

    # If we are upgrading a FreeBSD installation on USB, there won't be no opportunity to run truenas-initrd.py
    # So we have to assume worse.
    # If rootfs image is used in a Linux installation, initrd will be re-generated with proper configuration,
    # so initrd we make now will only be used on the first boot after FreeBSD upgrade.
    with open(os.path.join(CHROOT_BASEDIR, 'etc/default/zfs'), 'a') as f:
        f.write('ZFS_INITRD_POST_MODPROBE_SLEEP=15')

    run_in_chroot('update-initramfs -k all -u', logger=rootfs_logger)

    # Generate native systemd unit files for SysV services that lack ones to prevent systemd-sysv-generator warnings
    tmp_systemd = os.path.join(CHROOT_BASEDIR, 'tmp/systemd')
    os.makedirs(tmp_systemd)
    run_in_chroot(
        '/usr/lib/systemd/system-generators/systemd-sysv-generator /tmp/systemd /tmp/systemd /tmp/systemd',
        rootfs_logger
    )
    for unit_file in filter(lambda f: f.endswith('.service'), os.listdir(tmp_systemd)):
        with open(os.path.join(tmp_systemd, unit_file), 'a') as f:
            f.write(textwrap.dedent('''\
                [Install]
                WantedBy=multi-user.target
            '''))

    for file_path in map(
        lambda f: os.path.join(tmp_systemd, 'multi-user.target.wants', f),
        filter(
            lambda f: os.path.isfile(f) and not os.path.islink(f) and f != 'rrdcached.service',
            os.listdir(os.path.join(tmp_systemd, 'multi-user.target.wants'))
        )
    ):
        os.unlink(file_path)

    run_in_chroot('rsync -av /tmp/systemd/ /usr/lib/systemd/system/')
    shutil.rmtree(tmp_systemd, ignore_errors=True)


def clean_rootfs(rootfs_logger):
    to_remove = get_manifest()['base-prune']
    run_in_chroot(
        f'apt remove -y {" ".join(to_remove)}', rootfs_logger, f'Failed removing {", ".join(to_remove)!r} packages.'
    )

    # Remove any temp build depends
    run_in_chroot('apt autoremove -y', rootfs_logger, 'Failed atp autoremove')

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
        shutil.rmtree(path, ignore_errors=True)
        os.makedirs(path, exist_ok=True)
