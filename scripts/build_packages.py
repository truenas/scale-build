#!/usr/bin/python3
from build_packages.get_packages import get_to_build_packages


if __name__ == '__main__':
    from pprint import pprint
    pprint(get_to_build_packages())
