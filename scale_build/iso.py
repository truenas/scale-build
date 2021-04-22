import glob
import logging
import os

from .bootstrap.bootstrapdir import CdromBootstrapDirectory
from .config import VERSION
from .exceptions import CallError
from .image.bootstrap import (
    clean_mounts, setup_chroot_basedir, umount_chroot_basedir, umount_tmpfs_and_clean_chroot_dir
)
from .image.iso import install_iso_packages, make_iso_file
from .image.manifest import UPDATE_FILE
from .utils.logger import get_logger
from .utils.paths import LOG_DIR, RELEASE_DIR


logger = logging.getLogger(__name__)


def build_iso():
    try:
        return build_impl()
    finally:
        clean_mounts()


def build_impl():
    iso_logger = get_logger('iso_logger', 'create_iso.log', 'w')
    logger.info('Building TrueNAS SCALE iso (%s/create_iso.log)', LOG_DIR)
    clean_mounts()
    for f in glob.glob(os.path.join(LOG_DIR, 'cdrom*')):
        os.unlink(f)

    if not os.path.exists(UPDATE_FILE):
        raise CallError('Missing rootfs image. Run \'make update\' first.')

    logger.debug('Bootstrapping CD chroot [ISO]')
    cdrom_bootstrap_obj = CdromBootstrapDirectory(iso_logger)
    with cdrom_bootstrap_obj as p:
        p.setup()

    setup_chroot_basedir(cdrom_bootstrap_obj, cdrom_bootstrap_obj.logger)

    logger.debug('Installing packages [ISO]')
    install_iso_packages(iso_logger)
    umount_chroot_basedir()

    logger.debug('Creating ISO file [ISO]')
    make_iso_file(iso_logger)

    umount_tmpfs_and_clean_chroot_dir()
    logger.info('Success! CD/USB: %s/TrueNAS-SCALE-%s.iso', RELEASE_DIR, VERSION)
