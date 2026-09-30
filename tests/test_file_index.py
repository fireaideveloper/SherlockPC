import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from sherlock.capabilities.files.indexer import index_folder
from sherlock.capabilities.files.search import forget_root, search_files
from sherlock.storage.sqlite.database import Database


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / 'docs'
    root.mkdir()
    return root, tmp_path / 'files.db'


def write(root, name, text='hello'):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def test_metadata_only_is_default_and_unicode_names_work(setup):
    root, db = setup
    write(root, 'Резюме.txt', 'Секретный термин')
    report = index_folder(root, db)
    assert report.status == 'complete'
    assert report.indexed == 1
    assert search_files(db, 'РЕЗЮМЕ')[0].match == 'name'
    assert search_files(db, 'секретный') == ()
    with sqlite3.connect(db) as connection:
        assert connection.execute('SELECT content FROM indexed_files').fetchone()[0] is None


def test_text_search_and_incremental_update_delete_rename(setup):
    root, db = setup
    file = write(root, 'notes.md', 'Нейронная сеть SherlockPC')
    assert index_folder(root, db, text=True).indexed == 1
    hit = search_files(db, 'НЕЙРОННАЯ')[0]
    assert hit.match == 'content' and 'Нейронная' in hit.snippet
    assert index_folder(root, db, text=True).unchanged == 1
    file.write_text('Другая тема', encoding='utf-8')
    assert index_folder(root, db, text=True).indexed == 1
    assert search_files(db, 'нейронная') == ()
    renamed = root / 'renamed.md'
    file.rename(renamed)
    report = index_folder(root, db, text=True)
    assert report.indexed == 1 and report.removed == 1
    assert search_files(db, 'другая')[0].name == 'renamed.md'
    renamed.unlink()
    assert index_folder(root, db, text=True).removed == 1
    assert search_files(db, 'другая') == ()


def test_text_can_be_disabled_and_enabled_again(setup):
    root, db = setup
    write(root, 'a.txt', 'needle')
    index_folder(root, db, text=True)
    assert search_files(db, 'needle')
    index_folder(root, db)
    assert not search_files(db, 'needle')
    index_folder(root, db, text=True)
    assert search_files(db, 'needle')


@pytest.mark.parametrize('name', ['.env', '.ssh/secret.txt', '.git/a.txt', '.venv/a.txt',
                                  'node_modules/a.txt', 'data/a.txt', 'key.pem', 'key.pfx'])
def test_default_exclusions(setup, name):
    root, db = setup
    write(root, name, 'secret')
    assert index_folder(root, db, text=True).indexed == 0
    assert not search_files(db, 'secret')


def test_custom_exclusions_persist_and_can_be_explicitly_reset(setup):
    root, db = setup
    write(root, 'private/a.txt', 'privateword')
    write(root, 'other.md', 'otherword')
    index_folder(root, db, text=True)
    report = index_folder(root, db, text=True, excludes=('private',), exclude_extensions=('.md',))
    assert report.removed == 2
    assert not search_files(db, 'privateword')
    assert not search_files(db, 'otherword')
    index_folder(root, db, text=True)
    assert not search_files(db, 'privateword')
    assert not search_files(db, 'otherword')
    index_folder(root, db, text=True, reset_exclusions=True)
    assert search_files(db, 'privateword') and search_files(db, 'otherword')


def test_excluding_entire_root_removes_its_records(setup):
    root, db = setup
    write(root, 'a.txt')
    index_folder(root, db)
    assert index_folder(root, db, excludes=('.',)).removed == 1
    assert not search_files(db, '.txt')


@pytest.mark.parametrize('name,data,status', [
    ('doc.pdf', b'%PDF-not-a-real-pdf', 'unsupported_type'),
    ('image.png', b'PNG', 'unsupported_type'),
    ('binary.txt', b'abc\x00def', 'binary'),
    ('legacy.txt', b'\xff\xfe', 'unsupported_encoding'),
    ('large.txt', b'x' * 100, 'too_large'),
    ('empty.txt', b'', 'indexed'),
    ('bom.txt', b'\xef\xbb\xbfhello', 'indexed'),
])
def test_content_types_are_explicit(setup, name, data, status):
    root, db = setup
    (root / name).write_bytes(data)
    index_folder(root, db, text=True, max_bytes=50)
    assert search_files(db, name)[0].content_status == status


def test_size_policy_removes_cached_content(setup):
    root, db = setup
    write(root, 'a.txt', 'secretword' * 10)
    index_folder(root, db, text=True)
    index_folder(root, db, text=True, max_bytes=5)
    assert not search_files(db, 'secretword')


def test_symlink_files_and_directories_are_skipped(setup, tmp_path):
    root, db = setup
    outside = tmp_path / 'outside'
    outside.mkdir()
    target = write(outside, 'secret.txt', 'secretword')
    try:
        (root / 'file.txt').symlink_to(target)
        (root / 'directory').symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('Symlinks are not supported for this account')
    report = index_folder(root, db, text=True)
    assert report.skipped == 2 and report.indexed == 0
    assert not search_files(db, 'secretword')


