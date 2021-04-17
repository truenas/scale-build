import os
import shutil

from scale_build.bootstrap.cache import restore_basecache
from scale_build.utils.run import run
from scale_build.utils.variables import CHROOT_BASEDIR, PKG_DIR, TMPFS

from .utils import PACKAGE_PATH


def setup_chroot_basedir(basecache_type, logger=None):
    shutil.rmtree(CHROOT_BASEDIR, ignore_errors=True)
    os.makedirs(TMPFS, exist_ok=True)
    run(
        ['mount', '-t', 'tmpfs', '-o', f'size=12G', 'tmpfs', TMPFS],
        logger=logger
    )
    restore_basecache(basecache_type, CHROOT_BASEDIR, logger)
    run(['mount', 'proc', os.path.join(CHROOT_BASEDIR, 'proc'), '-t', 'proc'], logger=logger)
    run(['mount', 'sysfs', os.path.join(CHROOT_BASEDIR, 'sys'), '-t', 'sysfs'], logger=logger)
    os.makedirs(PACKAGE_PATH, exist_ok=True)
    run(['mount', '--bind', PKG_DIR, PACKAGE_PATH], logger=logger)


def umount_chroot_basedir():
    for command in (
        ['umount', '-f', PACKAGE_PATH],
        ['umount', '-f', os.path.join(CHROOT_BASEDIR, 'proc')],
        ['umount', '-f', os.path.join(CHROOT_BASEDIR, 'sys')],
        ['umount', '-f', TMPFS],
    ):
        run(command)
