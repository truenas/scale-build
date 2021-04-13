import logging
import os
import shutil

from .bootstrap.configure import make_bootstrapdir
from .clean import clean_bootstrap_logs
from .utils.manifest import get_packages
from .utils.variables import LOG_DIR, PKG_LOG_DIR


logger = logging.getLogger(__name__)


def build_packages():
    clean_bootstrap_logs()
    logger.debug('Creating debian bootstrap directory: (%s/bootstrap_chroot.log)', LOG_DIR)
    with open(os.path.join(LOG_DIR, 'bootstrap_chroot.log'), 'w') as f:
        make_bootstrapdir('package', f)

    shutil.rmtree(PKG_LOG_DIR, ignore_errors=True)
    os.makedirs(PKG_LOG_DIR)

