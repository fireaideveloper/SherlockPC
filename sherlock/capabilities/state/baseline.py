import math
from dataclasses import dataclass
from datetime import datetime
from statistics import fmean, median, pstdev
from typing import Literal


METRICS = (
    ("cpu_percent", "percent"),
    ("memory_percent", "percent"),
    ("memory_used", "bytes"),
    ("memory_available", "bytes"),
    ("swap_percent", "percent"),
)


@dataclass(frozen=True, slots=True)
class BaselinePoint:
    state_id: int
    timestamp: datetime

    cpu_percent: float
    memory_percent: float
    memory_used: int
    memory_available: int
    swap_percent: float

    def __post_init__(self) -> None:
        if self.state_id < 1:
            raise ValueError("state_id must be positive")

        if self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")

        for name, unit in METRICS:
            value = getattr(self, name)

            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")

            if value < 0:
                raise ValueError(f"{name} must not be negative")

            if unit == "percent" and value > 100:
                raise ValueError(f"{name} must not exceed 100")


@dataclass(frozen=True, slots=True)
class BaselineInput:
    target: BaselinePoint
    history: tuple[BaselinePoint, ...]

    window_start: datetime
    cutoff: datetime
    limit: int


@dataclass(frozen=True, slots=True)
class MetricBaseline:
    name: str
    unit: str

    current: int | float
    count: int

    mean: float | None
    median: float | None
    minimum: int | float | None
    maximum: int | float | None
    stddev: float | None
    p10: float | None
    p90: float | None

    delta_from_median: float | None


@dataclass(frozen=True, slots=True)
class BaselineReport:
    target_id: int
    target_timestamp: datetime

    window_start: datetime
    cutoff: datetime
    limit: int

    history_ids: tuple[int, ...]
    sample_count: int

    first_observed_at: datetime | None
    last_observed_at: datetime | None
    span_seconds: float
    largest_gap_seconds: float | None

    min_samples: int
    min_span_seconds: float

    status: Literal["insufficient_data", "enough_data"]
    reasons: tuple[str, ...]

    metrics: tuple[MetricBaseline, ...]
    warnings: tuple[str, ...]


def _percentile(
    sorted_values: list[int | float],
    fraction: float,
) -> float:
    """Линейная интерполяция по позиции (n - 1) * fraction."""

    position = (len(sorted_values) - 1) * fraction

    lower = math.floor(position)
    upper = math.ceil(position)
    weight = position - lower

    return float(
        sorted_values[lower] * (1 - weight)
        + sorted_values[upper] * weight
    )


def build_baseline(
    data: BaselineInput,
    *,
    min_samples: int = 30,
    min_span_seconds: float = 300.0,
) -> BaselineReport:
    if min_samples < 2:
        raise ValueError("min_samples must be at least 2")

    if (
        not math.isfinite(min_span_seconds)
        or min_span_seconds < 0
    ):
        raise ValueError(
            "min_span_seconds must be finite and non-negative"
        )

    if data.limit < 1:
        raise ValueError("limit must be positive")

    for timestamp in (data.window_start, data.cutoff):
        if timestamp.utcoffset() is None:
            raise ValueError(
                "Window timestamps must include a timezone"
            )

    if data.window_start >= data.cutoff:
        raise ValueError("window_start must precede cutoff")

    if data.target.timestamp < data.cutoff:
        raise ValueError(
            "Target observation must not precede cutoff"
        )

    history = tuple(
        sorted(
            data.history,
            key=lambda point: (point.timestamp, point.state_id),
        )
    )

    if len(history) > data.limit:
        raise ValueError("History exceeds the requested limit")

    seen_ids: set[int] = set()

    for point in history:
        if point.state_id == data.target.state_id:
            raise ValueError(
                "Target must not be included in history"
            )

        if point.state_id in seen_ids:
            raise ValueError("Duplicate state ID in history")

        if not (
            data.window_start
            <= point.timestamp
            < data.cutoff
        ):
            raise ValueError(
                "History observation is outside the window"
            )

        seen_ids.add(point.state_id)

    count = len(history)

    first = history[0].timestamp if history else None
    last = history[-1].timestamp if history else None

    span = (
        (last - first).total_seconds()
        if first is not None and last is not None
        else 0.0
    )

    gaps = [
        (right.timestamp - left.timestamp).total_seconds()
        for left, right in zip(history, history[1:])
    ]

    largest_gap = max(gaps) if gaps else None

    reasons: list[str] = []

    if count < min_samples:
        reasons.append(
            f"Need at least {min_samples} observations; got {count}."
        )

    if span < min_span_seconds:
        reasons.append(
            f"Need at least {min_span_seconds:.1f} seconds "
            f"of observation span; got {span:.1f}."
        )

    metrics: list[MetricBaseline] = []

    for name, unit in METRICS:
        current = getattr(data.target, name)

        values = sorted(
            getattr(point, name)
            for point in history
        )

        if not values:
            metrics.append(
                MetricBaseline(
                    name=name,
                    unit=unit,
                    current=current,
                    count=0,
                    mean=None,
                    median=None,
                    minimum=None,
                    maximum=None,
                    stddev=None,
                    p10=None,
                    p90=None,
                    delta_from_median=None,
                )
            )
            continue

        historical_median = float(median(values))

        metrics.append(
            MetricBaseline(
                name=name,
                unit=unit,
                current=current,
                count=count,
                mean=fmean(values),
                median=historical_median,
                minimum=values[0],
                maximum=values[-1],
                stddev=pstdev(values),
                p10=_percentile(values, 0.10),
                p90=_percentile(values, 0.90),
                delta_from_median=current - historical_median,
            )
        )

    return BaselineReport(
        target_id=data.target.state_id,
        target_timestamp=data.target.timestamp,
        window_start=data.window_start,
        cutoff=data.cutoff,
        limit=data.limit,
        history_ids=tuple(
            point.state_id for point in history
        ),
        sample_count=count,
        first_observed_at=first,
        last_observed_at=last,
        span_seconds=span,
        largest_gap_seconds=largest_gap,
        min_samples=min_samples,
        min_span_seconds=min_span_seconds,
        status=(
            "insufficient_data"
            if reasons
            else "enough_data"
        ),
        reasons=tuple(reasons),
        metrics=tuple(metrics),
        warnings=(
            "Statistics describe stored observations, not all computer activity.",
            "Observations have equal weight; statistics are not time-weighted.",
            "Observation span does not imply continuous monitoring.",
            "The sample and span thresholds do not guarantee representativeness.",
            "Workload modes are not separated.",
            "Differences from the median are not anomaly diagnoses.",
        ),
    )
