import copy
import pytest

from unittest.mock import patch

from scale_build.packages.order import get_to_build_packages
from scale_build.packages.package import Package, BinaryPackage
from scale_build.tests.unit.utils import get_asset


BUILD_MANIFEST = {
    'sources': [
        {
            'name': 'openzfs',
            'repo': 'https://github.com/truenas/zfs',
            'branch': 'truenas/zfs-2.1-release',
            'subpackages': [
                {
                    'name': 'openzfs-dbg',
                    'deps_path': 'contrib/debian',
                    'explicit_deps': ['kernel', 'kernel-dbg'],
                }
            ],
            'explicit_deps': ['kernel', 'kernel-dbg'],
        },
        {
            'name': 'kernel',
            'repo': 'https://github.com/truenas/linux',
            'branch': 'truenas/linux-5.15',
            'subpackages': [
                {
                    'name': 'kernel-dbg',
                    'batch_priority': 0,
                }
            ]
        },
        {
            'name': 'scst',
            'repo': 'https://github.com/truenas/scst',
            'branch': 'truenas-3.7.x',
            'explicit_deps': ['kernel', 'kernel-dbg'],
            'subpackages': [
                {
                    'name': 'scst-dbg',
                    'branch': 'truenas-3.7.x',
                    'explicit_deps': ['kernel', 'kernel-dbg'],
                }
            ]
        },
        {
            'name': 'py_libzfs',
            'repo': 'https://github.com/truenas/py-libzfs',
            'branch': 'master',
            'explicit_deps': [
                'openzfs',
            ]
        },
        {
            'name': 'zectl',
            'repo': 'https://github.com/truenas/zectl',
            'branch': 'master',
            'explicit_deps': [
                'openzfs',
            ]
        },
        {
            'name': 'truenas_samba',
            'repo': 'https://github.com/truenas/samba',
            'branch': 'SCALE-v4-18-stable',
            'explicit_deps': [
                'openzfs',
            ]
        },
    ],
}
BUILD_DEPENDS_MAPPING = {
    'openzfs': {
        'libaio-dev', 'python3-cffi', 'libssl1.0-dev', 'dh-python', 'debhelper-compat', 'libblkid-dev',
        'kernel', 'python3-setuptools', 'lsb-release', 'libpam0g-dev', 'uuid-dev', 'libtool', 'libelf-dev',
        'libssl-dev', 'po-debconf', 'python3-all-dev', 'libudev-dev', 'python3-sphinx', 'zlib1g-dev',
        'dh-sequence-dkms', 'kernel-dbg'
    },
    'openzfs-dbg': {'dkms', 'libtool', 'debhelper-compat', 'kernel', 'kernel-dbg'},
    'truenas_samba': {
        'libreadline-dev', 'python3-testtools', 'libzfs5', 'liburing-dev', 'dh-python', 'debhelper-compat',
        'libglusterfs-dev [linux-any]', 'libicu-dev', 'docbook-xml', 'libpcap-dev [hurd-i386 kfreebsd-any]',
        'po-debconf', 'python3-dev', 'libbsd-dev', 'pkg-config', 'libnvpair3', 'flex', 'libtasn1-bin',
        'libzfs5-devel', 'python3', 'xfslibs-dev [linux-any]', 'libjansson-dev', 'docbook-xsl',
        'libsystemd-dev [linux-any]', 'python3-etcd', 'libgpgme11-dev', 'libbison-dev', 'libblkid-dev',
        'libgnutls28-dev', 'libdbus-1-dev', 'perl', 'python3-dnspython', 'libcmocka-dev', 'libpam0g-dev',
        'libuutil3', 'libcap-dev [linux-any]', 'libldap2-dev', 'libncurses5-dev', 'bison', 'libparse-yapp-perl',
        'libacl1-dev', 'libkrb5-dev', 'libarchive-dev', 'zlib1g-dev', 'libtasn1-6-dev', 'libpopt-dev',
        'dh-exec', 'xsltproc'
    },
    'py_libzfs': {
        'libuutil3', 'libzfs5-devel', 'python3-all-dev', 'libzfs5', 'cython3', 'libnvpair3', 'dh-python',
        'debhelper-compat', 'python3-setuptools'
    },
    'scst': {'dpkg-dev', 'quilt', 'kernel-dbg', 'kernel', 'debhelper'},
    'scst-dbg': {'dpkg-dev', 'quilt', 'kernel-dbg', 'kernel', 'debhelper'},
    'zectl': {
        'libuutil3', 'libzpool5', 'cmake', 'libzfs5-devel', 'pkgconf', 'libzfs5', 'libbsd-dev', 'libnvpair3',
        'debhelper-compat'
    },
}


def get_binary_packages_of_pkg(pkg_name, all_binary_packages):
    return [bin_pkg for bin_pkg in all_binary_packages.values() if bin_pkg['source_name'] == pkg_name]


def all_packages():
    binary_packages = get_asset('binary_packages')
    pkgs = []
    for pkg in copy.deepcopy(BUILD_MANIFEST)['sources']:
        sub_packages = pkg.pop('subpackages', [])
        pkg = Package(**pkg)
        pkg._binary_packages = [
            BinaryPackage(**bin_pkg) for bin_pkg in get_binary_packages_of_pkg(pkg.name, binary_packages)
        ]
        pkg.build_depends = BUILD_DEPENDS_MAPPING.get(pkg.name, set())
        pkgs.append(pkg)
        for sub_pkg in sub_packages:
            sub_pkg = Package(**{
                **sub_pkg,
                'branch': pkg.branch,
                'repo': pkg.origin,
                'source_name': pkg.source_name,
            })
            sub_pkg._binary_packages = [
                BinaryPackage(**bin_pkg) for bin_pkg in get_binary_packages_of_pkg(sub_pkg.name, binary_packages)
            ]
            sub_pkg.build_depends = BUILD_DEPENDS_MAPPING.get(sub_pkg.name, set())
            pkgs.append(sub_pkg)
    return pkgs


def mock_hash_changed(hash_changed_packages: set):
    def hash_changed_internal(pkg: Package):
        return pkg.name in hash_changed_packages
    return hash_changed_internal


@pytest.mark.parametrize('packages_to_be_rebuilt,changed_hashes_mapping,rebuild', [
    (['zectl', 'py_libzfs'], {'openzfs'}, True),
    (['zectl', 'py_libzfs', 'openzfs', 'scst', 'scst-dbg'], {'kernel'}, True),
    (['py_libzfs'], {'zectl'}, False),
    (['py_libzfs'], {'openzfs-dbg'}, False),
    (['py_libzfs'], {'truenas_samba'}, False),
    (['openzfs'], {'scst'}, False),
])
def test_children_rebuild_logic(packages_to_be_rebuilt, changed_hashes_mapping, rebuild):
    with patch('scale_build.packages.order.get_packages') as get_packages:
        get_packages.return_value = all_packages()
        with patch.object(Package, 'exists', return_value=True):
            with patch.object(
                Package, '_hash_changed', autospec=True, side_effect=mock_hash_changed(changed_hashes_mapping)
            ):
                to_build_packages = get_to_build_packages()
                for package in packages_to_be_rebuilt:
                    if rebuild:
                        assert package in to_build_packages, to_build_packages.keys()
                    else:
                        assert package not in to_build_packages, to_build_packages.keys()
