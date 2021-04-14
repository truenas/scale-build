import os

from scale_build.utils.run import run
from scale_build.utils.variables import DPKG_OVERLAY, TMP_DIR


KERNTMP = os.path.join(TMP_DIR, 'kern')


def mount_kernel(kernel_dir=None):
    # In all cases where package being built is not the kernel itself, our
    # kernel source is mounted to /kernel so that it's visible to developer
    # when debugging a package build failure.
    if not kernel_dir:
        kernel_dir = 'kernel'
    kernel_lower = os.path.join(DPKG_OVERLAY, kernel_dir)
    os.makedirs(kernel_lower, exist_ok=True)
    run(['mount', '--bind', KERNTMP, kernel_lower])


def umount_kernel(kernel_dir=None):
    if not kernel_dir:
        kernel_dir = 'kernel'

    run(['umount', '-f', os.path.join(DPKG_OVERLAY, kernel_dir)])


def pre_build(package):
    if package.name == 'kernel':
        pass
