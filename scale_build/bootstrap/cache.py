import os

from scale_build.clean import clean_packages
from scale_build.exceptions import CallError

from .hash import get_all_repo_hash, get_base_hash
from .utils import CACHE_DIR, CHROOT_BASEDIR, get_cache_hash_filename, HASH_DIR, run


def create_basehash(cache_type):
    with open(os.path.join(CACHE_DIR, get_cache_hash_filename(cache_type)), 'w') as f:
        f.write(get_all_repo_hash())


def check_basechroot_changed(log_handle):
    base_hash = get_base_hash()
    basechroot_hash_path = os.path.join(HASH_DIR, '.basechroot.hash')
    if os.path.exists(basechroot_hash_path):
        with open(basechroot_hash_path, 'r') as f:
            saved_hash = f.read().strip()
        if saved_hash != base_hash:
            log_handle.write('Upstream repository changes detected. Rebuilding all packages...\n')
            clean_packages()

    with open(basechroot_hash_path, 'w') as f:
        f.write(base_hash)


def save_build_cache(cache_type, log_handle):
    log_handle.write('Caching CHROOT_BASEDIR for future runs...\n')
    run([
        'mksquashfs', CHROOT_BASEDIR, os.path.join(CACHE_DIR, get_cache_hash_filename(cache_type))
    ], stdout=log_handle, stderr=log_handle, exception=CallError, exception_msg='Failed squashfs')
