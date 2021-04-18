import logging
import os
import shutil

from .exceptions import CallError, MissingPackagesException
from .utils.manifest import get_manifest
from .utils.system import has_low_ram
from .utils.paths import CACHE_DIR, HASH_DIR, LOG_DIR, PKG_DIR, PKG_LOG_DIR, SOURCES_DIR, TMP_DIR, TMPFS


logger = logging.getLogger(__name__)

WANTED_PACKAGES = {
    'make',
    'debootstrap',
    'git',
    'xorriso',
    'grub-mkrescue',
    'mksquashfs',
    'unzip',
}


def is_root():
    return os.geteuid() == 0


def retrieve_missing_packages():
    missing = {pkg for pkg in WANTED_PACKAGES if not shutil.which(pkg)}
    if not os.path.exists('/lib/grub/x86_64-efi') and not os.path.exists('/usr/lib/grub/x86_64-efi'):
        missing.add('grub-efi-amd64-bin')

    if not os.path.exists('/lib/grub/i386-pc') and not os.path.exists('/usr/lib/grub/i386-pc'):
        missing.add('grub-pc-bin')

    return missing


def setup_dirs():
    for d in (CACHE_DIR, TMP_DIR, HASH_DIR, LOG_DIR, PKG_DIR, PKG_LOG_DIR, SOURCES_DIR, TMPFS):
        os.makedirs(d, exist_ok=True)


def preflight_check():
    # TODO: Please see how we should delete overlayfs/bootstrapdir when exceptions are raised
    if not is_root():
        raise CallError('Must be run as root (or using sudo)!')

    missing_packages = retrieve_missing_packages()
    if missing_packages:
        raise MissingPackagesException(missing_packages)

    if has_low_ram():
        logging.warning('WARNING: Running with less than 16GB of memory. Build may fail...')

    setup_dirs()
    # TODO: Validate contents of manifest like empty string is not provided for source name/repo etc
    get_manifest()
