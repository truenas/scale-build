import os


BUILDER_DIR = './'
TMPFS = './tmp/tmpfs'
CACHE_DIR = './tmp/cache'
CHROOT_BASEDIR = os.path.join(TMPFS, 'chroot')
CHROOT_OVERLAY = os.path.join(TMPFS, 'chroot-overlay')
DPKG_OVERLAY = './tmp/dpkg-overlay'
GIT_MANIFEST_PATH = './logs/GITMANIFEST'
GIT_LOG_PATH = './logs/git-checkout.log'
HASH_DIR = './tmp/pkghashes'
LOG_DIR = './logs'
MANIFEST = './conf/build.manifest'
PARALLEL_BUILDS = int(os.environ.get('PARALLEL_BUILDS') or 4)
PKG_DEBUG = bool(os.environ.get('PKG_DEBUG'))
PKG_DIR = './tmp/pkgdir'
REQUIRED_RAM = 16  # GB
SOURCES_DIR = './sources'
TMP_DIR = './tmp'
WORKDIR_OVERLAY = os.path.join(TMPFS, 'workdir-overlay')


if PKG_DEBUG:
    PARALLEL_BUILDS = 1
