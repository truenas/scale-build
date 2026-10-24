"""Exercise installer orchestration without mounting or modifying host storage."""

import contextlib
import importlib
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def install_flow(tmp_path, monkeypatch):
    # License parsing is unrelated to identity; the proprietary package is absent in CI.
    license_module = ModuleType('licenselib.license')
    license_module.ContractType = object
    license_module.License = object
    monkeypatch.setitem(sys.modules, 'licenselib', ModuleType('licenselib'))
    monkeypatch.setitem(sys.modules, 'licenselib.license', license_module)
    installer = importlib.import_module('truenas_install.__main__')
    target = tmp_path / 'target'
    target.mkdir()
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'manifest.json').write_text(json.dumps({'version': 'identity-test', 'kernel_version': 'test'}))
    iso_data = tmp_path / 'iso-data'
    iso_data.mkdir()
    (iso_data / '.vendor').write_text(json.dumps({'name': 'HexOS'}))
    old = tmp_path / 'old'
    old.mkdir()
    for name in ('data', 'etc', 'home', 'root'):
        (old / name).mkdir()
    (old / 'data/.vendor').write_text(json.dumps({'name': 'HexOS'}))
    (old / 'etc/hostid').write_bytes(b'old!')
    (old / 'etc/machine-id').write_text('existing-machine-id')
    state = SimpleNamespace(
        installer=installer, target=target, old=old, calls=[], checkpoints=[], clone=False,
        snapshot_ok=True, executable=True, writer_error=False, excluded=[], iso_data=iso_data,
    )

    @contextlib.contextmanager
    def target_directory():
        yield str(target)

    def extract(command, **_kwargs):
        assert command[0] == 'unsquashfs'
        assert command[command.index('-d') + 1] == str(target)
        state.calls.append(command)
        exclusions = Path(command[command.index('-exclude-file') + 1]).read_bytes()
        state.excluded = exclusions.splitlines()
        for name in ('conf', 'etc', 'data', 'dev', 'proc', 'sys', 'boot/grub', 'usr/bin'):
            (target / name).mkdir(exist_ok=True, parents=True)
        if state.executable:
            executable = target / 'usr/bin/truenas-hexos-identity'
            executable.write_text('#!/usr/bin/python3\n')
            executable.chmod(0o755)
        return SimpleNamespace(stdout=io.BytesIO(b''), returncode=0, wait=lambda: 0)

    def copy_entry(src, dest):
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

    def command(cmd, **kwargs):
        state.calls.append(cmd)
        output = ''
        code = 0
        if cmd[:2] == ['zpool', 'get']:
            output = 'boot-pool/ROOT/previous'
        elif cmd[:2] == ['zfs', 'get']:
            output = 'grub'
        elif cmd[:2] == ['zfs', 'snapshot'] and '@install-' in cmd[-1]:
            code = 0 if state.snapshot_ok else 1
        elif cmd[:2] == ['zfs', 'list']:
            output = '12345' if 'guid' in cmd else ''
        elif cmd[:3] == ['mount', '-t', 'zfs']:
            if cmd[-1] == str(target / 'data') and state.clone and state.snapshot_ok:
                shutil.copytree(old / 'data', target / 'data', dirs_exist_ok=True)
        elif cmd[:2] == ['cp', '/etc/hostid']:
            (target / 'etc/hostid').write_bytes(b'iso!')
        elif cmd[:3] == ['cp', '-r', '/data/.']:
            shutil.copytree(iso_data, target / 'data', dirs_exist_ok=True)
        elif cmd[0] == 'rsync':
            assert kwargs['cwd'] == str(old)
            args = iter(cmd[2:-1])
            for name in args:
                if name == '--exclude':
                    next(args)
                    continue
                copy_entry(old / name, target / name)
        elif cmd[:2] == ['grub-install', '--version'] or cmd[2:] == ['grub-install', '--version']:
            output = 'grub-install (GRUB) fixture'
        elif cmd[0] == 'chroot' and cmd[2] == '/usr/bin/truenas-hexos-identity':
            assert (target / 'data/first-boot').is_file()
            assert json.loads((target / 'data/.vendor').read_text())['name'] == 'HexOS'
            for fs in ('devtmpfs', 'proc', 'sysfs'):
                assert any(c[:3] == ['mount', '-t', fs] for c in state.calls)
            assert not any(c[:3] == ['mount', '-t', 'zfs'] and c[-1] == str(target / 'boot/grub')
                           for c in state.calls)
            if state.writer_error:
                raise subprocess.CalledProcessError(1, cmd)
            # The native writer has its own tests. This fixture proves where it is invoked.
            namespace = target / 'data/hexos-identity'
            namespace.mkdir()
            (namespace / 'identity.json').write_text('writer fixture')
        return subprocess.CompletedProcess(cmd, code, stdout=output, stderr='')

    real_initialize = installer.initialize_hexos_identity

    def initialize(root, fresh, run_command):
        state.checkpoints.append((root, fresh))
        return real_initialize(root, fresh, run_command)

    monkeypatch.setattr(installer, 'initialize_hexos_identity', initialize)
    monkeypatch.setattr(installer, 'run_command', command)
    monkeypatch.setattr(installer.subprocess, 'Popen', extract)
    monkeypatch.setattr(installer.subprocess, 'run', lambda *_a, **_k: pytest.fail('Unisolated subprocess'))
    monkeypatch.setattr(installer.tempfile, 'TemporaryDirectory', target_directory)
    monkeypatch.setattr(installer, 'getmntinfo', lambda: [
        SimpleNamespace(mountpoint=str(old), mount_source='boot-pool/ROOT/previous')
    ] if state.clone else [])
    exists = installer.os.path.exists
    monkeypatch.setattr(
        installer.os.path, 'exists', lambda path: False if path == '/sys/firmware/efi' else exists(path),
    )

    def run(upgrade=False):
        payload = {'src': str(source), 'pool_name': 'boot-pool', 'disks': [], 'dataset_name': 'boot-pool/ROOT/test'}
        if upgrade:
            payload['old_root'] = str(old)
        monkeypatch.setattr(installer.sys, 'stdin', io.StringIO(json.dumps(payload)))
        installer.main()

    state.run = run
    return state


