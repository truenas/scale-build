import os

from scale_build.exceptions import CallError
from scale_build.utils.environment import APT_ENV
from scale_build.utils.run import run
from scale_build.utils.paths import CHROOT_BASEDIR


PACKAGE_PATH = os.path.join(CHROOT_BASEDIR, 'packages')


def run_in_chroot(command, logger=None, exception_message=None, **kwargs):
    return run(
        f'chroot {CHROOT_BASEDIR} /bin/bash -c "{command}"', shell=True, logger=logger,
        exception=CallError, exception_msg=exception_message, env={**APT_ENV, **os.environ}, **kwargs
    )
