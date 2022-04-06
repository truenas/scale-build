from os import environ, cpu_count
from time import time
from datetime import datetime

_VERS = '22.02.1-MASTER'


def get_env_variable(key, default_value, _type):
    value = environ.get(key)
    if value:
        if _type == bool:
            if value.isdigit():
                return _type(value)
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
        return _type(default_value)


BUILD_TIME = int(time())
BUILD_TIME_OBJ = datetime.fromtimestamp(BUILD_TIME)
BUILDER_DIR = get_env_variable('BUILDER_DIR', './', str)
BRANCH_OUT_NAME = get_env_variable('NEW_BRANCH_NAME', '', str)
BRANCH_OVERRIDES = {k[:-(len('_OVERRIDE'))]: v for k, v in environ.items() if k.endswith('_OVERRIDE')}
FORCE_CLEANUP_WITH_EPOCH_CHANGE = get_env_variable('FORCE_CLEANUP_WITH_EPOCH_CHANGE', 0, bool)
GITHUB_TOKEN = get_env_variable('GITHUB_TOKEN', '', str)
PARALLEL_BUILD = get_env_variable('PARALLEL_BUILDS', (max(cpu_count(), 8) / 4), int)
PKG_DEBUG = get_env_variable('PKG_DEBUG', 0, bool)
SIGNING_KEY = get_env_variable('SIGNING_KEY', '', str)
SIGNING_PASSWORD = get_env_variable('SIGNING_PASSWORD', '', str)
SKIP_SOURCE_REPO_VALIDATION = get_env_variable('SKIP_SOURCE_REPO_VALIDATION', 0, bool)
TRAIN = get_env_variable('TRUENAS_TRAIN', '', str)
TRUENAS_BRANCH_OVERRIDE = get_env_variable('TRUENAS_BRANCH_OVERRIDE', '', str)
TRY_BRANCH_OVERRIDE = get_env_variable('TRY_BRANCH_OVERRIDE', '', str)
VERSION = get_env_variable('TRUENAS_VERSION', f'{_VERS}-{BUILD_TIME_OBJ.strftime("%Y%m%d-%H%M%S")}', str)
