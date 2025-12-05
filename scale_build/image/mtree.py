import os
import hashlib
import shutil

from contextlib import contextmanager
from scale_build.utils.paths import RELEASE_DIR
from scale_build.utils.run import run
from tempfile import NamedTemporaryFile


MTREE_FILE_NAME = 'rootfs.mtree'
MTREE_UPDATE_FILE = f'{RELEASE_DIR}/{MTREE_FILE_NAME}'
MTREE_DIRS = ['boot', 'etc', 'usr', 'opt', 'var', 'conf/audit_rules']

# The following is list of default etc files to remove from our image before we
# generate mtree file and then the squashfs filesystem. Generally we should put
# files that are generated via middleware and not required for first boot to
# eliminate files being flagged as changed rather than simply added to our
# base install.
ETC_FILES_TO_REMOVE = [
    'etc/audit/rules.d/audit.rules',  # Not used by TrueNAS
    'etc/exports',
    'etc/ftpusers',
    'etc/idmapd.conf',
    'etc/hostname',
    'etc/hosts',
    'etc/krb5.conf',
    'etc/mailname',
    'etc/motd',
    'etc/nscd.conf',
    'etc/resolv.conf',
    'etc/avahi/avahi-daemon.conf',
    'etc/avahi/services/nut.service',
    'etc/chrony/chrony.conf',
    'etc/default/rpcbind',
    # 'etc/netdata/netdata.conf',  # FIXME: please fix this once aligned with newer netdata packages
    'etc/nginx/nginx.conf',
    'etc/nvme/hostid',
    'etc/nvme/hostnqn',
    'etc/proftpd/proftpd.conf',
    'etc/proftpd/tls.conf',
    'etc/security/limits.conf',
    'etc/snmp/snmpd.conf',
    'etc/ssh/sshd_config',
    'etc/subuid',
    'etc/subgid',
    'etc/syslog-ng/syslog-ng.conf',
    'etc/rc2.d/K01ssh',             # systemd removes these symlinks on ssh start
    'etc/rc3.d/K01ssh',
    'etc/rc4.d/K01ssh',
    'etc/rc5.d/K01ssh',
    'etc/initramfs-tools/modules',  # These two are not used by systemd
    'etc/modules',
]

# The following is a list of directories to remove from our image before we
# generate the mtree file. These are directories that dynamically get removed
# during normal TrueNAS operation and should be removed to avoid tripping up
# the verification.
DIRS_TO_REMOVE = [
    'etc/nfs.conf.d',
]

# Some files or directories get the permission mode changed on install.
# The following is a list of tuples (files, mode).
# Preemptively change the mode before generating the mtree.
OBJS_TO_FIXUP = [
]


@contextmanager
def chdir(target_root_dir):
    # WARNING: this changes path resolution for relative paths.
    #
    # The stage of build process where this happens is single-threaded
    # and so it should be safe to do this, but this context manager should
    # be used with caution if it is imported into other parts of scale-build.
    old_cwd = os.getcwd()
    os.chdir(target_root_dir)
    try:
        yield
    finally:
        os.chdir(old_cwd)


def _do_mtree_impl(mtree_file_path, version):
    with NamedTemporaryFile(mode='w+', encoding='utf-8') as f:
        # We should add exclude paths for files that should exist on first
        # boot, but we dynamically generate on truenas or contain data that
        # changes routinely
        cmd = [
            '/usr/bin/bsdtar',
            '-f', f.name,
            '-c', '--format=mtree',
            '--exclude', './boot/initrd.img*',
            '--exclude', './etc/aliases',
            '--exclude', './etc/audit/audit.rules',  # TrueNAS managed and audited
            '--exclude', './etc/console-setup/cached_setup_*',
            '--exclude', './etc/default/keyboard',
            '--exclude', './etc/default/kdump-tools',
            '--exclude', './etc/default/zfs',        # Modifed in usr/local/bin/truenas-initrd.py
            '--exclude', './etc/fstab',
            '--exclude', './etc/group',
            '--exclude', './etc/machine-id',
            '--exclude', './etc/nsswitch.conf',
            '--exclude', './etc/passwd',
            '--exclude', './etc/shadow',
            '--exclude', './etc/sudoers',
            '--exclude', './etc/nfs.conf',
            '--exclude', './etc/nut',
            '--exclude', './etc/dhcpcd.conf',
            '--exclude', './etc/dhcp/dhclient.conf',
            '--exclude', './etc/libvirt',
            '--exclude', './etc/default/libvirt-guests',
            '--exclude', './etc/pam.d/common-account',
            '--exclude', './etc/pam.d/common-auth',
            '--exclude', './etc/pam.d/common-password',
            '--exclude', './etc/pam.d/common-session',
            '--exclude', './etc/pam.d/common-session-noninteractive',
            '--exclude', './etc/pam.d/sshd',
            '--exclude', './usr/lib/debug/*',
            '--exclude', './usr/lib/debug/*',
            '--exclude', './var/cache',
            '--exclude', './var/trash',
            '--exclude', './var/spool/*',
            '--exclude', './var/log/*',
            '--exclude', './var/lib/dbus/machine-id',
            '--exclude', './var/lib/certmonger/cas/*',
            '--exclude', './var/lib/smartmontools/*',
            '--options', '!all,mode,uid,gid,type,link,size,sha256',
        ]
        run(cmd + MTREE_DIRS)
        with open(mtree_file_path, 'w') as mtree_file:
            mtree_file.write(f'# {version}\n')

            for line in f:
                mtree_file.write(line)

            mtree_file.flush()


def generate_mtree(target_root_dir, version):

    # There are various default files distributed by packages that
    # we replace when we etc.generate. If they're not required for
    # first boot, then remove from update file.
    for file in ETC_FILES_TO_REMOVE:
        try:
            os.unlink(os.path.join(target_root_dir, file))
        except FileNotFoundError:
            # We want to avoid failing the build if the object is
            # aleady removed.  Possibly time to update the list.
            pass

    # Same for directories
    for dir in DIRS_TO_REMOVE:
        try:
            shutil.rmtree(os.path.join(target_root_dir, dir))
        except FileNotFoundError:
            # We want to avoid failing the build if the object is
            # aleady removed.  Possibly time to update the list.
            pass

    # Some files and/or directories get their permission mode changed
    # after install.  We preemptively make those mode changes here
    # to avoid unnecessary reporting.
    for fs_obj, mode in OBJS_TO_FIXUP:
        os.chmod(os.path.join(target_root_dir, fs_obj), mode)

    mtree_file_path = os.path.realpath(MTREE_UPDATE_FILE)

    with chdir(target_root_dir):
        _do_mtree_impl(mtree_file_path, version)

    with open(mtree_file_path, 'rb') as f:
        with open(f'{mtree_file_path}.sha256', 'w') as sf:
            sf.write(hashlib.file_digest(f, 'sha256').hexdigest())
            sf.flush()

    return mtree_file_path
