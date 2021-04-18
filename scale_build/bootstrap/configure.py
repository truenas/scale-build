import os
import shutil

from scale_build.exceptions import CallError

from .cache import check_basechroot_changed, create_basehash, save_build_cache, validate_basecache
from .cleanup import remove_boostrap_directory
from .logger import get_logger
from .utils import BUILDER_DIR, CACHE_DIR, CHROOT_BASEDIR, get_apt_preferences, get_manifest, run


def make_bootstrapdir(bootstrapdir_type, logger_file=None):
    assert bootstrapdir_type in ('cdrom', 'package')
    remove_boostrap_directory()
    try:
        _make_bootstrapdir_impl(bootstrapdir_type, logger_file)
    finally:
        remove_boostrap_directory()


def _make_bootstrapdir_impl(bootstrapdir_type, logger_file=None):
    logger = get_logger(bootstrapdir_type, 'w', logger_file)
    run_args = {'logger': logger}
    if bootstrapdir_type == 'cdrom':
        deopts = ['--components=main,contrib,nonfree', '--variant=minbase', '--include=systemd-sysv,gnupg']
    else:
        deopts = []

    # Check if we should invalidate the base cache
    if validate_basecache(bootstrapdir_type):
        logger.debug('Basechroot cache is intact and does not need to be changed')
        return

    run([
        'apt-key', '--keyring', '/etc/apt/trusted.gpg.d/debian-archive-truenas-automatic.gpg', 'add',
        os.path.join(BUILDER_DIR, 'keys/truenas.gpg')
    ], exception=CallError, exception_msg='Failed adding truenas.gpg apt-key', **run_args)

    apt_repos = get_manifest()['apt-repos']
    run(
        ['debootstrap'] + deopts + [
            '--keyring', '/etc/apt/trusted.gpg.d/debian-archive-truenas-automatic.gpg', 'bullseye',
            CHROOT_BASEDIR, apt_repos['url']
        ], exception=CallError, exception_msg='Failed debootstrap', **run_args
    )

    create_basehash(bootstrapdir_type)
    os.makedirs(os.path.join(CACHE_DIR, 'apt'), exist_ok=True)

    run(['mount', 'proc', os.path.join(CHROOT_BASEDIR, 'proc'), '-t', 'proc'], **run_args)
    run(['mount', 'sysfs', os.path.join(CHROOT_BASEDIR, 'sys'), '-t', 'sysfs'], **run_args)
    run([
        'mount', '--bind', os.path.join(CACHE_DIR, 'apt'), os.path.join(CHROOT_BASEDIR, 'var/cache/apt')
    ], exception=CallError, exception_msg='Failed mount --bind /var/cache/apt', **run_args
    )

    # TODO: Remove me please
    logger.debug('Setting up apt-cacher')
    os.makedirs(os.path.join(CHROOT_BASEDIR, 'etc/apt/apt.conf.d'), exist_ok=True)
    with open(os.path.join(CHROOT_BASEDIR, 'etc/apt/apt.conf.d/02proxy'), 'w') as f:
        f.write('Acquire::http::Proxy "http://192.168.0.3:3142";\n')

    if bootstrapdir_type == 'package':
        # Add extra packages for builds
        run([
            'chroot', CHROOT_BASEDIR, 'apt', 'install', '-y', 'build-essential', 'dh-make', 'devscripts', 'fakeroot'
        ], exception=CallError, exception_msg='Failed chroot setup', **run_args)

    # Save the correct repo in sources.list
    apt_path = os.path.join(CHROOT_BASEDIR, 'etc/apt')
    apt_sources_path = os.path.join(apt_path, 'sources.list')
    apt_sources = [f'deb {apt_repos["url"]} {apt_repos["distribution"]} {apt_repos["components"]}']

    # Set bullseye repo as the priority
    # TODO - This should be moved to manifest later
    with open(os.path.join(apt_path, 'preferences'), 'w') as f:
        f.write(get_apt_preferences())

    # Add additional repos
    for repo in apt_repos['additional']:
        logger.debug('Adding additional repo: %r', repo['url'])
        shutil.copy(os.path.join(BUILDER_DIR, repo['key']), os.path.join(CHROOT_BASEDIR, 'apt.key'))
        run([
            'chroot', CHROOT_BASEDIR, 'apt-key', 'add', '/apt.key'
        ], exception=CallError, exception_msg='Failed adding apt-key', **run_args)
        os.unlink(os.path.join(CHROOT_BASEDIR, 'apt.key'))
        apt_sources.append(f'deb {repo["url"]} {repo["distribution"]} {repo["component"]}')

    # If not building a cd environment
    if bootstrapdir_type == 'package':
        check_basechroot_changed()

    with open(apt_sources_path, 'w') as f:
        f.write('\n'.join(apt_sources))

    # Update apt
    run(['chroot', CHROOT_BASEDIR, 'apt', 'update'], exception=CallError, exception_msg='Failed apt update', **run_args)

    # Put our local package up at the top of the food chain
    apt_sources.insert(0, 'deb [trusted=yes] file:/packages /')
    with open(apt_sources_path, 'w') as f:
        f.write('\n'.join(apt_sources))

    run(['umount', '-f', os.path.join(CHROOT_BASEDIR, 'var/cache/apt')], **run_args)
    run(['umount', '-f', os.path.join(CHROOT_BASEDIR, 'proc')], **run_args)
    run(['umount', '-f', os.path.join(CHROOT_BASEDIR, 'sys')], **run_args)

    save_build_cache(bootstrapdir_type)
