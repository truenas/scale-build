import re

from urllib.parse import urlparse

from .run import run
from .paths import GIT_MANIFEST_PATH


# TODO: Let's please use python for git specific bits


def update_git_manifest(git_remote, git_sha, mode='a+'):
    with open(GIT_MANIFEST_PATH, mode) as f:
        f.write(f'{git_remote} {git_sha}\n')


def retrieve_git_remote_and_sha(path):
    return {
        'url': get_origin_uri(path),
        'sha': run(['git', '-C', path, 'rev-parse', '--short', 'HEAD'], log=False).stdout.strip(),
    }


def retrieve_git_branch(path):
    return run(['git', '-C', path, 'branch', '--show-current'], log=False).stdout.strip()


def branch_exists_in_repository(origin, branch):
    cp = run(['git', 'ls-remote', origin], log=False)
    return bool(re.findall(fr'/{branch}\n', cp.stdout, re.M))


def branch_checked_out_locally(path, branch):
    return bool(run(['git', '-C', path, 'branch', '--list', branch], log=False).stdout.strip())


def create_branch(path, base_branch, new_branch):
    run(['git', '-C', path, 'checkout', '-b', new_branch, base_branch])


def get_origin_uri(path):
    return run(['git', '-C', path, 'remote', 'get-url', 'origin'], log=False).stdout.strip()


def push_changes(path, api_token, branch):
    url = urlparse(get_origin_uri(path))
    run(['git', '-C', path, 'push', f'https://{api_token}@{url.hostname}{url.path}', branch])


def fetch_origin(path):
    run(['git', '-C', path, 'fetch', 'origin'])


def safe_checkout(path, branch):
    fetch_origin(path)
    if branch_exists_in_repository(get_origin_uri(path), branch):
        run(['git', '-C', path, 'checkout', branch])
    else:
        run(['git', '-C', path, 'checkout', '-b', branch])
