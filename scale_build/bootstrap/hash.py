import hashlib
import json
import logging
import os
import re
import requests
import urllib.parse

from scale_build.utils.manifest import APT_BASE_URL get_manifest
from scale_build.utils.run import run
from scale_build.utils.paths import CACHE_DIR, HASH_DIR

from .utils import get_apt_preferences


logging.getLogger('urllib3').setLevel(logging.INFO)


INSTALLED_PACKAGES_REGEX = re.compile(r'([^\t]+)\t([^\t]+)\t([\S]+)\n')


def get_repo_hash(repo_url, distribution):
    resp = requests.get(urllib.parse.urljoin(repo_url, os.path.join('dists', distribution, 'Release')), timeout=60)
    resp.raise_for_status()
    return hashlib.sha256(resp.content).hexdigest()


def get_all_repo_hash():
    apt_repos = get_manifest()['apt-repos']
    # Start by validating the main APT repo
    all_repo_hash = get_repo_hash(APT_BASE_URL + apt_repos['url'], apt_repos['distribution'])

    for repo_config in apt_repos['additional']:
        all_repo_hash += get_repo_hash(APT_BASE_URL + repo_config['url'], repo_config['distribution'])

    all_repo_hash += hashlib.sha256(get_apt_preferences().encode()).hexdigest()

    return all_repo_hash


class HashMixin:

    @property
    def cache_hash_filename(self):
        return f'{self.cache_filename}.hash'

    @property
    def cache_hash_file_path(self):
        return os.path.join(CACHE_DIR, self.cache_hash_filename)

    def update_mirror_cache(self):
        with open(self.cache_hash_file_path, 'w') as f:
            f.write(get_all_repo_hash())

    @property
    def saved_packages_file_path(self):
        return os.path.join(HASH_DIR, f'{os.path.splitext(self.cache_filename)[0]}_packages.json')

    @property
    def installed_packages_in_cache(self):
        if self.cache_exists:
            with open(self.saved_packages_file_path, 'r') as f:
                return json.loads(f.read().strip())
        else:
            return None

    def update_saved_packages_list(self, installed_packages):
        with open(self.saved_packages_file_path, 'w') as f:
            f.write(json.dumps(installed_packages))

    def get_packages(self):
        return {
            e[0]: {'version': e[1], 'architecture': e[2]}
            for e in INSTALLED_PACKAGES_REGEX.findall(run([
                'chroot', self.chroot_basedir, 'dpkg-query', '-W', '-f', '${Package}\t${Version}\t${Architecture}\n'
            ], log=False).stdout)
        }
