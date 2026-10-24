"""Initialize identity only at the fresh HexOS install boundary."""

import json
import os
from pathlib import Path


def initialize_hexos_identity(root, is_fresh_install, run_command):
    if not is_fresh_install:
        return
    root = Path(root)
    try:
        with open(root / 'data/.vendor') as stream:
            vendor = json.load(stream)
    except FileNotFoundError:
        return
    if not isinstance(vendor, dict):
        raise TypeError('Invalid vendor record in the new installation')
    if vendor.get('name') != 'HexOS':
        return
    executable = '/usr/bin/truenas-hexos-identity'
    target = root / executable.lstrip('/')
    if not target.is_file() or not os.access(target, os.X_OK):
        raise RuntimeError('The HexOS image is missing the installation identity reader and writer')
    run_command(['chroot', str(root), executable, 'install-create', '--installer'])