def writer_calls(flow):
    return [cmd for cmd in flow.calls if cmd[0] == 'chroot' and cmd[2] == '/usr/bin/truenas-hexos-identity']


def test_main_fresh_identity_runs_after_branding_and_mounts_before_bootloader(install_flow, capsys):
    flow = install_flow
    flow.run()
    assert flow.checkpoints == [(str(flow.target), True)]
    assert writer_calls(flow) == [[
        'chroot', str(flow.target), '/usr/bin/truenas-hexos-identity', 'install-create', '--installer',
    ]]
    identity_index = flow.calls.index(writer_calls(flow)[0])
    assert flow.calls.index(['cp', '-r', '/data/.', f'{flow.target}/data/']) < identity_index
    assert flow.calls.index(['chmod', '-R', 'u=rwX,g=,o=', str(flow.target / 'data')]) < identity_index
    assert (flow.target / 'etc/hostid').read_bytes() == b'iso!'
    assert 'Installation completed successfully' in capsys.readouterr().out


@pytest.mark.parametrize('clone', [False, True])
@pytest.mark.parametrize('identity', [None, b'{"version":1,"id":"' + b'a' * 64 + b'"}', b'corrupt existing record'])
def test_main_upgrade_preserves_identity_in_copy_and_clone_paths(install_flow, clone, identity, capsys):
    flow = install_flow
    flow.clone = clone
    record = Path('data/hexos-identity/identity.json')
    if identity is not None:
        (flow.old / record).parent.mkdir()
        (flow.old / record).write_bytes(identity)
    flow.run(upgrade=True)
    assert flow.checkpoints == [(str(flow.target), False)]
    assert writer_calls(flow) == []
    assert (flow.target / 'etc/hostid').read_bytes() == b'old!'
    assert not (flow.target / 'data/first-boot').exists()
    if identity is None:
        assert not (flow.target / record).parent.exists()
    else:
        assert (flow.target / record).read_bytes() == identity
        if clone:
            assert str(record).encode() in flow.excluded
    copies = [cmd for cmd in flow.calls if cmd[0] == 'rsync']
    assert len(copies) == 1
    assert ('data' in copies[0]) is not clone
    assert any(cmd[:2] == ['zfs', 'clone'] for cmd in flow.calls) is clone
    assert 'Upgrade completed successfully' in capsys.readouterr().out


