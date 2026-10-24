"""Build the real update manifest against a private minimal image tree."""
import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace


def test_update_artifact_includes_identity_module(tmp_path, monkeypatch):
    from scale_build.image import manifest
    source = Path(__file__).parents[1]
    builder = tmp_path / 'builder'
    builder.mkdir()
    shutil.copytree(source, builder / 'truenas_install', ignore=shutil.ignore_patterns('__pycache__'))
    root = tmp_path / 'root'
    (root / 'etc').mkdir(parents=True)
    (root / 'etc/version').write_text('identity-packaging-fixture')
    (root / 'boot').mkdir()
    (root / 'boot/vmlinuz-fixture-production+truenas').write_bytes(b'fixture')
    update = tmp_path / 'update'
    update.mkdir()
    monkeypatch.setattr(manifest, 'BUILDER_DIR', str(builder))
    monkeypatch.setattr(manifest, 'CHROOT_BASEDIR', str(root))
    monkeypatch.setattr(manifest, 'UPDATE_DIR', str(update))
    monkeypatch.setattr(manifest.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout='1024 root'))
    assert manifest.build_manifest() == 'identity-packaging-fixture'
    name = 'truenas_install/hexos_identity.py'
    assert (update / name).read_bytes() == (source / 'hexos_identity.py').read_bytes()
    index = json.loads((update / 'manifest.json').read_text())
    assert index['checksums'][name] == hashlib.sha1((update / name).read_bytes()).hexdigest()
