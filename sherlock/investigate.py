"""Run a bounded investigation of one stored state snapshot."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from sherlock.baseline import _json_default
from sherlock.investigation import InvestigationRequest, investigate
from sherlock.investigation.source import sqlite_source


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
    try:
        request = InvestigationRequest(
            state_id=args.state, hours=args.hours, limit=args.limit,
            min_samples=args.min_samples, min_span_seconds=args.min_span_seconds,
        )
    except ValueError as error:
        parser.error(str(error))
    report = investigate(request, sqlite_source(args.db))
    if args.json:
        print(json.dumps(asdict(report), default=_json_default,
                         ensure_ascii=False, indent=2, allow_nan=False))
    else:
        print(f"Case for state {request.state_id}: {report.status}")
        print(report.conclusion)
        print("Trace: " + " -> ".join(event.stage for event in report.trace))
        for finding in report.findings:
            print(f"[{', '.join(finding.evidence_ids)}] {finding.statement}")
        if report.anomaly_report is not None:
            baseline = report.anomaly_report.evidence_report.baseline
            print(f"History: {baseline.sample_count} samples, {baseline.span_seconds:.1f} seconds")
            for reason in baseline.reasons:
                print(f"  {reason}")
        if report.reasoning is not None:
            print("Reasoning: " + report.reasoning.summary)
            for hypothesis, critique, verdict in zip(
                report.reasoning.hypotheses, report.reasoning.critiques,
                report.reasoning.verdicts,
            ):
                print(f"[{hypothesis.hypothesis_id}] {hypothesis.statement}")
                print(f"  Verdict: {verdict.status}: {verdict.reason}")
                print(f"  Evidence: {', '.join(hypothesis.evidence_ids)}")
                for alternative in critique.alternatives:
                    print(f"  Alternative: {alternative}")
                for objection in critique.objections:
                    print(f"  Objection: {objection}")
                for check in critique.missing_checks:
                    print(f"  Next check: {check}")
        if report.error:
            print(f"Error: {report.error}")
        print("Limitations:")
        for limitation in report.limitations:
            print(f"  - {limitation}")
    if report.status == "DATA_UNAVAILABLE":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
