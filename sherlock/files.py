"""Index an explicit folder and search its local file index."""
import argparse
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from sherlock.capabilities.files.indexer import index_folder
from sherlock.capabilities.files.search import forget_root, search_files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    index = sub.add_parser('index', help='Scan one folder; content is opt-in')
    index.add_argument('root', type=Path)
    index.add_argument('--text', action='store_true', help='Index UTF-8 txt/md/rst/csv/tsv contents')
    index.add_argument('--exclude', action='append', default=[], help='Exclude path under root; repeatable, retained across scans')
    index.add_argument('--exclude-extension', action='append', default=[])
    index.add_argument('--reset-exclusions', action='store_true', help='Replace saved custom exclusions with those supplied now')
    index.add_argument('--max-files', type=int, default=10000)
    index.add_argument('--max-bytes', type=int, default=262144)
    index.add_argument('--refresh', action='store_true', help='Reread eligible text even if metadata is unchanged')
    search = sub.add_parser('search', help='Literal Unicode substring search')
    search.add_argument('query')
    search.add_argument('--root', type=Path)
    search.add_argument('--limit', type=int, default=20)
    forget = sub.add_parser('forget', help='Remove one root from the index, preserving source files')
    forget.add_argument('root', type=Path)
    for command in (index, search, forget):
        command.add_argument('--db', type=Path, default=Path('data/files.db'))
        command.add_argument('--json', action='store_true')
    args = parser.parse_args()
    exit_code = 0
    try:
        if args.command == 'index':
            report = index_folder(args.root, args.db, text=args.text,
                excludes=tuple(args.exclude), exclude_extensions=tuple(args.exclude_extension),
                max_files=args.max_files, max_bytes=args.max_bytes, refresh=args.refresh,
                reset_exclusions=args.reset_exclusions)
            payload = asdict(report)
            lines = [f'Scan: {report.status}', f'Root: {report.root}',
                     f'Indexed: {report.indexed}; unchanged: {report.unchanged}; removed: {report.removed}; skipped: {report.skipped}',
                     f'Text enabled: {report.text_enabled}', *report.errors]
            exit_code = 0 if report.status == 'complete' else 1
        elif args.command == 'search':
            hits = search_files(args.db, args.query, root=args.root, limit=args.limit)
            payload = {'query': args.query, 'hits': [asdict(hit) for hit in hits]}
            lines = [f'Matches: {len(hits)}']
            for hit in hits:
                lines.append(f'[{hit.match}; {hit.content_status}; scan={hit.scan_status}] {hit.path}')
                if hit.snippet:
                    lines.append('  ' + hit.snippet)
            lines.append('Results reflect stored observations; rescan to update changed or deleted files.')
        else:
            count = forget_root(args.db, args.root)
            payload = {'removed': count}
            lines = [f'Removed {count} indexed records. Source files unchanged.']
    except (OSError, sqlite3.Error, ValueError) as error:
        if args.json:
            print(json.dumps({'status': 'error', 'error': str(error)}, ensure_ascii=False))
        else:
            print(f'Cannot {args.command}: {error}')
        raise SystemExit(2)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
    else:
        print('\n'.join(lines))
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == '__main__':
    main()
