from os import environ, cpu_count
from time import time
from datetime import datetime

IDENTITY_FILE_PATH_OVERRIDE_SUFFIX = '_OVERRIDE_IDENTITY_FILE_PATH'
_VERS = '26.04.0-MASTER'


def get_env_variable(key, _type, default_value=None):
    return get_normalized_value(environ.get(key), _type, default_value)


def get_normalized_value(value, _type, default_value=None):
    if value:
        if _type == bool:
            if value.isdigit():
                return _type(int(value))
            elif value.lower()[0] == 'y':
                return True
            elif value.lower()[0] == 'n':
                return False
            else:
                # the variable is set but is something randon (i.e. VAR='please')
                # so just assume it's set
                return True
        else:
            return _type(value)
    else:
        return _type(default_value) if default_value else _type()


APT_BASE_CUSTOM = get_env_variable('APT_BASE_CUSTOM', str)
APT_INTERNAL_BUILD = get_env_variable('APT_INTERNAL_BUILD', bool, False)
BUILD_TIME = int(time())
BUILD_TIME_OBJ = datetime.fromtimestamp(BUILD_TIME)
BUILDER_DIR = get_env_variable('BUILDER_DIR', str, './')
BRANCH_OUT_NAME = get_env_variable('NEW_BRANCH_NAME', str)
BRANCH_OVERRIDES = {}
CCACHE_ENABLED = get_env_variable('CCACHE', bool, 0)
FORCE_CLEANUP_WITH_EPOCH_CHANGE = get_env_variable('FORCE_CLEANUP_WITH_EPOCH_CHANGE', bool)
GITHUB_TOKEN = get_env_variable('GITHUB_TOKEN', str)
PACKAGE_IDENTITY_FILE_PATH_OVERRIDES = {}
PARALLEL_BUILD = get_env_variable('PARALLEL_BUILDS', int, (max(cpu_count(), 8) / 4))
PKG_DEBUG = get_env_variable('PKG_DEBUG', bool, 0)
SECRET_ENV_VARS = {}
SIGNING_KEY = get_env_variable('SIGNING_KEY', str)
SIGNING_PASSWORD = get_env_variable('SIGNING_PASSWORD', str)
SKIP_SOURCE_REPO_VALIDATION = get_env_variable('SKIP_SOURCE_REPO_VALIDATION', bool)
TRAIN = get_env_variable('TRUENAS_TRAIN', str)
TRUENAS_BRANCH_OVERRIDE = get_env_variable('TRUENAS_BRANCH_OVERRIDE', str)
TRY_BRANCH_OVERRIDE = get_env_variable('TRY_BRANCH_OVERRIDE', str)
VERSION = get_env_variable('TRUENAS_VERSION', str, f'{_VERS}-{BUILD_TIME_OBJ.strftime("%Y%m%d-%H%M%S")}')
TRUENAS_VENDOR = get_env_variable('TRUENAS_VENDOR', str)
PRESERVE_ISO = get_env_variable('PRESERVE_ISO', bool, False)
TRUENAS_EXPERIMENTAL = get_env_variable('TRUENAS_EXPERIMENTAL', bool, True)


# We will get branch overrides and identity file path overrides from here
for k, v in environ.items():
    if k.endswith('_OVERRIDE'):
        BRANCH_OVERRIDES[k[:-(len('_OVERRIDE'))]] = v
    elif k.endswith(IDENTITY_FILE_PATH_OVERRIDE_SUFFIX):
        PACKAGE_IDENTITY_FILE_PATH_OVERRIDES[k[:-(len(IDENTITY_FILE_PATH_OVERRIDE_SUFFIX))]] = v
    elif k.startswith('SECRET_'):
        SECRET_ENV_VARS[k[len('SECRET_'):]] = v
