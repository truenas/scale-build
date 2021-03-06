import distutils.dir_util
import glob
import itertools
import os
import shutil

from scale_build.utils.manifest import get_manifest
from scale_build.utils.run import run
from scale_build.utils.paths import CD_DIR, CD_FILES_DIR, CHROOT_BASEDIR, CONF_GRUB, RELEASE_DIR, TMP_DIR

from .bootstrap import umount_chroot_basedir
from .manifest import UPDATE_FILE
from .utils import run_in_chroot, get_image_version


def install_iso_packages():
    try:
        install_iso_packages_impl()
    finally:
        umount_chroot_basedir()


def install_iso_packages_impl():
    run_in_chroot(['apt', 'update'])

    # echo "/dev/disk/by-label/TRUENAS / iso9660 loop 0 0" > ${CHROOT_BASEDIR}/etc/fstab
    for package in get_manifest()['iso-packages']:
        run_in_chroot(['apt', 'install', '-y', package])

    os.makedirs(os.path.join(CHROOT_BASEDIR, 'boot/grub'), exist_ok=True)
    shutil.copy(CONF_GRUB, os.path.join(CHROOT_BASEDIR, 'boot/grub/grub.cfg'))


def make_iso_file():
    for f in glob.glob(os.path.join(RELEASE_DIR, '*.iso*')):
        os.unlink(f)

    # Set default PW to root
    run(fr'chroot {CHROOT_BASEDIR} /bin/bash -c "echo -e \"root\nroot\" | passwd root"', shell=True)

    # Create /etc/version
    with open(os.path.join(CHROOT_BASEDIR, 'etc/version'), 'w') as f:
        f.write(get_image_version())

    # Set /etc/hostname so that hostname of builder is not advertised
    with open(os.path.join(CHROOT_BASEDIR, 'etc/hostname'), 'w') as f:
        f.write('truenas.local')

    # Copy the CD files
    distutils.dir_util._path_created = {}
    distutils.dir_util.copy_tree(CD_FILES_DIR, CHROOT_BASEDIR, preserve_symlinks=True)

    # Create the CD assembly dir
    if os.path.exists(CD_DIR):
        shutil.rmtree(CD_DIR)
    os.makedirs(CD_DIR, exist_ok=True)

    # Prune away the fat
    prune_cd_basedir()

    # Lets make squashfs now
    tmp_truenas_path = os.path.join(TMP_DIR, 'truenas.squashfs')
    run(['mksquashfs', CHROOT_BASEDIR, tmp_truenas_path, '-comp', 'xz'])
    os.makedirs(os.path.join(CD_DIR, 'live'), exist_ok=True)
    shutil.move(tmp_truenas_path, os.path.join(CD_DIR, 'live/filesystem.squashfs'))

    # Copy over boot and kernel before rolling CD
    shutil.copytree(os.path.join(CHROOT_BASEDIR, 'boot'), os.path.join(CD_DIR, 'boot'))
    # Dereference /initrd.img and /vmlinuz so this ISO can be re-written to a FAT32 USB stick using Windows tools
    shutil.copy(os.path.join(CHROOT_BASEDIR, 'initrd.img'), CD_DIR)
    shutil.copy(os.path.join(CHROOT_BASEDIR, 'vmlinuz'), CD_DIR)
    for f in itertools.chain(
        glob.glob(os.path.join(CD_DIR, 'boot/initrd.img-*')),
        glob.glob(os.path.join(CD_DIR, 'boot/vmlinuz-*')),
    ):
        os.unlink(f)

    shutil.copy(UPDATE_FILE, os.path.join(CD_DIR, 'TrueNAS-SCALE.update'))
    os.makedirs(os.path.join(CHROOT_BASEDIR, RELEASE_DIR), exist_ok=True)
    os.makedirs(os.path.join(CHROOT_BASEDIR, CD_DIR), exist_ok=True)

    try:
        run(['mount', '--bind', RELEASE_DIR, os.path.join(CHROOT_BASEDIR, RELEASE_DIR)])
        run(['mount', '--bind', CD_DIR, os.path.join(CHROOT_BASEDIR, CD_DIR)])
        run_in_chroot(['apt-get', 'update'], check=False)
        run_in_chroot([
            'apt-get', 'install', '-y', 'grub-common', 'grub2-common', 'grub-efi-amd64-bin',
            'grub-efi-amd64-signed', 'grub-pc-bin', 'mtools', 'xorriso'
        ])
        run_in_chroot([
            'grub-mkrescue', '-o', os.path.join(RELEASE_DIR, f'TrueNAS-SCALE-{get_image_version()}.iso'), CD_DIR
        ])
    finally:
        run(['umount', '-f', os.path.join(CHROOT_BASEDIR, CD_DIR)])
        run(['umount', '-f', os.path.join(CHROOT_BASEDIR, RELEASE_DIR)])

    with open(os.path.join(RELEASE_DIR, f'TrueNAS-SCALE-{get_image_version()}.iso.sha256'), 'w') as f:
        f.write(run(
            ['sha256sum', os.path.join(RELEASE_DIR, f'TrueNAS-SCALE-{get_image_version()}.iso')], log=False
        ).stdout.strip().split()[0])


def prune_cd_basedir():
    for path in filter(os.path.exists, itertools.chain([
        os.path.join(CHROOT_BASEDIR, 'var/cache/apt'),
        os.path.join(CHROOT_BASEDIR, 'var/lib/apt'),
        os.path.join(CHROOT_BASEDIR, 'usr/share/doc'),
        os.path.join(CHROOT_BASEDIR, 'usr/share/man'),
    ] + glob.glob(os.path.join(CHROOT_BASEDIR, 'lib/modules/*-amd64/kernel/sound')))):
        shutil.rmtree(path)
