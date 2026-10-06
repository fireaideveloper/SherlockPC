import os
import sqlite3
from unittest.mock import patch

import pytest

from test_desktop_service import make_service, FakeCollector
from sherlock.desktop_bridge import handle_request
from sherlock.storage.sqlite.telemetry_repository import TelemetryRepository


def test_clear_requires_explicit_confirmation(tmp_path):
    service = make_service(tmp_path)
    service.capture_state()
    for value in (None, False, 1, 'true'):
        with pytest.raises(ValueError):
            handle_request({'action': 'clear_history', 'confirmed': value}, service=service)
    assert service.history_store.info()['state_count'] == 1


def test_clear_is_persistent_resets_baseline_and_keeps_unrelated_data(tmp_path):
    service = make_service(tmp_path)
    for _ in range(4):
        service.capture_state()
    standalone = TelemetryRepository(service.database).save(FakeCollector().collect().system)
    old_generation = service.history_store.info()['generation']
    result = handle_request({'action': 'clear_history', 'confirmed': True}, service=service)
    assert result['deleted_count'] == 4
    assert result['storage']['state_count'] == 0
    assert result['storage']['generation'] != old_generation
    restarted = make_service(tmp_path)
    assert restarted.history_store.info()['generation'] == result['storage']['generation']
    with restarted.database.connection() as connection:
        for table in ('state_snapshots', 'process_snapshots', 'process_metrics'):
            assert connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
        assert [row[0] for row in connection.execute('SELECT id FROM system_metrics')] == [standalone]
        assert not connection.execute('PRAGMA foreign_key_check').fetchall()
    overview = restarted.overview()
    assert overview['current']['state_id'] == 1
    assert overview['history']['sample_count'] == 0
    assert overview['storage']['state_count'] == 1


def test_failed_clear_rolls_back_all_measurements(tmp_path):
    service = make_service(tmp_path)
    service.capture_state()
    with service.database.connection() as connection:
        connection.execute("CREATE TRIGGER fail_delete BEFORE DELETE ON system_metrics BEGIN SELECT RAISE(ABORT, 'test failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match='test failure'):
        service.history_store.clear(confirmed=True)
    assert service.history_store.info()['state_count'] == 1
    with service.database.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM process_metrics').fetchone()[0] == 2
        assert connection.execute('SELECT COUNT(*) FROM process_snapshots').fetchone()[0] == 1
    assert service.history_store.info()['generation'] == 'initial'


def test_history_pagination_stays_stable_as_new_samples_arrive(tmp_path):
    service = make_service(tmp_path)
    for _ in range(7):
        service.capture_state()
    first = service.history_store.page(page_size=3)
    service.capture_state()
    second = service.history_store.page(1, 3, first['anchor_id'])
    assert [row['state_id'] for row in first['rows']] == [7, 6, 5]
    assert [row['state_id'] for row in second['rows']] == [4, 3, 2]
    assert second['total'] == 7
    assert service.history_store.page(page_size=3)['total'] == 8
    assert service.history_store.page(100, 3)['page'] == 2


@pytest.mark.parametrize('page,size,anchor', [(-1, 5, None), (0, 0, None), (0, 51, None), (0, 5, -1)])
def test_invalid_history_page(tmp_path, page, size, anchor):
    with pytest.raises(ValueError):
        make_service(tmp_path).history_store.page(page, size, anchor)


def test_open_folder_uses_database_location_and_does_not_collect(tmp_path):
    service = make_service(tmp_path)
    target = 'sherlock.desktop.history.os.startfile' if os.name == 'nt' else 'sherlock.desktop.history.subprocess.run'
    with patch(target) as launch:
        info = service.history_store.open_folder()
    opened = launch.call_args.args[0] if os.name == 'nt' else launch.call_args.args[0][-1]
    assert opened == str(tmp_path.resolve())
    assert info['database_path'] == str((tmp_path / 'sherlock.db').resolve())
    assert info['state_count'] == 0
    assert info['size_bytes'] > 0


def test_clear_empty_history(tmp_path):
    service = make_service(tmp_path)
    assert service.history_store.clear(confirmed=True)['deleted_count'] == 0
    assert service.history_store.page()['rows'] == []
