# SherlockPC Python tools

[English README](../README.md) · [Русский README](../README.ru.md) · [Documentation](README.md) · [Desktop guide](desktop.md) · [File index](files.md)

These are developer utilities, separate from the desktop UI. Run commands from the repository root after installing the core:

```bash
python -m pip install -e ".[dev]"
```

## Know which database you are using

| Tool | Default database |
|---|---|
| Installed Windows desktop / desktop bridge | `%LOCALAPPDATA%\SherlockPC\data\sherlock.db`; bridge honors `SHERLOCK_DB_PATH` |
| Single telemetry sample | `data/sherlock.db` under the current directory |
| State Diff | `data/sherlock.db` under the current directory; no `--db` option |
| Investigation CLI | `data/sherlock.db`; override using `--db` |
| File index/search | `data/files.db`; override using `--db` |

A desktop state ID belongs to the desktop database. Do not assume that the same ID exists in a CLI database. Other tools have their own options; read their `--help` before use.

## One telemetry measurement

```bash
python -m sherlock
```

[Source](../sherlock/__main__.py). Collects and saves one system metric; this is not the full desktop state collector.

## Compare two saved state snapshots

```bash
python -m sherlock.state_diff --before 1 --after 2 --json
```

[Source](../sherlock/state_diff.py). Replace the example IDs with two existing **state** IDs in `data/sherlock.db`. Comparing states describes changes; it does not prove their cause.

## Investigate a stored state

```bash
python -m sherlock.investigate --state 2 --db data/sherlock.db --json
```

[Source](../sherlock/investigate.py). Use a valid saved state ID. Options include `--hours`, `--limit`, `--min-samples` and `--min-span-seconds`.

## Index and search a folder

```bash
python -m sherlock.files index "C:/Users/YourName/Documents" --db data/files.db
python -m sherlock.files search "report" --db data/files.db
```

[Source](../sherlock/files.py). Metadata is indexed by default. Content indexing requires `--text` and applies to eligible UTF-8 text formats (`txt`, `md`, `rst`, `csv`, `tsv`), with size limits and exclusions. PDF content extraction and embedding search are not provided by this CLI.

```bash
python -m sherlock.files index "C:/Users/YourName/Documents" --text --exclude Private --db data/files.db
```

Search is literal Unicode substring matching against stored observations. Rescan to update changed or deleted files. Custom exclusions persist across scans; inspect `--help` before resetting them. `forget` removes one root from the index while preserving source files.

## Further tools

| Tool | Source and help |
|---|---|
| State snapshots | [state_snapshot.py](../sherlock/state_snapshot.py): `python -m sherlock.state_snapshot --help` |
| Baseline reports | [baseline.py](../sherlock/baseline.py): `python -m sherlock.baseline --help` |
| Anomaly reports | [anomalies.py](../sherlock/anomalies.py): `python -m sherlock.anomalies --help` |
| Process history | [process_history.py](../sherlock/process_history.py): `python -m sherlock.process_history --help` |
| Collector benchmark | [benchmark_collector.py](../sherlock/benchmark_collector.py): `python -m sherlock.benchmark_collector --help` |
| Workload recording | [record_experiment.py](../sherlock/record_experiment.py): `python -m sherlock.record_experiment --help` |
| Scenario batches | [scenario_batch.py](../sherlock/scenario_batch.py): `python -m sherlock.scenario_batch --help` |

Workload experiments intentionally generate load. Select parameters appropriate to your machine before running them.

[Documentation](README.md) · [File index](files.md) · [English README](../README.md) · [Русский README](../README.ru.md)
