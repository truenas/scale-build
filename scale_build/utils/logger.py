import logging
import os

from .paths import LOG_DIR


def get_logger(logger_name, logger_path, mode='a+'):
    logger = logging.getLogger(logger_name)
    logger.propagate = False
    logger.setLevel('DEBUG')
    logger.handlers = []
    logger.addHandler(logging.FileHandler(os.path.join(LOG_DIR, logger_path), mode))
    return logger
