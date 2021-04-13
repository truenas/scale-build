import yaml

from scale_build.exceptions import MissingManifest, InvalidManifest
from scale_build.utils.variables import MANIFEST


def get_manifest():
    try:
        with open(MANIFEST, 'r') as f:
            return yaml.safe_load(f.read())
    except FileNotFoundError:
        raise MissingManifest()
    except yaml.YAMLError:
        raise InvalidManifest()
