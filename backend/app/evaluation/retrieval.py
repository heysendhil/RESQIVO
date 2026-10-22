"""Retrieval tracks. Ranks come from the existing evaluation scripts
(scripts/evaluate_embeddings.py for synthetic fixtures and
scripts/evaluate_who_retrieval.py for WHO-01); this module only turns them into
uniform metrics. Synthetic and real-source results are separate tracks and are
never combined."""

from typing import Any

from app.evaluation.metrics import summarize_ranks
from app.evaluation.report import CaseResult, SkippedItem, TrackResult

CUTOFFS = (1, 3, 5)
PASS_CUTOFF = 5


def _query_results(rows: list[dict[str, Any]], category_key: str | None):
    return [
        CaseResult(
            id=row["id"],
            category=row.get(category_key, "retrieval")
            if category_key
            else "retrieval",
            tags=[],
            passed=row["rank"] is not None and row["rank"] <= PASS_CUTOFF,
            failures=[]
            if row["rank"] is not None and row["rank"] <= PASS_CUTOFF
            else [f"relevant passage not within top {PASS_CUTOFF}"],
            observed={"rank": row["rank"]},
        )
        for row in rows
    ]


def synthetic_retrieval_track(
    runs: dict[str, dict[str, Any]], skipped: list[SkippedItem], dataset: dict
) -> TrackResult:
    """runs maps provider name to evaluate_embeddings.evaluate() output."""
    metrics: dict[str, Any] = {"dataset": dataset}
    results: list[CaseResult] = []
    for provider, run in runs.items():
        rows = run["queries_detail"]
        depth = run["corpus_passages"]
        by_type = {
            kind: summarize_ranks(
                {r["id"]: r["rank"] for r in rows if r["type"] == kind}, depth, CUTOFFS
            ).model_dump()
            for kind in sorted({r["type"] for r in rows})
        }
        metrics[provider] = {
            "overall": summarize_ranks(
                {r["id"]: r["rank"] for r in rows}, depth, CUTOFFS
            ).model_dump(),
            "by_query_type": by_type,
        }
        for result in _query_results(rows, "type"):
            result.id = f"{provider}:{result.id}"
            results.append(result)
    return TrackResult(
        track="retrieval_synthetic",
        status="completed" if runs else "skipped",
        synthetic=True,
        description=(
            "Retrieval over the synthetic embedding evaluation set (one relevant "
            "passage per query, full ranking of the corpus), in memory."
        ),
        cases=len(results),
        passed=sum(r.passed for r in results),
        failed=sum(not r.passed for r in results),
        metrics=metrics,
        results=results,
        skipped=skipped,
        limitations=[
            "Small synthetic corpus of single-topic passages; results do not "
            "predict performance on real multi-topic documents.",
            f"A query passes when its relevant passage is within the top "
            f"{PASS_CUTOFF}; this cut-off is a reporting convention, not a quality "
            "threshold.",
        ],
    )


def real_source_retrieval_track(
    runs: dict[str, dict[str, Any]], skipped: list[SkippedItem]
) -> TrackResult:
    """runs maps provider name to evaluate_who_retrieval.evaluate() output. Only
    IDs, ranks, hashes and chunk IDs are kept; no source text is copied."""
    metrics: dict[str, Any] = {}
    results: list[CaseResult] = []
    for provider, run in runs.items():
        rows = run["results"]
        metrics[provider] = {
            "source_id": run["source_id"],
            "eval_set_version": run["eval_set_version"],
            "source_text_sha256": run["source_text_sha256"],
            "questions_sha256": run["questions_sha256"],
            "chunks": run["chunks"],
            "overall": summarize_ranks(
                {r["id"]: r["rank"] for r in rows}, run["k"], CUTOFFS
            ).model_dump(),
        }
        for result in _query_results(rows, None):
            result.id = f"{provider}:{result.id}"
            results.append(result)
    return TrackResult(
        track="retrieval_real_source",
        status="completed" if runs else "skipped",
        synthetic=False,
        description=(
            "Retrieval over WHO-01 (CC BY-NC-SA 3.0 IGO) using local, Git-ignored "
            "source text and AI-written questions, in memory. A query's relevant "
            "chunk is the first one containing its verbatim evidence span."
        ),
        cases=len(results),
        passed=sum(r.passed for r in results),
        failed=sum(not r.passed for r in results),
        metrics=metrics,
        results=results,
        skipped=skipped,
        limitations=[
            "One source document and 28 questions written by an AI assistant; "
            "not yet reviewed by a domain expert.",
            "Never combined with synthetic results.",
        ],
    )
