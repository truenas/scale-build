import os
import shutil

from scale_build.exceptions import CallError
from scale_build.utils.run import run
from scale_build.utils.variables import CACHE_DIR, PKG_DIR, TMP_DIR, TMPFS


class OverlayMixin:

    @property
    def chroot_base_directory(self):
        return os.path.join(TMPFS, f'chroot_{self.name}')

    @property
    def chroot_overlay(self):
        return os.path.join(TMPFS, f'chroot-overlay_{self.name}')

    @property
    def dpkg_overlay(self):
        return os.path.join(TMP_DIR, f'dpkg-overlay_{self.name}')

    @property
    def workdir_overlay(self):
        return os.path.join(TMPFS, f'workdir-overlay_{self.name}')

    @property
    def dpkg_overlay_packages_path(self):
        return os.path.join(self.dpkg_overlay, 'packages')

    def make_overlayfs(self):
        for path in (self.chroot_overlay, self.dpkg_overlay, self.workdir_overlay):
            os.makedirs(path, exist_ok=True)

        for entry in (
            ([
                 'mount', '-t', 'overlay', '-o',
                 f'lowerdir={self.chroot_base_directory},upperdir={self.chroot_overlay},workdir={self.workdir_overlay}',
                 'none', f'{self.dpkg_overlay}/'
             ], 'Failed overlayfs'),
            (['mount', 'proc', os.path.join(self.dpkg_overlay, 'proc'), '-t', 'proc'], 'Failed mount proc'),
            (['mount', 'sysfs', os.path.join(self.dpkg_overlay, 'sys'), '-t', 'sysfs'], 'Failed mount sysfs'),
            (['mount', '--bind', PKG_DIR, self.dpkg_overlay_packages_path], 'Failed mount --bind /packages',
             self.dpkg_overlay_packages_path),
            (
                ['mount', '--bind', os.path.join(CACHE_DIR, 'apt'), os.path.join(self.dpkg_overlay, 'var/cache/apt')],
                'Failed mount --bind /var/cache/apt',
            ),
        ):
            if len(entry) == 2:
                command, msg = entry
            else:
                command, msg, path = entry
                os.makedirs(path, exist_ok=True)

            run(command, exception=CallError, exception_msg=msg)

    def delete_overlayfs(self):
        for command in (
            ['umount', '-f', os.path.join(self.dpkg_overlay, 'var/cache/apt')],
            ['umount', '-f', self.dpkg_overlay_packages_path],
            ['umount', '-f', os.path.join(self.dpkg_overlay, 'proc')],
            ['umount', '-f', os.path.join(self.dpkg_overlay, 'sys')],
            ['umount', '-f', self.dpkg_overlay],
            ['umount', '-R', '-f', self.dpkg_overlay],
        ):
            run(command, check=False)

        for path in (self.chroot_overlay, self.dpkg_overlay, self.workdir_overlay):
            shutil.rmtree(path, ignore_errors=True)
