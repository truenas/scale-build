import os

from scale_build.clean import clean_packages
from scale_build.exceptions import CallError

from .hash import get_all_repo_hash, get_base_hash
from .logger import get_logger
from .utils import CACHE_DIR, CHROOT_BASEDIR, get_cache_filename, get_cache_hash_filename, HASH_DIR, run


def create_basehash(cache_type):
    with open(os.path.join(CACHE_DIR, get_cache_hash_filename(cache_type)), 'w') as f:
        f.write(get_all_repo_hash())


def check_basechroot_changed():
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
    logger.debug('Removing base chroot cache for %s', cache_type)
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
