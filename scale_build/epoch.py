import logging
import os

from .clean import complete_cleanup
from .preflight import setup_dirs
from .utils.manifest import get_manifest
from .utils.paths import TMP_DIR


logger = logging.getLogger(__name__)
EPOCH_PATH = os.path.join(TMP_DIR, '.buildEpoch')


def update_epoch(epoch_value):
    os.makedirs(TMP_DIR, exist_ok=True)
    with open(EPOCH_PATH, 'w') as f:
        f.write(str(epoch_value))


def check_epoch():
    current_epoch = str(get_manifest()['build-epoch'])
    if os.path.exists(EPOCH_PATH):
        with open(EPOCH_PATH, 'r') as f:
            epoch_num = f.read().strip()
            if epoch_num != current_epoch:
                logger.warning('Build epoch changed! Removing temporary files and forcing clean build.')
                update_epoch(current_epoch)
                complete_cleanup()
                setup_dirs()
    else:
        update_epoch(current_epoch)
