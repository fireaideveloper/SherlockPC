import sqlite3
from typing import Protocol

from sherlock.capabilities.state.anomalies import detect_anomalies
from sherlock.capabilities.state.baseline import BaselineInput, build_baseline
from sherlock.storage.sqlite.state_reader import StateNotFoundError

from .models import CaseReport, Finding, InvestigationRequest, Stage, TraceEvent
from .investigator import generate_hypotheses
from .critic import critique_hypotheses
from .verifier import verify_hypotheses
from .reasoning_models import ReasoningReport


class BaselineSource(Protocol):
    def load(self, target_id: int, *, hours: float, limit: int) -> BaselineInput: ...


class _StateMachine:
    """Only forward transitions; one collection, no retries or autonomous loop."""

    _allowed = {
        None: ("UNDERSTAND",),
        "UNDERSTAND": ("PLAN",),
        "PLAN": ("COLLECT",),
        "COLLECT": ("ANALYZE", "COMPLETE"),
        "ANALYZE": ("GENERATE_HYPOTHESES", "COMPLETE"),
        "GENERATE_HYPOTHESES": ("CRITIQUE",),
        "CRITIQUE": ("VERIFY",),
        "VERIFY": ("COMPLETE",),
        "COMPLETE": (),
    }

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def move(self, stage: Stage, detail: str) -> None:
        previous = self.events[-1].stage if self.events else None
        if stage not in self._allowed[previous]:
            raise RuntimeError(f"Invalid investigation transition: {previous} -> {stage}")
        self.events.append(TraceEvent(stage, detail))


def investigate(request: InvestigationRequest, source: BaselineSource) -> CaseReport:
    """Check stored CPU/RAM/swap deviations; do not diagnose their root cause."""
    machine = _StateMachine()
    machine.move("UNDERSTAND", f"Check system deviations for state {request.state_id}.")
    machine.move("PLAN", f"One read, up to {request.limit} historical states; CPU/RAM/swap rules.")
    machine.move("COLLECT", "Read target and earlier history from the baseline source.")
    try:
        data = source.load(request.state_id, hours=request.hours, limit=request.limit)
        if data.target.state_id != request.state_id:
            raise ValueError("Source returned a different target state")
        if data.limit != request.limit:
            raise ValueError("Source returned a different history limit")
        machine.move("ANALYZE", "Build baseline and apply existing anomaly rules.")
        report = detect_anomalies(build_baseline(
            data, min_samples=request.min_samples,
            min_span_seconds=request.min_span_seconds,
        ))
    except (OSError, sqlite3.Error, StateNotFoundError, ValueError) as error:
        machine.move("COMPLETE", "No conclusion: input data unavailable or invalid.")
        return CaseReport(
            schema_version="1.1", engine_version="investigation-v2",
            request=request, status="DATA_UNAVAILABLE",
            conclusion="Cannot assess deviations: source data is unavailable or invalid.",
            findings=(), trace=tuple(machine.events), anomaly_report=None,
            limitations=("No assessment of system health or slowdown cause was made.",),
            error=str(error),
        )

    findings = tuple(Finding(item.statement, (item.evidence_id,)) for item in report.anomalies)
    machine.move("GENERATE_HYPOTHESES", "Generate at most three resource hypotheses from stored metrics.")
    hypotheses = generate_hypotheses(report.evidence_report)
    machine.move("CRITIQUE", "List alternatives, objections and missing measurements.")
    critiques = critique_hypotheses(hypotheses, report.evidence_report)
    machine.move("VERIFY", "Check evidence provenance, claim scope and absolute signal thresholds.")
    verdicts = verify_hypotheses(hypotheses, critiques, report.evidence_report)
    supported = sum(v.status == "SUPPORTED_SIGNAL" for v in verdicts)
    reasoning = ReasoningReport(
        rule_version="resource-signals-v1", hypotheses=hypotheses,
        critiques=critiques, verdicts=verdicts,
        summary=f"{supported} resource signal(s) supported. No slowdown cause confirmed.",
    )
    evidence = {item.evidence_id: item for item in report.evidence_report.evidence}
    for finding in findings:
        if not finding.evidence_ids or any(
            identifier not in evidence
            or request.state_id not in evidence[identifier].source_state_ids
            or evidence[identifier].statement != finding.statement
            for identifier in finding.evidence_ids
        ):
            raise RuntimeError("Finding has missing or inconsistent evidence")

    if report.status == "insufficient_data":
        status = "INSUFFICIENT_EVIDENCE"
        conclusion = "Not enough historical data to assess deviations."
    elif report.status == "anomalies_found":
        status = "ANOMALIES_FOUND"
        conclusion = "System metric deviations found; a slowdown cause has not been established."
    else:
        status = "NO_ANOMALY_FOUND"
        conclusion = "No deviations under the selected CPU/RAM/swap rules. This does not establish system health."
    machine.move("COMPLETE", status)
    return CaseReport(
        schema_version="1.1", engine_version="investigation-v2", request=request,
        status=status, conclusion=conclusion, findings=findings,
        trace=tuple(machine.events), anomaly_report=report,
        limitations=(*report.evidence_report.limitations,
            "Absolute signal thresholds are uncalibrated heuristics, not fault probabilities.",
            "Verification checks consistency with stored evidence, not independent measurements."),
        reasoning=reasoning,
    )
