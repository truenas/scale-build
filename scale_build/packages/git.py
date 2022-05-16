import logging
import os
import shutil
import contextlib

from scale_build.config import BRANCH_OVERRIDES, TRUENAS_BRANCH_OVERRIDE, TRY_BRANCH_OVERRIDE
from scale_build.exceptions import CallError
from scale_build.utils.git_utils import (
    branch_checked_out_locally, branch_exists_in_repository, create_branch,
    retrieve_git_remote_and_sha, retrieve_git_branch, update_git_manifest
)
from scale_build.utils.logger import LoggingContext
from scale_build.utils.paths import GIT_LOG_DIR_NAME, GIT_LOG_DIR
from scale_build.utils.run import run

logger = logging.getLogger(__name__)


class GitPackageMixin:

    def branch_out(self, new_branch_name, base_branch_override=None):
        create_branch(self.source_path, base_branch_override or self.branch, new_branch_name)

    def branch_exists_in_remote(self, branch):
        return branch_exists_in_repository(self.origin, branch)

    def branch_checked_out_locally(self, branch):
        return branch_checked_out_locally(self.source_path, branch)

    def retrieve_current_remote_origin_and_sha(self):
        if self.exists:
            return retrieve_git_remote_and_sha(self.source_path)
        else:
            return {'url': None, 'sha': None}

    def update_git_manifest(self):
        info = self.retrieve_current_remote_origin_and_sha()
        update_git_manifest(info['url'], info['sha'])

    @property
    def git_log_file(self):
        return os.path.join(GIT_LOG_DIR_NAME, self.name)

    @property
    def git_log_file_path(self):
        return os.path.join(GIT_LOG_DIR, f'{self.name}.log')

    def checkout(self, branch_override=None, retries=3):
        origin_url = self.retrieve_current_remote_origin_and_sha()['url']
        branch = branch_override or self.branch
        update = (branch == self.existing_branch) and self.origin == origin_url
        if update:
            cmds = (
                ['git', '-C', self.source_path, 'fetch', 'origin'],
                ['git', '-C', self.source_path, 'checkout', branch],
                ['git', '-C', self.source_path, 'reset', '--hard', f'origin/{branch}'],
            )
        else:
            cmds = (
                ['git', 'clone', '--recurse', self.origin, self.source_path],
                ['git', '-C', self.source_path, 'checkout', branch],
            )

        retries = 3 if retries <= 0 or retries > 10 else retries
        for i in range(1, retries + 1):
            if i == 1:
                log = 'Updating git repo' if update else 'Checking out git repo'
                logger_method = logger.debug
            else:
                log = 'Retrying to update git repo' if update else 'Retrying to checkout git repo'
                logger_method = logger.warning

            log += f' {self.name!r} (using branch {branch!r}) ({self.git_log_file_path})'
            logger_method(log)

            if not update:
                # if we're not updating then we need to remove the existing
                # git directory (if it exists) before trying to checkout
                with contextlib.suppress(FileNotFoundError):
                    shutil.rmtree(self.source_path)

            failed = False
            with LoggingContext(self.git_log_file, 'w'):
                for cmd in cmds:
                    cp = run(cmd, check=False)
                    if cp.returncode:
                        failed = (f'{" ".join(cmd)}', f'{cp.stderr}', f'{cp.returncode}')
                        break

            if failed:
                failed_log_file = self.git_log_file + f'.failed.{i}'
                err = f'Failed cmd {failed[0]!r} with error {failed[1]!r} with returncode {failed[2]!r}.'
                err += f' Check {failed_log_file!r} for details.'
                shutil.copyfile(self.git_log_file, failed_log_file)
                if i == retries:
                    raise CallError(err)
                else:
                    logger.warning(err)
                    continue
            else:
                break

        self.update_git_manifest()
        log = 'Checkout ' if not update else 'Updating '
        logger.info(log + 'of git repo %r (using branch %r) complete', self.name, branch)

    @property
    def existing_branch(self):
        if not self.exists:
            return None
        return retrieve_git_branch(self.source_path)

    def get_branch_override(self):
        # We prioritise TRUENAS_BRANCH_OVERRIDE over any individual branch override
        # keeping in line with the behavior we used to have before
        gh_override = TRUENAS_BRANCH_OVERRIDE or BRANCH_OVERRIDES.get(self.name)

        # TRY_BRANCH_OVERRIDE is a special use-case. It allows setting a branch name to be used
        # during the checkout phase, only if it exists on the remote.
        #
        # This is useful for PR builds and testing where you want to use defaults for most repos
        # but need to test building of a series of repos with the same experimental branch
        #
        if TRY_BRANCH_OVERRIDE:
            retries = 3
            while retries:
                try:
                    if branch_exists_in_repository(self.origin, TRY_BRANCH_OVERRIDE):
                        gh_override = TRY_BRANCH_OVERRIDE
                except CallError:
                    retries -= 1
                    logger.debug(
                        'Failed to determine if %r branch exists for %r. Trying again', TRY_BRANCH_OVERRIDE, self.origin
                    )
                    if not retries:
                        logger.debug('Unable to determine if %r branch exists in 3 attempts.', TRY_BRANCH_OVERRIDE)
                else:
                    break

        return gh_override
