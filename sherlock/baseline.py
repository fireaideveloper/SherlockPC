import argparse
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from sherlock.capabilities.state.baseline import (
    BaselineReport,
    build_baseline,
)
from sherlock.storage.sqlite.baseline_reader import BaselineReader
from sherlock.storage.sqlite.database import Database
from sherlock.storage.sqlite.state_reader import StateNotFoundError


MIB = 1024 * 1024


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()

    raise TypeError(
        f"Cannot serialize {type(value).__name__}"
    )


def _format_value(
    value: int | float | None,
    unit: str,
    *,
    signed: bool = False,
) -> str:
    if value is None:
        return "unknown"

    if unit == "bytes":
        number = value / MIB
        suffix = "MiB"
    else:
        number = value
        suffix = "pp" if signed else "%"

    formatted = (
        f"{number:+.2f}"
        if signed
        else f"{number:.2f}"
    )

    return f"{formatted} {suffix}"


def print_report(report: BaselineReport) -> None:
    print(f"Baseline for state: {report.target_id}")
    print(f"Status: {report.status}")
    print(f"Historical observations: {report.sample_count}")
    print(f"Maximum selected observations: {report.limit}")

    print(
        "History window: "
        f"{report.window_start.isoformat()} .. "
        f"{report.cutoff.isoformat()} (exclusive)"
    )

    print(
        f"Observed span: {report.span_seconds:.1f} s"
    )

    gap = (
        "unknown"
        if report.largest_gap_seconds is None
        else f"{report.largest_gap_seconds:.1f} s"
    )
    print(f"Largest gap between observations: {gap}")

    if report.reasons:
        print()
        print("Insufficient data:")

        for reason in report.reasons:
            print(f"  - {reason}")

    print()

    for metric in report.metrics:
        current = _format_value(
            metric.current, metric.unit
        )
        mean = _format_value(
            metric.mean, metric.unit
        )
        historical_median = _format_value(
            metric.median, metric.unit
        )
        p10 = _format_value(
            metric.p10, metric.unit
        )
        p90 = _format_value(
            metric.p90, metric.unit
        )
        delta = _format_value(
            metric.delta_from_median,
            metric.unit,
            signed=True,
        )

        print(metric.name)
        print(f"  Current: {current}")
        print(f"  Historical mean: {mean}")
        print(f"  Historical median: {historical_median}")
        print(f"  Historical P10 .. P90: {p10} .. {p90}")
        print(f"  Difference from median: {delta}")
        print()

    print("Limitations:")

    for warning in report.warnings:
        print(f"  - {warning}")

    print()
    print("Use --json for the full report and source state IDs.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Describe historical system observations "
            "before a stored state snapshot"
        )
    )

    parser.add_argument(
        "--state",
        type=int,
        required=True,
        help="Target state snapshot ID",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=24.0,
        help="History window in hours, default: 24",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Maximum historical observations, default: 200",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=30,
        help="Minimum observation count, default: 30",
    )
    parser.add_argument(
        "--min-span-seconds",
        type=float,
        default=300.0,
        help="Minimum observation span, default: 300",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the complete report as JSON",
    )

    args = parser.parse_args()

    if args.min_samples < 2:
        parser.error("--min-samples must be at least 2")

    if args.limit < args.min_samples:
        parser.error(
            "--limit must be at least --min-samples"
        )

    database = Database(
        Path.cwd() / "data" / "sherlock.db"
    )

    try:
        database.initialize()

        data = BaselineReader(database).load(
            args.state,
            hours=args.hours,
            limit=args.limit,
        )

        report = build_baseline(
            data,
            min_samples=args.min_samples,
            min_span_seconds=args.min_span_seconds,
        )

    except (
        StateNotFoundError,
        ValueError,
        sqlite3.Error,
    ) as error:
        parser.exit(
            status=1,
            message=f"Error: {error}\n",
        )

    if args.json:
        print(
            json.dumps(
                asdict(report),
                ensure_ascii=False,
                indent=2,
                default=_json_default,
                allow_nan=False,
            )
        )
    else:
        print_report(report)


if __name__ == "__main__":
    main()
