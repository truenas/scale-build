import collections
import logging
import os
import threading

from .paths import LOG_DIR


def get_logger(logger_name, logger_path, mode='a+'):
    logger = logging.getLogger(logger_name)
    logger.propagate = False
    logger.setLevel('DEBUG')
    logger.handlers = []
    logger.addHandler(logging.FileHandler(os.path.join(LOG_DIR, logger_path), mode))
    return logger


class LoggingContext:

    CONTEXTS = collections.defaultdict(list)

    def __init__(self, path, mode='a+'):
        self.path = f'{path}.log'
        self.mode = mode

    def __enter__(self):
        self.CONTEXTS[threading.currentThread().name].append(
            logging.FileHandler(os.path.join(LOG_DIR, self.path), self.mode, delay=True)
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.CONTEXTS[threading.currentThread().name].pop()

    @staticmethod
    def has_handler():
        return bool(LoggingContext.CONTEXTS[threading.current_thread().name])

    @staticmethod
    def handler():
        return LoggingContext.CONTEXTS[threading.current_thread().name][-1]


class ConsoleFilter(logging.Filter):

    def filter(self, record):
        return not LoggingContext.has_handler()


class LogHandler(logging.NullHandler):

    def handle(self, record):
        rv = LoggingContext.has_handler()
        if rv:
            return LoggingContext.handler().handle(record)
        return rv