def test_truncated_scan_never_prunes_unvisited_records(setup):
    root, db = setup
    for i in range(4):
        write(root, f'file{i}.txt')
    index_folder(root, db)
    report = index_folder(root, db, max_files=1)
    assert report.status == 'truncated' and report.removed == 0
    assert len(search_files(db, '.txt')) == 4
    assert all(hit.scan_status == 'truncated' for hit in search_files(db, '.txt'))


def test_access_error_does_not_prune_old_records(setup, monkeypatch):
    from sherlock.capabilities.files import indexer
    root, db = setup
    write(root, 'locked/a.txt', 'needle')
    index_folder(root, db, text=True)
    real_scan = os.scandir

    def scan(path):
        if Path(path).name == 'locked':
            raise PermissionError('simulated denied')
        return real_scan(path)

    monkeypatch.setattr(indexer.os, 'scandir', scan)
    report = index_folder(root, db, text=True)
    assert report.status == 'partial' and report.removed == 0
    assert search_files(db, 'needle')[0].scan_status == 'partial'


def test_read_error_clears_stale_content(setup, monkeypatch):
    from sherlock.capabilities.files import indexer
    root, db = setup
    write(root, 'a.txt', 'needle')
    index_folder(root, db, text=True)

    def fail(*args):
        raise PermissionError('denied')

    monkeypatch.setattr(indexer, '_read_text', fail)
    report = index_folder(root, db, text=True, refresh=True)
    assert report.status == 'partial'
    assert not search_files(db, 'needle')
    assert search_files(db, 'a.txt')[0].content_status == 'unreadable'


def test_changed_file_during_open_is_not_read(setup, monkeypatch):
    from sherlock.capabilities.files import indexer
    root, db = setup
    file = write(root, 'a.txt', 'first')
    original = indexer._read_text

    def mutate(path, info, limit):
        path.write_text('a different content', encoding='utf-8')
        return original(path, info, limit)

    monkeypatch.setattr(indexer, '_read_text', mutate)
    assert index_folder(root, db, text=True).status == 'partial'
    assert not search_files(db, 'different')


def test_multiple_roots_search_filter_forget_and_source_unchanged(setup, tmp_path):
    root, db = setup
    second = tmp_path / 'second'
    second.mkdir()
    a = write(root, 'shared.txt', 'needle')
    b = write(second, 'shared.txt', 'needle')
    before = a.read_bytes(), b.read_bytes()
    index_folder(root, db, text=True)
    index_folder(second, db, text=True)
    assert len(search_files(db, 'needle')) == 2
    assert len(search_files(db, 'needle', root=root)) == 1
    assert forget_root(db, root) == 1
    assert len(search_files(db, 'needle')) == 1
    assert (a.read_bytes(), b.read_bytes()) == before


def test_literal_query_and_rank(setup):
    root, db = setup
    write(root, 'needle.txt', 'normal')
    write(root, 'other.txt', 'needle.txt plus 100% underscore_')
    index_folder(root, db, text=True)
    hits = search_files(db, 'needle.txt')
    assert [h.match for h in hits] == ['name', 'content']
    assert len(search_files(db, '%')) == 1
    assert not search_files(db, "' OR 1=1 --")


def test_database_is_not_indexed_even_inside_root(setup):
    root, _ = setup
    db = root / 'local.db'
    write(root, 'a.txt')
    index_folder(root, db)
    assert not search_files(db, 'local.db')
    assert len(search_files(db, 'a.txt')) == 1


def test_telemetry_database_is_not_modified(setup):
    root, db = setup
    Database(db).initialize()
    before = db.read_bytes()
    with pytest.raises(ValueError, match='separate'):
        index_folder(root, db)
    assert db.read_bytes() == before


@pytest.mark.parametrize('kwargs', [{'max_files': 0}, {'max_files': 100001},
                                    {'max_bytes': 0}, {'max_bytes': 1048577},
                                    {'excludes': ('../outside',)}, {'exclude_extensions': ('pdf',)}])
def test_bad_scan_options_do_not_create_database(setup, kwargs):
    root, db = setup
    with pytest.raises(ValueError):
        index_folder(root, db, **kwargs)
    assert not db.exists()


def test_missing_root_leaves_existing_index_intact(setup):
    root, db = setup
    write(root, 'a.txt')
    index_folder(root, db)
    with pytest.raises(FileNotFoundError):
        index_folder(root / 'missing', db)
    assert search_files(db, 'a.txt')


def test_search_and_forget_do_not_create_missing_db(setup):
    root, db = setup
    with pytest.raises(sqlite3.OperationalError):
        search_files(db, 'x')
    with pytest.raises(sqlite3.OperationalError):
        forget_root(db, root)
    assert not db.exists()


@pytest.mark.parametrize('query', ['', '   ', 'x' * 257])
def test_bad_query(setup, query):
    root, db = setup
    with pytest.raises(ValueError):
        search_files(db, query)


def test_cli_index_search_forget_json(setup):
    root, db = setup
    file = write(root, 'cv.txt', 'computer vision')

    def run(*args):
        result = subprocess.run([sys.executable, '-m', 'sherlock.files', *args,
                                 '--db', str(db), '--json'], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)

    assert run('index', str(root), '--text')['status'] == 'complete'
    assert run('search', 'computer vision')['hits'][0]['match'] == 'content'
    assert run('forget', str(root))['removed'] == 1
    assert file.read_text() == 'computer vision'
