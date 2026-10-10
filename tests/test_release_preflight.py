import json
from pathlib import Path
import shutil

import pytest

from build_support.release_preflight import release_metadata, validate_release_inputs


@pytest.fixture
def source_tree(tmp_path):
    root = Path(__file__).resolve().parents[1]
    names = [
        'VERSION', 'pyproject.toml', 'RELEASE_NOTES_v0.1.md',
        'desktop/package.json', 'desktop/package-lock.json',
        'desktop/src-tauri/tauri.conf.json', 'desktop/src-tauri/Cargo.toml',
        'desktop/src-tauri/build.rs', 'desktop/src-tauri/src/main.rs',
        'desktop/src-tauri/installer-hooks.nsh', 'sherlock/desktop_bridge.py',
        'build_support/build_desktop_sidecar.py',
        'build_support/package_desktop_release.py', 'tests/test_telemetry.py',
    ]
    names.extend(str(p.relative_to(root)) for p in (root / 'desktop/src-tauri/icons').iterdir())
    names.extend(str(p.relative_to(root)) for p in (root / 'desktop/src/locales').glob('*.json'))
    for name in names:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
    (tmp_path / 'desktop/src-tauri/binaries').mkdir()
    return tmp_path


def test_preflight_succeeds_without_compiled_outputs(source_tree):
    assert validate_release_inputs(source_tree) == ('0.1', '0.1.0')
    assert not (source_tree / 'desktop/src-tauri/target').exists()


@pytest.mark.parametrize('name', [
    'RELEASE_NOTES_v0.1.md', 'desktop/src-tauri/icons/icon.ico',
    'desktop/src-tauri/installer-hooks.nsh', 'desktop/package-lock.json',
    'build_support/build_desktop_sidecar.py', 'sherlock/desktop_bridge.py',
])
@pytest.mark.parametrize('empty', [False, True])
def test_incomplete_source_fails_before_build(source_tree, name, empty):
    path = source_tree / name
    if empty:
        path.write_bytes(b'')
    else:
        path.unlink()
    with pytest.raises(FileNotFoundError):
        validate_release_inputs(source_tree)
    assert not (source_tree / 'release').exists()


def test_legacy_directory_is_rejected(source_tree):
    (source_tree / 'desktop/src-tauri/binares').mkdir()
    with pytest.raises(ValueError, match='legacy typo'):
        validate_release_inputs(source_tree)


@pytest.mark.parametrize('name', ['pyproject.toml', 'desktop/src-tauri/Cargo.toml', 'desktop/package.json'])
def test_cross_package_version_mismatch(source_tree, name):
    path = source_tree / name
    path.write_text(path.read_text().replace('0.1', '0.2'), encoding='utf-8')
    with pytest.raises(ValueError, match='disagree'):
        validate_release_inputs(source_tree)


@pytest.mark.parametrize('value', ['', '.', '0..1', 'v0.1', '../0.1'])
def test_invalid_public_version(source_tree, value):
    (source_tree / 'VERSION').write_text(value)
    with pytest.raises(ValueError, match='numeric release version'):
        release_metadata(source_tree)


def test_missing_locale_is_rejected(source_tree):
    (source_tree / 'desktop/src/locales/ar.json').unlink()
    with pytest.raises(FileNotFoundError):
        validate_release_inputs(source_tree)


def test_configured_installer_asset_is_validated(source_tree):
    path = source_tree / 'desktop/src-tauri/tauri.conf.json'
    config = json.loads(path.read_text())
    config['bundle']['windows']['nsis']['installerHooks'] = 'missing-hooks.nsh'
    path.write_text(json.dumps(config))
    with pytest.raises(FileNotFoundError, match='missing-hooks'):
        validate_release_inputs(source_tree)
