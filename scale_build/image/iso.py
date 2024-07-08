import glob
import itertools
import os
import shutil
import tarfile
import tempfile
import time
import json

import requests

from scale_build.exceptions import CallError
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

    # Bring up network for the installer
    run(f'chroot {CHROOT_BASEDIR} systemctl enable systemd-networkd', shell=True)

    # Create /etc/version
    with open(os.path.join(CHROOT_BASEDIR, 'etc/version'), 'w') as f:
        f.write(get_image_version())

    # Set /etc/hostname so that hostname of builder is not advertised
    with open(os.path.join(CHROOT_BASEDIR, 'etc/hostname'), 'w') as f:
        f.write('truenas-installer.local')

    vendor = os.environ.get('TRUENAS_VENDOR')
    if vendor:
        os.makedirs(os.path.join(CHROOT_BASEDIR, 'data'), exist_ok=True)
        with open(os.path.join(CHROOT_BASEDIR, 'data/.vendor'), 'w') as f:
            f.write(json.dumps({'name': vendor}))

    # Copy the CD files
    run(f'rsync -aKv {CD_FILES_DIR}/ {CHROOT_BASEDIR}/', shell=True)

    # Create the CD assembly dir
    if os.path.exists(CD_DIR):
        shutil.rmtree(CD_DIR)
    os.makedirs(CD_DIR, exist_ok=True)

    # Let's make squashfs now while pruning away the fat
    tmp_truenas_path = os.path.join(TMP_DIR, 'truenas.squashfs')
    with tempfile.NamedTemporaryFile(mode='w') as exclude_file:
        exclude_file.write('\n'.join(pruning_cd_basedir_contents()))
        exclude_file.flush()

        run(['mksquashfs', CHROOT_BASEDIR, tmp_truenas_path, '-comp', 'xz', '-ef', exclude_file.name])

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

        # Default grub EFI image does not support `search` command which we need to make TrueNAS ISO working in
        # Rufus "ISO Image mode".
        # Let's use pre-built Debian GRUB EFI image that the official Debian ISO installer uses.
        with tempfile.NamedTemporaryFile(dir=RELEASE_DIR) as efi_img:
            with tempfile.NamedTemporaryFile(suffix='.tar.gz') as f:
                apt_repos = get_manifest()['apt-repos']
                r = requests.get(
                    f'{apt_repos["url"]}dists/{apt_repos["distribution"]}/main/installer-amd64/current/images/cdrom/'
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

            run_in_chroot([
                'grub-mkrescue',
                '-o', iso,
                '--efi-boot-part', os.path.join(RELEASE_DIR,
                                                os.path.relpath(efi_img.name, os.path.abspath(RELEASE_DIR))),
                CD_DIR,
            ])

        lo = run(['losetup', '-f'], log=False).stdout.strip()
        run(['losetup', '-P', lo, iso])
        try:
            with tempfile.TemporaryDirectory() as td:
                for i in itertools.count():
                    try:
                        run(['mount', f'{lo}p2', td])
                        break
                    except CallError:
                        if i >= 10:
                            raise
                        else:
                            # losetup --partscan instructs the kernel to scan the partition table and add separate
                            # partition devices for each of the partitions it finds. However, this operation is
                            # asynchronous which means losetup will return before all partition devices have been
                            # initialized. This can result in a race condition where we try to access a partition device
                            # before it's been initialized by the kernel.
                            time.sleep(1)

                try:
                    grub_cfg_path = os.path.join(td, 'EFI/debian/grub.cfg')
                    with open(grub_cfg_path) as f:
                        grub_cfg = f.read()

                    substr = 'source $prefix/x86_64-efi/grub.cfg'
                    if substr not in grub_cfg:
                        raise ValueError(f'Invalid grub.cfg:\n{grub_cfg}')

                    grub_cfg = grub_cfg.replace(substr, 'source $prefix/grub.cfg')

                    with open(grub_cfg_path, 'w') as f:
                        f.write(grub_cfg)
                finally:
                    run(['umount', td])
        finally:
            run(['losetup', '-d', lo])
    finally:
        run(['umount', '-f', os.path.join(CHROOT_BASEDIR, CD_DIR)])
        run(['umount', '-f', os.path.join(CHROOT_BASEDIR, RELEASE_DIR)])
        run(['umount', '-f', os.path.join(CHROOT_BASEDIR, 'packages')])

    with open(os.path.join(RELEASE_DIR, f'TrueNAS-SCALE-{get_image_version()}.iso.sha256'), 'w') as f:
        f.write(run(
            ['sha256sum', os.path.join(RELEASE_DIR, f'TrueNAS-SCALE-{get_image_version()}.iso')], log=False
        ).stdout.replace(f'{RELEASE_DIR}/', '').strip())


def pruning_cd_basedir_contents():
    return itertools.chain(
        [
            'var/cache/apt',
            'var/lib/apt',
            'usr/share/doc',
            'usr/share/man',
            'etc/resolv.conf',
        ], map(
            lambda path: path.removeprefix(f'{CHROOT_BASEDIR}/'),
            glob.glob(os.path.join(CHROOT_BASEDIR, 'lib/modules/*truenas/kernel/sound'))
        )
    )
