import logging
import os

from .bootstrap.bootstrapdir import RootfsBootstrapDir
from .exceptions import CallError
from .image.bootstrap import (
    clean_mounts, setup_chroot_basedir, umount_chroot_basedir, umount_tmpfs_and_clean_chroot_dir
)
from .image.manifest import update_file_path
from .image.update import install_rootfs_packages, build_rootfs_image
from .utils.logger import LoggingContext
from .utils.paths import CHROOT_BASEDIR, LOG_DIR, REFERENCE_FILES, REFERENCE_FILES_DIR, RELEASE_DIR
from .utils.reference_files import compare_reference_files


logger = logging.getLogger(__name__)


def build_update_image():
    try:
        return build_update_image_impl()
    finally:
        clean_mounts()


def build_update_image_impl():
    os.makedirs(RELEASE_DIR, exist_ok=True)
    clean_mounts()
    os.makedirs(CHROOT_BASEDIR)
    logger.debug('Bootstrapping TrueNAS rootfs [UPDATE] (%s/rootfs-bootstrap.log)', LOG_DIR)

    with LoggingContext('rootfs-bootstrap', 'w'):
        package_bootstrap_obj = RootfsBootstrapDir()
        package_bootstrap_obj.setup()

    logger.debug('Installing TrueNAS rootfs package [UPDATE] (%s/rootfs-packages.log)', LOG_DIR)
    try:
        with LoggingContext('rootfs-packages', 'w'):
            setup_chroot_basedir(package_bootstrap_obj)

            # These files will be overwritten, so we should make sure that new build does not have any entities that
            # are not in our reference files.
            for reference_file, diff in compare_reference_files(cut_nonexistent_user_group_membership=True):
                if any(line.startswith('+') for line in diff):
                    raise CallError(
                        f'Reference file {reference_file!r} has new lines in newly installed system.\n'
                        f'Full diff below:\n' +
                        ''.join(diff) + '\n' +
                        'Please update corresponding file in `conf/reference-files/` directory of scale-build '
                        'repository.'
                    )

            # built-in users and groups are typically created by debian packages postinst scripts.
            # As newly created user/group uid/gid uses autoincrement counter and debian packages install order is
            # undetermined, different builds are not guaranteed to have the same uid/gids. We overcome this issue by
            # persisting `group` and `passwd` files between builds.
            for reference_file in REFERENCE_FILES:
                with open(os.path.join(CHROOT_BASEDIR, reference_file), 'w') as dst:
                    with open(os.path.join(REFERENCE_FILES_DIR, reference_file)) as src:
                        dst.write(src.read())

            install_rootfs_packages()

            for reference_file, diff in compare_reference_files():
                if diff:
                    raise CallError(
                        f'Reference file {reference_file!r} changed.\n'
                        f'Full diff below:\n' +
                        ''.join(diff) + '\n' +
                        'Please update corresponding file in `conf/reference-files/` directory of scale-build '
                        'repository.'
                    )

        logger.debug('Building TrueNAS rootfs image [UPDATE] (%s/rootfs-image.log)', LOG_DIR)
        with LoggingContext('rootfs-image', 'w'):
            build_rootfs_image()
    finally:
        umount_chroot_basedir()
        umount_tmpfs_and_clean_chroot_dir()

    logger.info('Success! Update image created at: %s', update_file_path())
