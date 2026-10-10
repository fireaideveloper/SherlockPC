"""Validate source-only Windows release inputs without build dependencies."""
from __future__ import annotations

import json
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def release_metadata(root: Path) -> tuple[str, str]:
    version = (root / 'VERSION').read_text(encoding='ascii').strip()
    if re.fullmatch(r'[0-9]+\.[0-9]+(?:\.[0-9]+)?', version) is None:
        raise ValueError('Expected a numeric release version')
    config = json.loads((root / 'desktop/src-tauri/tauri.conf.json').read_text(encoding='utf-8'))
    native_version = version + '.0' if version.count('.') == 1 else version
    if config.get('version') != native_version:
        raise ValueError('VERSION and Tauri version disagree')
    notes = root / f'RELEASE_NOTES_v{version}.md'
    if not notes.is_file() or not notes.stat().st_size:
        raise FileNotFoundError(f'Required release notes are missing or empty: {notes}')
    return version, native_version


def validate_release_inputs(root: Path = ROOT) -> tuple[str, str]:
    if (root / 'desktop/src-tauri/binares').exists():
        raise ValueError('Remove legacy typo directory desktop/src-tauri/binares')
    required = (
        'VERSION', 'pyproject.toml', 'desktop/package.json',
        'desktop/package-lock.json', 'desktop/src-tauri/tauri.conf.json',
        'desktop/src-tauri/Cargo.toml', 'desktop/src-tauri/build.rs',
        'desktop/src-tauri/src/main.rs', 'sherlock/desktop_bridge.py',
        'build_support/build_desktop_sidecar.py',
        'build_support/package_desktop_release.py', 'tests/test_telemetry.py',
    )
    for name in required:
        path = root / name
        if not path.is_file() or not path.stat().st_size:
            raise FileNotFoundError(f'Required release input is missing or empty: {name}')
    if not (root / 'desktop/src-tauri/binaries').is_dir():
        raise FileNotFoundError('Required sidecar directory is missing: desktop/src-tauri/binaries')
    version, native_version = release_metadata(root)
    package = json.loads((root / 'desktop/package.json').read_text(encoding='utf-8'))
    python = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))
    cargo = tomllib.loads((root / 'desktop/src-tauri/Cargo.toml').read_text(encoding='utf-8'))
    if python['project']['version'] != version:
        raise ValueError('VERSION and Python project version disagree')
    if package['version'] != native_version or cargo['package']['version'] != native_version:
        raise ValueError('VERSION, npm and Cargo versions disagree')
    tauri_root = root / 'desktop/src-tauri'
    config = json.loads((tauri_root / 'tauri.conf.json').read_text(encoding='utf-8'))
    bundle = config['bundle']
    nsis = bundle['windows']['nsis']
    assets = [*bundle['icon'], nsis['installerIcon'], nsis['installerHooks']]
    for name in assets:
        path = tauri_root / name
        if not path.is_file() or not path.stat().st_size:
            raise FileNotFoundError(f'Required Tauri asset is missing or empty: {name}')
    for locale in ('en', 'ru', 'es', 'pt-BR', 'zh-CN', 'fr', 'it', 'de', 'ja', 'ko', 'ar', 'hi'):
        path = root / f'desktop/src/locales/{locale}.json'
        catalog = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(catalog, dict) or not catalog:
            raise ValueError(f'Invalid locale catalog: {locale}')
    return version, native_version


if __name__ == '__main__':
    try:
        version, _ = validate_release_inputs()
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(f'ERROR: {error}') from error
    print(f'Release preflight: OK (v{version}, Windows x64)')
