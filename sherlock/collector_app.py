import ctypes
import json
import os
import time
import uuid
import zipfile
from pathlib import Path

import psutil
from sherlock.scenario_batch import SCENARIOS, record_run, save_json, validate_alias

PROFILE = dict(before=60, active=180, after=60, interval=5,
               workers=2, memory_mb=256, duty=0.5)
REPEATS = 3
COOLDOWN = 30
EXPECTED_SECONDS = 12 * 300 + 11 * COOLDOWN


def app_home():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'SherlockBench'


class InstanceLock:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open('a+b')

        try:
            self.file.seek(0)
            if not self.file.read(1):
                self.file.write(b'0')
                self.file.flush()

            self.file.seek(0)

            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(
                    self.file,
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
        except OSError as error:
            self.file.close()
            raise RuntimeError(
                'Не удалось получить блокировку сборщика. '
                'Возможно, он уже открыт; также проверь права доступа.'
            ) from error

    def close(self):
        self.file.close()


def reserve_session(root, machine, first_session):
    validate_alias(machine)
    if not 1 <= first_session <= 9999:
        raise ValueError('Номер сессии должен быть от 1 до 9999.')
    config_path = root / 'settings.json'
    config = json.loads(config_path.read_text('utf-8')) if config_path.exists() else {}
    counters = config.get('next_sessions', {})
    number = max(first_session, int(counters.get(machine, first_session)))
    if number > 9999:
        raise ValueError('Исчерпан диапазон номеров сессий.')
    counters[machine] = number + 1
    save_json(config_path, dict(machine_id=machine, next_sessions=counters))
    return f's{number:02d}'


def preflight():
    mem = psutil.virtual_memory()
    target = PROFILE['memory_mb'] * 1024**2
    if target > .2 * mem.available or mem.available - target < max(512*1024**2, .1*mem.total):
        raise ValueError('Недостаточно свободной RAM для профиля. Закрой тяжёлые программы.')


def archive_batch(batch, exports):
    exports.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((batch/'batch.json').read_text('utf-8'))
    name = f"SherlockBench-{manifest['machine_id']}-{manifest['session_id']}-{batch.name[:8]}-{manifest['status']}.zip"
    target = exports/name
    temporary = target.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(batch.rglob('*')):
            if path.is_file():
                archive.write(path, Path(batch.name)/path.relative_to(batch))
    temporary.replace(target)
    return target


def run_collection(root, machine, session, cancel, notify, *, profile=None, repeats=REPEATS, cooldown=COOLDOWN):
    profile = dict(PROFILE if profile is None else profile)
    batch = root/'batches'/uuid.uuid4().hex
    batch.mkdir(parents=True)
    manifest = dict(status='recording', machine_id=machine, session_id=session,
                    planned_runs=4*repeats, runs=[], collector_app_version='0.1.0',
                    profile=profile, repeats=repeats, cooldown_seconds=cooldown)
    save_json(batch/'batch.json', manifest)
    sleep_active = False
    try:
        if os.name == 'nt':
            sleep_active = bool(ctypes.windll.kernel32.SetThreadExecutionState(0x80000001))
            if not sleep_active:
                notify(kind='warning', text='Не удалось запретить сон. Отключи автоматический сон вручную.')
        for repeat in range(repeats):
            order = SCENARIOS[repeat % 4:] + SCENARIOS[:repeat % 4]
            for scenario in order:
                if cancel.is_set():
                    raise KeyboardInterrupt
                number = len(manifest['runs']) + 1
                notify(kind='run', number=number, total=4*repeats, scenario=scenario)
                folder = record_run(batch, scenario=scenario, machine_id=machine,
                    session_id=session, repeat=repeat, **profile, cancel_event=cancel,
                    on_progress=lambda **data: notify(kind='phase', **data))
                manifest['runs'].append(folder.name)
                save_json(batch/'batch.json', manifest)
                notify(kind='completed_run', completed=len(manifest['runs']))
                if len(manifest['runs']) < manifest['planned_runs']:
                    notify(kind='cooldown', seconds=cooldown)
                    if cancel.wait(cooldown):
                        raise KeyboardInterrupt
        manifest['status'] = 'completed'
    except KeyboardInterrupt:
        manifest['status'] = 'interrupted'
    except Exception as error:
        manifest['status'] = 'failed'
        manifest['error_type'] = type(error).__name__
        notify(kind='warning', text=str(error))
    finally:
        if sleep_active:
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        manifest['partial_runs'] = [p.parent.name for p in batch.glob('*/metadata.json')
                                    if p.parent.name not in manifest['runs']]
        save_json(batch/'batch.json', manifest)
    archive = archive_batch(batch, root/'exports')
    return dict(status=manifest['status'], completed=len(manifest['runs']),
                planned=manifest['planned_runs'], archive=str(archive), batch=str(batch))