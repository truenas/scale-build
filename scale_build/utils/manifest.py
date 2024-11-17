import functools
import jsonschema
import re
import yaml

from urllib.parse import urlparse

from scale_build.config import SKIP_SOURCE_REPO_VALIDATION, TRAIN
from scale_build.exceptions import CallError, MissingManifest
from scale_build.utils.paths import MANIFEST


BRANCH_REGEX = re.compile(r'(branch\s*:\s*)\b[\w/\.-]+\b')
SSH_SOURCE_REGEX = re.compile(r'^[\w]+@(\w.+):(\w.+)')

INDIVIDUAL_REPO_SCHEMA = {
    'type': 'object',
    'properties': {
        'name': {'type': 'string'},
        'identity_file_path': {'type': 'string'},
        'batch_priority': {'type': 'integer'},
        'predepscmd': {
            'type': 'array',
            'items': {'type': 'string'},
        },
        'build_constraints': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'name': {'type': 'string'},
                    'value': {
                        'anyOf': [
                            {'type': 'string'},
                            {'type': 'integer'},
                            {'type': 'boolean'},
                        ],
                    },
                    'type': {
                        'type': 'string',
                        'enum': ['boolean', 'string', 'integer'],
                    },
                },
                'required': ['name', 'value', 'type'],
            },
        },
        'buildcmd': {
            'type': 'array',
            'items': {'type': 'string'},
        },
        'prebuildcmd': {
            'type': 'array',
            'items': {'type': 'string'},
        },
        'depscmd': {
            'type': 'array',
            'items': {'type': 'string'},
        },
        'deps_path': {'type': 'string'},
        'supports_ccache': {'type': 'boolean'},
        'generate_version': {'type': 'boolean'},
        'explicit_deps': {
            'type': 'array',
            'items': {'type': 'string'},
        },
        'subdir': {'type': 'string'},
        'deoptions': {'type': 'string'},
        'jobs': {'type': 'integer'},
        'debian_fork': {'type': 'boolean'},
        'env': {'type': 'object', 'patternProperties': {'^.+$': {'type': 'string'}}},
    },
    'additionalProperties': False,
}
MANIFEST_SCHEMA = {
    'type': 'object',
    'properties': {
        'code_name': {'type': 'string'},
        'debian_release': {'type': 'string'},
        'identity_file_path_default': {'type': 'string'},
        'apt-repos': {
            'type': 'object',
            'properties': {
                'base-url': {'type': 'string', 'pattern': '.*/$'},
                'base-url-internal': {'type': 'string', 'pattern': '.*/$'},
                'url': {'type': 'string'},
                'distribution': {'type': 'string'},
                'components': {'type': 'string'},
                'additional': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'url': {'type': 'string'},
                            'distribution': {'type': 'string'},
                            'component': {'type': 'string'},
                            'key': {'type': 'string'},
                        },
                        'required': ['url', 'distribution', 'component',],
                    }
                }
            },
            'required': ['url', 'distribution', 'components', 'additional'],
        },
        'base-packages': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'install_recommends': {'type': 'boolean'},
                    'name': {'type': 'string'},
                },
                'required': ['install_recommends', 'name'],
                'additionalProperties': False,
            },
        },
        'base-prune': {
            'type': 'array',
            'items': {'type': 'string'},
        },
        'build-epoch': {'type': 'integer'},
        'apt_preferences': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'Package': {'type': 'string'},
                    'Pin': {'type': 'string'},
                    'Pin-Priority': {'type': 'integer'},
                },
                'required': ['Package', 'Pin', 'Pin-Priority'],
            }
        },
        'additional-packages': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'name': {'type': 'string'},
                    'comment': {'type': 'string'},
                    'install_recommends': {'type': 'boolean'},
                },
                'required': ['name', 'comment', 'install_recommends'],
                'additionalProperties': False,
            }
        },
        'iso-packages': {
            'type': 'array',
            'items': {'type': 'string'},
        },
        'sources': {
            'type': 'array',
            'items': {
                **{k: v for k, v in INDIVIDUAL_REPO_SCHEMA.items() if k != 'properties'},
                'properties': {
                    **INDIVIDUAL_REPO_SCHEMA['properties'],
                    'branch': {'type': 'string'},
                    'repo': {'type': 'string'},
                    'subpackages': {
                        'type': 'array',
                        'items': {
                            **INDIVIDUAL_REPO_SCHEMA,
                            'required': ['name'],
                        },
                    },
                },
                'required': ['name', 'branch', 'repo'],
            }
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


def get_manifest_str():
    try:
        with open(MANIFEST, 'r') as f:
            return f.read()
    except FileNotFoundError:
        raise MissingManifest()


def validate_apt_preferences_order(manifest):
    packages = [p['Package'] for p in manifest['apt_preferences']]
    if sorted(packages, key=lambda k: k.strip('*')) != packages:
        raise CallError('Please list down apt preferences in alphabetical order')


@functools.cache
def get_manifest():
    try:
        manifest = yaml.safe_load(get_manifest_str())
        jsonschema.validate(manifest, MANIFEST_SCHEMA)
        validate_apt_preferences_order(manifest)
        return manifest
    except yaml.YAMLError:
        raise CallError('Provided manifest has invalid format')
    except jsonschema.ValidationError as e:
        raise CallError(f'Provided manifest is invalid: {e}')


def get_release_code_name():
    return get_manifest()['code_name']


def get_truenas_train():
    return TRAIN or f'TrueNAS-SCALE-{get_release_code_name()}-Nightlies'


def update_packages_branch(branch_name):
    # We would like to update branches but if we use python module, we would lose the comments which is not desired
    # Let's please use regex and find a better way to do this in the future
    manifest_str = get_manifest_str()
    updated_str = BRANCH_REGEX.sub(fr'\1{branch_name}', manifest_str)

    with open(MANIFEST, 'w') as f:
        f.write(updated_str)


def validate_manifest():
    manifest = get_manifest()
    if SKIP_SOURCE_REPO_VALIDATION:
        return

    # We would like to make sure that each package source we build from is from our fork and not another one
    invalid_packages = []
    for package in manifest['sources']:
        repo_source = package['repo']
        if url := SSH_SOURCE_REGEX.findall(repo_source):
            hostname, repo_path = url[0]
        else:
            url = urlparse(repo_source)
            hostname = url.hostname
            repo_path = url.path

        if hostname not in ['github.com', 'www.github.com'] or not repo_path.lower().strip('/').startswith((
            'truenas/', 'ixsystems/'
        )):
            invalid_packages.append(package['name'])

    if invalid_packages:
        raise CallError(
            f'{",".join(invalid_packages)!r} are using repos from unsupported git upstream. Scale-build only '
            'accepts packages from github.com/truenas organization (To skip this for dev '
            'purposes, please set "SKIP_SOURCE_REPO_VALIDATION" in your environment).'
        )
