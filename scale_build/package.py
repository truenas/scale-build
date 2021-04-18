import logging
import os
import shutil

from .bootstrap.configure import make_bootstrapdir
from .clean import clean_bootstrap_logs
from .packages.order import get_to_build_packages
from .utils.paths import LOG_DIR, PKG_LOG_DIR


logger = logging.getLogger(__name__)


def build_packages():
    clean_bootstrap_logs()
    try:
        _build_packages_impl()
    except Exception:
        pass
        #clean()


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
        except:
            logger.error('errored out', exc_info=True)
            raise

    logger.debug('Success! Done building packages')
