import re

from .run import run
from .paths import GIT_MANIFEST_PATH


# TODO: Let's please use python for git specific bits


def update_git_manifest(git_remote, git_sha, mode='a+'):
    with open(GIT_MANIFEST_PATH, mode) as f:
        f.write(f'{git_remote} {git_sha}\n')


def retrieve_git_remote_and_sha(path):
    return {
        'url': run(['git', '-C', path, 'remote', 'get-url', 'origin']).stdout.strip(),
        'sha': run(['git', '-C', path, 'rev-parse', '--short', 'HEAD']).stdout.strip(),
    }


def retrieve_git_branch(path):
    return run(['git', '-C', path, 'branch', '--show-current']).stdout.strip()


def branch_exists_in_repository(origin, branch):
    cp = run(['git', 'ls-remote', origin])
    return bool(re.findall(fr'/{branch}\n', cp.stdout, re.M))
