import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path

from .models import IndexReport
from .store import connect, initialize


TEXT_EXTENSIONS = {'.txt', '.md', '.rst', '.csv', '.tsv'}
SKIP_NAMES = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', 'data', 'build', 'dist'}
SECRET_EXTENSIONS = {'.pem', '.key', '.p12', '.pfx'}


def _linked(info) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 1024)


def _fingerprint(info, *, include_ctime=True):
    result = (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
    )
    if include_ctime:
        result += (info.st_ctime_ns,)
    return result


def _read_text(path: Path, info, max_bytes: int) -> tuple[str | None, str]:
    flags = (
        os.O_RDONLY
        | getattr(os, 'O_BINARY', 0)
        | getattr(os, 'O_NOFOLLOW', 0)
    )
    fd = os.open(path, flags)

    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())

        include_ctime = os.name != 'nt'
        if (
            _fingerprint(opened, include_ctime=include_ctime)
            != _fingerprint(info, include_ctime=include_ctime)
        ):
            raise OSError('File changed before reading')

        raw = stream.read(max_bytes + 1)

        after = os.fstat(stream.fileno())
        if _fingerprint(after) != _fingerprint(opened):
            raise OSError('File changed during reading')

    if len(raw) > max_bytes:
        return None, 'too_large'
    if b'\x00' in raw:
        return None, 'binary'
    try:
        return raw.decode('utf-8-sig'), 'indexed'
    except UnicodeDecodeError:
        return None, 'unsupported_encoding'


