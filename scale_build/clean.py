import logging
import os
import shutil

from .utils.paths import HASH_DIR, LOG_DIR, PKG_DIR, SOURCES_DIR, TMP_DIR


logger = logging.getLogger(__name__)


def clean_bootstrap_logs():
    for f in filter(lambda f: f.startswith('bootstrap'), os.listdir(LOG_DIR)):
        os.unlink(os.path.join(LOG_DIR, f))


def clean_packages():
    for d in (HASH_DIR, PKG_DIR):
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d)


def complete_cleanup():
    for path in filter(os.path.exists, (LOG_DIR, SOURCES_DIR, TMP_DIR)):
        shutil.rmtree(path)

    logger.debug('Removed %s, %s, and %s directories', LOG_DIR, SOURCES_DIR, TMP_DIR)
