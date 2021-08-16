import logging
import os
import shutil

from .config import BRANCH_OUT_NAME, GITHUB_TOKEN
from .exceptions import CallError
from .utils.git_utils import push_changes
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
    os.makedirs(BRANCH_OUT_LOG_DIR)

    logger.info('Starting branch out of source using %r branch', BRANCH_OUT_NAME)

    for package in get_packages():
        logger.debug('Branching out %r', package.name)
        skip_log = None
        with LoggingContext(os.path.join('branchout', package.name), 'w'):
            if package.branch_exists_in_remote(BRANCH_OUT_NAME):
                skip_log = 'Branch already available in remote upstream, skipping'
            if package.branch_checked_out_locally(BRANCH_OUT_LOG_DIR):
                skip_log = 'Branch checked out locally already, skipping'
            if skip_log:
                logger.debug(skip_log)
                continue

            package.branch_out(BRANCH_OUT_NAME)


def push_branched_out_repos():
    if not GITHUB_TOKEN:
        raise CallError('In order to push branched out packages, "GITHUB_TOKEN" must be specified')

    logger.info('Starting pushing new %r branch', BRANCH_OUT_NAME)

    for package in get_packages():
        logger.debug('Pushing %r package\'s branch', package.name)
        with LoggingContext(os.path.join('branchout', package.name), 'a+'):
            push_changes(package.source_path, GITHUB_TOKEN, BRANCH_OUT_NAME)
