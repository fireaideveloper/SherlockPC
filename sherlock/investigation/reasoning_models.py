from dataclasses import dataclass
from typing import Literal


HypothesisKind = Literal['cpu_contention', 'memory_pressure', 'swap_usage']


@dataclass(frozen=True, slots=True)
class Hypothesis:
    hypothesis_id: str
    kind: HypothesisKind
    statement: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Critique:
    hypothesis_id: str
    alternatives: tuple[str, ...]
    missing_checks: tuple[str, ...]
    objections: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Verdict:
    hypothesis_id: str
    status: Literal['SUPPORTED_SIGNAL', 'INSUFFICIENT_EVIDENCE', 'REJECTED']
    reason: str
    evidence_ids: tuple[str, ...]
    cause_confirmed: bool = False


@dataclass(frozen=True, slots=True)
class ReasoningReport:
    rule_version: str
    hypotheses: tuple[Hypothesis, ...]
    critiques: tuple[Critique, ...]
    verdicts: tuple[Verdict, ...]
    summary: str
