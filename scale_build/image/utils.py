import json
import os
import shutil

from scale_build.exceptions import CallError
from scale_build.utils.environment import APT_ENV
from scale_build.utils.run import run
from scale_build.utils.paths import CHROOT_BASEDIR, TMP_DIR

from .manifest import UPDATE_FILE


PACKAGE_PATH = os.path.join(CHROOT_BASEDIR, 'packages')
IMAGE_VERSION = None


def run_in_chroot(command, logger=None, exception_message=None, **kwargs):
    return run(
        ['chroot', CHROOT_BASEDIR] + command, logger=logger, exception_msg=exception_message,
        env={**APT_ENV, **os.environ}, **kwargs
    )


def get_image_version():
    global IMAGE_VERSION
    if IMAGE_VERSION:
        return IMAGE_VERSION

    if not os.path.exists(UPDATE_FILE):
        raise CallError(f'{UPDATE_FILE!r} update file does not exist')

    mount_dir = os.path.join(TMP_DIR, 'update_dir')
    if os.path.exists(mount_dir):
        shutil.rmtree(mount_dir)
    os.makedirs(mount_dir)
    try:
        run(['mount', UPDATE_FILE, mount_dir, '-t', 'squashfs', '-o', 'loop'])
        with open(os.path.join(mount_dir, 'manifest.json'), 'r') as f:
            update_manifest = json.loads(f.read())
        IMAGE_VERSION = update_manifest['version']
    finally:
        run(['umount', '-f', mount_dir])
        shutil.rmtree(mount_dir)

    return IMAGE_VERSION
