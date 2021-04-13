import errno
import logging

from collections import defaultdict
from scale_build.exceptions import CallError
from scale_build.utils.manifest import get_packages


logger = logging.getLogger(__name__)


def get_to_build_packages():
    binary_packages = {}
    packages_list = get_packages()
    packages = {}
    for package in packages_list:
        if not package.exists:
            raise CallError(
                f'Missing sources for {package.name},  did you forget to run "make checkout" ?', errno=errno.ENOENT
            )

        packages[package.name] = package
        for binary_package in package.binary_packages:
            binary_packages[binary_package.name] = binary_package

    parent_mapping = defaultdict(set)
    for pkg_name, package in packages.items():
        for dep in package.build_time_dependencies(binary_packages):
            parent_mapping[dep].add(pkg_name)

    for pkg_name, package in filter(lambda i: i[1].hash_changed, packages.items()):
        for child in parent_mapping[pkg_name]:
            packages[child].parent_changed = True

    return {package.name: package for package in packages.values() if package.rebuild}
