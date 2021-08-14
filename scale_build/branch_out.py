import logging
import os
import shutil

from .config import BRANCH_OUT_NAME
from .exceptions import CallError
from .utils.logger import LoggingContext
from .utils.package import get_packages
from .utils.paths import BRANCH_OUT_LOG_DIR


logger = logging.getLogger(__name__)


def validate_branch_out_config():
    if not BRANCH_OUT_NAME:
        raise CallError('"NEW_BRANCH_NAME" must be configured')


def branch_out_repos():
    if os.path.exists(BRANCH_OUT_LOG_DIR):
        shutil.rmtree(BRANCH_OUT_LOG_DIR)

    logger.info('Starting branch out of source using %r branch', BRANCH_OUT_NAME)

    for package in get_packages():
        logger.debug('Branching out %r', package.name)
        with LoggingContext(os.path.join('branchout', package.name), 'w'):
            package.branch_out()
