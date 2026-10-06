import hashlib
import json
import struct
from pathlib import Path

import pytest

from build_support.package_desktop_release import package_release, require_gui_executable


def pe_image(subsystem=2, magic=0x20b):
    data = bytearray(512)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 128)
    data[128:132] = b'PE\0\0'
    struct.pack_into('<H', data, 148, 240)
    struct.pack_into('<H', data, 152, magic)
    struct.pack_into('<H', data, 220, subsystem)
    return bytes(data)


def build_tree(root: Path):
    tauri = root / 'desktop/src-tauri'
    nsis = tauri / 'target/release/bundle/nsis'
    nsis.mkdir(parents=True)
    (tauri / 'tauri.conf.json').write_text(json.dumps({'version': '0.1.0'}))
    (root / 'VERSION').write_text('0.1\n')
    (tauri / 'target/release/sherlockpc.exe').write_bytes(pe_image())
    installer = nsis / 'SherlockPC_0.1.0_x64-setup.exe'
    installer.write_bytes(b'MZinstaller\x00\xff')
    (root / 'RELEASE_NOTES_v0.1.md').write_text('Release notes', encoding='utf-8')
    return installer


def test_package_special_path_and_replace(tmp_path):
    root = tmp_path / "Sherlock ПК's project ! & (1)"
    installer = build_tree(root)
    previous = root / 'release'
    previous.mkdir()
    (previous / 'stale.exe').write_bytes(b'old')
    result = package_release(root)
    name = 'SherlockPC-v0.1-Setup.exe'
    assert (result / name).read_bytes() == installer.read_bytes()
    assert (result / 'SHA256SUMS.txt').read_text() == f'{hashlib.sha256(installer.read_bytes()).hexdigest()}  {name}\n'
    assert {p.name for p in result.iterdir()} == {name, 'SHA256SUMS.txt', 'RELEASE_NOTES.md'}
    assert not (root / 'release.previous').exists()


@pytest.mark.parametrize('failure', ['missing', 'empty', 'invalid'])
def test_bad_build_preserves_previous_release(tmp_path, failure):
    installer = build_tree(tmp_path)
    release = tmp_path / 'release'
    release.mkdir()
    (release / 'keep.txt').write_text('existing release')
    if failure == 'missing':
        installer.unlink()
    else:
        installer.write_bytes(b'' if failure == 'empty' else b'not an exe')
    with pytest.raises((FileNotFoundError, ValueError)):
        package_release(tmp_path)
    assert (release / 'keep.txt').read_text() == 'existing release'


def test_failed_publish_restores_previous_release(tmp_path, monkeypatch):
    build_tree(tmp_path)
    release = tmp_path / 'release'
    release.mkdir()
    (release / 'keep.txt').write_text('old')
    original = Path.rename
    def rename(path, target):
        if path.name.startswith('release-stage-'):
            raise OSError('simulated locked directory')
        return original(path, target)
    monkeypatch.setattr(Path, 'rename', rename)
    with pytest.raises(OSError):
        package_release(tmp_path)
    assert (release / 'keep.txt').read_text() == 'old'


@pytest.mark.parametrize('image', [pe_image(3), b'MZfake', pe_image()[:170], pe_image(magic=0)])
def test_invalid_or_console_app_cannot_be_published(tmp_path, image):
    build_tree(tmp_path)
    (tmp_path / 'desktop/src-tauri/target/release/sherlockpc.exe').write_bytes(image)
    release = tmp_path / 'release'
    release.mkdir()
    (release / 'keep.txt').write_text('old')
    with pytest.raises(ValueError):
        package_release(tmp_path)
    assert (release / 'keep.txt').read_text() == 'old'


@pytest.mark.parametrize('magic', [0x10b, 0x20b])
def test_gui_pe32_and_pe32plus_accepted(tmp_path, magic):
    app = tmp_path / 'app.exe'
    app.write_bytes(pe_image(magic=magic))
    require_gui_executable(app)


def test_version_mismatch_cannot_be_published(tmp_path):
    build_tree(tmp_path)
    (tmp_path / 'VERSION').write_text('0.2')
    with pytest.raises(ValueError, match='disagree'):
        package_release(tmp_path)
