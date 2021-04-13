import logging
import os
import shutil

from .utils.variables import HASH_DIR, LOG_DIR, PKG_DIR


logger = logging.getLogger(__name__)


def clean_bootstrap_logs():
    for f in filter(lambda f: f.startswith('bootstrap'), os.listdir(LOG_DIR)):
        os.unlink(os.path.join(LOG_DIR, f))


def clean_packages():
    for d in (HASH_DIR, PKG_DIR):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)

