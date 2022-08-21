import os

from scale_build.config import BUILDER_DIR


LOG_DIR = os.path.join(BUILDER_DIR, 'logs')
TMP_DIR = os.path.join(BUILDER_DIR, 'tmp')
TMPFS = os.path.join(TMP_DIR, 'tmpfs')
BRANCH_OUT_LOG_FILENAME = 'git-branchout.log'
BRANCH_OUT_LOG_DIR = os.path.join(LOG_DIR, 'branchout')
CACHE_DIR = os.path.join(TMP_DIR, 'cache')
CD_DIR = os.path.join(TMP_DIR, 'cdrom')
CD_FILES_DIR = os.path.join(BUILDER_DIR, 'conf/cd-files')
CHROOT_BASEDIR = os.path.join(TMPFS, 'chroot')
CHROOT_OVERLAY = os.path.join(TMPFS, 'chroot-overlay')
CONF_GRUB = os.path.join(BUILDER_DIR, 'scripts/grub.cfg')
DPKG_OVERLAY = os.path.join(TMP_DIR, 'dpkg-overlay')
GIT_MANIFEST_PATH = os.path.join(LOG_DIR, 'GITMANIFEST')
GIT_LOG_DIR_NAME = 'git'
GIT_LOG_DIR = os.path.join(LOG_DIR, GIT_LOG_DIR_NAME)
HASH_DIR = os.path.join(TMP_DIR, 'pkghashes')
MANIFEST = os.path.join(BUILDER_DIR, 'conf/build.manifest')
PKG_DIR = os.path.join(TMP_DIR, 'pkgdir')
PKG_LOG_DIR = os.path.join(LOG_DIR, 'packages')
REFERENCE_FILES = ('etc/group', 'etc/passwd')
REFERENCE_FILES_DIR = os.path.join(BUILDER_DIR, 'conf/reference-files')
RELEASE_DIR = os.path.join(TMP_DIR, 'release')
SOURCES_DIR = os.path.join(BUILDER_DIR, 'sources')
UPDATE_DIR = os.path.join(TMP_DIR, 'update')
WORKDIR_OVERLAY = os.path.join(TMPFS, 'workdir-overlay')
