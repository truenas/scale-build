import glob
import itertools
import os
import shutil
import tarfile
import tempfile

import requests

from scale_build.utils.manifest import get_manifest
from scale_build.utils.run import run
from scale_build.utils.paths import CD_DIR, CD_FILES_DIR, CHROOT_BASEDIR, CONF_GRUB, PKG_DIR, RELEASE_DIR, TMP_DIR

from .bootstrap import umount_chroot_basedir
from .manifest import get_image_version, update_file_path
from .utils import run_in_chroot


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
    run(f'rsync -aKv {CD_FILES_DIR}/ {CHROOT_BASEDIR}/', shell=True)

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

    shutil.copy(update_file_path(), os.path.join(CD_DIR, 'TrueNAS-SCALE.update'))
    os.makedirs(os.path.join(CHROOT_BASEDIR, RELEASE_DIR), exist_ok=True)
    os.makedirs(os.path.join(CHROOT_BASEDIR, CD_DIR), exist_ok=True)

    # Debian GRUB EFI image probes for `.disk/info` file to identify a device/partition
    # to load config file from.
    os.makedirs(os.path.join(CD_DIR, '.disk'), exist_ok=True)
    with open(os.path.join(CD_DIR, '.disk/info'), 'w') as f:
        pass

    try:
        run(['mount', '--bind', RELEASE_DIR, os.path.join(CHROOT_BASEDIR, RELEASE_DIR)])
        run(['mount', '--bind', CD_DIR, os.path.join(CHROOT_BASEDIR, CD_DIR)])
        run(['mount', '--bind', PKG_DIR, os.path.join(CHROOT_BASEDIR, 'packages')])
        run_in_chroot(['apt-get', 'update'], check=False)
        run_in_chroot([
            'apt-get', 'install', '-y', 'grub-common', 'grub2-common', 'grub-efi-amd64-bin',
            'grub-efi-amd64-signed', 'grub-pc-bin', 'mtools', 'xorriso'
        ])

        # Debian GRUB EFI searches for GRUB config in a different place
        os.makedirs(os.path.join(CD_DIR, 'EFI/debian'), exist_ok=True)
        shutil.copy(CONF_GRUB, os.path.join(CD_DIR, 'EFI/debian/grub.cfg'))
        os.makedirs(os.path.join(CD_DIR, 'EFI/debian/fonts'), exist_ok=True)
        shutil.copy(os.path.join(CHROOT_BASEDIR, 'usr/share/grub/unicode.pf2'),
                    os.path.join(CD_DIR, 'EFI/debian/fonts/unicode.pf2'))

        iso = os.path.join(RELEASE_DIR, f'TrueNAS-SCALE-{get_image_version()}.iso')
        run_in_chroot(['grub-mkrescue', '-o', iso, CD_DIR])

        # Installed grub EFI image does not support `search` command which we need to make TrueNAS ISO working in
        # Rufus "ISO Image mode".
        # Let's just replace it with pre-built Debian GRUB EFI image that the official Debian ISO installer uses.
        with tempfile.NamedTemporaryFile() as efi_img:
            with tempfile.NamedTemporaryFile(suffix='.tar.gz') as f:
                apt_repos = get_manifest()['apt-repos']
                r = requests.get(
                    f'{apt_repos["url"]}/dists/{apt_repos["distribution"]}/main/installer-amd64/current/images/cdrom/'
                    'debian-cd_info.tar.gz',
                    timeout=10,
                    stream=True,
                )
                r.raise_for_status()
                shutil.copyfileobj(r.raw, f)
                f.flush()

                with tarfile.open(f.name) as tf:
                    shutil.copyfileobj(tf.extractfile('./grub/efi.img'), efi_img)

            efi_img.flush()
            with tempfile.TemporaryDirectory() as td:
                run(['mount', '-t', 'vfat', efi_img.name, td])
                try:
                    lo = run(['losetup', '-f'], log=False).stdout.strip()
                    run(['losetup', '-P', lo, iso])
                    try:
                        with tempfile.TemporaryDirectory() as td2:
                            run(['mount', f'{lo}p2', td2])
                            try:
                                shutil.rmtree(os.path.join(td2, 'EFI'))
                                shutil.copytree(os.path.join(td, 'EFI'), os.path.join(td2, 'EFI'))

                                grub_cfg_path = os.path.join(td2, 'EFI/debian/grub.cfg')
                                with open(grub_cfg_path) as f:
                                    grub_cfg = f.read()

                                substr = 'source $prefix/x86_64-efi/grub.cfg'
                                if substr not in grub_cfg:
                                    raise ValueError(f'Invalid grub.cfg:\n{grub_cfg}')

                                grub_cfg = grub_cfg.replace(substr, 'source $prefix/grub.cfg')

                                with open(grub_cfg_path, 'w') as f:
                                    f.write(grub_cfg)
                            finally:
                                run(['umount', td2])
                    finally:
                        run(['losetup', '-d', lo])
                finally:
                    run(['umount', td])
    finally:
        run(['umount', '-f', os.path.join(CHROOT_BASEDIR, CD_DIR)])
        run(['umount', '-f', os.path.join(CHROOT_BASEDIR, RELEASE_DIR)])
        run(['umount', '-f', os.path.join(CHROOT_BASEDIR, 'packages')])

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
        os.path.join(CHROOT_BASEDIR, 'etc/resolv.conf'),
    ] + glob.glob(os.path.join(CHROOT_BASEDIR, 'lib/modules/*-amd64/kernel/sound')))):
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.unlink(path)
