import argparse
import csv
import json
import math
import multiprocessing as mp
import platform
import time
import uuid
from pathlib import Path

import psutil

from sherlock.record_experiment import validate_alias

SCENARIOS = ('normal', 'cpu_load', 'memory_growth', 'mixed')
FIELDS = ('run_id', 'sample_index', 'elapsed_seconds', 'phase',
          'measurement_end_seconds', 'cpu_window_seconds',
          'cpu_percent', 'memory_percent', 'memory_used_bytes',
          'memory_available_bytes', 'swap_percent', 'collection_seconds')


def cpu_worker(stop, ready, go, duty, max_seconds):
    ready.set()
    if not go.wait(30):
        return
    deadline = time.monotonic() + max_seconds
    while not stop.is_set() and time.monotonic() < deadline:
        start = time.monotonic()
        while time.monotonic() - start < 0.1 * duty:
            if stop.is_set() or time.monotonic() >= deadline:
                return
        stop.wait(max(0, 0.1 - (time.monotonic() - start)))


def memory_worker(stop, ready, go, target_bytes, available_floor, active_seconds):
    blocks = []
    ready.set()
    if not go.wait(30):
        return
    start = time.monotonic()
    allocated = 0
    try:
        while not stop.is_set() and time.monotonic() - start < active_seconds + 30:
            # Reach the requested size gradually over the first 80% of the active phase.
            fraction = min(1.0, (time.monotonic()-start) / (active_seconds*0.8))
            desired = int(target_bytes * fraction)
            if allocated < desired:
                chunk = min(4*1024*1024, desired-allocated)
                if psutil.virtual_memory().available - chunk < available_floor:
                    raise RuntimeError('Available memory reserve reached')
                block = bytearray(chunk)
                for index in range(0, chunk, 4096):
                    block[index] = 1
                blocks.append(block)
                allocated += chunk
            stop.wait(0.05)
    finally:
        blocks.clear()


def validate_config(*, before, active, after, interval, repeats, cooldown,
                    workers, memory_mb, duty):
    for name, value in [('before', before), ('active', active), ('after', after),
                        ('interval', interval)]:
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f'{name} must be finite and positive')
    if interval < 2 or min(before, active, after) < interval:
        raise ValueError('interval >= 2 and each phase >= interval are required')
    if before+active+after > 1800:
        raise ValueError('One experiment is limited to 1800 seconds')
    if not 1 <= repeats <= 30:
        raise ValueError('repeats must be between 1 and 30')
    if not math.isfinite(cooldown) or not 0 <= cooldown <= 600:
        raise ValueError('cooldown must be between 0 and 600 seconds')
    if not 1 <= workers <= 2:
        raise ValueError('CPU workers must be 1 or 2')
    if not 16 <= memory_mb <= 512:
        raise ValueError('memory-mb must be between 16 and 512')
    if not math.isfinite(duty) or not 0 < duty <= 0.75:
        raise ValueError('cpu-duty must be > 0 and <= 0.75')


def save_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False)+'\n', encoding='utf-8')
    temporary.replace(path)


class Load:
    def __init__(self, scenario, workers, memory_mb, duty, active):
        self.context = mp.get_context('spawn')
        self.stop = self.context.Event()
        self.go = self.context.Event()
        self.children = []
        self.scenario, self.workers = scenario, workers
        self.memory_mb, self.duty, self.active = memory_mb, duty, active
        self.forced_terminations = 0

    def start(self):
        specs = []
        if self.scenario in ('cpu_load', 'mixed'):
            specs += [(cpu_worker, (self.duty, self.active+30))] * self.workers
        if self.scenario in ('memory_growth', 'mixed'):
            memory = psutil.virtual_memory()
            target = self.memory_mb*1024*1024
            if target > 0.2*memory.available:
                raise ValueError('Requested allocation exceeds 20% of currently available RAM')
            reserve = max(512*1024*1024, int(memory.total*0.1))
            if memory.available-target < reserve:
                raise ValueError('Insufficient free memory reserve')
            specs.append((memory_worker, (target, reserve, self.active)))
        for target, args in specs:
            ready = self.context.Event()
            child = self.context.Process(target=target,
                       args=(self.stop, ready, self.go, *args), daemon=True)
            child.start()
            self.children.append(child)
            if not ready.wait(15) or not child.is_alive():
                raise RuntimeError('Load worker did not start')

    def check(self):
        if any(not child.is_alive() for child in self.children):
            raise RuntimeError('Load worker exited before the active phase ended')

    def close(self):
        self.stop.set()
        self.go.set()
        for child in self.children:
            child.join(2)
            if child.is_alive():
                self.forced_terminations += 1
                child.terminate()
                child.join(2)
            if child.is_alive():
                child.kill()
                child.join(2)
        return [child.exitcode for child in self.children]


