import math
from dataclasses import dataclass
from typing import Literal

from sherlock.capabilities.state.anomalies import AnomalyReport
from .reasoning_models import ReasoningReport


Stage = Literal["UNDERSTAND", "PLAN", "COLLECT", "ANALYZE", "GENERATE_HYPOTHESES", "CRITIQUE", "VERIFY", "COMPLETE"]
Status = Literal[
    "ANOMALIES_FOUND", "NO_ANOMALY_FOUND", "INSUFFICIENT_EVIDENCE", "DATA_UNAVAILABLE"
]


@dataclass(frozen=True, slots=True)
class InvestigationRequest:
    state_id: int
    hours: float = 24.0
    limit: int = 200
    min_samples: int = 30
    min_span_seconds: float = 300.0

    def __post_init__(self) -> None:
        if type(self.state_id) is not int or self.state_id < 1:
            raise ValueError("state_id must be a positive integer")
        if not math.isfinite(self.hours) or not 0 < self.hours <= 8760:
            raise ValueError("hours must be finite and in (0, 8760]")
        if type(self.limit) is not int or not 2 <= self.limit <= 2000:
            raise ValueError("limit must be an integer in [2, 2000]")
        if type(self.min_samples) is not int or not 2 <= self.min_samples <= self.limit:
            raise ValueError("min_samples must be an integer in [2, limit]")
        if not math.isfinite(self.min_span_seconds) or self.min_span_seconds < 0:
            raise ValueError("min_span_seconds must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class TraceEvent:
    stage: Stage
    detail: str


@dataclass(frozen=True, slots=True)
class Finding:
    statement: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CaseReport:
    schema_version: str
    engine_version: str
    request: InvestigationRequest
    status: Status
    conclusion: str
    findings: tuple[Finding, ...]
    trace: tuple[TraceEvent, ...]
    anomaly_report: AnomalyReport | None
    limitations: tuple[str, ...]
    error: str | None = None
    reasoning: ReasoningReport | None = None