def index_folder(root: Path, database: Path, *, text: bool = False,
                 excludes: tuple[str, ...] = (), exclude_extensions: tuple[str, ...] = (),
                 max_files: int = 10000, max_bytes: int = 262144,
                 refresh: bool = False, reset_exclusions: bool = False) -> IndexReport:
    if not 1 <= max_files <= 100000:
        raise ValueError('max_files must be in [1, 100000]')
    if not 1 <= max_bytes <= 1048576:
        raise ValueError('max_bytes must be in [1, 1048576]')
    root = root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError('root must be an existing directory')
    database = database.expanduser().resolve()
    excluded_paths = []
    for value in excludes:
        path = Path(value).expanduser()
        path = (root / path).resolve() if not path.is_absolute() else path.resolve()
        if not path.is_relative_to(root):
            raise ValueError('Excluded paths must be inside the indexed root')
        excluded_paths.append(path)
    extensions = set(SECRET_EXTENSIONS)
    for value in exclude_extensions:
        if not value.startswith('.') or '/' in value or '\\' in value:
            raise ValueError('Excluded extensions must look like .pdf')
        extensions.add(value.casefold())
    db_paths = {database, *(Path(str(database) + suffix) for suffix in ('-wal', '-shm', '-journal'))}

    def excluded(path: Path) -> bool:
        relative = path.relative_to(root)
        return (any(part.startswith('.') or part.casefold() in SKIP_NAMES for part in relative.parts)
                or path.suffix.casefold() in extensions or path in db_paths
                or any(path == p or p in path.parents for p in excluded_paths))

    now = datetime.now(timezone.utc).isoformat()
    indexed = unchanged = removed = skipped = 0
    errors = []
    seen = set()
    truncated = False
    visited = 0
    with connect(database) as connection, connection:
        initialize(connection)
        previous = connection.execute('SELECT policy_json FROM scan_roots WHERE root=?',
                                      (str(root),)).fetchone()
        if previous is not None and not reset_exclusions:
            policy = json.loads(previous['policy_json'])
            excluded_paths.extend(Path(p) for p in policy['excludes'])
            extensions.update(policy['exclude_extensions'])
        excluded_paths = list(dict.fromkeys(excluded_paths))
        rows = connection.execute('SELECT * FROM indexed_files WHERE root=?', (str(root),)).fetchall()
        cached = {}
        for row in rows:
            path = Path(row['path'])
            if excluded(path):
                connection.execute('DELETE FROM indexed_files WHERE root=? AND path=?', (str(root), str(path)))
                removed += 1
                continue
            if not text or row['size_bytes'] > max_bytes:
                status = 'disabled' if not text else 'too_large'
                connection.execute('''UPDATE indexed_files SET content=NULL, content_fold=NULL,
                    content_status=? WHERE root=? AND path=?''', (status, str(root), str(path)))
                row = dict(row) | {'content': None, 'content_fold': None, 'content_status': status}
            cached[str(path)] = row
        policy = json.dumps({'text': text, 'excludes': [str(p) for p in excluded_paths],
                             'exclude_extensions': sorted(extensions), 'max_files': max_files,
                             'max_bytes': max_bytes}, ensure_ascii=False)
        connection.execute('INSERT OR REPLACE INTO scan_roots VALUES (?, ?, ?, ?)',
                           (str(root), now, 'partial', policy))
        connection.commit()
        stack = [root]
        while stack and not truncated:
            directory = stack.pop()
            if excluded(directory):
                skipped += 1
                continue
            try:
                if _linked(directory.lstat()) or directory.resolve() != directory:
                    skipped += 1
                    continue
                with os.scandir(directory) as entries:
                    for entry in entries:
                        visited += 1
                        if visited > max_files * 10:
                            truncated = True
                            break
                        path = Path(entry.path)
                        if excluded(path):
                            skipped += 1
                            continue
                        try:
                            info = os.stat(path, follow_symlinks=False)
                            if _linked(info):
                                skipped += 1
                                continue
                            if stat.S_ISDIR(info.st_mode):
                                stack.append(path)
                                continue
                            if not stat.S_ISREG(info.st_mode):
                                skipped += 1
                                continue
                            if len(seen) >= max_files:
                                truncated = True
                                break
                            seen.add(str(path))
                            desired = ('disabled' if not text else
                                       'unsupported_type' if path.suffix.casefold() not in TEXT_EXTENSIONS else
                                       'too_large' if info.st_size > max_bytes else 'indexed')
                            old = cached.get(str(path))
                            stable = (old is not None and old['size_bytes'] == info.st_size
                                      and old['modified_ns'] == info.st_mtime_ns
                                      and old['changed_ns'] == info.st_ctime_ns)
                            if not refresh and stable and old['content_status'] == desired:
                                unchanged += 1
                                continue
                            content, status = None, desired
                            if desired == 'indexed':
                                try:
                                    content, status = _read_text(path, info, max_bytes)
                                except OSError as error:
                                    status = 'unreadable'
                                    errors.append(f'{path}: {error}')
                            connection.execute('''INSERT OR REPLACE INTO indexed_files
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
                                str(root), str(path), path.name, str(path.relative_to(root)), info.st_size,
                                info.st_mtime_ns, info.st_ctime_ns, path.name.casefold(),
                                str(path).casefold(), content, content.casefold() if content is not None else None,
                                status, now))
                            indexed += 1
                        except OSError as error:
                            errors.append(f'{path}: {error}')
            except OSError as error:
                errors.append(f'{directory}: {error}')
        complete = not truncated and not errors
        if complete:
            obsolete = set(cached) - seen
            connection.executemany('DELETE FROM indexed_files WHERE root=? AND path=?',
                                   ((str(root), path) for path in obsolete))
            removed += len(obsolete)
        status = 'complete' if complete else 'truncated' if truncated else 'partial'
        policy = json.dumps({'text': text, 'excludes': [str(p) for p in excluded_paths],
                             'exclude_extensions': sorted(extensions), 'max_files': max_files,
                             'max_bytes': max_bytes}, ensure_ascii=False)
        connection.execute('INSERT OR REPLACE INTO scan_roots VALUES (?, ?, ?, ?)',
                           (str(root), now, status, policy))
    return IndexReport(str(root), status, indexed, unchanged, removed, skipped, tuple(errors), text)