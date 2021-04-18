import glob
import itertools
import os
import shutil

from scale_build.utils.manifest import get_manifest
from scale_build.utils.run import run
from scale_build.utils.paths import BUILDER_DIR, CD_DIR, CHROOT_BASEDIR, CONF_GRUB, RELEASE_DIR, TMP_DIR

from .logger import get_logger
from .manifest import UPDATE_FILE
from .utils import run_in_chroot


def install_iso_packages():
    installer_logger = get_logger('cdrom-packages')
    run_in_chroot('apt update', logger=installer_logger)

    # echo "/dev/disk/by-label/TRUENAS / iso9660 loop 0 0" > ${CHROOT_BASEDIR}/etc/fstab
    for package in get_manifest()['iso-packages']:
        run_in_chroot(
            f'apt install -y {package}', logger=installer_logger, exception_message=f'Failed apt install {package}'
        )

    os.makedirs(os.path.join(CHROOT_BASEDIR, 'boot/grub'), exist_ok=True)
    shutil.copy(CONF_GRUB, os.path.join(CHROOT_BASEDIR, 'boot/grub/grub.cfg'))


def make_iso_file():
    iso_logger = get_logger('cdrom-iso')
    for f in glob.glob(os.path.join(RELEASE_DIR, '*.iso*')):
        os.unlink(f)

    # Set default PW to root
    run_in_chroot(r'echo -e \"root\nroot\" | passwd root', logger=iso_logger)

    # Create /etc/version
    with open(os.path.join(CHROOT_BASEDIR, 'etc/version'), 'w') as f:
        f.write(str(os.environ.get('VERSION')))

    # Copy the CD files
    for source, destination in (
        (os.path.join(BUILDER_DIR, 'conf/cd-files/getty@.service'), os.path.join(CHROOT_BASEDIR, 'lib/systemd/system')),
        (
            os.path.join(BUILDER_DIR, 'conf/cd-files/serial-getty@.service'),
            os.path.join(CHROOT_BASEDIR, 'lib/systemd/system')
        ),
        (os.path.join(BUILDER_DIR, 'conf/cd-files/bash_profile'), os.path.join(CHROOT_BASEDIR, 'root/.bash_profile')),
    ):
        shutil.copy(source, destination)

    # Create the CD assembly dir
    shutil.rmtree(CD_DIR, ignore_errors=True)
    os.makedirs(CD_DIR, exist_ok=True)

    # Prune away the fat
    prune_cd_basedir()

    # Lets make squashfs now
    tmp_truenas_path = os.path.join(TMP_DIR, 'truenas.squashfs')
    run(['mksquashfs', CHROOT_BASEDIR, tmp_truenas_path, '-comp', 'xz'], logger=iso_logger)
    os.makedirs(os.path.join(CD_DIR, 'live'), exist_ok=True)
    shutil.move(tmp_truenas_path, os.path.join(CD_DIR, 'live/filesystem.squashfs'))

    # Copy over boot and kernel before rolling CD
    shutil.copytree(os.path.join(CHROOT_BASEDIR, 'boot'), os.path.join(CD_DIR, 'boot'))
    # Dereference /initrd.img and /vmlinuz so this ISO can be re-written to a FAT32 USB stick using Windows tools
    shutil.copy(os.path.join(CHROOT_BASEDIR, 'initrd.img'), CD_DIR)
    shutil.copy(os.path.join(CHROOT_BASEDIR, 'vmlinuz'), CD_DIR)
    for f in itertools.chain(
        glob.glob(os.path.join(CD_DIR, 'boot/initrd.img-')),
        glob.glob(os.path.join(CD_DIR, 'boot/vmlinuz-*')),
    ):
        os.unlink(f)

    shutil.copy(UPDATE_FILE, os.path.join(CD_DIR, 'TrueNAS-SCALE.update'))
    os.makedirs(os.path.join(CHROOT_BASEDIR, RELEASE_DIR), exist_ok=True)
    os.makedirs(os.path.join(CHROOT_BASEDIR, CD_DIR), exist_ok=True)

    run(['mount', '--bind', RELEASE_DIR, os.path.join(CHROOT_BASEDIR, RELEASE_DIR)])
    run(['mount', '--bind', CD_DIR, os.path.join(CHROOT_BASEDIR, CD_DIR)])

    run_in_chroot('apt-get update', logger=iso_logger, check=False)
    run_in_chroot('apt-get install -y grub-efi grub-pc-bin mtools xorriso', logger=iso_logger, check=False)
    version = str(os.getenv('VERSION'))
    run_in_chroot(
        f'grub-mkrescue -o {os.path.join(RELEASE_DIR, f"TrueNAS-SCALE-{version}.iso")} {CD_DIR}', logger=iso_logger
    )
    run(['umount', '-f', os.path.join(CHROOT_BASEDIR, CD_DIR)])
    run(['umount', '-f', os.path.join(CHROOT_BASEDIR, RELEASE_DIR)])

    with open(os.path.join(RELEASE_DIR, f'TrueNAS-SCALE-{version}.iso.sha256'), 'w') as f:
        f.write(run(['sha256sum', os.path.join(RELEASE_DIR, f'TrueNAS-SCALE-{version}.iso')]).stdout.decode().strip())


def prune_cd_basedir():
    for path in itertools.chain([
        os.path.join(CHROOT_BASEDIR, 'var/cache/apt'),
        os.path.join(CHROOT_BASEDIR, 'var/lib/apt'),
        os.path.join(CHROOT_BASEDIR, 'usr/share/doc'),
        os.path.join(CHROOT_BASEDIR, 'usr/share/man'),
    ] + glob.glob(os.path.join(CHROOT_BASEDIR, 'lib/modules/*-amd64/kernel/sound'))):
        shutil.rmtree(path, ignore_errors=True)
