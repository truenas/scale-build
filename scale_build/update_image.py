import logging
import os
import shutil

from scale_build.bootstrap.configure import make_bootstrapdir
from scale_build.image.bootstrap import setup_chroot_basedir, umount_chroot_basedir
from scale_build.image.logger import get_logger
from scale_build.image.manifest import UPDATE_FILE
from scale_build.image.update import install_rootfs_packages, build_rootfs_image
from scale_build.utils.variables import CHROOT_BASEDIR, LOG_DIR, RELEASE_DIR


logger = logging.getLogger(__name__)


def build_update_image():
    os.makedirs(RELEASE_DIR, exist_ok=True)

    umount_chroot_basedir()
    shutil.rmtree(CHROOT_BASEDIR, ignore_errors=True)
    os.makedirs(CHROOT_BASEDIR)
    logger.debug('Bootstrapping TrueNAS rootfs [UPDATE] (%s/rootfs-bootstrap.log)', LOG_DIR)
    make_bootstrapdir('update')

    logger.debug('Installing TrueNAS rootfs package [UPDATE] (%s/rootfs-package.log)', LOG_DIR)
    setup_chroot_basedir('update', get_logger('rootfs-bootstrap'))
    install_rootfs_packages()
    umount_chroot_basedir()

    logger.debug('Building TrueNAS rootfs image [UPDATE] (%s/rootfs-image.log)', LOG_DIR)
    build_rootfs_image()
    shutil.rmtree(CHROOT_BASEDIR, ignore_errors=True)

    logger.debug('Success! Update image created at: %s', UPDATE_FILE)
