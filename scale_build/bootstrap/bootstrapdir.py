import logging
import os
import shutil

from scale_build.clean import clean_packages
from scale_build.utils.manifest import get_manifest, get_apt_repos
from scale_build.utils.paths import BUILDER_DIR, CHROOT_BASEDIR, REFERENCE_FILES, REFERENCE_FILES_DIR
from scale_build.utils.run import run

from .cache import CacheMixin
from .hash import HashMixin
from .utils import get_apt_preferences


logger = logging.getLogger(__name__)


class BootstrapDir(CacheMixin, HashMixin):

    def __init__(self):
        self.logger = logger
        self.chroot_basedir = CHROOT_BASEDIR

    def setup(self):
        self.clean_setup()
        try:
            self.setup_impl()
        finally:
            self.clean_setup()

    def debootstrap_debian(self):
        manifest = get_manifest()
        run(
            ['debootstrap'] + self.deopts + [
                '--keyring', '/etc/apt/keyrings/truenas.gpg',
                manifest['debian_release'],
                self.chroot_basedir, get_apt_repos(check_custom=True)['url']
            ]
        )

    def setup_impl(self):
        if self.mirror_cache_intact:
            # Mirror cache is intact, we do not need to re-create the bootstrap directory
            self.logger.debug('Basechroot cache is intact and does not need to be changed')
            return

        self.add_trusted_apt_key()
        apt_repos = get_apt_repos(check_custom=True)
        self.debootstrap_debian()
        self.setup_mounts()

        self.logger.debug('Updating apt preferences')

        # Create keyrings directory for modern apt key management
        keyrings_dir = os.path.join(self.chroot_basedir, 'etc/apt/keyrings')
        os.makedirs(keyrings_dir, exist_ok=True)
        shutil.copy(os.path.join(BUILDER_DIR, 'keys/truenas.gpg'), os.path.join(keyrings_dir, 'truenas.gpg'))

        apt_path = os.path.join(self.chroot_basedir, 'etc/apt')
        apt_sources_path = os.path.join(apt_path, 'sources.list')
        # Set bullseye repo as the priority
        with open(os.path.join(apt_path, 'preferences'), 'w') as f:
            f.write(get_apt_preferences())

        run(['chroot', self.chroot_basedir, 'apt', 'update'])

        # Save the correct repo in sources.list
        apt_sources = [f'deb [signed-by=/etc/apt/keyrings/truenas.gpg] {apt_repos["url"]} {apt_repos["distribution"]} {apt_repos["components"]}']

        # Add additional repos
        for repo in apt_repos['additional']:
            self.logger.debug('Adding additional repo: %r', repo['url'])
            if repo.get('key'):
                # Use modern keyring approach instead of deprecated apt-key
                key_name = os.path.basename(repo['key']).replace('.gpg', '')
                shutil.copy(os.path.join(BUILDER_DIR, repo['key']), os.path.join(keyrings_dir, f'{key_name}.gpg'))
                apt_sources.append(f'deb [signed-by=/etc/apt/keyrings/{key_name}.gpg] {repo["url"]} {repo["distribution"]} {repo["component"]}')
            else:
                apt_sources.append(f'deb [signed-by=/etc/apt/keyrings/truenas.gpg] {repo["url"]} {repo["distribution"]} {repo["component"]}')

        with open(apt_sources_path, 'w') as f:
            f.write('\n'.join(apt_sources))

        self.logger.debug('apt sources')
        self.logger.debug('\n'.join(apt_sources))
        
        # Update apt
        run(['chroot', self.chroot_basedir, 'apt', 'update'])
        # Upgrade apt so that packages which were pulled in by debootstrap i.e libssl, they also
        # respect the apt preferences we have specified
        run(['chroot', self.chroot_basedir, 'apt', 'upgrade', '-y'])

        if self.extra_packages_to_install:
            run(['chroot', self.chroot_basedir, 'apt', 'install', '-y'] + self.extra_packages_to_install)

        installed_packages = self.get_packages()

        self.after_extra_packages_installation_steps()

        # Put our local package up at the top of the food chain
        apt_sources.insert(0, 'deb [trusted=yes] file:/packages /')
        with open(apt_sources_path, 'w') as f:
            f.write('\n'.join(apt_sources))

        self.clean_mounts()
        self.save_build_cache(installed_packages)

    def after_extra_packages_installation_steps(self):
        pass

    def add_trusted_apt_key(self):
        # Use modern keyring approach instead of deprecated apt-key
        keyring_path = '/etc/apt/keyrings/truenas.gpg'
        os.makedirs('/etc/apt/keyrings', exist_ok=True)
        shutil.copy(os.path.join(BUILDER_DIR, 'keys/truenas.gpg'), keyring_path)

    @property
    def extra_packages_to_install(self):
        raise NotImplementedError

    @property
    def deopts(self):
        raise NotImplementedError

    def setup_mounts(self):
        run(['mount', 'proc', os.path.join(self.chroot_basedir, 'proc'), '-t', 'proc'])
        run(['mount', 'sysfs', os.path.join(self.chroot_basedir, 'sys'), '-t', 'sysfs'])

    def clean_mounts(self):
        for command in (
            ['umount', '-f', os.path.join(self.chroot_basedir, 'proc')],
            ['umount', '-f', os.path.join(self.chroot_basedir, 'sys')],
        ):
            run(command, check=False, log=False)

    def clean_setup(self):
        self.clean_mounts()
        if os.path.exists(self.chroot_basedir):
            shutil.rmtree(self.chroot_basedir)


class RootfsBootstrapDir(BootstrapDir):

    @property
    def deopts(self):
        return []

    @property
    def extra_packages_to_install(self):
        return []

    @property
    def cache_filename(self):
        return 'basechroot-rootfs.squashfs'

    def debootstrap_debian(self):
        manifest = get_manifest()
        run(
            ['debootstrap'] + self.deopts + [
                '--foreign', '--keyring', '/etc/apt/keyrings/truenas.gpg',
                manifest['debian_release'],
                self.chroot_basedir, get_apt_repos(check_custom=True)['url']
            ]
        )
        for reference_file in REFERENCE_FILES:
            shutil.copyfile(
                os.path.join(REFERENCE_FILES_DIR, reference_file),
                os.path.join(self.chroot_basedir, reference_file)
            )
        run(['chroot', self.chroot_basedir, '/debootstrap/debootstrap', '--second-stage'])
        # For some reason debootstrap --second stage is removing ftp group, it does get added back by some
        # other package later on but currently it results in base cache not reflecting reference files
        # so we add it back here
        # FIXME: Figure out why debootstrap --second-stage is removing ftp group
        shutil.copyfile(os.path.join(REFERENCE_FILES_DIR, 'etc/group'), os.path.join(self.chroot_basedir, 'etc/group'))


class PackageBootstrapDir(RootfsBootstrapDir):

    @property
    def extra_packages_to_install(self):
        return ['build-essential', 'dh-make', 'devscripts', 'fakeroot']

    @property
    def cache_filename(self):
        return 'basechroot-package.squashfs'

    def after_extra_packages_installation_steps(self):
        if self.installed_packages_in_cache_changed:
            clean_packages()


class CdromBootstrapDirectory(BootstrapDir):

    @property
    def deopts(self):
        return ['--components=main,contrib,nonfree', '--variant=minbase', '--include=systemd-sysv,gnupg']

    @property
    def extra_packages_to_install(self):
        return []

    @property
    def cache_filename(self):
        return 'basechroot-cdrom.squashfs'
