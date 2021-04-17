import logging
import os

from scale_build.bootstrap.configure import make_bootstrapdir
from scale_build.image.bootstrap import (
    clean_mounts, setup_chroot_basedir, umount_chroot_basedir, umount_tmpfs_and_clean_chroot_dir
)
from scale_build.image.logger import get_logger
from scale_build.image.manifest import UPDATE_FILE
from scale_build.image.update import install_rootfs_packages, build_rootfs_image
from scale_build.utils.variables import CHROOT_BASEDIR, LOG_DIR, RELEASE_DIR


logger = logging.getLogger(__name__)


def build_update_image():
    os.makedirs(RELEASE_DIR, exist_ok=True)

    clean_mounts()
    os.makedirs(CHROOT_BASEDIR)
    logger.debug('Bootstrapping TrueNAS rootfs [UPDATE] (%s/rootfs-bootstrap.log)', LOG_DIR)
    make_bootstrapdir('update')

    logger.debug('Installing TrueNAS rootfs package [UPDATE] (%s/rootfs-package.log)', LOG_DIR)
    setup_chroot_basedir('update', get_logger('rootfs-bootstrap'))
    install_rootfs_packages()
    umount_chroot_basedir()

    logger.debug('Building TrueNAS rootfs image [UPDATE] (%s/rootfs-image.log)', LOG_DIR)
    build_rootfs_image()
    umount_tmpfs_and_clean_chroot_dir()

    logger.debug('Success! Update image created at: %s', UPDATE_FILE)
