from datetime import datetime
import glob
import json
import os
import shutil
import subprocess

from scale_build.utils.variables import CHROOT_BASEDIR, RELEASE_DIR, UPDATE_DIR


UPDATE_FILE = os.path.join(RELEASE_DIR, 'TrueNAS-SCALE.update')
UPDATE_FILE_HASH = f'{UPDATE_FILE}.sha256'


def build_manifest():
    with open(os.path.join(CHROOT_BASEDIR, 'etc/version')) as f:
        version = f.read().strip()

    size = int(int(subprocess.run(
        ['du', '--block-size', '1', '-d', '0', '-x', CHROOT_BASEDIR],
        check=True, stdout=subprocess.PIPE, encoding='utf-8', errors='ignore',
    ).stdout.split()[0]) * 1.1)

    shutil.copytree(
        os.path.join(os.path.dirname(__file__), '../truenas_install'),
        os.path.join(UPDATE_DIR, 'truenas_install'),
    )

    checksums = {}
    for root, dirs, files in os.walk(UPDATE_DIR):
        for file in files:
            abspath = os.path.join(root, file)
            checksums[os.path.relpath(abspath, UPDATE_DIR)] = subprocess.run(
                ['sha1sum', abspath],
                check=True, stdout=subprocess.PIPE, encoding='utf-8', errors='ignore',
            ).stdout.split()[0]

    with open(os.path.join(UPDATE_DIR, 'manifest.json'), "w") as f:
        f.write(json.dumps({
            'date': datetime.utcnow().isoformat(),
            'version': version,
            'size': size,
            'checksums': checksums,
            'kernel_version': glob.glob(
                os.path.join(CHROOT_BASEDIR, 'boot/vmlinuz-*')
            )[0].split('/')[-1][len('vmlinuz-'):],
        }))


def build_update_manifest(update_file_checksum):
    with open(os.path.join(UPDATE_DIR, 'manifest.json')) as f:
        manifest = json.load(f)

    with open(os.path.join(RELEASE_DIR, 'manifest.json'), 'w') as f:
        json.dump({
            'filename': os.path.basename(UPDATE_FILE),
            'version': manifest['version'],
            'date': manifest['date'],
            'changelog': '',
            'checksum': update_file_checksum,
        }, f)
