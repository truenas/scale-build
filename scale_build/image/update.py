import distutils.dir_util
import glob
import itertools
import logging
import os
import textwrap
import shutil
import stat

from scale_build.config import SIGNING_KEY, SIGNING_PASSWORD
from scale_build.utils.manifest import get_manifest
from scale_build.utils.run import run
from scale_build.utils.paths import CHROOT_BASEDIR, CUSTOM_TN, RELEASE_DIR, UPDATE_DIR

from .bootstrap import umount_chroot_basedir
from .manifest import build_manifest, build_release_manifest, update_file_path, update_file_checksum_path
from .utils import run_in_chroot


logger = logging.getLogger(__name__)


def build_rootfs_image():
    for f in glob.glob(os.path.join('./tmp/release', '*.update*')):
        os.unlink(f)

    if os.path.exists(UPDATE_DIR):
        shutil.rmtree(UPDATE_DIR)
    os.makedirs(RELEASE_DIR, exist_ok=True)
    os.makedirs(UPDATE_DIR)

    # We are going to build a nested squashfs image.

    # Why nested? So that during update we can easily RO mount the outer image
    # to read a MANIFEST and verify signatures of the real rootfs inner image
    #
    # This allows us to verify without ever extracting anything to disk

    # Create the inner image
    run(['mksquashfs', CHROOT_BASEDIR, os.path.join(UPDATE_DIR, 'rootfs.squashfs'), '-comp', 'xz'])
    # Build any MANIFEST information
    version = build_manifest()

    # Sign the image (if enabled)
    if SIGNING_KEY and SIGNING_PASSWORD:
        sign_manifest(SIGNING_KEY, SIGNING_PASSWORD)

    # Create the outer image now
    update_file = update_file_path(version)
    run(['mksquashfs', UPDATE_DIR, update_file, '-noD'])
    update_file_checksum = run(['sha256sum', update_file_path(version)], log=False).stdout.strip().split()[0]
    with open(update_file_checksum_path(version), 'w') as f:
        f.write(update_file_checksum)

    build_release_manifest(update_file, update_file_checksum)


def sign_manifest(signing_key, signing_pass):
    run(
        f'echo "{signing_pass}" | gpg -ab --batch --yes --no-use-agent --pinentry-mode loopback --passphrase-fd 0 '
        f'--default-key {signing_key} --output {os.path.join(UPDATE_DIR, "MANIFEST.sig")} '
        f'--sign {os.path.join(UPDATE_DIR, "MANIFEST")}', shell=True,
        exception_msg='Failed gpg signing with SIGNING_PASSWORD', log=False,
    )


def install_rootfs_packages():
    try:
        install_rootfs_packages_impl()
    finally:
        umount_chroot_basedir()


def install_rootfs_packages_impl():
    os.makedirs(os.path.join(CHROOT_BASEDIR, 'etc/dpkg/dpkg.cfg.d'), exist_ok=True)
    with open(os.path.join(CHROOT_BASEDIR, 'etc/dpkg/dpkg.cfg.d/force-unsafe-io'), 'w') as f:
        f.write('force-unsafe-io')

    run_in_chroot(['apt', 'update'])

    manifest = get_manifest()
    for package_entry in itertools.chain(manifest['base-packages'], manifest['additional-packages']):
        log_message = f'Installing {package_entry}'
        install_cmd = ['apt', 'install', '-V', '-y', package_entry['name']]
        if not package_entry['install_recommends']:
            install_cmd.insert(3, '--no-install-recommends')
            log_message += ' (no recommends)'

        logger.debug(log_message)
        run_in_chroot(install_cmd)

    # Do any custom rootfs setup
    custom_rootfs_setup()

    # Do any pruning of rootfs
    clean_rootfs()

    with open(os.path.join(CHROOT_BASEDIR, 'etc/apt/sources.list'), 'w') as f:
        f.write('\n'.join(get_apt_sources()))

    post_rootfs_setup()


def get_apt_sources():
    apt_repos = get_manifest()['apt-repos']
    apt_sources = [f'deb {apt_repos["url"]} {apt_repos["distribution"]} {apt_repos["components"]}']
    for repo in apt_repos['additional']:
        apt_sources.append(f'deb {repo["url"]} {repo["distribution"]} {repo["component"]}')
    return apt_sources


def should_rem_execute_bit(binary):
    if binary.is_file() and any((binary.name in ('dpkg', 'apt'), binary.name.startswith('apt-'))):
        # disable apt related binaries so that users can avoid footshooting themselves
        # also disable dpkg since you can do the same type of footshooting
        return True

    return False


