import os

from contextlib import contextmanager
from scale_build.utils.paths import RELEASE_DIR
from scale_build.utils.run import run
from tempfile import NamedTemporaryFile


MTREE_FILE_NAME = 'rootfs.mtree'
MTREE_UPDATE_FILE = f'{RELEASE_DIR}/{MTREE_FILE_NAME}'
MTREE_DIRS = ['boot', 'etc', 'usr', 'opt', 'var']

# The following is list of default etc files to remove from our image before we
# generate mtree file and then the squashfs filesystem. Generally we should put
# files that are generated via middleware and not required for first boot to
# eliminate files being flagged as changed rather than simply added to our
# base install.
ETC_FILES_TO_REMOVE = [
    'etc/exports',
    'etc/ftpusers',
    'etc/idmapd.conf',
    'etc/hosts',
    'etc/krb5.conf',
    'etc/motd',
    'etc/nscd.conf',
    'etc/resolv.conf',
    'etc/avahi/avahi-daemon.conf',
    'etc/avahi/services/nut.service',
    'etc/chrony/chrony.conf',
    'etc/default/rpcbind',
    'etc/default/smartmontools',
    'etc/netdata/netdata.conf',
    'etc/nginx/nginx.conf',
    'etc/proftpd/proftpd.conf',
    'etc/proftpd/tls.conf',
    'etc/smartd.conf',
    'etc/snmp/snmpd.conf',
    'etc/ssh/sshd_config',
    'etc/syslog-ng/syslog-ng.conf',
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
            '--exclude', './etc/fstab',
            '--exclude', './etc/group',
            '--exclude', './etc/hostname',
            '--exclude', './etc/hostname',
            '--exclude', './etc/machine-id',
            '--exclude', './etc/nsswitch.conf',
            '--exclude', './etc/passwd',
            '--exclude', './etc/shadow',
            '--exclude', './etc/sudoers',
            '--exclude', './etc/nut',
            '--exclude', './etc/dhcp/dhclient.conf',
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
        os.unlink(os.path.join(target_root_dir, file))

    mtree_file_path = os.path.realpath(MTREE_UPDATE_FILE)

    with chdir(target_root_dir):
        _do_mtree_impl(mtree_file_path, version)

    mtree_file_checksum = run(['sha256sum', mtree_file_path], log=False).stdout.strip().split()[0]
    with open(f'{mtree_file_path}.sha256', 'w') as f:
        f.write(mtree_file_checksum)
        f.flush()

    return mtree_file_path
