import logging
import os

from .utils.system import has_low_ram
from .utils.paths import CACHE_DIR, HASH_DIR, LOG_DIR, PKG_DIR, PKG_LOG_DIR, SOURCES_DIR, TMP_DIR, TMPFS


logger = logging.getLogger(__name__)


def setup_dirs():
    for d in (CACHE_DIR, TMP_DIR, HASH_DIR, LOG_DIR, PKG_DIR, PKG_LOG_DIR, SOURCES_DIR, TMPFS):
        os.makedirs(d, exist_ok=True)


def preflight_check():
    if has_low_ram():
        logging.warning('WARNING: Running with less than 16GB of memory. Build may fail...')

    setup_dirs()
