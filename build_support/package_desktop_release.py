from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import tempfile
import struct

if __package__:
    from .release_preflight import release_metadata
else:
    from release_preflight import release_metadata

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def require_gui_executable(path: Path) -> None:
    with path.open('rb') as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b'MZ':
            raise ValueError(f'Invalid Windows executable: {path}')
        pe_offset = struct.unpack_from('<I', header, 60)[0]
        if pe_offset < 64:
            raise ValueError(f'Invalid PE header: {path}')
        stream.seek(pe_offset)
        pe = stream.read(24)
        if len(pe) != 24 or pe[:4] != b'PE\0\0':
            raise ValueError(f'Invalid PE signature: {path}')
        optional_size = struct.unpack_from('<H', pe, 20)[0]
        optional = stream.read(optional_size)
        if len(optional) != optional_size or optional_size < 70:
            raise ValueError(f'Truncated PE optional header: {path}')
        if struct.unpack_from('<H', optional)[0] not in (0x10b, 0x20b):
            raise ValueError(f'Unsupported PE optional header: {path}')
        if struct.unpack_from('<H', optional, 68)[0] != 2:
            raise ValueError('SherlockPC is a console executable. Rebuild with windows_subsystem = "windows" before packaging.')


def package_release(root: Path = ROOT) -> Path:
    version, native_version = release_metadata(root)
    target = root / 'desktop/src-tauri/target/release'
    installer = target / 'bundle/nsis' / f'SherlockPC_{native_version}_x64-setup.exe'
    notes = root / f'RELEASE_NOTES_v{version}.md'
    for path in (target / 'sherlockpc.exe', installer, notes):
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(f'Required build output is missing or empty: {path}')
    require_gui_executable(target / 'sherlockpc.exe')
    with installer.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise ValueError(f'Installer is not a Windows executable: {installer}')
    release = root / 'release'
    backup = root / 'release.previous'
    if backup.exists():
        raise FileExistsError(f'Previous release backup exists; review it before retrying: {backup}')
    stage = Path(tempfile.mkdtemp(prefix='release-stage-', dir=root))
    try:
        name = f'SherlockPC-v{version}-Setup.exe'
        shutil.copy2(installer, stage / name)
        shutil.copy2(notes, stage / 'RELEASE_NOTES.md')
        checksum = sha256(stage / name)
        if checksum != sha256(installer):
            raise OSError('Installer copy verification failed')
        (stage / 'SHA256SUMS.txt').write_text(f'{checksum}  {name}\n', encoding='ascii')
        if release.exists():
            release.rename(backup)
        try:
            stage.rename(release)
        except OSError:
            if backup.exists():
                backup.rename(release)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    print(f'Release artifacts ready: {release}')
    print(f'SHA256: {checksum}')
    return release


if __name__ == '__main__':
    try:
        package_release()
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(f'ERROR: {error}') from error
