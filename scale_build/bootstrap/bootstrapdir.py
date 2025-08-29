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
                '--keyring', os.path.join(BUILDER_DIR, 'keys/truenas.gpg'),
                manifest['debian_release'],
                self.chroot_basedir, get_apt_repos(check_custom=True)['url']
            ]
        )

    def setup_impl(self):
        if self.mirror_cache_intact:
            # Mirror cache is intact, we do not need to re-create the bootstrap directory
            self.logger.debug('Basechroot cache is intact and does not need to be changed')
            return

        apt_repos = get_apt_repos(check_custom=True)
        self.debootstrap_debian()
        self.setup_mounts()

        self.logger.debug('Updating apt preferences')
        apt_path = os.path.join(self.chroot_basedir, 'etc/apt')
        apt_sources_path = os.path.join(apt_path, 'sources.list')

        # Set up apt preferences
        with open(os.path.join(apt_path, 'preferences'), 'w') as f:
            f.write(get_apt_preferences())

        # Create keyrings directory in chroot
        keyring_dir = os.path.join(self.chroot_basedir, 'etc/apt/keyrings')
        os.makedirs(keyring_dir, exist_ok=True)

        # Copy TrueNAS key to chroot keyrings
        truenas_key = os.path.join(keyring_dir, 'truenas-archive.gpg')
        shutil.copy(os.path.join(BUILDER_DIR, 'keys/truenas.gpg'), truenas_key)

        # Build sources.list with signed-by directives
        # Main repository
        apt_sources = [
            'deb [signed-by=/etc/apt/keyrings/truenas-archive.gpg] '
            f'{apt_repos["url"]} {apt_repos["distribution"]} {apt_repos["components"]}'
        ]

        # Add additional repos
        for repo in apt_repos['additional']:
            self.logger.debug('Adding additional repo: %r', repo['url'])
            if repo.get('key'):
                # Copy specific key to chroot keyrings
                key_name = os.path.basename(repo['key'])
                shutil.copy(os.path.join(BUILDER_DIR, repo['key']), os.path.join(keyring_dir, key_name))
                # Add repo with its specific key
                apt_sources.append(
                    f'deb [signed-by=/etc/apt/keyrings/{key_name}] '
                    f'{repo["url"]} {repo["distribution"]} {repo["component"]}'
                )
            else:
                # Repo without specific key - uses TrueNAS key
                apt_sources.append(
                    f'deb [signed-by=/etc/apt/keyrings/truenas-archive.gpg] '
                    f'{repo["url"]} {repo["distribution"]} {repo["component"]}'
                )

        # Write initial sources.list
        with open(apt_sources_path, 'w') as f:
            f.write('\n'.join(apt_sources))

        # Update and upgrade
        run(['chroot', self.chroot_basedir, 'apt', 'update'])
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
                '--foreign', '--keyring', os.path.join(BUILDER_DIR, 'keys/truenas.gpg'),
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
