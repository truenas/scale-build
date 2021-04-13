import logging
import os
import re

from scale_build.sources.source import Source
from scale_build.utils.git_utils import retrieve_git_remote_and_sha, update_git_manifest
from scale_build.utils.manifest import get_manifest
from scale_build.utils.run import run


logger = logging.getLogger(__name__)


def checkout_sources():
    info = retrieve_git_remote_and_sha('.')
    update_git_manifest(info['url'], info['sha'])
    logger.debug(f'Starting checkout of source')
    try_branch_override = os.environ.get('TRY_BRANCH_OVERRIDE')

    for source_info in get_manifest()['sources']:
        source = Source(source_info['name'], source_info['branch'], source_info['repo'])
        gh_override = os.environ.get('TRUENAS_BRANCH_OVERRIDE')
        if not gh_override:
            gh_override = os.environ.get(f'{source.name}_OVERRIDE')

        # TRY_BRANCH_OVERRIDE is a special use-case. It allows setting a branch name to be used
        # during the checkout phase, only if it exists on the remote.
        #
        # This is useful for PR builds and testing where you want to use defaults for most repos
        # but need to test building of a series of repos with the same experimental branch
        #
        if try_branch_override:
            cp = run(['git', 'ls-remote', source.origin])
            if re.findall(fr'/{try_branch_override}$', cp.stdout.decode()):
                gh_override = try_branch_override

        source.checkout(gh_override)
