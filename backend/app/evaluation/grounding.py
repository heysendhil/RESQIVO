"""Grounded Q&A track: runs the real QuestionAnsweringService with fixture
retrieval and scripted model answers.

The application's own sentence-level checker (app/qa/grounding.py) decides
acceptance; this track records which rule rejected each answer and compares it
with the dataset. The checker is lexical, so semantic support is reported as
needing human review or an LLM judge.
"""

from collections import Counter

from app.evaluation.dataset import GroundingCase, LoadedDataset
from app.evaluation.fakes import FixtureRetriever, ScriptedChatModel, to_passage
from app.evaluation.metrics import count_ratio
from app.evaluation.report import (
    CaseResult,
    SkippedItem,
    TrackResult,
    compare,
    track_from_cases,
)
from app.qa.config import DEFAULT_MAX_DISTANCE, DEFAULT_TOP_K
from app.qa.errors import QAError
from app.qa.grounding import check_grounding
from app.qa.prompt import passage_label
from app.qa.schemas import AnswerResponse
from app.qa.service import QuestionAnsweringService
from app.rag.store import KnowledgeBaseEmptyError, RetrievedPassage


def _run_case(case: GroundingCase, loaded: LoadedDataset, top_k, max_distance):
    passages = [
        to_passage(loaded.passages[r.passage], r.distance) for r in case.retrieved or []
    ]
    error = KnowledgeBaseEmptyError("empty") if case.knowledge_base_empty else None
    model = ScriptedChatModel(answer=case.scripted_answer)
    service = QuestionAnsweringService(
        FixtureRetriever(passages, error), model, top_k=top_k, max_distance=max_distance
    )
    shown = [p for p in passages[:top_k] if p.distance <= max_distance]
    try:
        return service.answer(case.question), None, shown, model
    except QAError as exc:
        return None, type(exc).__name__, shown, model
    except Exception as exc:  # reported as a failed case, never dropped
        return None, f"unexpected:{type(exc).__name__}", shown, model


def _citations_valid(answer: AnswerResponse, shown: list[RetrievedPassage]) -> bool:
    """Every citation's metadata equals the passage shown under its label."""
    by_label = {passage_label(i): p for i, p in enumerate(shown)}
    return all(
        c.label in by_label
        and (c.source_id, c.title, c.publisher, c.url, c.chunk_id, c.synthetic)
        == (
            by_label[c.label].source_id,
            by_label[c.label].title,
            by_label[c.label].publisher,
            by_label[c.label].url,
            by_label[c.label].chunk_id,
            by_label[c.label].synthetic,
        )
        for c in answer.citations
    )


def run_grounding(
    loaded: LoadedDataset,
    top_k: int = DEFAULT_TOP_K,
    max_distance: float = DEFAULT_MAX_DISTANCE,
) -> TrackResult:
    results: list[CaseResult] = []
    answered: list[tuple[GroundingCase, AnswerResponse, bool]] = []
    rules: Counter[str] = Counter()

    for case in loaded.dataset.grounding:
        response, error, shown, model = _run_case(case, loaded, top_k, max_distance)
        expected = case.expected
        failures: list[str] = []
        compare(failures, "error", expected.error, error)
        if expected.error is None and error is not None:
            failures.append(f"error: unexpected {error}")
        observed: dict = {"error": error, "model_calls": model.calls["answer"]}
        if response is not None:
            rule = None
            if model.answers and response.reason in (None, "answer_not_grounded"):
                check = check_grounding(model.answers[-1], shown)
                rule = check.rule
                observed["sentences"] = [
                    {"index": s.index, "factual": s.factual, "rule": s.rule}
                    for s in check.sentences
                ]
            if rule:
                rules[rule] += 1
            cited = [c.source_id for c in response.citations]
            observed.update(
                status=response.status,
                reason=response.reason,
                grounding_rule=rule,
                cited_sources=cited,
            )
            compare(failures, "status", expected.status, response.status)
            compare(failures, "reason", expected.reason, response.reason)
            compare(failures, "grounding_rule", expected.grounding_rule, rule)
            if response.status == "answered":
                valid = _citations_valid(response, shown)
                answered.append((case, response, valid))
                observed["citations_structurally_valid"] = valid
                if expected.cited_sources:
                    compare(failures, "cited_sources", expected.cited_sources, cited)
                if not valid:
                    failures.append("citations: metadata does not match retrieval")
        results.append(
            CaseResult(
                id=case.id,
                category=case.category,
                tags=case.tags,
                passed=not failures,
                failures=failures,
                observed=observed,
            )
        )

    by_id = {r.id: r for r in results}
    cases = loaded.dataset.grounding

    def tagged(tag):
        return [c for c in cases if tag in c.tags]

    metrics = {
        "answerable_answered": count_ratio(
            by_id[c.id].observed.get("status") == "answered"
            for c in tagged("answerable")
        ),
        "unanswerable_declined": count_ratio(
            by_id[c.id].observed.get("status") == "insufficient_evidence"
            for c in tagged("unanswerable")
        ),
        "unsupported_answers_rejected": count_ratio(
            by_id[c.id].observed.get("reason") == "answer_not_grounded"
            for c in cases
            if {"unsupported_claim", "fabricated_citation", "uncited_answer"}
            & set(c.tags)
        ),
        "rejected_by_expected_rule": count_ratio(
            by_id[c.id].observed.get("grounding_rule") == c.expected.grounding_rule
            for c in cases
            if c.expected.grounding_rule
        ),
        "answered_with_citation": count_ratio(
            bool(r.citations) for _, r, _ in answered
        ),
        "citations_structurally_valid": count_ratio(v for *_, v in answered),
        "expected_sources_cited": count_ratio(
            [c.source_id for c in r.citations] == case.expected.cited_sources
            for case, r, _ in answered
            if case.expected.cited_sources
        ),
        "grounding_rejections_by_rule": dict(sorted(rules.items())),
    }
    return track_from_cases(
        track="grounding",
        description=(
            "Grounded Q&A through the real QuestionAnsweringService with fixture "
            "retrieval and scripted answers, checked by the application's "
            "sentence-level grounding validator. Measures the application's "
            "handling, not model quality."
        ),
        results=results,
        metrics=metrics,
        skipped=[
            SkippedItem(
                item=f"semantic_support ({len(answered)} answered responses)",
                reason=(
                    "The validator checks citations, numbers and word overlap. "
                    "Whether cited passages mean what each sentence says needs a "
                    "human reviewer or an LLM judge; not assessed offline."
                ),
            )
        ],
        limitations=[
            "Scripted answers stand in for the model, so results describe the "
            "application's safeguards, not the model's answer quality.",
            "Support checks are lexical: a sentence whose words mostly come from "
            "the cited passage can pass while misstating it, and a faithful "
            "paraphrase can be rejected.",
            "Instruction-like passage text is detected with vocabulary rules; "
            "injections phrased without that vocabulary are not recognised.",
        ],
    )
