#!/usr/bin/python3
import collections
import json
import os
import subprocess
import yaml

from toposort import toposort


DEPENDS_SCRIPT_PATH = './scripts/parse_deps.pl'


def run(*args, **kwargs):
    if isinstance(args[0], list):
        args = tuple(args[0])
    kwargs.setdefault('stdout', subprocess.PIPE)
    kwargs.setdefault('stderr', subprocess.PIPE)
    check = kwargs.pop('check', True)
    proc = subprocess.Popen(args, stdout=kwargs['stdout'], stderr=kwargs['stderr'])
    stdout, stderr = proc.communicate()
    cp = subprocess.CompletedProcess(args, proc.returncode, stdout=stdout, stderr=stderr)
    if check:
        cp.check_returncode()
    return cp


def normalize_bin_packages_depends(depends_str):
    return list(filter(lambda k: k and '$' not in k, map(str.strip, depends_str.split(','))))


def normalize_build_depends(build_depends_str):
    deps = []
    for dep in filter(bool, map(str.strip, build_depends_str.split(','))):
        index = dep.find('(')
        if index != -1:
            dep = dep[:index]
        deps.append(dep)
    return deps


def get_install_deps(packages, deps, deps_list):
    for dep in filter(lambda p: p in packages, deps_list):
        deps.add(packages[dep]['source'])
        deps.update(get_install_deps(packages, deps, packages[dep]['install_deps'] | packages[dep]['build_deps']))
    return deps


if __name__ == '__main__':
    # Okay so the order of business here is to first locate all the packages which are in the manifest
    # Remove those packages whose cache's contents are intact
    # Figure out dependencies of remaining packages
    # Implement topological sort and figure out
    sources_path = os.environ['SOURCES']
    with open(os.environ['MANIFEST'], 'r') as f:
        manifest = yaml.safe_load(f.read())

    packages = collections.defaultdict(lambda: {'info': None, 'build_deps': set(), 'install_deps': set()})
    sources = []
    for package in manifest['sources']:
        if package['name'] == 'kernel':
            continue
        name = package['name']
        package_path = os.path.join(sources_path, name)
        if not os.path.exists(package_path):
            raise FileNotFoundError(f'{package_path!r} not found, did you forget to "make checkout" ?')

        if package.get('predepscmd'):
            # TODO: Let's skip these for now
            continue

        if package.get('subdir'):
            package_path = os.path.join(package_path, package['subdir'])

        cp = run([DEPENDS_SCRIPT_PATH, os.path.join(package_path, 'debian/control')])
        info = json.loads(cp.stdout)

        for bin_package in info['binary_packages']:
            packages[bin_package['name']].update({
                'build_deps': set(normalize_build_depends(info['source_package']['build_depends'])),
                'install_deps': set(normalize_bin_packages_depends(bin_package['depends'] or '')),
                'source_package': info['source_package']['name'],
                'source': name,
            })
            if name == 'truenas':
                packages[bin_package['name']]['build_deps'] |= packages[bin_package['name']]['install_deps']

    package_dep = {
        i['source']: list(get_install_deps(packages, set(), i['build_deps'])) for n, i in packages.items()
    }
    print(yaml.dump(package_dep))
    # kernel package is special, let's please have it as the first package to be be considered to be built
    # packages_ordering = [['kernel']] + [list(deps) for deps in toposort(package_dep)]
    # print(yaml.dump(packages_ordering))
