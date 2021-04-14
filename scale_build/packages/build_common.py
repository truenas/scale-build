import os

from distutils.dir_util import copy_tree
from scale_build.utils.run import run
from scale_build.utils.variables import DPKG_OVERLAY, TMP_DIR

from .overlayfs import make_kernel_overlay
from .utils import chroot_run


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


def pre_build(package, log_handle):
    if package.name == 'kernel':
        make_kernel_overlay(log_handle)
        mount_kernel(package.chroot_source_directory)
    else:
        mount_kernel()
        copy_tree(package.source_path, os.path.join(DPKG_OVERLAY, package.chroot_source_directory))

    if package.kernel_module:
        for command in (
            'apt install -y /packages/linux-headers-truenas*',
            'apt install -y /packages/linux-image-truenas*',
        ):
            chroot_run(command, log_handle)

    if package.predepscmd:
        log_handle.write(f'Running predepcmd: {package.predepscmd}\n')
        chroot_run([''])
