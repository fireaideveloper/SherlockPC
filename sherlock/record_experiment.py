import argparse
import csv
import json
import math
import platform
import re
import time
import uuid
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import psutil

from sherlock.capabilities.state.collector import StateCollector

SCENARIOS = ('normal', 'heavy_normal', 'cpu_load', 'memory_growth', 'disk_io', 'mixed')
FIELDS = (
    'run_id', 'sample_index', 'elapsed_seconds', 'collection_seconds',
    'cpu_percent', 'memory_percent', 'memory_used_bytes', 'memory_available_bytes',
    'swap_percent', 'process_count', 'skipped_process_count',
    'process_rss_known_count', 'max_process_rss_bytes',
)


def validate_alias(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', value):
        raise ValueError('Use a non-personal alias of 1-40 letters, digits, _ or -')
    return value


def sample_row(snapshot, run_id, index, elapsed, collection):
    """Explicit allowlist: never serialize a snapshot wholesale."""
    system = snapshot.system
    rss = [p.memory_rss for p in snapshot.processes.processes if p.memory_rss is not None]
    return dict(zip(FIELDS, (
        run_id, index, round(elapsed, 6), round(collection, 6),
        system.cpu_percent, system.memory_percent, system.memory_used,
        system.memory_available, system.swap_percent,
        len(snapshot.processes.processes), snapshot.processes.skipped_count,
        len(rss), max(rss) if rss else None,
    )))


def record_experiment(*, output, scenario, machine_id, session_id,
                      duration=600.0, interval=5.0, collector=None,
                      clock=time.monotonic, sleep=time.sleep):
    if scenario not in SCENARIOS:
        raise ValueError('Unknown scenario')
    validate_alias(machine_id)
    validate_alias(session_id)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('duration must be finite and positive')
    if not math.isfinite(interval) or interval < 2:
        raise ValueError('interval must be finite and at least 2 seconds')
    if duration < interval:
        raise ValueError('duration must be at least interval')
    collector = StateCollector() if collector is None else collector
    run_id = uuid.uuid4().hex
    folder = Path(output) / run_id
    folder.mkdir(parents=True, exist_ok=False)
    try:
        package_version = version('sherlockpc')
    except PackageNotFoundError:
        package_version = 'source-tree'
    meta = {
        'schema_version': 'sherlockbench-0.1', 'recorder_version': '1.0',
        'package_version': package_version, 'psutil_version': psutil.__version__,
        'run_id': run_id, 'machine_id': machine_id, 'session_id': session_id,
        'scenario': scenario, 'label_source': 'user_declared_whole_run',
        'origin': 'real_measurement', 'status': 'recording',
        'requested_duration_seconds': duration, 'requested_interval_seconds': interval,
        'os_family': platform.system(), 'logical_cpu_count': psutil.cpu_count(),
        'memory_total_bytes': psutil.virtual_memory().total,
        'sample_count': 0, 'elapsed_seconds': 0,
        'limitations': [
            'Scenario is user declared; it is not a verified fault or causal label.',
            'Collection is sequential, not an atomic snapshot.',
            'CPU uses a one-second sample; other metrics are point observations.',
            'Collection overhead is included; this recorder is part of the workload.',
            'No disk/network rates or process-level attribution in schema 0.1.',
            'A started collection can finish after the requested duration.',
            'Completed means recording finished, not that data quality is sufficient.',
        ],
    }
    def save_metadata():
        temporary = folder / 'metadata.tmp'
        temporary.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(folder / 'metadata.json')
    save_metadata()
    start = clock()
    count = 0
    try:
        with (folder / 'samples.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            while clock() - start < duration:
                before = clock()
                snapshot = collector.collect()
                after = clock()
                writer.writerow(sample_row(snapshot, run_id, count, before-start, after-before))
                stream.flush()
                count += 1
                # Never catch up with bursts after a slow collection.
                delay = min(max(0, interval-(after-before)), max(0, duration-(clock()-start)))
                if delay:
                    sleep(delay)
            meta['status'] = 'completed'
    except KeyboardInterrupt:
        meta['status'] = 'interrupted'
    except Exception:
        meta['status'] = 'failed'
        raise
    finally:
        meta['sample_count'] = count
        meta['elapsed_seconds'] = round(clock()-start, 6)
        save_metadata()
    return folder, meta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=SCENARIOS, required=True)
    parser.add_argument('--machine-id', required=True, help='Anonymous alias, e.g. pc-01')
    parser.add_argument('--session-id', required=True, help='Same alias for runs from one work session')
    parser.add_argument('--duration', type=float, default=600, help='Seconds, default 600')
    parser.add_argument('--interval', type=float, default=5, help='Seconds, default 5')
    parser.add_argument('--output', type=Path, default=Path('data/experiments'))
    args = parser.parse_args()
    print('Recording actual measurements. No load is generated. Ctrl+C stops the run.', flush=True)
    try:
        folder, meta = record_experiment(output=args.output, scenario=args.scenario,
            machine_id=args.machine_id, session_id=args.session_id,
            duration=args.duration, interval=args.interval)
    except (ValueError, OSError) as error:
        parser.exit(1, f'Recording error: {error}\n')
    print(f"Status: {meta['status']} | Samples: {meta['sample_count']}\nSaved: {folder}")
    if meta['status'] != 'completed':
        raise SystemExit(130)


if __name__ == '__main__':
    main()
