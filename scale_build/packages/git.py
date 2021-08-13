import logging
import os
import shutil

from scale_build.utils.git_utils import (
    create_branch, retrieve_git_remote_and_sha, retrieve_git_branch, update_git_manifest
)
from scale_build.utils.logger import LoggingContext
from scale_build.utils.paths import BRANCH_OUT_LOG_FILENAME, GIT_LOG_PATH
from scale_build.utils.run import run


logger = logging.getLogger(__name__)


class GitPackageMixin:

    def branch_out(self, new_branch_name, base_branch_override=None):
        with LoggingContext(BRANCH_OUT_LOG_FILENAME):
            create_branch(self.source_path, base_branch_override or self.branch, new_branch_name)

    def retrieve_current_remote_origin_and_sha(self):
        if self.exists:
            return retrieve_git_remote_and_sha(self.source_path)
        else:
            return {'url': None, 'sha': None}

    def update_git_manifest(self):
        info = self.retrieve_current_remote_origin_and_sha()
        update_git_manifest(info['url'], info['sha'])

    def checkout(self, branch_override=None):
        origin_url = self.retrieve_current_remote_origin_and_sha()['url']
        branch = branch_override or self.branch
        if branch == self.existing_branch and self.origin == origin_url:
            logger.debug('Updating git repo [%s] (%s)', self.name, GIT_LOG_PATH)
            with LoggingContext('git-checkout', 'w'):
                run(['git', '-C', self.source_path, 'fetch', 'origin'])
                run(['git', '-C', self.source_path, 'checkout', branch])
                run(['git', '-C', self.source_path, 'reset', '--hard', f'origin/{branch}'])
        else:
            logger.debug('Checking out git repo [%s] (%s)', self.name, GIT_LOG_PATH)
            if os.path.exists(self.source_path):
                shutil.rmtree(self.source_path)
            with LoggingContext('git-checkout', 'w'):
                run(['git', 'clone', '--recurse', self.origin, self.source_path])
                run(['git', '-C', self.source_path, 'checkout', branch])

        self.update_git_manifest()

    @property
    def existing_branch(self):
        if not self.exists:
            return None
        return retrieve_git_branch(self.source_path)
