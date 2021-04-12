import argparse
import logging
import sys

logger = logging.getLogger(__name__)


def setup_logging():
    logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] %(message)s')
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s'))
    logger.addHandler(handler)


def main():
    setup_logging()
    parser = argparse.ArgumentParser(prog='scale-build')
    subparsers = parser.add_subparsers(help='sub-command help', dest='action')

    subparsers.add_parser('checkout', help='Checkout TrueNAS Scale repositories')

    args = parser.parse_args()
    if args.action == 'checkout':
        pass
    else:
        parser.print_help()
