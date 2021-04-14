import logging
import os
import shutil

from scale_build.bootstrap.cleanup import remove_boostrap_directory
from scale_build.packages.overlayfs import remove_overlay_fs

from .utils.variables import HASH_DIR, LOG_DIR, PKG_DIR, SOURCES_DIR, TMP_DIR


logger = logging.getLogger(__name__)


def clean_bootstrap_logs():
    for f in filter(lambda f: f.startswith('bootstrap'), os.listdir(LOG_DIR)):
        os.unlink(os.path.join(LOG_DIR, f))


def clean_packages():
    for d in (HASH_DIR, PKG_DIR):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)


def clean():
    remove_overlay_fs()
    remove_boostrap_directory()


def complete_cleanup():
    clean()
    for path in (LOG_DIR, SOURCES_DIR, TMP_DIR):
        shutil.rmtree(path, ignore_errors=True)
