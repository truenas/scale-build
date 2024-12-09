import contextlib
import json
import logging
import os

from scale_build.exceptions import CallError
from scale_build.utils.run import run
from scale_build.utils.paths import HASH_DIR, PKG_LOG_DIR, SOURCES_DIR

from .binary_package import BinaryPackage
from .bootstrap import BootstrapMixin
from .build import BuildPackageMixin
from .ccache import CCacheMixin
from .clean import BuildCleanMixin
from .git import GitPackageMixin
from .overlay import OverlayMixin
from .utils import (
    DEPENDS_SCRIPT_PATH, gather_build_time_dependencies, get_normalized_build_constraint_value,
    get_normalized_specified_build_constraint_value, normalize_build_depends, normalize_bin_packages_depends,
)


logger = logging.getLogger(__name__)

MANDATORY_EXPLICIT_DEPS = frozenset(['python3'])


class Package(BootstrapMixin, BuildPackageMixin, BuildCleanMixin, CCacheMixin, GitPackageMixin, OverlayMixin):
    def __init__(
        self, name, branch, repo, prebuildcmd=None, explicit_deps=None,
        generate_version=True, predepscmd=None, deps_path=None, subdir=None, deoptions=None, jobs=None,
        buildcmd=None, tmpfs=True, tmpfs_size=12, batch_priority=100, env=None, identity_file_path=None,
        build_constraints=None, debian_fork=False, source_name=None, depscmd=None, supports_ccache=False,
    ):
        self.name = name
        self.source_name = source_name or name
        self.branch = branch
        self.origin = repo
        self.supports_ccache = supports_ccache
        self.prebuildcmd = prebuildcmd or []
        self.buildcmd = buildcmd or []
        self.build_constraints = build_constraints or []
        self.depscmd = depscmd or []
        self.explicit_deps = set(explicit_deps or set()) | MANDATORY_EXPLICIT_DEPS
        self.generate_version = generate_version
        self.predepscmd = predepscmd or []
        self.deps_path = deps_path
        self.subdir = subdir
        self.identity_file_path = identity_file_path
        self.deoptions = deoptions
        self.jobs = jobs
        self.tmpfs = tmpfs
        self.tmpfs_size = tmpfs_size
        self.initialized_deps = False
        self._binary_packages = []
        self.build_depends = set()
        self.source_package = None
        self.parent_changed = False
        self.force_build = False
        self._build_time_dependencies = None
        self.build_stage = None
        self.logger = logger
        self.children = set()
        self.batch_priority = batch_priority
        self.env = env or {}
        self.debian_fork = debian_fork

        if name in self.explicit_deps:
            self.explicit_deps.remove(name)

    def __eq__(self, other):
        return other == self.name if isinstance(other, str) else self.name == other.name

    @property
    def log_file_path(self):
        return os.path.join(PKG_LOG_DIR, f'{self.name}.log')

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
        return os.path.join(SOURCES_DIR, self.source_name)

    @property
    def binary_packages(self):
        if self._binary_packages:
            return self._binary_packages

        if self.name in ('kernel', 'kernel-dbg') or (self.predepscmd and not self.deps_path):
            # We cannot determine dependency of this package because it does not probably have a control file
            # in it's current state - the only example we have is grub right now. Let's improve this if there are
            # more examples
            self._binary_packages.append(BinaryPackage(self.name, self.build_depends, self.name, self.name, set()))
            return self._binary_packages

        with (self.build_dir() if self.depscmd else contextlib.nullcontext()):
            if self.depscmd:
                self.setup_control_file_for_dependency_ordering()
                control_file_path = os.path.join(self.package_source_with_chroot, 'debian/control')
            else:
                control_file_path = self.debian_control_file_path

            cp = run([DEPENDS_SCRIPT_PATH, control_file_path], log=False)
            info = json.loads(cp.stdout)
            self.build_depends = set(
                normalize_build_depends(info['source_package']['build_depends'])
            ) | self.explicit_deps
            self.source_package = info['source_package']['name']
            for bin_package in info['binary_packages']:
                self._binary_packages.append(BinaryPackage(
                    bin_package['name'], self.build_depends, self.source_package, self.name,
                    set(normalize_bin_packages_depends(bin_package['depends'] or ''))
                ))
                if self.name == 'truenas':
                    self._binary_packages[-1].build_dependencies |= self._binary_packages[-1].install_dependencies

        return self._binary_packages

    def setup_control_file_for_dependency_ordering(self):
        self.execute_pre_depends_commands()
        for dependency_command in self.depscmd:
            self.logger.debug('Running depscmd: %r', dependency_command)
            self.run_in_chroot(
                f'cd {self.package_source} && {dependency_command}', 'Failed to execute depscmd command'
            )

    def build_time_dependencies(self, all_binary_packages=None):
        if self._build_time_dependencies is not None:
            return self._build_time_dependencies
        elif not all_binary_packages:
            raise CallError('Binary packages must be specified when computing build time dependencies')

        self._build_time_dependencies = gather_build_time_dependencies(
            all_binary_packages, set(), self.build_depends
        ) | self.explicit_deps
        return self._build_time_dependencies

    @property
    def hash_changed(self):
        return self._hash_changed()

    def _hash_changed(self):
        if self.name == 'truenas':
            # truenas is special and we want to rebuild it always
            # TODO: Do see why that is so
            return True

        source_hash = self.source_hash
        existing_hash = None
        if os.path.exists(self.hash_path):
            with open(self.hash_path, 'r') as f:
                existing_hash = f.read().strip()
        if source_hash == existing_hash:
            return run(
                ['git', '-C', self.source_path, 'diff-files', '--quiet', '--ignore-submodules'], check=False, log=False
            ).returncode != 0
        else:
            return True

    @property
    def source_hash(self):
        return run(['git', '-C', self.source_path, 'rev-parse', '--verify', 'HEAD'], log=False).stdout.strip()

    @property
    def rebuild(self):
        return self.hash_changed or self.parent_changed

    @property
    def hash_path(self):
        return os.path.join(HASH_DIR, f'{self.name}.hash')

    @property
    def exists(self):
        return os.path.exists(self.source_path)

    @property
    def pkglist_hash_file_path(self):
        return os.path.join(HASH_DIR, f'{self.name}.pkglist')

    @property
    def to_build(self):
        return all(
            get_normalized_build_constraint_value(constraint) == get_normalized_specified_build_constraint_value(
                constraint
            ) for constraint in self.build_constraints
        ) if self.build_constraints else True
