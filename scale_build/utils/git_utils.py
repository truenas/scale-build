from .run import run
from .variables import GIT_MANIFEST_PATH


# TODO: Let's please use python for git specific bits


def update_git_manifest(git_remote, git_sha):
    with open(GIT_MANIFEST_PATH, 'a+') as f:
        f.write(f'{git_remote} {git_sha}\n')


def retrieve_git_remote_and_sha(path):
    return {
        'url': run(['git', '-C', path, 'remote', 'get-url', 'origin']).stdout.decode(),
        'sha': run(['git', '-C', path, 'rev-parse', '--short', 'HEAD']).stdout.decode(),
    }


def retrieve_git_branch(path):
    return run(['git', '-C', path, 'branch', '--show-current']).stdout.decode()
