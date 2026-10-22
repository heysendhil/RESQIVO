"""Assembles the offline evaluation report."""

import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.evaluation.dataset import LoadedDataset
from app.evaluation.drafting import run_drafting
from app.evaluation.grounding import run_grounding
from app.evaluation.report import REPORT_VERSION, SkippedItem, TrackResult
from app.evaluation.tool_calling import run_tool_calling
from app.qa.config import (
    DEFAULT_MAX_DISTANCE,
    DEFAULT_MAX_TOOL_CALLS,
    DEFAULT_TOP_K,
    HARD_MAX_TOOL_CALLS,
)
from app.workflow.schemas import MAX_CORRECTION_ATTEMPTS

REPORT_LIMITATIONS = [
    "Offline tracks use scripted model outputs: they evaluate RESQIVO's "
    "guardrails, validation and citation handling, not Claude's quality.",
    "Expected outcomes were written by an AI assistant from the documented rules "
    "and have not been independently reviewed.",
    "Semantic grounding needs human review or an LLM judge; it is not scored.",
    "A plan passing the deterministic validator is not evidence of real-world "
    "operational safety.",
    "Synthetic and real-source results are separate tracks and are never combined "
    "into one score.",
]


class EvaluationReport(BaseModel):
    report_version: int = REPORT_VERSION
    generated_at: str
    mode: Literal["offline"] = "offline"
    live_model_calls: int = 0
    network: Literal["blocked"] = "blocked"
    datasets: dict[str, Any]
    configuration: dict[str, Any]
    summary: dict[str, dict[str, Any]]
    tracks: dict[str, TrackResult]
    skipped: list[SkippedItem] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=lambda: list(REPORT_LIMITATIONS))


def run_agentic_tracks(loaded: LoadedDataset) -> list[TrackResult]:
    return [run_grounding(loaded), run_drafting(loaded), run_tool_calling(loaded)]


def build_report(
    loaded: LoadedDataset,
    tracks: list[TrackResult],
    datasets: dict[str, Any] | None = None,
    providers: list[str] | None = None,
    now: datetime.datetime | None = None,
) -> EvaluationReport:
    generated = now or datetime.datetime.now(datetime.UTC)
    by_name = {track.track: track for track in tracks}
    return EvaluationReport(
        generated_at=generated.isoformat(timespec="seconds"),
        datasets={
            "agentic": {
                "path": "data/synthetic/agentic_evaluation.json",
                "version": loaded.dataset.version,
                "sha256": loaded.sha256,
                "synthetic": True,
                "cases": {
                    "grounding": len(loaded.dataset.grounding),
                    "drafting": len(loaded.dataset.drafting),
                    "tool_calling": len(loaded.dataset.tool_calling),
                },
            },
            **(datasets or {}),
        },
        configuration={
            "embedding_providers": providers or [],
            "qa_top_k": DEFAULT_TOP_K,
            "max_distance": DEFAULT_MAX_DISTANCE,
            "max_correction_attempts": MAX_CORRECTION_ATTEMPTS,
            "default_max_tool_calls": DEFAULT_MAX_TOOL_CALLS,
            "hard_max_tool_calls": HARD_MAX_TOOL_CALLS,
        },
        summary={
            name: {
                "status": track.status,
                "synthetic": track.synthetic,
                "cases": track.cases,
                "passed": track.passed,
                "failed": track.failed,
                "skipped": len(track.skipped),
            }
            for name, track in by_name.items()
        },
        tracks=by_name,
        skipped=[
            SkippedItem(item=f"{track.track}: {item.item}", reason=item.reason)
            for track in tracks
            for item in track.skipped
        ],
    )
