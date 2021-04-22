import json
import os

from scale_build.clean import clean_packages
from scale_build.exceptions import CallError

from .hash import get_all_repo_hash
from .logger import get_logger
from .utils import CACHE_DIR, CHROOT_BASEDIR, get_cache_filename, get_cache_hash_filename, HASH_DIR, run


def create_basehash(cache_type):
    # This is to check if apt mirrors have changed
    with open(os.path.join(CACHE_DIR, get_cache_hash_filename(cache_type)), 'w') as f:
        f.write(get_all_repo_hash())


def check_basechroot_changed():
    # This is for checking if we should clean packages
    logger = get_logger('package')
    base_hash = get_base_hash()
    basechroot_hash_path = os.path.join(HASH_DIR, '.basechroot.hash')
    if os.path.exists(basechroot_hash_path):
        with open(basechroot_hash_path, 'r') as f:
            saved_hash = f.read().strip()
        if saved_hash != base_hash:
            logger.debug('Upstream repository changes detected. Rebuilding all packages...')
            clean_packages()

    with open(basechroot_hash_path, 'w') as f:
        f.write(base_hash)


def save_build_cache(cache_type):
    logger = get_logger(cache_type)
    logger.debug('Caching CHROOT_BASEDIR for future runs...')
    run([
        'mksquashfs', CHROOT_BASEDIR, os.path.join(CACHE_DIR, get_cache_filename(cache_type))
    ], logger=logger, exception=CallError, exception_msg='Failed squashfs')


def remove_basecache(cache_type):
    logger = get_logger(cache_type)
    logger.debug('Removing base chroot cache for %s', cache_type.name)
    for path in map(
        lambda p: os.path.join(CACHE_DIR, p), (get_cache_filename(cache_type), get_cache_hash_filename(cache_type))
    ):
        if os.path.exists(path):
            os.unlink(path)


def restore_basecache(cache_type, chroot_basedir, logger=None):
    run([
        'unsquashfs', '-f', '-d', chroot_basedir, os.path.join(CACHE_DIR, get_cache_filename(cache_type))
    ], exception=CallError, exception_msg='Failed unsquashfs', logger=logger)


def validate_basecache(cache_type):
    # No hash file? Lets remove to be safe
    logger = get_logger(cache_type)
    cache_hash_file = os.path.join(CACHE_DIR, get_cache_hash_filename(cache_type))
    invalidated = True
    if not os.path.exists(cache_hash_file) or not os.path.exists(
        os.path.join(CACHE_DIR, get_cache_filename(cache_type))
    ):
        remove_basecache(cache_type)
    else:
        with open(cache_hash_file, 'r') as f:
            saved_hash = f.read().strip()
        if saved_hash != get_all_repo_hash():
            logger.debug('Upstream repo changed! Removing squashfs cache to re-create.')
            remove_basecache(cache_type)
        else:
            invalidated = False

    return not invalidated


class CacheMixin:

    @property
    def cache_filename(self):
        raise NotImplementedError

    @property
    def cache_file_path(self):
        return os.path.join(CACHE_DIR, self.cache_filename)

    @property
    def cache_exists(self):
        return all(
            os.path.exists(p) for p in (self.cache_file_path, self.saved_packages_file_path, self.cache_hash_file_path)
        )

    def remove_cache(self):
        for path in filter(
            lambda p: os.path.exists(p),
            (self.cache_file_path, self.saved_packages_file_path, self.cache_hash_file_path)
        ):
            os.unlink(path)

    def get_mirror_cache(self):
        if self.cache_exists:
            with open(self.cache_hash_file_path, 'r') as f:
                return f.read().strip()

    def save_build_cache(self, installed_packages):
        self.logger.debug('Caching CHROOT_BASEDIR for future runs...')
        self.run(['mksquashfs', self.chroot_basedir, self.cache_filename])
        self.update_saved_packages_list(installed_packages)
        self.update_mirror_cache()

    @property
    def mirror_cache_intact(self):
        intact = True
        if not self.cache_exists:
            # No hash file? Lets remove to be safe
            intact = False
            self.logger.debug('Cache does not exist')

        if get_all_repo_hash() != self.get_mirror_cache():
            self.logger.debug('Upstream repo changed! Removing squashfs cache to re-create.')
            intact = False

        if not intact:
            self.remove_cache()

        return intact

    @property
    def installed_packages_in_cache_changed(self):
        return self.installed_packages_in_cache != self.get_packages()

    def restore_cache(self, chroot_basedir):
        self.run([
            'unsquashfs', '-f', '-d', chroot_basedir, self.cache_file_path
        ])