def post_rootfs_setup():
    no_executable_flag = ~stat.S_IXUSR & ~stat.S_IXGRP & ~stat.S_IXOTH
    with os.scandir(os.path.join(CHROOT_BASEDIR, 'usr/bin')) as binaries:
        for binary in filter(lambda x: should_rem_execute_bit(x), binaries):
            os.chmod(binary.path, stat.S_IMODE(binary.stat(follow_symlinks=False).st_mode) & no_executable_flag)

    # Copy over custom tn setup
    distutils.dir_util._path_created = {}
    distutils.dir_util.copy_tree(CUSTOM_TN, CHROOT_BASEDIR, preserve_symlinks=True)

    run_in_chroot(['locale-gen'])
    run(['mkdir', '-p', os.path.join(CHROOT_BASEDIR, 'var/log/apt-cacher-ng')])
    run(['chown', '-R', 'apt-cacher-ng:apt-cacher-ng', os.path.join(CHROOT_BASEDIR, 'var/log/apt-cacher-ng')])
    run([
        'chown', '-R', 'root:root', os.path.join(CHROOT_BASEDIR, 'root/.zshrc'),
        os.path.join(CHROOT_BASEDIR, 'root/.oh-my-zsh'), os.path.join(CHROOT_BASEDIR, 'root/.zsh_history')
    ])


def custom_rootfs_setup():
    # Any kind of custom mangling of the built rootfs image can exist here

    os.makedirs(os.path.join(CHROOT_BASEDIR, 'boot/grub'), exist_ok=True)

    # If we are upgrading a FreeBSD installation on USB, there won't be no opportunity to run truenas-initrd.py
    # So we have to assume worse.
    # If rootfs image is used in a Linux installation, initrd will be re-generated with proper configuration,
    # so initrd we make now will only be used on the first boot after FreeBSD upgrade.
    with open(os.path.join(CHROOT_BASEDIR, 'etc/default/zfs'), 'a') as f:
        f.write('ZFS_INITRD_POST_MODPROBE_SLEEP=15')

    run_in_chroot(['update-initramfs', '-k', 'all', '-u'])

    # Generate native systemd unit files for SysV services that lack ones to prevent systemd-sysv-generator warnings
    tmp_systemd = os.path.join(CHROOT_BASEDIR, 'tmp/systemd')
    os.makedirs(tmp_systemd)
    run_in_chroot([
        '/usr/lib/systemd/system-generators/systemd-sysv-generator', '/tmp/systemd', '/tmp/systemd', '/tmp/systemd'
    ])
    for unit_file in filter(lambda f: f.endswith('.service'), os.listdir(tmp_systemd)):
        with open(os.path.join(tmp_systemd, unit_file), 'a') as f:
            f.write(textwrap.dedent('''\
                [Install]
                WantedBy=multi-user.target
            '''))

    for f in os.listdir(os.path.join(tmp_systemd, 'multi-user.target.wants')):
        file_path = os.path.join(tmp_systemd, f)
        if os.path.isfile(file_path) and not os.path.islink(file_path):
            os.unlink(file_path)

    run_in_chroot(['rsync', '-av', '/tmp/systemd/', '/usr/lib/systemd/system/'])
    shutil.rmtree(tmp_systemd)
    run_in_chroot(['depmod'], check=False)


def clean_rootfs():
    to_remove = get_manifest()['base-prune']
    run_in_chroot(['apt', 'remove', '-y'] + to_remove)

    # Remove any temp build depends
    run_in_chroot(['apt', 'autoremove', '-y'])

    # OpenSSH generates its server keys on installation, we don't want all SCALE builds
    # of the same version to have the same keys. middleware will generate these keys on
    # specific installation first boot.
    ssh_keys = os.path.join(CHROOT_BASEDIR, 'etc/ssh')
    for f in os.listdir(ssh_keys):
        if f.startswith('ssh_host_') and (f.endswith('_key') or f.endswith('_key.pub') or f.endswith('key-cert.pub')):
            os.unlink(os.path.join(ssh_keys, f))

    for path in (
        os.path.join(CHROOT_BASEDIR, 'usr/share/doc'),
        os.path.join(CHROOT_BASEDIR, 'var/cache/apt'),
        os.path.join(CHROOT_BASEDIR, 'var/lib/apt/lists'),
    ):
        shutil.rmtree(path)
        os.makedirs(path, exist_ok=True)
