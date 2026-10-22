"""Machine-readable report structures shared by every evaluation track."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.evaluation.metrics import Ratio

REPORT_VERSION = 1


class CaseResult(BaseModel):
    id: str
    category: str
    tags: list[str]
    passed: bool
    failures: list[str] = Field(default_factory=list)
    observed: dict[str, Any] = Field(default_factory=dict)


class SkippedItem(BaseModel):
    item: str
    reason: str


class TrackResult(BaseModel):
    """One evaluation track. Failed cases stay in results; nothing is dropped."""

    track: str
    status: Literal["completed", "skipped"]
    synthetic: bool
    description: str
    cases: int = 0
    passed: int = 0
    failed: int = 0
    metrics: dict[str, Any] = Field(default_factory=dict)
    results: list[CaseResult] = Field(default_factory=list)
    skipped: list[SkippedItem] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def track_from_cases(
    track: str,
    description: str,
    results: list[CaseResult],
    metrics: dict[str, Ratio | Any],
    limitations: list[str],
    skipped: list[SkippedItem] | None = None,
) -> TrackResult:
    return TrackResult(
        track=track,
        status="completed",
        synthetic=True,
        description=description,
        cases=len(results),
        passed=sum(r.passed for r in results),
        failed=sum(not r.passed for r in results),
        metrics=metrics,
        results=results,
        skipped=skipped or [],
        limitations=limitations,
    )


def compare(failures: list[str], name: str, expected: Any, observed: Any) -> None:
    """Record a failure if an expectation that was set is not met."""
    if expected is not None and expected != observed:
        failures.append(f"{name}: expected {expected!r}, observed {observed!r}")
