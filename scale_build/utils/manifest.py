import functools
import jsonschema
import yaml

from scale_build.config import TRAIN
from scale_build.exceptions import CallError, MissingManifest
from scale_build.utils.paths import MANIFEST


MANIFEST_SCHEMA = {
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


@functools.cache
def get_manifest():
    try:
        with open(MANIFEST, 'r') as f:
            manifest = yaml.safe_load(f.read())
            return manifest
    except FileNotFoundError:
        raise MissingManifest()
    except yaml.YAMLError:
        raise CallError('Provided manifest has invalid format')


def get_release_code_name():
    return get_manifest()['code_name']


def get_truenas_train():
    return TRAIN or f'TrueNAS-SCALE-{get_release_code_name()}-Nightlies'


def validate_manifest():
    try:
        jsonschema.validate(get_manifest(), MANIFEST_SCHEMA)
    except jsonschema.ValidationError as e:
        raise CallError(f'Provided manifest is invalid: {e}')
