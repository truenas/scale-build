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
                '--keyring', '/etc/apt/trusted.gpg.d/debian-archive-truenas-automatic.gpg',
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
        apt_path = os.path.join(self.chroot_basedir, 'etc/apt')
        apt_sources_path = os.path.join(apt_path, 'sources.list')
        # Set bullseye repo as the priority
        with open(os.path.join(apt_path, 'preferences'), 'w') as f:
            f.write(get_apt_preferences())

        run(['chroot', self.chroot_basedir, 'apt', 'update'])
        # We need to have gnupg installed before adding apt mirrors because apt-key needs it
        run(['chroot', self.chroot_basedir, 'apt', 'install', '-y', 'gnupg'])

        self.logger.debug('Setting up apt-cacher')
        os.makedirs(os.path.join(self.chroot_basedir, 'etc/apt/apt.conf.d'), exist_ok=True)
        with open(os.path.join(self.chroot_basedir, 'etc/apt/apt.conf.d/02proxy'), 'w') as f:
            f.write('Acquire::http::Proxy "http://192.168.0.3:3142";\n')

        self.logger.debug('Adding ssh key to authorized file')
        os.makedirs(os.path.join(self.chroot_basedir, 'root/.ssh'), exist_ok=True)
        with open(os.path.join(self.chroot_basedir, 'root/.ssh/authorized_keys'), 'a+') as f:
            f.write('''ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQClkokvZ7Rq75GcOvP65xlubdkMY3Ob81cNrsVg7dDJ/xJ5dmWDvEIpBelTskKDUyBrpcteq6RkmAomNvRe0M4I80syELRtlJULtfKBuA5bM0DXAd1+3kjVAi/VqH+7fNKxbMMZN1u3MaCbW31S3Hk3WMIYbZnkgfXmXauPfA6bWf6pKmpAVIezfUqbEaQRktbDzPb4G0pZmZs8N4hf8dxWnaRn0BRhRx/EUpCtgE+A0ESy1ZTN7SpsSlTYeqUx+PphSURnY+oNmwLR1ZsKqRiv69rmKBUZBOUH0vGvX6EFbcWPp/wJjsGeMrMI1hAyUuDoHEMZDPZgnycuS1HtfDTd waqar@Waqar's-mbp\n''')
            f.write('''ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCrzF/xK6YVa0EEa9NFfJIHQyUq2VWSakHdQmvHyKiMxRm5MQ+2I/XdBw+QRAPEUThcCCC/1+Xb4YBHKWF1yIKMlvim2r1cuJgN+LlIJro9H/DjLcSCqZwp8WoDte7zEIpI36u2YNErH/bXDV3pMW/etXtL4KtLLUcHY8FjNzDXlsQZjVNiKMQk9c9tX8LmegOyLqa4j3Eyk30EqqZrKSthVs3NOuX+yVWeYmYW7srjnbMP+Iz3qkP0b3bTlomtQTZNME4bXmRti00u/bhq7YWR+G/2IcWHpVoAI3mUU2cR8u+WpNrYHJ1ocLogOKeVqYcxjr4zx96ADrC+kMwQwdPzF3fNdV1j99O7b+rmuRyBTTzWRepLuqlQAecY8+XB+OGpetk1VNuNocUzdwQZe1kPrmMsX5Kb29PjaA9V+lhpOdh0qce3YfhxrGh2+rNbpukIk6gZ6nU8TxfCO/j8mBFd4rF9xS+cYMuB/HUcpiAsea0PNXPnm9hUGH+i3SAbXM0= root@truenas.local\n''')

        # Save the correct repo in sources.list
        apt_sources = [f'deb {apt_repos["url"]} {apt_repos["distribution"]} {apt_repos["components"]}']

        # Add additional repos
        for repo in apt_repos['additional']:
            self.logger.debug('Adding additional repo: %r', repo['url'])
            if repo.get('key'):
                shutil.copy(os.path.join(BUILDER_DIR, repo['key']), os.path.join(self.chroot_basedir, 'apt.key'))
                run(['chroot', self.chroot_basedir, 'apt-key', 'add', '/apt.key'])
                os.unlink(os.path.join(self.chroot_basedir, 'apt.key'))

            apt_sources.append(f'deb {repo["url"]} {repo["distribution"]} {repo["component"]}')

        with open(apt_sources_path, 'w') as f:
            f.write('\n'.join(apt_sources))

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
                '--foreign', '--keyring', '/etc/apt/trusted.gpg.d/debian-archive-truenas-automatic.gpg',
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