def record_run(folder, *, scenario, machine_id, session_id, repeat,
               before, active, after, interval, workers, memory_mb, duty):
    run_id = uuid.uuid4().hex
    output = folder/run_id
    output.mkdir()
    phases = [('baseline', before), ('active', active), ('recovery', after)]
    meta = {
        'schema_version': 'sherlockbench-system-0.2', 'recorder_version': '2.0',
        'run_id': run_id, 'machine_id': machine_id, 'session_id': session_id,
        'scenario': scenario, 'repeat_index': repeat, 'origin': 'real_measurement',
        'label_source': 'controlled_schedule' if scenario != 'normal' else 'no_injected_load',
        'status': 'recording', 'os_family': platform.system(),
        'psutil_version': psutil.__version__, 'logical_cpu_count': psutil.cpu_count(),
        'memory_total_bytes': psutil.virtual_memory().total,
        'requested_interval_seconds': interval,
        'requested_phases_seconds': dict(phases),
        'load_parameters': {
            'cpu_workers': workers if scenario in ('cpu_load', 'mixed') else 0,
            'cpu_duty': duty if scenario in ('cpu_load', 'mixed') else 0,
            'memory_target_mb': memory_mb if scenario in ('memory_growth', 'mixed') else 0,
        },
        'events': [], 'sample_count': 0,
        'limitations': [
            'Scenario describes injected workload, not a proven fault or slowdown.',
            'normal means no injected load; background user activity is uncontrolled.',
            'active phases include onset/ramp, not uniform resource consumption.',
            'Requested CPU duty is per worker, not measured whole-machine CPU percent.',
            'Memory target is requested, not a separately verified achieved allocation.',
            'CPU samples cover roughly one second; remaining time between rows is unsampled.',
            'Phase deadlines can be exceeded by collection time; actual events are recorded.',
            'No process details, disk rates, network data or absolute timestamps are exported.',
            'This schema differs from process-inclusive pilot records; do not concatenate blindly.',
        ],
    }
    save_json(output/'metadata.json', meta)
    load = Load(scenario, workers, memory_mb, duty, active)
    start = time.monotonic()
    cpu_start = time.process_time()
    try:
        with (output/'samples.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            for phase, duration in phases:
                if phase == 'active':
                    setup_start = time.monotonic()-start
                    load.start()
                    meta['events'].append({'event': 'worker_setup', 'start_seconds': setup_start,
                                           'end_seconds': time.monotonic()-start})
                phase_start = time.monotonic()
                if phase == 'active':
                    load.go.set()
                meta['events'].append({'event': phase+'_start', 'elapsed_seconds': phase_start-start})
                deadline = phase_start + duration
                while time.monotonic() < deadline:
                    if phase == 'active':
                        load.check()
                    tick = time.monotonic()
                    cpu_before = time.monotonic()
                    cpu = psutil.cpu_percent(interval=1.0)
                    cpu_window = time.monotonic()-cpu_before
                    memory = psutil.virtual_memory()
                    swap = psutil.swap_memory()
                    end = time.monotonic()
                    if phase == 'active':
                        load.check()
                    writer.writerow(dict(zip(FIELDS, (
                        run_id, meta['sample_count'], tick-start, phase,
                        end-start, cpu_window, cpu, memory.percent, memory.used,
                        memory.available, swap.percent, end-tick))))
                    stream.flush()
                    meta['sample_count'] += 1
                    time.sleep(max(0, min(tick+interval, deadline)-time.monotonic()))
                meta['events'].append({'event': phase+'_end', 'elapsed_seconds': time.monotonic()-start})
                if phase == 'active':
                    load.check()
                    meta['worker_exit_codes'] = load.close()
                    meta['events'].append({'event': 'load_stopped', 'elapsed_seconds': time.monotonic()-start})
                    if any(code != 0 for code in meta['worker_exit_codes']) or load.forced_terminations:
                        raise RuntimeError('Load worker required forced cleanup or failed')
        meta['status'] = 'completed'
    except KeyboardInterrupt:
        meta['status'] = 'interrupted'
        raise
    except Exception as error:
        meta['status'] = 'failed'
        meta['error_type'] = type(error).__name__
        raise
    finally:
        meta['worker_exit_codes'] = load.close()
        meta['forced_terminations'] = load.forced_terminations
        meta['elapsed_seconds'] = time.monotonic()-start
        meta['recorder_cpu_seconds'] = time.process_time()-cpu_start
        meta['recorder_cpu_scope'] = 'parent process only, excluding load workers'
        save_json(output/'metadata.json', meta)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--machine-id', required=True)
    parser.add_argument('--session-id', required=True)
    parser.add_argument('--scenarios', nargs='+', choices=SCENARIOS, default=list(SCENARIOS))
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--before', type=float, default=60)
    parser.add_argument('--active', type=float, default=180)
    parser.add_argument('--after', type=float, default=60)
    parser.add_argument('--interval', type=float, default=5)
    parser.add_argument('--cooldown', type=float, default=30)
    parser.add_argument('--cpu-workers', type=int, default=1)
    parser.add_argument('--cpu-duty', type=float, default=0.5)
    parser.add_argument('--memory-mb', type=int, default=128)
    parser.add_argument('--output', type=Path, default=Path('data/scenario_batches'))
    args = parser.parse_args()
    try:
        validate_alias(args.machine_id)
        validate_alias(args.session_id)
        validate_config(before=args.before, active=args.active, after=args.after,
            interval=args.interval, repeats=args.repeats, cooldown=args.cooldown,
            workers=args.cpu_workers, memory_mb=args.memory_mb, duty=args.cpu_duty)
    except ValueError as error:
        parser.error(str(error))
    batch = args.output/uuid.uuid4().hex
    batch.mkdir(parents=True)
    manifest = {'status': 'recording', 'runs': [], 'session_id': args.session_id,
                'machine_id': args.machine_id, 'planned_runs': len(args.scenarios)*args.repeats}
    print(f'Batch: {batch}\nCPU/RAM load is bounded. Ctrl+C stops the batch.', flush=True)
    try:
        for repeat in range(args.repeats):
            order = args.scenarios[repeat % len(args.scenarios):]+args.scenarios[:repeat % len(args.scenarios)]
            for scenario in order:
                print(f'Run {len(manifest["runs"])+1}/{manifest["planned_runs"]}: {scenario}', flush=True)
                folder = record_run(batch, scenario=scenario, machine_id=args.machine_id,
                    session_id=args.session_id, repeat=repeat, before=args.before,
                    active=args.active, after=args.after, interval=args.interval,
                    workers=args.cpu_workers, memory_mb=args.memory_mb, duty=args.cpu_duty)
                manifest['runs'].append(folder.name)
                save_json(batch/'batch.json', manifest)
                if len(manifest['runs']) < manifest['planned_runs']:
                    time.sleep(args.cooldown)
        manifest['status'] = 'completed'
    except KeyboardInterrupt:
        manifest['status'] = 'interrupted'
    except Exception as error:
        manifest['status'] = 'failed'
        print(f'Batch stopped: {type(error).__name__}: {error}', flush=True)
    finally:
        save_json(batch/'batch.json', manifest)
    print(f'Status: {manifest["status"]}\nSaved: {batch}')
    if manifest['status'] != 'completed':
        raise SystemExit(1)


if __name__ == '__main__':
    mp.freeze_support()
    main()
