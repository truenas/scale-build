import json
import os
import shutil

from datetime import datetime
from scale_build.config import BUILD_TIME, VERSION
from scale_build.exceptions import CallError
from scale_build.utils.environment import APT_ENV
from scale_build.utils.manifest import get_truenas_train
from scale_build.utils.run import run
from scale_build.utils.paths import PKG_DIR


class BuildPackageMixin:

    def run_in_chroot(self, command, exception_message=None):
        run(
            f'chroot {self.dpkg_overlay} /bin/bash -c "{command}"', shell=True, exception_msg=exception_message,
            env=self._get_build_env()
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
        self.delete_overlayfs()
        self.setup_chroot_basedir()
        self.make_overlayfs()
        self.clean_previous_packages()
        self._build_impl()

    def _get_build_env(self):
        return {
            **os.environ,
            **APT_ENV,
            **self.env,
        }

    def _build_impl(self):
        shutil.copytree(self.source_path, self.source_in_chroot, dirs_exist_ok=True, symlinks=True)
        if os.path.exists(os.path.join(self.dpkg_overlay_packages_path, 'Packages.gz')):
            self.run_in_chroot('apt update')

        if self.kernel_module:
            self.logger.debug('Installing truenas linux headers')
            self.run_in_chroot('apt install -y /packages/linux-headers-truenas*')
            self.run_in_chroot('apt install -y /packages/linux-image-truenas*')

        for predep_entry in self.predepscmd:
            if isinstance(predep_entry, dict):
                predep_cmd = predep_entry['command']
                skip_cmd = False
                build_env = self._get_build_env()
                for env_var in predep_entry['env_checks']:
                    if build_env.get(env_var['key']) != env_var['value']:
                        self.logger.debug(
                            'Skipping %r predep command because %r does not match %r',
                            predep_cmd, env_var['key'], env_var['value']
                        )
                        skip_cmd = True
                        break
                if skip_cmd:
                    continue
            else:
                predep_cmd = predep_entry

            self.logger.debug('Running predepcmd: %r', predep_cmd)
            self.run_in_chroot(
                f'cd {self.package_source} && {predep_cmd}', 'Failed to execute predep command'
            )

        if not os.path.exists(os.path.join(self.package_source_with_chroot, 'debian/control')):
            raise CallError(
                f'Missing debian/control file for {self.name} in {self.package_source_with_chroot}'
            )

        self.run_in_chroot(f'cd {self.package_source} && mk-build-deps --build-dep', 'Failed mk-build-deps')
        self.run_in_chroot(f'cd {self.package_source} && apt install -y ./*.deb', 'Failed install build deps')

        # Truenas package is special
        if self.name == 'truenas':
            os.makedirs(os.path.join(self.package_source_with_chroot, 'data'))
            with open(os.path.join(self.package_source_with_chroot, 'data/manifest.json'), 'w') as f:
                f.write(json.dumps({
                    'buildtime': BUILD_TIME,
                    'train': get_truenas_train(),
                    'version': VERSION,
                }))
            os.makedirs(os.path.join(self.package_source_with_chroot, 'etc'), exist_ok=True)
            with open(os.path.join(self.package_source_with_chroot, 'etc/version'), 'w') as f:
                f.write(VERSION)

        for prebuild_command in self.prebuildcmd:
            self.logger.debug('Running prebuildcmd: %r', prebuild_command)
            self.run_in_chroot(
                f'cd {self.package_source} && {prebuild_command}', 'Failed to execute prebuildcmd command'
            )

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
    def debug_command(self):
        return f'chroot {self.dpkg_overlay} /bin/bash'

    @property
    def deflags(self):
        return [f'-j{self.jobs if self.jobs else os.cpu_count()}', '-us', '-uc', '-b']
