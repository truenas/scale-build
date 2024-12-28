from functools import cache

REQUIRED_RAM_GB = 16 * (1024 ** 3)

__all__ = ("has_low_ram",)


@cache
def has_low_ram():
    with open('/proc/meminfo') as f:
        for line in filter(lambda x: 'MemTotal' in x, f):
            return int(line.split()[1]) * 1024 < REQUIRED_RAM_GB
