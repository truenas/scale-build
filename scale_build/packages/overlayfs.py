import os
import shutil

from distutils.dir_util import copy_tree
from scale_build.exceptions import CallError
from scale_build.utils.run import run
from scale_build.utils.variables import (
    CACHE_DIR, CHROOT_BASEDIR, CHROOT_OVERLAY, DPKG_OVERLAY, PKG_DIR, SOURCES_DIR, WORKDIR_OVERLAY
)

from .build_common import KERNTMP, mount_kernel, umount_kernel


# TODO: Let's please see if we should maybe move this to package class

# Kernel build variables
# Config options can be overridden by adding a stub
# config with kernel parameters to scripts/package/truenas/extra.config
# in the kernel source directory and uncommenting EXTRA_KERNEL_CONFIG
# Debug kernel can be built by uncommenting DEBUG_KERNEL


KERNDEPS = ['flex', 'bison', 'dwarves', 'libssl-dev']
KERNMERGE = './scripts/kconfig/merge_config.sh'
TN_CONFIG = 'scripts/package/truenas/tn.config'
DEBUG_CONFIG = 'scripts/package/truenas/debug.config'
EXTRA_CONFIG = 'scripts/package/truenas/extra.config'


def make_kernel_overlay(log_handle):
    # Generate kernel overlay (but not mount).
    # This makes our debian directory and kernel config used for building
    # debian folder is required to install pre-build dependencies.
    # TODO: Please add debug kernel bits after deciding how best to access the env variables
    os.makedirs(KERNTMP, exist_ok=True)
    copy_tree(os.path.join(SOURCES_DIR, 'kernel'), KERNTMP)
    mount_kernel()
    for entry in (
        (
            f'chroot {DPKG_OVERLAY} /bin/bash -c "apt install -y {" ".join(KERNDEPS)}"',
            'Failed to install kernel build dependencies.'
        ),
        'chroot {DPKG_OVERLAY} /bin/bash -c "cd kernel && make defconfig"',
        'chroot {DPKG_OVERLAY} /bin/bash -c "cd kernel && make syncconfig"',
        'chroot {DPKG_OVERLAY} /bin/bash -c "cd kernel && make archprepare"',
        (
            f'chroot {DPKG_OVERLAY} /bin/bash -c "cd kernel && {KERNMERGE} .config {TN_CONFIG}"',
            'Failed to merge config'
        ),
        'chroot {DPKG_OVERLAY} /bin/bash -c "cd kernel && ./scripts/package/mkdebian"',

    ):
        if len(entry) == 2:
            command, msg = entry
        else:
            command = entry
            msg = 'Failed to configure kernel'

        run(command, stdout=log_handle, stderr=log_handle, shell=True, exception=CallError, exception_msg=msg)

    umount_kernel()


def delete_kernel_overlay():
    umount_kernel()
    shutil.rmtree(KERNTMP, ignore_errors=True)
