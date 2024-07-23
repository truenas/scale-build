import os

from scale_build.config import SIGNING_KEY, SIGNING_PASSWORD
from scale_build.utils.paths import RELEASE_DIR
from scale_build.utils.run import run

MTREE_DIRS = ['boot', 'usr', 'opt', 'var']


def generate_mtree(target_root_dir, mtree_file):
    cwd = os.getcwd()
    os.chdir(target_root_dir)

    mtree_file_path = os.path.join(cwd, mtree_file)
    mt_tgz = f'{mtree_file_path}.tgz'

    try:
        cmd = [
            '/usr/bin/bsdtar',
            '-f', mtree_file_path,
            '-c', '--format=mtree',
            '--options', '!all,mode,uid,gid,type,link,size,sha256',
        ]
        run(cmd + MTREE_DIRS)
        run(['tar', '-cvzf', mt_tgz, mtree_file_path])
        os.unlink(mtree_file_path)
    finally:
        os.chdir(cwd)

    if SIGNING_KEY:
        sign_mtree_file(mt_tgz, SIGNING_KEY, SIGNING_PASSWORD)

    return mt_tgz


def mtree_update_file(version=None):
    return f'{RELEASE_DIR}/rootfs.mtree'


def sign_mtree_file(mtree_file, signing_key, signing_pass):
    run(
        f'echo "{signing_pass}" | gpg -ab --batch --yes --no-use-agent --pinentry-mode loopback --passphrase-fd 0 '
        f'--default-key {signing_key} --output {mtree_file}.sig --sign {mtree_file}', shell=True,
        exception_msg='Failed gpg signing with SIGNING_PASSWORD', log=False,
    )
