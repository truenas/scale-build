import hashlib
import os
import shutil

from .config import BUILDER_DIR
from .exceptions import CallError
from .image.utils import run_in_chroot
from .utils.paths import PKG_DIR
from .utils.run import run


VENDORED_PACKAGES_DIR = os.path.join(BUILDER_DIR, 'conf/vendored-packages')
# Debian security fixes that the pinned goldeye apt mirror snapshot predates.
VENDORED_PACKAGES = {
    'ca-certificates_20250419~deb12u2_all.deb': 'b9f76b5271a7ac373fd5e7e1b5b826a71ddd702b42a0d104955ecb1acfffc94b',
}


def add_vendored_packages():
    # PKG_DIR is wiped whenever the package bootstrap cache is rebuilt, so this has to run after that
    # and must regenerate the index itself in case no source package gets rebuilt.
    for filename, sha256 in VENDORED_PACKAGES.items():
        src = os.path.join(VENDORED_PACKAGES_DIR, filename)
        with open(src, 'rb') as f:
            if hashlib.file_digest(f, 'sha256').hexdigest() != sha256:
                raise CallError(f'{src!r} does not match its pinned sha256')
        shutil.copyfile(src, os.path.join(PKG_DIR, filename))

    run(f'cd {PKG_DIR} && dpkg-scanpackages --multiversion . /dev/null | gzip -9c > Packages.gz', shell=True)


def verify_vendored_packages():
    # The `origin ""` pin makes file:/packages win over the mirrors, so a vendored package would
    # silently shadow a newer mirror version; fail instead so it gets dropped.
    for filename in VENDORED_PACKAGES:
        name, version = filename.split('_')[:2]
        installed = run_in_chroot(['dpkg-query', '-W', '-f', '${Version}', name], log=False).stdout.strip()
        if installed != version:
            raise CallError(f'{name} {installed!r} is installed instead of vendored {version!r}')

        for line in run_in_chroot(['apt-cache', 'madison', name], log=False).stdout.splitlines():
            _, available, source = map(str.strip, line.split('|'))
            if source.startswith('file:/packages'):
                continue
            if run_in_chroot(['dpkg', '--compare-versions', available, 'ge', version], check=False).returncode == 0:
                raise CallError(f'{name} {available} is available from the apt mirrors, drop vendored {filename}')
