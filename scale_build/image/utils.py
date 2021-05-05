import functools
import json
import os
import tempfile

from scale_build.exceptions import CallError
from scale_build.utils.environment import APT_ENV
from scale_build.utils.run import run
from scale_build.utils.paths import CHROOT_BASEDIR

from .manifest import UPDATE_FILE


PACKAGE_PATH = os.path.join(CHROOT_BASEDIR, 'packages')


def run_in_chroot(command, exception_message=None, **kwargs):
    return run(
        ['chroot', CHROOT_BASEDIR] + command, exception_msg=exception_message, env={**APT_ENV, **os.environ}, **kwargs
    )


@functools.cache
def get_image_version():
    if not os.path.exists(UPDATE_FILE):
        raise CallError(f'{UPDATE_FILE!r} update file does not exist')

    with tempfile.TemporaryDirectory() as mount_dir:
        try:
            run(['mount', UPDATE_FILE, mount_dir, '-t', 'squashfs', '-o', 'loop'])
            with open(os.path.join(mount_dir, 'manifest.json'), 'r') as f:
                update_manifest = json.loads(f.read())
            return update_manifest['version']
        finally:
            run(['umount', '-f', mount_dir])
