import logging

from .utils.git_utils import retrieve_git_remote_and_sha, update_git_manifest
from .utils.package import get_packages


logger = logging.getLogger(__name__)


def checkout_sources():
    info = retrieve_git_remote_and_sha('.')
    update_git_manifest(info['url'], info['sha'], 'w')
    logger.info('Starting checkout of source')

    for package in get_packages():
        package.checkout(package.get_branch_override())
