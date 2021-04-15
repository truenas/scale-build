import yaml

from scale_build.exceptions import MissingManifest, InvalidManifest
from scale_build.utils.variables import MANIFEST


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
