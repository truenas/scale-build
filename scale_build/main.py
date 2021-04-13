import argparse
import logging
import sys

from scale_build.checkout import checkout_sources
from scale_build.epoch import check_epoch
from scale_build.package import build_packages
from scale_build.preflight import preflight_check

logger = logging.getLogger(__name__)


def setup_logging():
    logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] %(message)s')
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s'))
    logger.addHandler(handler)


def main():
    setup_logging()
    preflight_check()
    parser = argparse.ArgumentParser(prog='scale-build')
    subparsers = parser.add_subparsers(help='sub-command help', dest='action')

    subparsers.add_parser('checkout', help='Checkout TrueNAS Scale repositories')

    args = parser.parse_args()
    if args.action == 'checkout':
        check_epoch()
        checkout_sources()
    elif args.action == 'package':
        check_epoch()
        build_packages()
    else:
        parser.print_help()
