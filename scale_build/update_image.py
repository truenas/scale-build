import logging
import os

from .bootstrap.bootstrapdir import PackageBootstrapDirectory
from .image.bootstrap import clean_mounts, setup_chroot_basedir, umount_tmpfs_and_clean_chroot_dir
from .image.manifest import UPDATE_FILE
from .image.update import install_rootfs_packages, build_rootfs_image
from .utils.logger import LoggingContext
from .utils.paths import CHROOT_BASEDIR, LOG_DIR, RELEASE_DIR


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
        package_bootstrap_obj = PackageBootstrapDirectory()
        package_bootstrap_obj.setup()

    logger.debug('Installing TrueNAS rootfs package [UPDATE] (%s/rootfs-packages.log)', LOG_DIR)
    try:
        with LoggingContext('rootfs-packages', 'w'):
            setup_chroot_basedir(package_bootstrap_obj)
            install_rootfs_packages()

        logger.debug('Building TrueNAS rootfs image [UPDATE] (%s/rootfs-image.log)', LOG_DIR)
        with LoggingContext('rootfs-image', 'w'):
            build_rootfs_image()
    finally:
        umount_tmpfs_and_clean_chroot_dir()

    logger.info('Success! Update image created at: %s', UPDATE_FILE)
