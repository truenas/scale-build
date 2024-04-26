import argparse
import json
import pathlib
import subprocess

SCALE_BUILD_ROOT = pathlib.Path(__file__).parent.parent.resolve()
SCALE_BUILD_SOURCES = pathlib.Path(SCALE_BUILD_ROOT, 'sources')


def repo_json(dir, since):
    print('Yellow')


def git_command(dir, command):
    _cmd = ['git', '-C', dir]
    _cmd.extend(command)
    # print(' '.join(_cmd))
    cp = subprocess.run(_cmd, stdout=subprocess.PIPE, encoding='utf8')
    output = []
    for line in cp.stdout.split('\n'):
        line = line.strip()
        if line:
            output.append(line)
    return output


def git_branch(dir):
    return git_command(dir, ['branch', '--show-current'])[0]


def git_origin(dir):
    return git_command(dir, ['config', '--get', 'remote.origin.url'])[0]


def git_commits(dir, since, long=False):
    origin = git_origin(dir)
    if origin.endswith('.git'):
        origin = origin[:-4]
    result = []
    command = ['log', f'--since={since}', '--oneline', '--decorate=no']
    if long:
        command.append('--no-abbrev-commit')
    for line in git_command(dir, command):
        commit = line.split()[0]
        data = {
            'commit': commit,
            'url': f'{origin}/commit/{commit}',
            'text': line[len(commit) + 1:]
        }
        result.append(data)
    return result


def generate(since):
    result = []
    for dir in filter(lambda x: x.is_dir(), SCALE_BUILD_SOURCES.iterdir()):
        data = {
            'name': dir.name,
            'branch': git_branch(dir.as_posix()),
            'commits': git_commits(dir.as_posix(), since),
        }
        result.append(data)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("since", type=int, help="Start time in seconds since epoch")
    parser.add_argument("--pretty", help="Pretty-print JSON output", action="store_true")
    args = parser.parse_args()
    data = generate(args.since)
    if args.pretty:
        print(json.dumps(data, indent=4))
    else:
        print(json.dumps(data))
