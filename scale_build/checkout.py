import logging
import re

from .config import BRANCH_OVERRIDES, TRY_BRANCH_OVERRIDE
from .utils.git_utils import retrieve_git_remote_and_sha, update_git_manifest
from .utils.package import get_packages
from .utils.run import run


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
            cp = run(['git', 'ls-remote', package.origin], check=False)
            if cp.returncode == 0 and re.findall(fr'/{TRY_BRANCH_OVERRIDE}\n', cp.stdout.decode(), re.M):
                gh_override = TRY_BRANCH_OVERRIDE

        package.checkout(gh_override)
