import importlib
import logging
import gzip
import os
import re
import sys

import requests
from packaging import version

from .utils.manifest import get_manifest
from .utils.package import get_packages

logger = logging.getLogger(__name__)


def get_debian_version(debian_packages, name):
    if m := re.search(
            rf'Package: {name}\n('
            rf'Version: |'
            rf'Source: .+? \(|'
            rf'Source: .+?\nVersion: '
            rf')([0-9.\-]+)',
            debian_packages
    ):
        return m.group(2)

    return None


def check_python_truenas_requirements(debian_packages, pkg):
    sys.path.insert(0, pkg.source_path)
    pip_to_debian = importlib.import_module('generate').pip_to_debian
    sys.path.remove(pkg.source_path)

    need_update = False
    with open(os.path.join(pkg.source_path, 'requirements.txt')) as f:
        requirements = f.read().strip().split()
    with open(os.path.join(pkg.source_path, 'constraints.txt')) as f:
        requirements += f.read().strip().split()
    for requirement in requirements:
        pip_package_name, requirement_version = requirement.split('#egg=')[-1].split('==')

        debian_package_name = pip_to_debian(pip_package_name)
        debian_version = get_debian_version(debian_packages, debian_package_name)
        if debian_version is None:
            logger.info(f'Debian package {debian_package_name} does not exist')
            continue

        if version.parse(debian_version.split('-')[0]) > version.parse(requirement_version):
            logger.error(f'Upstream version for python package {pip_package_name} ({debian_version}) is newer than '
                         f'local ({requirement_version})')
            need_update = True

    return need_update


def check_debian_fork(debian_packages, pkg):
    with open(os.path.join(pkg.source_path, 'pull.sh')) as f:
        pull_sh = f.read()

    local_version = re.search(r'^VERSION=([0-9.]+)$', pull_sh, flags=re.MULTILINE).group(1)
    local_version += ('-' + re.search(r'^REVISION=([0-9]+)$', pull_sh, flags=re.MULTILINE).group(1))

    debian_version = get_debian_version(debian_packages, pkg.name)
    if debian_version is None:
        raise RuntimeError(f'Unable to find debian package {pkg.name}')

    if version.parse(debian_version) > version.parse(local_version):
        logger.error(f'Upstream version for package {pkg.name} ({debian_version}) is newer than local '
                     f'({local_version})')
        return True

    return False


def check_upstream_package_updates():
    manifest = get_manifest()
    response = requests.get(
        f'https://deb.debian.org/debian/dists/{manifest["debian_release"]}/main/binary-amd64/Packages.gz'
    )
    response.raise_for_status()
    debian_packages = gzip.decompress(response.content).decode("utf-8")

    need_update = False
    for pkg in get_packages():
        if pkg.name == 'python_truenas_requirements':
            need_update |= check_python_truenas_requirements(debian_packages, pkg)

        if pkg.debian_fork:
            need_update |= check_debian_fork(debian_packages, pkg)

    if need_update:
        sys.exit(1)
