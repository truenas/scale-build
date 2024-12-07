from datetime import datetime
import hashlib
import json
import os
import shutil
import subprocess

from scale_build.exceptions import CallError
from scale_build.utils.kernel import get_kernel_version
from scale_build.utils.paths import BUILDER_DIR, CHROOT_BASEDIR, RELEASE_DIR, UPDATE_DIR


RELEASE_MANIFEST = os.path.join(RELEASE_DIR, 'manifest.json')


def get_version():
    with open(os.path.join(CHROOT_BASEDIR, 'etc/version')) as f:
        return f.read().strip()


def build_manifest():
    version = get_version()

    size = int(int(subprocess.run(
        ['du', '--block-size', '1', '-d', '0', '-x', CHROOT_BASEDIR],
        check=True, stdout=subprocess.PIPE, encoding='utf-8', errors='ignore',
    ).stdout.split()[0]) * 1.1)

    shutil.copytree(
        os.path.join(BUILDER_DIR, 'truenas_install'),
        os.path.join(UPDATE_DIR, 'truenas_install'),
    )

    checksums = {}
    for root, dirs, files in os.walk(UPDATE_DIR):
        for file in files:
            abspath = os.path.join(root, file)
            with open(abspath, 'rb') as f:
                # FIXME: before we release 25.04.0 proper, change this to sha256
                checksums[os.path.relpath(abspath, UPDATE_DIR)] = hashlib.file_digest(f, 'sha1').hexdigest()

    with open(os.path.join(UPDATE_DIR, 'manifest.json'), "w") as f:
        f.write(json.dumps({
            'date': datetime.utcnow().isoformat(),
            'version': version,
            'size': size,
            'checksums': checksums,
            'kernel_version': get_kernel_version(CHROOT_BASEDIR),
        }))

    return version


def build_release_manifest(update_file, update_file_checksum):
    with open(os.path.join(UPDATE_DIR, 'manifest.json')) as f:
        manifest = json.load(f)

    with open(RELEASE_MANIFEST, 'w') as f:
        json.dump({
            'filename': os.path.basename(update_file),
            'version': manifest['version'],
            'date': manifest['date'],
            'changelog': '',
            'checksum': update_file_checksum,
            'filesize': os.path.getsize(update_file),
        }, f)


def get_image_version(vendor=None):
    if not os.path.exists(RELEASE_MANIFEST):
        raise CallError(f'{RELEASE_MANIFEST!r} does not exist')

    with open(RELEASE_MANIFEST) as f:
        vendor = f'-{vendor}' if vendor else ''
        return f"{json.load(f)['version']}{vendor}"


def update_file_path(version=None):
    return os.path.join(RELEASE_DIR, f'TrueNAS-SCALE-{version or get_image_version()}.update')


def update_file_checksum_path(version=None):
    return f'{update_file_path(version)}.sha256'
