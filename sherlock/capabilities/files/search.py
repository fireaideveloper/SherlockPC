from pathlib import Path

from .models import SearchHit
from .store import connect, validate


def search_files(database: Path, query: str, *, root: Path | None = None,
                 limit: int = 20) -> tuple[SearchHit, ...]:
    query = query.strip().casefold()
    if not query or len(query) > 256:
        raise ValueError('query must contain 1-256 non-blank characters')
    if not 1 <= limit <= 200:
        raise ValueError('limit must be in [1, 200]')
    root_value = str(root.expanduser().resolve()) if root is not None else None
    with connect(database.expanduser(), readonly=True) as connection:
        validate(connection)
        rows = connection.execute('''SELECT f.*, r.status AS scan_status,
            CASE WHEN f.name_fold = :q THEN 0
                 WHEN instr(f.name_fold, :q) > 0 THEN 1
                 WHEN instr(coalesce(f.content_fold, ''), :q) > 0 THEN 2 ELSE 3 END AS rank
            FROM indexed_files f JOIN scan_roots r ON r.root = f.root
            WHERE (:root IS NULL OR f.root = :root)
              AND (instr(f.name_fold, :q) > 0 OR instr(f.path_fold, :q) > 0
                   OR instr(coalesce(f.content_fold, ''), :q) > 0)
            ORDER BY rank, f.path, f.root LIMIT :limit''',
            {'q': query, 'root': root_value, 'limit': limit}).fetchall()
    hits = []
    for row in rows:
        match = 'name' if row['rank'] < 2 else 'content' if row['rank'] == 2 else 'path'
        snippet = None
        if match == 'content' and row['content'] is not None:
            # Casefold can expand characters; snippets are approximate context only.
            start = max(0, row['content_fold'].find(query) - 40)
            snippet = row['content'][start:start + 180].replace('\n', ' ')
        hits.append(SearchHit(row['root'], row['path'], row['name'], row['size_bytes'],
                              row['modified_ns'], row['content_status'], match, snippet,
                              row['indexed_at'], row['scan_status']))
    return tuple(hits)


def forget_root(database: Path, root: Path) -> int:
    # mode=rw requires an existing DB; it cannot create one on a typo.
    import sqlite3
    connection = sqlite3.connect(database.expanduser().resolve().as_uri() + '?mode=rw', uri=True)
    try:
        with connection:
            validate(connection)
            root_value = str(root.expanduser().resolve())
            count = connection.execute('DELETE FROM indexed_files WHERE root=?', (root_value,)).rowcount
            connection.execute('DELETE FROM scan_roots WHERE root=?', (root_value,))
        return count
    finally:
        connection.close()
