import logging
import os

from .bootstrap.bootstrapdir import PackageBootstrapDirectory
from .image.bootstrap import (
    clean_mounts, setup_chroot_basedir, umount_chroot_basedir, umount_tmpfs_and_clean_chroot_dir
)
from .image.manifest import UPDATE_FILE
from .image.update import install_rootfs_packages, build_rootfs_image
from .utils.logger import get_logger
from .utils.paths import CHROOT_BASEDIR, LOG_DIR, RELEASE_DIR


logger = logging.getLogger(__name__)


def build_update_image():
    try:
        return build_update_image_impl()
    finally:
        clean_mounts()


def build_update_image_impl():
    os.makedirs(RELEASE_DIR, exist_ok=True)

    update_image_logger = get_logger('update_image', 'update_image.log', 'w')
    logger.info('Building update image (%s/update_image.log)', LOG_DIR)
    clean_mounts()
    os.makedirs(CHROOT_BASEDIR)
    logger.debug('Bootstrapping TrueNAS rootfs [UPDATE]')

    package_bootstrap_obj = PackageBootstrapDirectory(update_image_logger)
    with package_bootstrap_obj as p:
        p.setup()

    logger.debug('Installing TrueNAS rootfs package [UPDATE]')
    setup_chroot_basedir(package_bootstrap_obj, package_bootstrap_obj.logger)
    install_rootfs_packages(update_image_logger)
    umount_chroot_basedir()

    logger.debug('Building TrueNAS rootfs image [UPDATE]')
    build_rootfs_image(update_image_logger)
    umount_tmpfs_and_clean_chroot_dir()

    logger.info('Success! Update image created at: %s', UPDATE_FILE)
