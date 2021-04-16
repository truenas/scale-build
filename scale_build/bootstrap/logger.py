import logging
import os

from scale_build.utils.variables import LOG_DIR


def get_log_file_name(bootstrap_dir_type):
    if bootstrap_dir_type == 'package':
        return 'bootstrap_chroot.log'
    elif bootstrap_dir_type == 'cd':
        return 'cdrom-bootstrap.log'
    else:
        return 'rootfs-bootstrap.log'


def get_logger(bootstrap_dir_type, mode='a+'):
    logger = logging.getLogger(f'bootstrap_dir_{bootstrap_dir_type}')
    logger.propagate = False
    logger.setLevel('DEBUG')
    logger.handlers = []
    logger.addHandler(logging.FileHandler(os.path.join(LOG_DIR, get_log_file_name(bootstrap_dir_type)), mode))
    return logger
