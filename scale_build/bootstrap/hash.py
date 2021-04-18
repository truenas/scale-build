import hashlib
import logging
import os
import requests
import urllib.parse

from scale_build.exceptions import CallError

from .utils import CHROOT_BASEDIR, get_apt_preferences, get_manifest, run


to_disable = ('requests', 'urllib3')
for name in filter(lambda k: k.startswith(to_disable), logging.Logger.manager.loggerDict.keys()):
    custom_logger = logging.getLogger(name)
    custom_logger.disabled = True


def get_repo_hash(repo_url, distribution):
    resp = requests.get(urllib.parse.urljoin(repo_url, os.path.join('dists', distribution, 'Release')))
    if resp.status_code != 200:
        raise CallError(f'Unable to retrieve hash for {repo_url}')
    return hashlib.sha256(resp.content).hexdigest()


def get_all_repo_hash():
    apt_repos = get_manifest()['apt-repos']
    # Start by validating the main APT repo
    all_repo_hash = get_repo_hash(apt_repos['url'], apt_repos['distribution'])

    for repo_config in apt_repos['additional']:
        all_repo_hash += get_repo_hash(repo_config['url'], repo_config['distribution'])

    all_repo_hash += hashlib.sha256(get_apt_preferences().encode()).hexdigest()

    return all_repo_hash


def get_base_hash():
    cp = run(['chroot', CHROOT_BASEDIR, 'apt', 'list', '--installed'])
    return hashlib.sha256(cp.stdout.strip()).hexdigest()
