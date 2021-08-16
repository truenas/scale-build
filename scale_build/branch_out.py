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


def validate_branch_out_config(push_branched_out_repos):
    if not BRANCH_OUT_NAME:
        raise CallError('"NEW_BRANCH_NAME" must be configured')
    if push_branched_out_repos and not GITHUB_TOKEN:
        raise CallError('In order to push branched out packages, "GITHUB_TOKEN" must be specified')


def branch_out_repos(push_branched_out_repos):
    if os.path.exists(BRANCH_OUT_LOG_DIR):
        shutil.rmtree(BRANCH_OUT_LOG_DIR)
    os.makedirs(BRANCH_OUT_LOG_DIR)

    logger.info('Starting branch out of source using %r branch', BRANCH_OUT_NAME)

    for package in get_packages():
        logger.debug('Branching out %r', package.name)
        skip_log = None
        with LoggingContext(os.path.join('branchout', package.name), 'w'):
            branch_exists_remotely = package.branch_exists_in_remote(BRANCH_OUT_NAME)
            if branch_exists_remotely:
                skip_log = 'Branch already available in remote upstream, skipping'
            if package.branch_checked_out_locally(BRANCH_OUT_NAME):
                skip_log = 'Branch checked out locally already, skipping'
            if not skip_log:
                package.branch_out(BRANCH_OUT_NAME)
            else:
                logger.debug(skip_log)

        if push_branched_out_repos:
            if branch_exists_remotely:
                logger.debug('%r branch exists remotely already for %r', BRANCH_OUT_NAME, package.name)
            else:
                logger.debug('Pushing %r package\'s branch', package.name)

                with LoggingContext(os.path.join('branchout', package.name), 'a+'):
                    push_changes(package.source_path, GITHUB_TOKEN, BRANCH_OUT_NAME)
