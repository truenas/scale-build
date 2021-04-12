import logging
import os
import shutil

from scale_build.utils.git_utils import retrieve_git_remote_and_sha, retrieve_git_branch, update_git_manifest
from scale_build.utils.run import run
from scale_build.utils.variables import GIT_LOG_PATH, SOURCES_DIR


logger = logging.getLogger(__name__)


class Source:
    def __init__(self, name, branch, git_origin):
        self.name = name
        self.branch = branch
        self.origin = git_origin

    @property
    def path(self):
        return os.path.join(SOURCES_DIR, self.name)

    @property
    def exists(self):
        return os.path.exists(self.path)

    def retrieve_current_remote_origin_and_sha(self):
        if self.exists:
            return retrieve_git_remote_and_sha(self.path)
        else:
            return {'url': None, 'sha': None}

    def update_git_manifest(self):
        info = self.retrieve_current_remote_origin_and_sha()
        update_git_manifest(info['url'], info['sha'])

    def checkout(self):
        origin_url = self.retrieve_current_remote_origin_and_sha()['url']
        if self.branch == self.existing_branch and self.origin == origin_url:
            logger.debug(f'Updating git repo [{self.name}] ({GIT_LOG_PATH})')
            with open(GIT_LOG_PATH, 'w') as f:
                run(['git', '-C', self.path, 'fetch', '--unshallow'], stdout=f, stderr=f, check=False)
                run(['git', '-C', self.path, 'fetch', 'origin', self.branch], stdout=f, stderr=f)
                run(['git', '-C', self.path, 'reset', '--hard', f'origin/{self.branch}'], stdout=f, stderr=f)
        else:
            logger.debug(f'Checking out git repo [{self.name}] ({GIT_LOG_PATH})')
            shutil.rmtree(self.path, ignore_errors=True)
            with open(GIT_LOG_PATH, 'w') as f:
                run(['git', 'clone', '--depth=1', '-b', self.branch, self.origin, self.path], stdout=f, stderr=f)

        self.update_git_manifest()

    @property
    def existing_branch(self):
        if not self.exists:
            return None
        return retrieve_git_branch(self.path)
