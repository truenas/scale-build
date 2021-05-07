import argparse
import coloredlogs
import logging
import sys

from .checkout import checkout_sources
from .clean import complete_cleanup
from .config import BRANCH_OVERRIDES
from .epoch import check_epoch
from .exceptions import CallError
from .iso import build_iso
from .package import build_packages
from .preflight import preflight_check
from .update_image import build_update_image
from .utils.logger import ConsoleFilter, LogHandler
from .utils.manifest import get_manifest
from .validate import validate


logger = logging.getLogger('scale_build')


def setup_logging():
    logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] %(message)s', force=True)
    if sys.stdout.isatty():
        coloredlogs.install(logging.DEBUG, fmt='[%(asctime)s] %(message)s', logger=logger)
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s'))
    handler.addFilter(ConsoleFilter())
    logger.addHandler(handler)
    log_handler = LogHandler()
    log_handler.setLevel(logging.DEBUG)
    logger.addHandler(log_handler)
    logger.propagate = False


def validate_config():
    manifest = get_manifest()
    packages = [p['name'] for p in manifest['sources']]
    invalid_overrides = [o for o in BRANCH_OVERRIDES if o not in packages]
    if invalid_overrides:
        raise CallError(
            f'Invalid branch override(s) provided: {", ".join(invalid_overrides)!r} sources not configured in manifest'
        )


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
    validate_parser = subparsers.add_parser('validate', help='Validate TrueNAS Scale build manifest and system state')
    for action in ('manifest', 'system_state'):
        validate_parser.add_argument(f'--validate-{action}', dest=action, action='store_true')
        validate_parser.add_argument(f'--no-validate-{action}', dest=action, action='store_false')
        validate_parser.set_defaults(**{action: True})

    args = parser.parse_args()
    if args.action == 'checkout':
        check_epoch()
        checkout_sources()
    elif args.action == 'packages':
        validate()
        check_epoch()
        build_packages()
    elif args.action == 'update':
        validate()
        build_update_image()
    elif args.action == 'iso':
        validate()
        build_iso()
    elif args.action == 'clean':
        complete_cleanup()
    elif args.action == 'validate':
        validate(args.system_state, args.manifest)
    else:
        parser.print_help()
