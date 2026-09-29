import argparse
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from sherlock.baseline import _json_default
from sherlock.capabilities.state.anomalies import detect_anomalies
from sherlock.capabilities.state.baseline import build_baseline
from sherlock.storage.sqlite.baseline_reader import BaselineReader
from sherlock.storage.sqlite.database import Database
from sherlock.storage.sqlite.state_reader import StateNotFoundError


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=int, required=True)
    parser.add_argument("--db", type=Path, default=Path("data/sherlock.db"))
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--min-samples", type=int, default=30)
    parser.add_argument("--min-span-seconds", type=float, default=300.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.db.is_file():
        parser.error(f"Database does not exist: {args.db}")
    if args.limit < args.min_samples:
        parser.error("--limit must be at least --min-samples")
    try:
        data = BaselineReader(Database(args.db)).load(
            args.state, hours=args.hours, limit=args.limit)
        baseline = build_baseline(
            data, min_samples=args.min_samples,
            min_span_seconds=args.min_span_seconds)
        report = detect_anomalies(baseline)
    except (ValueError, StateNotFoundError, sqlite3.Error) as error:
        parser.exit(1, f"Cannot detect anomalies: {error}\n")
    if args.json:
        print(json.dumps(asdict(report), default=_json_default,
                         ensure_ascii=False, indent=2, allow_nan=False))
        return
    print(f"Anomalies for state {baseline.target_id}: {report.status}")
    print(f"History: {baseline.sample_count} samples, {baseline.span_seconds:.1f} seconds")
    print(f"Evaluated metrics: {', '.join(report.evaluated_metrics) or 'none'}")
    for reason in baseline.reasons:
        print(f"  {reason}")
    for item in report.anomalies:
        print(f"[{item.evidence_id}] {item.statement}")
        print(f"  current={item.value}; P10={item.reference_p10}; P90={item.reference_p90}")
        print(f"  rule: {item.rule}")
    print("Limitations:")
    for limitation in report.evidence_report.limitations:
        print(f"  - {limitation}")
    print("Use --json for source state IDs and the full baseline.")


if __name__ == "__main__":
    main()
