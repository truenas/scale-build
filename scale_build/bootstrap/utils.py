import textwrap

from scale_build.utils.manifest import get_manifest # noqa
from scale_build.utils.run import run # noqa
from scale_build.utils.system import has_low_ram # noqa
from scale_build.utils.variables import BUILDER_DIR, CACHE_DIR, CHROOT_BASEDIR, HASH_DIR, TMP_DIR, TMPFS # noqa


APT_PREFERENCES = textwrap.dedent('''
    Package: *
    Pin: release n=bullseye
    Pin-Priority: 900

    Package: grub*
    Pin: version 2.99*
    Pin-Priority: 950
    
    Package: python3-*
    Pin: origin ""
    Pin-Priority: 950
    
    Package: *truenas-samba*
    Pin: version 4.13.*
    Pin-Priority: 950
    
    Package: *netatalk*
    Pin: version 3.1.12~ix*
    Pin-Priority: 950
    
    Package: *zfs*
    Pin: version 2.0.*
    Pin-Priority: 1000
''')


def get_cache_filename(cache_type):
    return f'basechroot-{cache_type}.squashfs'


def get_cache_hash_filename(cache_type):
    return f'{get_cache_filename(cache_type)}.hash'
