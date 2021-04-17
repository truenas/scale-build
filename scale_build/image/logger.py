from scale_build.utils.logger import get_logger as _get_logger


def get_logger(filename, mode='a+'):
    return _get_logger(filename, f'{filename}.log', mode)
