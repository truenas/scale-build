import os
import logging
import shutil

from .exceptions import CallError, MissingPackagesException
from .utils.manifest import validate_manifest


logger = logging.getLogger(__name__)

WANTED_PACKAGES = {
    'make',
    'debootstrap',
    'git',
    'mksquashfs',
    'rsync',
    'unzip',
}


def retrieve_missing_packages():
    return {pkg for pkg in WANTED_PACKAGES if not shutil.which(pkg)}


def validate_system_state():
    if os.geteuid() != 0:
        raise CallError('Must be run as root (or using sudo)!')

    missing_packages = retrieve_missing_packages()
    if missing_packages:
        raise MissingPackagesException(missing_packages)


def validate(system_state_flag=True, manifest_flag=True):
    if system_state_flag:
        validate_system_state()
        logger.debug('System state Validated')
    if manifest_flag:
        validate_manifest()
        logger.debug('Manifest Validated')
