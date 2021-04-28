import psutil


REQUIRED_RAM = 16  # GB


def has_low_ram():
    return psutil.virtual_memory().total < REQUIRED_RAM * 1024 * 1024 * 1024
