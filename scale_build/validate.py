import os
import jsonschema
import logging
import shutil

from .exceptions import CallError, MissingPackagesException
from .utils.manifest import validate_manifest
from truenas_install import fhs


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


def validate_datasets():
    try:
        jsonschema.validate(fhs.TRUENAS_DATASETS, fhs.TRUENAS_DATASET_SCHEMA)
    except jsonschema.ValidationError as e:
        raise CallError(f'Provided dataset schema is invalid: {e}')


def validate(system_state_flag=True, manifest_flag=True, datasets_flag=True):
    if system_state_flag:
        validate_system_state()
        logger.debug('System state Validated')
    if manifest_flag:
        validate_manifest()
        logger.debug('Manifest Validated')

    if datasets_flag:
        validate_datasets()
        logger.debug('Dataset schema Validated')
