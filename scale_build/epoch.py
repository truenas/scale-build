import logging
import os

from scale_build.utils.manifest import get_manifest
from .utils.variables import TMP_DIR


logger = logging.getLogger(__name__)
EPOCH_PATH = os.path.join(TMP_DIR, '.buildEpoch')


def update_epoch(epoch_value):
    os.makedirs(TMP_DIR, exist_ok=True)
    with open(EPOCH_PATH, 'w') as f:
        f.write(str(epoch_value))


def check_epoch():
    current_epoch = get_manifest()['build-epoch']
    if os.path.exists(EPOCH_PATH):
        with open(EPOCH_PATH, 'r') as f:
            epoch_num = f.read().strip()
            if epoch_num != current_epoch:
                logger.warning('Build epoch changed! Removing temporary files and forcing clean build.')
                update_epoch(current_epoch)
    else:
        update_epoch(current_epoch)
