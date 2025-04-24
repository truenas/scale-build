import os
import shutil

from scale_build.utils.run import run
from scale_build.utils.paths import CCACHE_DIR, TMP_DIR, TMPFS


class OverlayMixin:

    @property
    def tmpfs_path(self):
        return f'{TMPFS}_{self.name}'

    @property
    def host_shared_folder(self):
        return '/etc/keys'

    @property
    def chroot_shared_folder_path(self):
        return os.path.join(self.dpkg_overlay, 'mnt', 'shared')

    @property
    def chroot_base_directory(self):
        return os.path.join(self.tmpfs_path, f'chroot_{self.name}')

    @property
    def chroot_overlay(self):
        return os.path.join(self.tmpfs_path, f'chroot-overlay_{self.name}')

    @property
    def sources_overlay(self):
        return os.path.join(TMP_DIR, f'sources_{self.name}')

    @property
    def dpkg_overlay(self):
        return os.path.join(TMP_DIR, f'dpkg-overlay_{self.name}')

    @property
    def workdir_overlay(self):
        return os.path.join(self.tmpfs_path, f'workdir-overlay_{self.name}')

    @property
    def dpkg_overlay_packages_path(self):
        return os.path.join(self.dpkg_overlay, 'packages')

    def make_overlayfs(self):
        for path in (self.chroot_overlay, self.dpkg_overlay, self.sources_overlay, self.workdir_overlay, self.chroot_shared_folder_path):
            os.makedirs(path, exist_ok=True)

        for entry in [
            ([
                 'mount', '-t', 'overlay', '-o',
                 f'lowerdir={self.chroot_base_directory},upperdir={self.chroot_overlay},workdir={self.workdir_overlay}',
                 'none', f'{self.dpkg_overlay}/'
             ], 'Failed overlayfs'),
            (['mount', 'proc', os.path.join(self.dpkg_overlay, 'proc'), '-t', 'proc'], 'Failed mount proc'),
            (['mount', 'sysfs', os.path.join(self.dpkg_overlay, 'sys'), '-t', 'sysfs'], 'Failed mount sysfs'),
            (
                ['mount', '--bind', self.sources_overlay, self.source_in_chroot],
                'Failed mount --bind /dpkg-src', self.source_in_chroot
            ),
            (
                ['mount', '--bind', self.host_shared_folder, self.chroot_shared_folder_path],
                'Failed to mount --bind shared host folder', self.chroot_shared_folder_path
            )
        ] + ([
            (['mount', '--bind', CCACHE_DIR, self.ccache_with_chroot_path],
             'Failed to mount --bind ccache', self.ccache_with_chroot_path),
        ] if self.ccache_enabled else []):
            if len(entry) == 2:
                command, msg = entry
            else:
                command, msg, path = entry
                os.makedirs(path, exist_ok=True)

            run(command, exception_msg=msg)

    def delete_overlayfs(self):
        for command in (
            ['umount', '-f', os.path.join(self.dpkg_overlay, 'proc')],
            ['umount', '-f', os.path.join(self.dpkg_overlay, 'sys')],
            ['umount', '-f', self.ccache_with_chroot_path],
            ['umount', '-f', self.dpkg_overlay],
            ['umount', '-R', '-f', self.dpkg_overlay],
            ['umount', '-R', '-f', self.tmpfs_path],
            ['umount', '-f', self.chroot_shared_folder_path],
        ):
            run(command, check=False)

        for path in filter(os.path.exists, (
            self.chroot_overlay, self.dpkg_overlay, self.workdir_overlay, self.chroot_base_directory,
            self.sources_overlay, self.tmpfs_path
        )):
            shutil.rmtree(path)
