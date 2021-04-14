import os
import shutil

from scale_build.utils.run import run
from scale_build.utils.variables import CHROOT_OVERLAY, DPKG_OVERLAY, WORKDIR_OVERLAY


def remove_overlay_fs():
    for command in (
        ['umount', '-f', os.path.join(DPKG_OVERLAY, 'var/cache/apt')],
        ['umount', '-f', os.path.join(DPKG_OVERLAY, 'packages')],
        ['umount', '-f', os.path.join(DPKG_OVERLAY, 'proc')],
        ['umount', '-f', os.path.join(DPKG_OVERLAY, 'sys')],
        ['umount', '-f', DPKG_OVERLAY],
        ['umount', '-R', '-f', DPKG_OVERLAY],
    ):
        run(command, check=False)

    for path in (CHROOT_OVERLAY, DPKG_OVERLAY, WORKDIR_OVERLAY):
        shutil.rmtree(path, ignore_errors=True)
