"""Bounded, deterministic investigations over stored telemetry."""

from .engine import investigate
from .models import CaseReport, InvestigationRequest

__all__ = ["CaseReport", "InvestigationRequest", "investigate"]
