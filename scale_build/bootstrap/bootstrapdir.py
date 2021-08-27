import logging
import os
import shutil

from scale_build.clean import clean_packages
from scale_build.utils.manifest import get_manifest
from scale_build.utils.paths import BUILDER_DIR, CHROOT_BASEDIR
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

    def setup_impl(self):
        if self.mirror_cache_intact:
            # Mirror cache is intact, we do not need to re-create the bootstrap directory
            self.logger.debug('Basechroot cache is intact and does not need to be changed')
            return

        self.add_trusted_apt_key()
        manifest = get_manifest()
        apt_repos = manifest['apt-repos']
        run(
            ['debootstrap'] + self.deopts + [
                '--keyring', '/etc/apt/trusted.gpg.d/debian-archive-truenas-automatic.gpg', manifest['debian_release'],
                self.chroot_basedir, apt_repos['url']
            ]
        )
        self.setup_mounts()

        self.logger.debug('Updating apt preferences')
        apt_path = os.path.join(self.chroot_basedir, 'etc/apt')
        apt_sources_path = os.path.join(apt_path, 'sources.list')
        # Set bullseye repo as the priority
        with open(os.path.join(apt_path, 'preferences'), 'w') as f:
            f.write(get_apt_preferences())

        self.logger.debug('Adding debian-security to sources')
        deb_security = '\n'.join([
            'deb http://deb.debian.org/debian-security/ bullseye-security main',
            'deb-src http://deb.debian.org/debian-security/ bullseye-security main',
        ])
        with open(apt_sources_path, 'a+') as f:
            f.write(f'\n{deb_security}\n')
        run(['chroot', self.chroot_basedir, 'apt', 'update'])

        if self.extra_packages_to_install:
            run(['chroot', self.chroot_basedir, 'apt', 'install', '-y'] + self.extra_packages_to_install)

        installed_packages = self.get_packages()

        self.after_extra_packages_installation_steps()

        # Save the correct repo in sources.list
        apt_sources = [f'deb {apt_repos["url"]} {apt_repos["distribution"]} {apt_repos["components"]}']

        # Add additional repos
        for repo in apt_repos['additional']:
            self.logger.debug('Adding additional repo: %r', repo['url'])
            shutil.copy(os.path.join(BUILDER_DIR, repo['key']), os.path.join(self.chroot_basedir, 'apt.key'))
            run(['chroot', self.chroot_basedir, 'apt-key', 'add', '/apt.key'])
            os.unlink(os.path.join(self.chroot_basedir, 'apt.key'))
            apt_sources.append(f'deb {repo["url"]} {repo["distribution"]} {repo["component"]}')

        with open(apt_sources_path, 'w') as f:
            f.write('\n'.join(apt_sources))

        # Update apt
        run(['chroot', self.chroot_basedir, 'apt', 'update'])

        # Put our local package up at the top of the food chain
        apt_sources.insert(0, 'deb [trusted=yes] file:/packages /')
        with open(apt_sources_path, 'w') as f:
            f.write('\n'.join(apt_sources))

        self.clean_mounts()
        self.save_build_cache(installed_packages)

    def after_extra_packages_installation_steps(self):
        pass

    def add_trusted_apt_key(self):
        run([
            'apt-key', '--keyring', '/etc/apt/trusted.gpg.d/debian-archive-truenas-automatic.gpg', 'add',
            os.path.join(BUILDER_DIR, 'keys/truenas.gpg')
        ])

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


class PackageBootstrapDirectory(BootstrapDir):

    @property
    def deopts(self):
        return []

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
