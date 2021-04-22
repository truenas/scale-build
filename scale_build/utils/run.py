import os
import pexpect
import subprocess

from scale_build.exceptions import CallError


def run(*args, **kwargs):
    if isinstance(args[0], list):
        args = tuple(args[0])
    kwargs.setdefault('stdout', subprocess.PIPE)
    kwargs.setdefault('stderr', subprocess.PIPE)
    exception_message = kwargs.pop('exception_msg', None)
    check = kwargs.pop('check', True)
    shell = kwargs.pop('shell', False)
    logger = kwargs.pop('logger', None)
    env = kwargs.pop('env', None) or os.environ
    if logger:
        kwargs['stderr'] = subprocess.STDOUT

    proc = subprocess.Popen(args, stdout=kwargs['stdout'], stderr=kwargs['stderr'], shell=shell, env=env)
    if logger:
        for line in map(lambda l: l.rstrip().decode(errors='ignore'), iter(proc.stdout.readline, b'')):
            logger.debug(line)

    stdout, stderr = proc.communicate()

    cp = subprocess.CompletedProcess(args, proc.returncode, stdout=stdout, stderr=stderr)
    if check:
        error_str = exception_message or stderr or ''
        error_str = error_str.decode(errors='ignore') if isinstance(error_str, bytes) else error_str
        if cp.returncode:
            raise CallError(
                f'Command {" ".join(args) if isinstance(args, list) else args!r} returned exit code '
                f'{cp.returncode}' + (f' ({error_str})' if error_str else '')
            )
    return cp


def interactive_run(command):
    child = pexpect.spawnu(command)
    print(f'Executing {command!r} command')
    child.interact()
    child.kill(1)
