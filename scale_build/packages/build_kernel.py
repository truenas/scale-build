import os

from scale_build.exceptions import CallError
from scale_build.utils.run import run
from scale_build.utils.paths import DPKG_OVERLAY


def build_kernel_package(package, log_handle):
    run_args = {'stdout': log_handle, 'stderr': log_handle}
    if os.path.exists(os.path.join(DPKG_OVERLAY, 'packages/Packages.gz')):
        run(
            ['chroot', DPKG_OVERLAY, 'apt', 'update'], exception=CallError,
            exception_msg='Failed apt update', **run_args
        )


