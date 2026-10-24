import json
import subprocess

import pytest

from truenas_install.hexos_identity import initialize_hexos_identity


@pytest.fixture
def target(tmp_path):
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data/.vendor').write_text(json.dumps({'name': 'HexOS'}))
    executable = tmp_path / 'usr/bin/truenas-hexos-identity'
    executable.parent.mkdir(parents=True)
    executable.write_text('#!/usr/bin/python3\n')
    executable.chmod(0o755)
    return tmp_path


def test_fresh_hexos_target_invokes_required_writer(target):
    calls = []
    initialize_hexos_identity(target, True, calls.append)
    assert calls == [['chroot', str(target), '/usr/bin/truenas-hexos-identity', 'install-create', '--installer']]


@pytest.mark.parametrize('namespace', [None, b'{"version":1,"id":"' + b'a' * 64 + b'"}', b'bad state'])
def test_upgrades_neither_create_nor_replace_identity(target, namespace):
    record = target / 'data/hexos-identity/identity.json'
    if namespace is not None:
        record.parent.mkdir()
        record.write_bytes(namespace)
    (target / 'usr/bin/truenas-hexos-identity').unlink()
    initialize_hexos_identity(target, False, lambda _cmd: pytest.fail('Upgrade invoked fresh identity writer'))
    if namespace is None:
        assert not record.parent.exists()
    else:
        assert record.read_bytes() == namespace


@pytest.mark.parametrize('vendor', [None, {}, {'name': 'Other'}])
def test_non_hexos_fresh_installs_do_not_invoke_writer(target, vendor):
    path = target / 'data/.vendor'
    if vendor is None:
        path.unlink()
    else:
        path.write_text(json.dumps(vendor))
    initialize_hexos_identity(target, True, lambda _cmd: pytest.fail('Non-HexOS invoked writer'))
    assert not (target / 'data/hexos-identity').exists()


@pytest.mark.parametrize('mode', ['missing', 'not-executable'])
def test_hexos_install_cannot_silently_ship_without_reader(target, mode):
    path = target / 'usr/bin/truenas-hexos-identity'
    if mode == 'missing':
        path.unlink()
    else:
        path.chmod(0o600)
    with pytest.raises(RuntimeError, match='missing'):
        initialize_hexos_identity(target, True, lambda _cmd: pytest.fail('Invalid executable invoked'))


def test_identity_creation_error_aborts_installer(target):
    def fail(command):
        raise subprocess.CalledProcessError(1, command)
    with pytest.raises(subprocess.CalledProcessError):
        initialize_hexos_identity(target, True, fail)


def test_invalid_vendor_is_not_silently_treated_as_unbranded(target):
    (target / 'data/.vendor').write_text('broken')
    with pytest.raises(ValueError):
        initialize_hexos_identity(target, True, lambda _cmd: pytest.fail('Malformed vendor invoked writer'))
