import logging
import os
import shutil

from .bootstrap.configure import make_bootstrapdir
from .clean import clean_bootstrap_logs
from .config import PKG_DEBUG
from .packages.order import get_to_build_packages
from .utils.paths import LOG_DIR, PKG_LOG_DIR


logger = logging.getLogger(__name__)


def build_packages():
    clean_bootstrap_logs()
    _build_packages_impl()


def _build_packages_impl():
    logger.debug('Building packages')
    make_bootstrapdir('package')

    shutil.rmtree(PKG_LOG_DIR, ignore_errors=True)
    os.makedirs(PKG_LOG_DIR)

    packages = get_to_build_packages()
    for pkg_name, package in packages.items():
        logger.debug('Building package [%s] (%s/packages/%s.log)', pkg_name, LOG_DIR, pkg_name)
        try:
            package.build()
        except Exception:
            logger.error('Failed to build %r package', exc_info=True)
            package.delete_overlayfs()
            raise

    logger.debug('Success! Done building packages')
