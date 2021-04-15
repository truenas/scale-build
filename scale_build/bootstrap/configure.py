import logging
import os
import shutil

from scale_build.clean import clean
from scale_build.exceptions import CallError

from .cache import check_basechroot_changed, create_basehash, save_build_cache, validate_basecache
from .utils import APT_PREFERENCES, BUILDER_DIR, CACHE_DIR, CHROOT_BASEDIR, get_manifest, has_low_ram, run, TMPFS


logger = logging.getLogger(__name__)


def make_bootstrapdir(bootstrapdir_type, log_handle):
    assert bootstrapdir_type in ('cd', 'update', 'package')
    clean()
    try:
        _make_bootstrapdir_impl(bootstrapdir_type, log_handle)
    except Exception:
        clean()
        raise


def _make_bootstrapdir_impl(bootstrapdir_type, log_handle):
    run_args = {'stdout': log_handle, 'stderr': log_handle}
    if bootstrapdir_type == 'cd':
        deopts = '--components=main,contrib,nonfree --variant=minbase --include=systemd-sysv,gnupg'
        cache_name = 'cdrom'
    else:
        deopts = ''
        cache_name = 'package'

    if not has_low_ram() or bootstrapdir_type == 'update':
        run(['mount', '-t', 'tmpfs', '-o', 'size=12G', 'tmpfs', TMPFS], **run_args)

    # Check if we should invalidate the base cache
    if validate_basecache(cache_name, log_handle):
        return

    run([
        'apt-key', '--keyring', '/etc/apt/trusted.gpg.d/debian-archive-truenas-automatic.gpg', 'add',
        os.path.join(BUILDER_DIR, 'keys/truenas.gpg')
    ], exception=CallError, exception_msg='Failed adding truenas.gpg apt-key', **run_args)

    apt_repos = get_manifest()['apt-repos']
    run(list(filter(
        bool, [
            'debootstrap', deopts, '--keyring', '/etc/apt/trusted.gpg.d/debian-archive-truenas-automatic.gpg',
            'bullseye', CHROOT_BASEDIR, apt_repos['url']
        ]
    )), exception=CallError, exception_msg='Failed debootstrap', **run_args)

    create_basehash(cache_name)
    os.makedirs(os.path.join(CACHE_DIR, 'apt'), exist_ok=True)

    run(['mount', 'proc', os.path.join(CHROOT_BASEDIR, 'proc'), '-t', 'proc'], **run_args)
    run(['mount', 'sysfs', os.path.join(CHROOT_BASEDIR, 'sys'), '-t', 'sysfs'], **run_args)
    run([
        'mount', '--bind', os.path.join(CACHE_DIR, 'apt'), os.path.join(CHROOT_BASEDIR, 'var/cache/apt')
    ], exception=CallError, exception_msg='Failed mount --bind /var/cache/apt', **run_args
    )

    if bootstrapdir_type != 'cd':
        # Add extra packages for builds
        run([
            'chroot', CHROOT_BASEDIR, 'apt', 'install', '-y', 'build-essential', 'dh-make', 'devscripts', 'fakeroot'
        ], exception=CallError, exception_msg='Failed chroot setup', **run_args)

    # Save the correct repo in sources.list
    apt_path = os.path.join(CHROOT_BASEDIR, 'etc/apt')
    apt_sources_path = os.path.join(apt_path, 'sources.list')
    apt_sources = []
    with open(apt_sources_path, 'w') as f:
        apt_sources.append(f'deb {apt_repos["url"]} {apt_repos["distribution"]} {apt_repos["components"]}')

    # Set bullseye repo as the priority
    # TODO - This should be moved to manifest later
    with open(os.path.join(apt_path, 'preferences'), 'w') as f:
        f.write(APT_PREFERENCES)

    # Add additional repos
    for repo in apt_repos['additional']:
        log_handle.write(f'Adding additional repo: {repo["url"]}\n')
        shutil.copy(os.path.join(BUILDER_DIR, repo['key']), os.path.join(CHROOT_BASEDIR, 'apt.key'))
        run([
            'chroot', CHROOT_BASEDIR, 'apt-key', 'add', '/apt.key'
        ], exception=CallError, exception_msg='Failed adding apt-key', **run_args)
        os.unlink(os.path.join(CHROOT_BASEDIR, 'apt.key'))
        apt_sources.append(f'deb {repo["url"]} {repo["distribution"]} {repo["component"]}')

    # If not building a cd environment
    if bootstrapdir_type != 'cd':
        check_basechroot_changed(log_handle)

    # Update apt
    run(['chroot', CHROOT_BASEDIR, 'apt', 'update'], exception=CallError, exception_msg='Failed apt update', **run_args)

    # Put our local package up at the top of the food chain
    apt_sources.insert(0, 'deb [trusted=yes] file:/packages /')
    with open(apt_sources_path, 'w') as f:
        f.write('\n'.join(apt_sources))

    run(['umount', '-f', os.path.join(CHROOT_BASEDIR, 'var/cache/apt')], **run_args)
    run(['umount', '-f', os.path.join(CHROOT_BASEDIR, 'proc')], **run_args)
    run(['umount', '-f', os.path.join(CHROOT_BASEDIR, 'sys')], **run_args)

    save_build_cache(cache_name, log_handle)
