import os
import subprocess


TMPFS = './tmp/tmpfs'
CACHE_DIR = './tmp/cache'
CHROOT_BASEDIR = os.path.join(TMPFS, 'chroot')
CHROOT_OVERLAY = os.path.join(TMPFS, 'chroot-overlay')
DPKG_OVERLAY = './tmp/dpkg-overlay'
HASH_DIR = './tmp/pkghashes'
LOG_DIR = './logs'
MANIFEST = './conf/build.manifest'
PARALLEL_BUILDS = int(os.environ.get('PARALLEL_BUILDS') or 4)
PKG_DEBUG = bool(os.environ.get('PKG_DEBUG'))
PKG_DIR = './tmp/pkgdir'
SOURCES = './sources'
WORKDIR_OVERLAY = os.path.join(TMPFS, 'workdir-overlay')


if PKG_DEBUG:
    PARALLEL_BUILDS = 1


def run(*args, **kwargs):
    if isinstance(args[0], list):
        args = tuple(args[0])
    kwargs.setdefault('stdout', subprocess.PIPE)
    kwargs.setdefault('stderr', subprocess.PIPE)
    check = kwargs.pop('check', True)
    proc = subprocess.Popen(args, stdout=kwargs['stdout'], stderr=kwargs['stderr'])
    stdout, stderr = proc.communicate()
    cp = subprocess.CompletedProcess(args, proc.returncode, stdout=stdout, stderr=stderr)
    if check:
        cp.check_returncode()
    return cp
