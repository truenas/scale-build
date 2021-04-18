import logging
import os

from .bootstrap.configure import make_bootstrapdir
from .image.bootstrap import (
    clean_mounts, setup_chroot_basedir, umount_chroot_basedir, umount_tmpfs_and_clean_chroot_dir
)
from .image.logger import get_logger
from .image.manifest import UPDATE_FILE
from .image.update import install_rootfs_packages, build_rootfs_image
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
    make_bootstrapdir('package', 'rootfs-bootstrap.log')

    logger.debug('Installing TrueNAS rootfs package [UPDATE] (%s/rootfs-package.log)', LOG_DIR)
    setup_chroot_basedir('package', get_logger('rootfs-bootstrap'))
    install_rootfs_packages()
    umount_chroot_basedir()

    logger.debug('Building TrueNAS rootfs image [UPDATE] (%s/rootfs-image.log)', LOG_DIR)
    build_rootfs_image()
    umount_tmpfs_and_clean_chroot_dir()

    logger.debug('Success! Update image created at: %s', UPDATE_FILE)
