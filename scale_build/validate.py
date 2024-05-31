import os
import jsonschema
import logging
import shutil

from truenas_install import dhs, fhs

from .exceptions import CallError, MissingPackagesException
from .utils.manifest import validate_manifest
from .utils.paths import REFERENCE_FILES, REFERENCE_FILES_DIR


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

    if missing_files := [
        f for f in map(lambda f: os.path.join(REFERENCE_FILES_DIR, f), REFERENCE_FILES) if not os.path.exists(f)
    ]:
        raise CallError(f'Missing reference files: {", ".join(missing_files)!r}')


def validate_datasets():
    try:
        jsonschema.validate(fhs.TRUENAS_DATASETS, fhs.TRUENAS_DATASET_SCHEMA)
    except jsonschema.ValidationError as e:
        raise CallError(f'Provided dataset schema is invalid: {e}')


def validate_data_dir_schema():
    try:
        jsonschema.validate(dhs.TRUENAS_DATA_HIERARCHY, dhs.TRUENAS_DATA_HIERARCHY_SCHEMA)
    except jsonschema.ValidationError as e:
        raise CallError(f'Provided data hierarchy schema is invalid: {e}')


def validate(system_state_flag=True, manifest_flag=True, datasets_flag=True, data_flag=True):
    if system_state_flag:
        validate_system_state()
        logger.debug('System state Validated')
    if manifest_flag:
        validate_manifest()
        logger.debug('Manifest Validated')

    if datasets_flag:
        validate_datasets()
        logger.debug('Dataset schema Validated')

    if data_flag:
        validate_data_dir_schema()
        logger.debug('Data directory schema Validated')