def test_main_upgrade_failed_snapshot_uses_copy_without_identity_rotation(install_flow):
    flow = install_flow
    flow.clone = True
    flow.snapshot_ok = False
    namespace = flow.old / 'data/hexos-identity'
    namespace.mkdir()
    (namespace / 'identity.json').write_bytes(b'preserve exactly')
    flow.run(upgrade=True)
    assert writer_calls(flow) == []
    assert (flow.target / 'data/hexos-identity/identity.json').read_bytes() == b'preserve exactly'
    assert any(cmd[0] == 'rsync' and 'data' in cmd for cmd in flow.calls)
    assert not any(cmd[:2] == ['zfs', 'clone'] for cmd in flow.calls)


@pytest.mark.parametrize('failure', ['missing-reader', 'writer-error'])
def test_main_identity_failure_unmounts_and_does_not_mark_install_successful(install_flow, failure, capsys):
    flow = install_flow
    flow.executable = failure != 'missing-reader'
    flow.writer_error = failure == 'writer-error'
    expected = RuntimeError if failure == 'missing-reader' else subprocess.CalledProcessError
    with pytest.raises(expected):
        flow.run()
    unmounts = [cmd for cmd in flow.calls if cmd[0] == 'umount']
    assert unmounts[:3] == [['umount', str(flow.target / fs)] for fs in ('sys', 'proc', 'dev')]
    assert unmounts[-1] == ['umount', str(flow.target)]
    assert not any('update-grub' in cmd for cmd in flow.calls)
    assert ['zpool', 'set', 'bootfs=boot-pool/ROOT/previous', 'boot-pool'] in flow.calls
    assert 'completed successfully' not in capsys.readouterr().out


@pytest.mark.parametrize('vendor', [None, {'name': 'TrueNAS'}])
def test_main_unbranded_fresh_install_completes_without_identity_writer(install_flow, vendor, capsys):
    flow = install_flow
    marker = flow.iso_data / '.vendor'
    if vendor is None:
        marker.unlink()
    else:
        marker.write_text(json.dumps(vendor))
    flow.executable = False
    flow.run()
    assert writer_calls(flow) == []
    assert not (flow.target / 'data/hexos-identity').exists()
    assert 'Installation completed successfully' in capsys.readouterr().out


def test_main_legacy_upgrade_does_not_require_identity_executable(install_flow, capsys):
    flow = install_flow
    flow.executable = False
    flow.run(upgrade=True)
    assert writer_calls(flow) == []
    assert not (flow.target / 'data/hexos-identity').exists()
    assert 'Upgrade completed successfully' in capsys.readouterr().out


@pytest.mark.parametrize('vendor', ['{broken', '[]'])
def test_main_identity_validation_failure_reaches_installer_ui(install_flow, vendor, capsys):
    flow = install_flow
    (flow.iso_data / '.vendor').write_text(vendor)
    with pytest.raises((ValueError, TypeError)):
        flow.run()
    messages = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert any('Unable to initialize HexOS installation identity' in value.get('error', '') for value in messages)
    assert not writer_calls(flow)
    assert not any('update-grub' in cmd for cmd in flow.calls)


def test_main_missing_identity_writer_reaches_installer_ui(install_flow, capsys):
    flow = install_flow
    flow.executable = False
    with pytest.raises(RuntimeError):
        flow.run()
    messages = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert any('missing the installation identity reader and writer' in value.get('error', '') for value in messages)
