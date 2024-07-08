import glob
import logging
import os

from .bootstrap.bootstrapdir import CdromBootstrapDirectory
from .exceptions import CallError
from .image.bootstrap import clean_mounts, setup_chroot_basedir, umount_tmpfs_and_clean_chroot_dir
from .image.iso import install_iso_packages, make_iso_file
from .image.manifest import get_image_version, update_file_path, build_manifest
from .utils.logger import LoggingContext
from .utils.paths import LOG_DIR, RELEASE_DIR


logger = logging.getLogger(__name__)


def build_iso():
    try:
        return build_impl()
    finally:
        clean_mounts()


def build_impl():
    clean_mounts()
    for f in glob.glob(os.path.join(LOG_DIR, 'cdrom*')):
        os.unlink(f)

    version = build_manifest()  # Otherwise, it looks for a vendor in the filename. Update files never have a vendor.
    if not os.path.exists(update_file_path(version)):
        raise CallError(f'Missing rootfs image. Run \'make update\' first.{update_file_path()}')

    logger.debug('Bootstrapping CD chroot [ISO] (%s/cdrom-bootstrap.log)', LOG_DIR)
    with LoggingContext('cdrom-bootstrap', 'w'):
        cdrom_bootstrap_obj = CdromBootstrapDirectory()
        cdrom_bootstrap_obj.setup()
        setup_chroot_basedir(cdrom_bootstrap_obj)

    image_version = get_image_version()
    logger.debug('Image version identified as %r', image_version)
    logger.debug('Installing packages [ISO] (%s/cdrom-packages.log)', LOG_DIR)
    try:
        with LoggingContext('cdrom-packages', 'w'):
            install_iso_packages()

        logger.debug('Creating ISO file [ISO] (%s/cdrom-iso.log)', LOG_DIR)
        with LoggingContext('cdrom-iso', 'w'):
            make_iso_file()
    finally:
        umount_tmpfs_and_clean_chroot_dir()

    logger.info('Success! CD/USB: %s/TrueNAS-SCALE-%s.iso', RELEASE_DIR, image_version)
