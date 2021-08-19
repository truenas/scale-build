import os
import time

from datetime import datetime


BUILD_TIME = int(time.time())
BUILD_TIME_OBJ = datetime.fromtimestamp(BUILD_TIME)
BUILDER_DIR = os.getenv('BUILDER_DIR', './')
BRANCH_OUT_NAME = os.getenv('NEW_BRANCH_NAME')
BRANCH_OVERRIDES = {k[:-(len('_OVERRIDE'))]: v for k, v in os.environ.items() if k.endswith('_OVERRIDE')}
FORCE_CLEANUP_WITH_EPOCH_CHANGE = bool(int(os.getenv('FORCE_CLEANUP_WITH_EPOCH_CHANGE') or '0'))
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
PARALLEL_BUILD = int(os.getenv('PARALLEL_BUILDS', max(os.cpu_count(), 8) / 4))
PKG_DEBUG = os.getenv('PKG_DEBUG', False)
SIGNING_KEY = os.getenv('SIGNING_KEY')
SIGNING_PASSWORD = os.getenv('SIGNING_PASSWORD')
TRAIN = os.getenv('TRUENAS_TRAIN')
TRY_BRANCH_OVERRIDE = os.getenv('TRY_BRANCH_OVERRIDE')
if os.getenv('TRUENAS_VERSION'):
    VERSION = os.getenv('TRUENAS_VERSION')
else:
    VERSION = f'{BUILD_TIME_OBJ.strftime("%y.%m")}-MASTER-{BUILD_TIME_OBJ.strftime("%Y%m%d-%H%M%S")}'
