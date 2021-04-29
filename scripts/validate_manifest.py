#!/usr/bin/env python3
import argparse
import jsonschema
import yaml


def validate(manifest_path):

    error_str = None
    try:
        with open(manifest_path, 'r') as f:
            manifest = yaml.safe_load(f.read())
    except FileNotFoundError:
        error_str = f'{manifest_path!r} does not exist'
    except yaml.YAMLError:
        error_str = f'Unable to read {manifest_path!r} contents. Can you please confirm format is valid ?'

    if error_str:
        print(f'[\033[91mFAILED\x1B[0m]\t{error_str}')
        exit(1)

    schema = {
        'type': 'object',
        'properties': {
            'code_name': {'type': 'string'},
            'debian_release': {'type': 'string'},
            'apt-repos': {
                'type': 'object',
                'properties': {
                    'url': {'type': 'string'},
                    'distribution': {'type': 'string'},
                    'components': {'type': 'string'},
                    'additional': {
                        'type': 'array',
                        'items': [{
                            'type': 'object',
                            'properties': {
                                'url': {'type': 'string'},
                                'distribution': {'type': 'string'},
                                'component': {'type': 'string'},
                                'key': {'type': 'string'},
                            },
                            'required': ['url', 'distribution', 'component', 'key'],
                        }]
                    }
                },
                'required': ['url', 'distribution', 'components', 'additional'],
            },
            'base-packages': {
                'type': 'array',
                'items': [{'type': 'string'}],
            },
            'base-prune': {
                'type': 'array',
                'items': [{'type': 'string'}],
            },
            'build-epoch': {'type': 'integer'},
            'apt_preferences': {
                'type': 'array',
                'items': [{
                    'type': 'object',
                    'properties': {
                        'Package': {'type': 'string'},
                        'Pin': {'type': 'string'},
                        'Pin-Priority': {'type': 'integer'},
                    },
                    'required': ['Package', 'Pin', 'Pin-Priority'],
                }]
            },
            'additional-packages': {
                'type': 'array',
                'items': [{
                    'type': 'object',
                    'properties': {
                        'package': {'type': 'string'},
                        'comment': {'type': 'string'},
                    },
                    'required': ['package', 'comment'],
                }]
            },
            'iso-packages': {
                'type': 'array',
                'items': [{'type': 'string'}],
            },
            'sources': {
                'type': 'array',
                'items': [{
                    'type': 'object',
                    'properties': {
                        'name': {'type': 'string'},
                        'repo': {'type': 'string'},
                        'branch': {'type': 'string'},
                        'batch_priority': {'type': 'integer'},
                        'predepscmd': {
                            'type': 'array',
                            'items': [{'type': 'string'}],
                        },
                        'buildcmd': {
                            'type': 'array',
                            'items': [{'type': 'string'}],
                        },
                        'prebuildcmd': {
                            'type': 'array',
                            'items': [{'type': 'string'}],
                        },
                        'deps_path': {'type': 'string'},
                        'kernel_module': {'type': 'boolean'},
                        'generate_version': {'type': 'boolean'},
                        'explicit_deps': {
                            'type': 'array',
                            'items': [{'type': 'string'}],
                        },
                        'subdir': {'type': 'string'},
                        'deoptions': {'type': 'string'},
                        'jobs': {'type': 'integer'},
                    },
                    'required': ['name', 'branch', 'repo'],
                }]
            },
        },
        'required': [
            'code_name',
            'debian_release',
            'apt-repos',
            'base-packages',
            'base-prune',
            'build-epoch',
            'apt_preferences',
            'additional-packages',
            'iso-packages',
            'sources'
        ],
    }

    try:
        jsonschema.validate(manifest, schema)
    except jsonschema.ValidationError as e:
        print(f'[\033[91mFAILED\x1B[0m]\tFailed to validate manifest: {e}')
        exit(1)
    else:
        print('[\033[92mOK\x1B[0m]\tManifest validated')


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help='sub-command help', dest='action')

    parser_setup = subparsers.add_parser('validate', help='Validate TrueNAS Scale build manifest')
    parser_setup.add_argument('--path', help='Specify path of build manifest')

    args = parser.parse_args()
    if args.action == 'validate':
        validate(args.path)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
