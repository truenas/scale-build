from scale_build.packages.package import Package

from .manifest import get_manifest


def get_packages():
    return [
        pkg for pkg in map(lambda p: Package(**p), get_manifest()['sources'])
        if pkg.to_build
    ]
