from scale_build.packages.package import Package

from .manifest import get_manifest


def get_packages():
    return [Package(**pkg) for pkg in get_manifest()['sources']]
