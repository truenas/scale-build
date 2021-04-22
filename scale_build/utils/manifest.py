import yaml

from scale_build.config import TRAIN
from scale_build.exceptions import MissingManifest, InvalidManifest
from scale_build.utils.paths import MANIFEST


manifest = None


def get_manifest():
    global manifest
    if not manifest:
        try:
            with open(MANIFEST, 'r') as f:
                manifest = yaml.safe_load(f.read())
                return manifest
        except FileNotFoundError:
            raise MissingManifest()
        except yaml.YAMLError:
            raise InvalidManifest()
    else:
        return manifest


def get_release_code_name():
    return get_manifest()['code_name']


def get_truenas_train():
    return TRAIN or f'TrueNAS-SCALE-{get_release_code_name()}-Nightlies'
