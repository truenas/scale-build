import contextlib
import os

from scale_build.utils.variables import HASH_DIR, PKG_DIR


def clean_previous_packages(package_name, log_handle):
    pkglist_path = os.path.join(HASH_DIR, f'{package_name}.pkglist')
    if not os.path.exists(pkglist_path):
        # Nothing to do
        return

    with open(pkglist_path, 'r') as f:
        to_remove = [p for p in map(str.strip, f.read().split()) if p]

    os.unlink(pkglist_path)
    if not to_remove:
        return

    log_handle.write(f'Removing previously built packages for {package_name}:\n')
    for name in to_remove:
        with contextlib.suppress(OSError, FileNotFoundError):
            os.unlink(os.path.join(PKG_DIR, name))
