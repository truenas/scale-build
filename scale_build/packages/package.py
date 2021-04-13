import json
import logging
import os
import shutil

from collections import defaultdict
from scale_build.utils.git_utils import retrieve_git_remote_and_sha, retrieve_git_branch, update_git_manifest
from scale_build.utils.run import run
from scale_build.utils.variables import GIT_LOG_PATH, SOURCES_DIR

from .utils import DEPENDS_SCRIPT_PATH, get_install_deps, normalize_build_depends, normalize_bin_packages_depends


logger = logging.getLogger(__name__)


class Package:
    def __init__(
        self, name, branch, repo, prebuildcmd=None, kernel_module=False, explicit_deps=None,
        generate_version=False, predepscmd=None, deps_path=None, subdir=None, deoptions=None, jobs=None,
    ):
        self.name = name
        self.branch = branch
        self.origin = repo
        self.prebuildcmd = prebuildcmd
        self.kernel_module = kernel_module
        self.explicit_deps = explicit_deps or set()
        self.generate_version = generate_version
        self.predepscmd = predepscmd
        self.deps_path = deps_path
        self.subdir = subdir
        self.deoptions = deoptions
        self.jobs = jobs
        self.initialized_deps = False
        self.binary_packages = defaultdict(
            lambda: {'install_deps': set(), 'source_name': self.name, 'build_deps': set()}
        )
        self.build_depends = set()
        self.source_package = None

    @property
    def package_path(self):
        pkg_path = self.source_path
        if self.subdir:
            pkg_path = os.path.join(pkg_path, self.subdir)
        return pkg_path

    @property
    def debian_control_file_path(self):
        if self.deps_path:
            return os.path.join(self.package_path, self.deps_path, 'control')
        else:
            return os.path.join(self.package_path, 'debian/control')

    @property
    def source_path(self):
        return os.path.join(SOURCES_DIR, self.name)

    @property
    def dependencies(self):
        if self.initialized_deps:
            return self.binary_packages

        if self.name == 'kernel' or (self.predepscmd and not self.deps_path):
            # We cannot determine dependency of this package because it does not probably have a control file
            # in it's current state - the only example we have is grub right now. Let's improve this if there are
            # more examples
            self.binary_packages[self.name].update({
                'source_package': self.name,
            })

        cp = run([DEPENDS_SCRIPT_PATH, self.debian_control_file_path])
        info = json.loads(cp.stdout)
        default_dependencies = {'kernel'} if self.kernel_module else set()
        self.build_depends = set(
            normalize_build_depends(info['source_package']['build_depends'])
        ) | default_dependencies
        self.source_package = info['source_package']['name']
        for bin_package in info['binary_packages']:
            default_dependencies = {'kernel'} if self.kernel_module else set()
            self.binary_packages[bin_package['name']].update({
                'install_deps': set(normalize_bin_packages_depends(bin_package['depends'] or '')),
                'build_deps': self.build_depends,
            })
            if self.name == 'truenas':
                self.binary_packages[bin_package['name']]['build_deps'] |= self.binary_packages[
                    bin_package['name']]['install_deps']

        self.initialized_deps = True

        return self.binary_packages

    def build_time_dependencies(self, all_binary_packages):
        # Dependencies at build time will be build_depends
        return get_install_deps(all_binary_packages, set(), self.binary_packages[self.name]) | self.explicit_deps

    @property
    def exists(self):
        return os.path.exists(self.source_path)

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
            logger.debug(f'Updating git repo [{self.name}] ({GIT_LOG_PATH})')
            with open(GIT_LOG_PATH, 'w') as f:
                run(['git', '-C', self.source_path, 'fetch', '--unshallow'], stdout=f, stderr=f, check=False)
                run(['git', '-C', self.source_path, 'fetch', 'origin', branch], stdout=f, stderr=f)
                run(['git', '-C', self.source_path, 'reset', '--hard', f'origin/{branch}'], stdout=f, stderr=f)
        else:
            logger.debug(f'Checking out git repo [{self.name}] ({GIT_LOG_PATH})')
            shutil.rmtree(self.source_path, ignore_errors=True)
            with open(GIT_LOG_PATH, 'w') as f:
                run(['git', 'clone', '--depth=1', '-b', branch, self.origin, self.source_path], stdout=f, stderr=f)

        self.update_git_manifest()

    @property
    def existing_branch(self):
        if not self.exists:
            return None
        return retrieve_git_branch(self.source_path)
