import argparse
import coloredlogs
import logging
import sys

from .checkout import checkout_sources
from .clean import complete_cleanup
from .epoch import check_epoch
from .iso import build_iso
from .package import build_packages
from .preflight import preflight_check
from .update_image import build_update_image


logger = logging.getLogger(__name__)


def setup_logging():
    logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] %(message)s')
    if sys.stdout.isatty():
        coloredlogs.install(logging.DEBUG, fmt='[%(asctime)s] %(message)s')
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
    subparsers.add_parser('clean', help='Clean build package(s) / cloned source(s) / image(s) of TrueNAS Scale')
    subparsers.add_parser('packages', help='Build TrueNAS Scale packages')
    subparsers.add_parser('update', help='Create TrueNAS Scale update image')
    subparsers.add_parser('iso', help='Create TrueNAS Scale iso installation file')

    args = parser.parse_args()
    if args.action == 'checkout':
        check_epoch()
        checkout_sources()
    elif args.action == 'packages':
        check_epoch()
        build_packages()
    elif args.action == 'update':
        build_update_image()
    elif args.action == 'iso':
        build_iso()
    elif args.action == 'clean':
        complete_cleanup()
    else:
        parser.print_help()
