import os

from scale_build.utils.paths import CACHE_DIR
from scale_build.utils.run import run

from .hash import get_all_repo_hash


class CacheMixin:

    @property
    def cache_filename(self):
        raise NotImplementedError

    @property
    def cache_file_path(self):
        return os.path.join(CACHE_DIR, self.cache_filename)

    @property
    def extra_cache_files(self):
        return []

    @property
    def cache_exists(self):
        return all(
            os.path.exists(p) for p in [self.cache_file_path, self.cache_hash_file_path] + self.extra_cache_files
        )

    def remove_cache(self):
        for path in filter(
            lambda p: os.path.exists(p),
            [self.cache_file_path, self.cache_hash_file_path] + self.extra_cache_files
        ):
            os.unlink(path)

    def get_mirror_cache(self):
        if self.cache_exists:
            with open(self.cache_hash_file_path, 'r') as f:
                return f.read().strip()

    def save_build_cache(self, installed_packages):
        self.logger.debug('Caching CHROOT_BASEDIR for future runs...')
        run(['mksquashfs', self.chroot_basedir, self.cache_file_path])
        self.update_mirror_cache()

    @property
    def mirror_cache_intact(self):
        intact = True
        if not self.cache_exists:
            # No hash file? Lets remove to be safe
            intact = False
            self.logger.debug('Cache does not exist')

        elif get_all_repo_hash() != self.get_mirror_cache():
            self.logger.debug('Upstream repo changed! Removing squashfs cache to re-create.')
            intact = False

        if not intact:
            self.remove_cache()

        return intact

    def restore_cache(self, chroot_basedir):
        run(['unsquashfs', '-f', '-d', chroot_basedir, self.cache_file_path])
