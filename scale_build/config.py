import os
import time

from datetime import datetime


BUILD_TIME = int(time.time())
BUILD_TIME_OBJ = datetime.fromtimestamp(BUILD_TIME)
BUILDER_DIR = os.getenv('BUILDER_DIR', './')
BRANCH_OVERRIDES = {k[:-(len('_OVERRIDE'))]: v for k, v in os.environ.items() if k.endswith('_OVERRIDE')}
CODE_NAME = os.getenv('CODENAME', 'Angelfish')
PARALLEL_BUILD = int(os.getenv('PARALLEL_BUILDS', os.cpu_count() / 4))
PKG_DEBUG = os.getenv('PKG_DEBUG', False)
TRAIN = os.getenv('TRUENAS_TRAIN', f'TrueNAS-SCALE-{CODE_NAME}-Nightlies')
TRY_BRANCH_OVERRIDE = os.getenv('TRY_BRANCH_OVERRIDE')
if os.getenv('TRUENAS_VERSION'):
    VERSION = os.getenv('TRUENAS_VERSION')
else:
    VERSION = f'{BUILD_TIME_OBJ.strftime("%y.%m")}-MASTER-{BUILD_TIME_OBJ.strftime("%Y%m%d-%H%M%S")}'
