from scale_build.utils.manifest import get_manifest
from scale_build.utils.run import run # noqa
from scale_build.utils.paths import BUILDER_DIR, CACHE_DIR, CHROOT_BASEDIR, HASH_DIR, TMP_DIR, TMPFS # noqa
from scale_build.utils.types import BootstrapDirectoryType  # noqa


def get_apt_preferences():
    return '\n\n'.join(
        '\n'.join(f'{k}: {v}' for k, v in pref.items()) for pref in get_manifest()['apt_preferences']
    )


def get_cache_filename(cache_type):
    return f'basechroot-{cache_type.name}.squashfs'


def get_cache_hash_filename(cache_type):
    return f'{get_cache_filename(cache_type)}.hash'
