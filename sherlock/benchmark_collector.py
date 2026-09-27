import argparse
import json
import math
import platform
import statistics
import time
from pathlib import Path

import psutil
from sherlock.capabilities.processes.collector import ProcessCollector
from sherlock.capabilities.telemetry.collector import TelemetryCollector


def measure(system, processes, *, wall=time.perf_counter, cpu=time.process_time):
    start = wall()
    cpu_start = cpu()
    system.collect()
    system_end = wall()
    snapshot = processes.collect()
    end = wall()
    cpu_seconds = cpu() - cpu_start
    elapsed = end - start
    return {
        'system_seconds': system_end-start,
        'processes_seconds': end-system_end,
        'total_seconds': elapsed,
        'self_cpu_seconds': cpu_seconds,
        'self_cpu_percent_one_core': 100*cpu_seconds/elapsed if elapsed > 0 else None,
        'observed_process_count': len(snapshot.processes),
        'skipped_process_count': snapshot.skipped_count,
    }


def summarize(rows):
    return {key: {'median': statistics.median(r[key] for r in rows),
                  'min': min(r[key] for r in rows),
                  'max': max(r[key] for r in rows)}
            for key in ('system_seconds', 'processes_seconds', 'total_seconds',
                        'self_cpu_seconds', 'self_cpu_percent_one_core')}


def benchmark(repeats=3, pause=1.0):
    if repeats < 1 or repeats > 30:
        raise ValueError('repeats must be between 1 and 30')
    if not math.isfinite(pause) or pause < 0:
        raise ValueError('pause must be finite and non-negative')
    results = {'full': [], 'rss_only': []}
    system = TelemetryCollector()
    collectors = {'full': ProcessCollector(), 'rss_only': ProcessCollector(include_details=False)}
    try:
        own_process = psutil.Process()
    except (psutil.Error, OSError):
        own_process = None
    for repeat in range(repeats):
        order = ('full', 'rss_only') if repeat % 2 == 0 else ('rss_only', 'full')
        for mode in order:
            row = measure(system, collectors[mode])
            row['repeat'] = repeat
            try:
                row['self_rss_after_bytes'] = (own_process.memory_info().rss
                                               if own_process is not None else None)
            except (psutil.Error, OSError):
                row['self_rss_after_bytes'] = None
            results[mode].append(row)
            print(f"{mode}: total={row['total_seconds']:.3f}s "
                  f"system={row['system_seconds']:.3f}s processes={row['processes_seconds']:.3f}s", flush=True)
            time.sleep(pause)
    return {
        'benchmark_version': '1.0', 'os_family': platform.system(),
        'psutil_version': psutil.__version__, 'logical_cpu_count': psutil.cpu_count(),
        'repeats_per_mode': repeats, 'measurements': results,
        'summary': {mode: summarize(rows) for mode, rows in results.items()},
        'limitations': [
            'One-core CPU percent = process CPU seconds / collection wall seconds * 100.',
            'CPU cost covers this Python process during collection only, not whole-run cost.',
            'One-second blocking system CPU measurement remains unchanged.',
            'RSS is sampled after collection, not peak memory usage.',
            'Modes run sequentially; background workload can change between measurements.',
            'RSS-only omits name, status and CPU-time reads; PID identity checks remain.',
            'No speedup is guaranteed. Compare repeated measurements on the target Windows host.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--pause', type=float, default=1.0)
    parser.add_argument('--output', type=Path, default=Path('data/collector-benchmark.json'))
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; choose a new --output path')
    try:
        result = benchmark(args.repeats, args.pause)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    except (ValueError, OSError) as error:
        parser.exit(1, f'Benchmark error: {error}\n')
    print(f'Saved: {args.output}')


if __name__ == '__main__':
    main()
