import os
import shutil

from scale_build.exceptions import CallError
from scale_build.utils.run import run
from scale_build.utils.variables import (
    CACHE_DIR, CHROOT_BASEDIR, CHROOT_OVERLAY, DPKG_OVERLAY, PKG_DIR, WORKDIR_OVERLAY
)


def make_overlay_fs():
    for path in (CHROOT_OVERLAY, DPKG_OVERLAY, WORKDIR_OVERLAY):
        os.makedirs(path, exist_ok=True)

    dpkg_overlay_packages = os.path.join(DPKG_OVERLAY, 'packages')

    for entry in (
        ([
             'mount', '-t', 'overlay', '-o',
             f'lowerdir={CHROOT_BASEDIR},upperdir={CHROOT_OVERLAY},workdir={WORKDIR_OVERLAY}',
             'none', f'{DPKG_OVERLAY}/'
        ], 'Failed overlayfs'),
        (['mount', 'proc', os.path.join(DPKG_OVERLAY, 'proc'), '-t', 'proc'], 'Failed mount proc'),
        (['mount', 'sysfs', os.path.join(DPKG_OVERLAY, 'sys'), '-t', 'sysfs'], 'Failed mount sysfs'),
        (['mount', '--bind', PKG_DIR, dpkg_overlay_packages], 'Failed mount --bind /packages', dpkg_overlay_packages),
        (
            ['mount', '--bind', os.path.join(CACHE_DIR, 'apt'), os.path.join(DPKG_OVERLAY, 'var/cache/apt')],
            'Failed mount --bind /var/cache/apt',
        ),
    ):
        if len(entry) == 2:
            command, msg = entry
        else:
            command, msg, path = entry
            os.makedirs(path, exist_ok=True)

        run(command, exception=CallError, exception_msg=msg)


def remove_overlay_fs():
    for command in (
        ['umount', '-f', os.path.join(DPKG_OVERLAY, 'var/cache/apt')],
        ['umount', '-f', os.path.join(DPKG_OVERLAY, 'packages')],
        ['umount', '-f', os.path.join(DPKG_OVERLAY, 'proc')],
        ['umount', '-f', os.path.join(DPKG_OVERLAY, 'sys')],
        ['umount', '-f', DPKG_OVERLAY],
        ['umount', '-R', '-f', DPKG_OVERLAY],
    ):
        run(command, check=False)

    for path in (CHROOT_OVERLAY, DPKG_OVERLAY, WORKDIR_OVERLAY):
        shutil.rmtree(path, ignore_errors=True)
