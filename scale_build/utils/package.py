from scale_build.packages.package import Package

from .manifest import get_manifest


def get_sources():
    return [
        pkg for pkg in map(lambda p: Package(**p), get_manifest()['sources'])
        if pkg.to_build
    ]


def get_packages():
    pkgs = []
    for pkg in get_manifest()['sources']:
        sub_packages = pkg.pop('subpackages', [])
        pkg = Package(**pkg)
        if pkg.to_build:
            pkgs.append(pkg)
        if sub_packages:
            for sub_pkg in sub_packages:
                sub_pkg = Package(**{
                    **sub_pkg,
                    'branch': pkg.branch,
                    'repo': pkg.origin,
                })
                if sub_pkg.to_build:
                    pkgs.append(sub_pkg)
    return pkgs
