import errno
import json
import os
import shutil

from datetime import datetime
from distutils.dir_util import copy_tree
from scale_build.exceptions import CallError
from scale_build.utils.run import run
from scale_build.utils.variables import PKG_DIR


class BuildPackageMixin:

    def run_in_chroot(self, command, exception_message=None):
        exception = CallError if exception_message else None
        run(
            f'chroot {self.dpkg_overlay} /bin/bash -c "{command}"', shell=True, logger=self.logger,
            exception=exception, exception_msg=exception_message, env={
                **os.environ,
                # When logging in as 'su root' the /sbin dirs get dropped out of PATH
                'PATH': f'{os.environ["PATH"]}:/sbin:/usr/sbin:/usr/local/sbin',
                'LC_ALL': 'C',  # Makes some perl scripts happy during package builds
                'LANG': 'C',
                'DEB_BUILD_OPTIONS': f'parallel={os.cpu_count()}',  # Passed along to WAF for parallel build,
                'CONFIG_DEBUG_INFO': 'N',  # Build kernel with debug symbols
                'CONFIG_LOCALVERSION': '+truenas',
                'DEBIAN_FRONTEND': 'noninteractive',  # Never go full interactive on any packages
            }
        )

    @property
    def source_in_chroot(self):
        return os.path.join(self.dpkg_overlay, 'dpkg-src')

    @property
    def package_source_with_chroot(self):
        return os.path.join(self.dpkg_overlay, self.package_source)

    @property
    def package_source(self):
        return os.path.join(*filter(bool, ('dpkg-src', self.subdir)))

    def build(self):
        # The flow is the following steps
        # 1) Bootstrap a directory for package
        # 2) Delete existing overlayfs
        # 3) Create an overlayfs
        # 4) Clean previous packages
        # 5) Apt update
        # 6) Install linux custom headers/image for kernel based packages
        # 7) Execute relevant predep commands
        # 8) Install build depends
        # 9) Execute relevant prebuild commands
        # 10) Generate version
        # 11) Execute relevant building commands
        # 12) Save
        self._build_impl()

    def _build_impl(self):
        self.delete_overlayfs()
        self.setup_chroot_basedir()
        self.make_overlayfs()
        self.clean_previous_packages()
        if os.path.exists(os.path.join(self.dpkg_overlay_packages_path, 'Packages.gz')):
            self.run_in_chroot('apt update')
        copy_tree(self.source_path, self.source_in_chroot)

        if self.kernel_module:
            self.logger.debug('Installing truenas linux headers')
            self.run_in_chroot('apt install -y /packages/linux-headers-truenas*')
            self.run_in_chroot('apt install -y /packages/linux-image-truenas*')

        for predep_entry in self.predepscmd:
            if isinstance(predep_entry, dict):
                predep_cmd = predep_entry['command']
                for env_var in predep_entry['env_checks']:
                    if os.environ.get(env_var['key']) != env_var['value']:
                        self.logger.debug(
                            'Skipping %r predep command because %r does not match %r',
                            predep_cmd, env_var['key'], env_var['value']
                        )
                        continue
            else:
                predep_cmd = predep_entry

            self.logger.debug('Running predepcmd: %r', predep_cmd)
            self.run_in_chroot(
                f'cd {self.package_source} && {predep_cmd}', 'Failed to execute predep command'
            )

        if not os.path.exists(os.path.join(self.package_source_with_chroot, 'debian/control')):
            raise CallError(
                f'Missing debian/control file for {self.name} in {self.package_source_with_chroot}', errno.ENOENT
            )

        self.run_in_chroot(f'cd {self.package_source} && mk-build-deps --build-dep', 'Failed mk-build-deps')
        self.run_in_chroot(f'cd {self.package_source} && apt install -y ./*.deb', 'Failed install build deps')

        # Truenas package is special
        if self.name == 'truenas':
            os.makedirs(os.path.join(self.package_source_with_chroot, 'data'))
            # FIXME: Please see a good way to have environment variables available
            with open(os.path.join(self.package_source_with_chroot, 'data/manifest.json'), 'w') as f:
                f.write(json.dumps({
                    'buildtime': os.environ.get('BUILDTIME'),
                    'train': os.environ.get('TRAIN'),
                    'version': os.environ.get('VERSION'),
                }))
            os.makedirs(os.path.join(self.package_source_with_chroot, 'etc'), exist_ok=True)
            with open(os.path.join(self.package_source_with_chroot, 'etc/version'), 'w') as f:
                # FIXME: Remove string type cast please
                f.write(str(os.environ.get('VERSION')))

        # Make a programmatically generated version for this build
        generate_version_flags = ''
        if self.generate_version:
            generate_version_flags = f' -v {datetime.today().strftime("%Y%m%d%H%M%S")}~truenas+1 '

        self.run_in_chroot(
            f'cd {self.package_source} && dch -b -M {generate_version_flags}--force-distribution '
            '--distribution bullseye-truenas-unstable \'Tagged from truenas-build\'',
            'Failed dch changelog'
        )

        for command in self.build_command:
            self.logger.debug('Running build command: %r', command)
            self.run_in_chroot(
                f'cd {self.package_source} && {command}', f'Failed to build {self.name} package'
            )

        self.logger.debug('Copying finished packages')
        # Copy and record each built packages for cleanup later
        package_dir = os.path.dirname(self.package_source_with_chroot)
        built_packages = []
        for pkg in filter(lambda p: p.endswith(('.deb', '.udeb')), os.listdir(package_dir)):
            shutil.move(os.path.join(package_dir, pkg), os.path.join(PKG_DIR, pkg))
            built_packages.append(pkg)

        with open(self.pkglist_hash_file_path, 'w') as f:
            f.write('\n'.join(built_packages))

        # Update the local APT repo
        self.logger.debug('Building local APT repo Packages.gz...')
        self.run_in_chroot('cd /packages && dpkg-scanpackages . /dev/null | gzip -9c > Packages.gz')

        with open(self.hash_path, 'w') as f:
            f.write(self.source_hash)

        self.delete_overlayfs()

    @property
    def build_command(self):
        if self.buildcmd:
            return self.buildcmd
        else:
            build_env = f'DEB_BUILD_OPTIONS={self.deoptions} ' if self.deoptions else ''
            return [f'{build_env} debuild {" ".join(self.deflags)}']

    @property
    def deflags(self):
        return [f'-j{self.jobs if self.jobs else os.cpu_count()}', '-us', '-uc', '-b']


