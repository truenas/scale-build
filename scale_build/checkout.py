import logging
import subprocess

from .config import BRANCH_OVERRIDES, TRY_BRANCH_OVERRIDE
from .utils.git_utils import branch_exists_in_repository, retrieve_git_remote_and_sha, update_git_manifest
from .utils.package import get_packages


logger = logging.getLogger(__name__)


def checkout_sources():
    info = retrieve_git_remote_and_sha('.')
    update_git_manifest(info['url'], info['sha'], 'w')
    logger.info('Starting checkout of source')

    for package in get_packages():
        gh_override = BRANCH_OVERRIDES.get(package.name)

        # TRY_BRANCH_OVERRIDE is a special use-case. It allows setting a branch name to be used
        # during the checkout phase, only if it exists on the remote.
        #
        # This is useful for PR builds and testing where you want to use defaults for most repos
        # but need to test building of a series of repos with the same experimental branch
        #
        if TRY_BRANCH_OVERRIDE:
            retries = 2
            while retries:
                try:
                    branch_exists_in_repository(package.origin, TRY_BRANCH_OVERRIDE)
                except subprocess.CalledProcessError:
                    retries -= 1
                else:
                    gh_override = TRY_BRANCH_OVERRIDE
                    break

        package.checkout(gh_override)
