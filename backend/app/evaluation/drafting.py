"""Plan-drafting track: runs the real DraftPlanWorkflow (default mode) with
fixture retrieval and scripted drafts and corrections. The deterministic
validator decides rule compliance; a passing result is not evidence of
real-world operational safety."""

import copy
from collections import Counter

from app.evaluation.dataset import DraftingCase, LoadedDataset
from app.evaluation.fakes import FixtureRetriever, ScriptedChatModel, to_passage
from app.evaluation.metrics import count_ratio
from app.evaluation.report import CaseResult, TrackResult, compare, track_from_cases
from app.qa.config import DEFAULT_MAX_DISTANCE, DEFAULT_TOP_K
from app.qa.errors import QAError
from app.qa.service import QuestionAnsweringService
from app.rag.store import KnowledgeBaseEmptyError
from app.services.validation import validate_plan
from app.workflow.drafting import NO_EVIDENCE_LIMITATION, DraftPlanWorkflow
from app.workflow.schemas import DraftPlanRequest
from app.workflow.tools import make_search_guidance_tool, make_validate_plan_tool

DEFAULT_RETRIEVED = [("SYN-001", 0.35)]
DEFAULT_GUIDANCE = (
    "Shelter teams store drinking water in clean covered containers [SYN-001]."
)
UNKNOWN_REFERENCE_CODES = {"DOM-04-UNKNOWN-RESOURCE", "DOM-06-UNKNOWN-DESTINATION"}


def build_request(loaded: LoadedDataset, overrides: dict) -> DraftPlanRequest:
    data = copy.deepcopy(loaded.dataset.base_request)
    data.update(copy.deepcopy(overrides))
    return DraftPlanRequest.model_validate(data)


def fixture_passages(loaded: LoadedDataset, case) -> list:
    if case.knowledge_base_empty:
        return []
    if case.retrieved is None:
        return [to_passage(loaded.passages[p], d) for p, d in DEFAULT_RETRIEVED]
    return [to_passage(loaded.passages[r.passage], r.distance) for r in case.retrieved]


def _run_case(case: DraftingCase, loaded: LoadedDataset, top_k, max_distance):
    request = build_request(loaded, case.request_overrides)
    draft = (
        loaded.dataset.default_draft
        if case.scripted_draft == "default"
        else case.scripted_draft
    )
    model = ScriptedChatModel(
        answer=case.scripted_guidance or DEFAULT_GUIDANCE,
        draft=draft,
        corrections=case.scripted_corrections,
    )
    error = KnowledgeBaseEmptyError("empty") if case.knowledge_base_empty else None
    retriever = FixtureRetriever(fixture_passages(loaded, case), error)
    workflow = DraftPlanWorkflow(
        search_tool=make_search_guidance_tool(retriever),
        validate_tool=make_validate_plan_tool(),
        answer_service=QuestionAnsweringService(
            retriever, model, top_k=top_k, max_distance=max_distance
        ),
        model=model,
        top_k=top_k,
        max_distance=max_distance,
    )
    try:
        return request, workflow.run(request, f"eval-{case.id}"), None, model
    except QAError as exc:
        return request, None, type(exc).__name__, model
    except Exception as exc:  # reported as a failed case, never dropped
        return request, None, f"unexpected:{type(exc).__name__}", model


def run_drafting(
    loaded: LoadedDataset,
    top_k: int = DEFAULT_TOP_K,
    max_distance: float = DEFAULT_MAX_DISTANCE,
) -> TrackResult:
    results: list[CaseResult] = []
    drafts = []  # (case, response, preserved, agrees)

    for case in loaded.dataset.drafting:
        request, response, error, model = _run_case(case, loaded, top_k, max_distance)
        expected = case.expected
        failures: list[str] = []
        compare(failures, "error", expected.error, error)
        if expected.error is None and error is not None:
            failures.append(f"error: unexpected {error}")
        observed: dict = {"error": error, "model_calls": dict(model.calls)}
        if response is not None:
            compare(failures, "status", expected.status, response.status)
            compare(failures, "reason", expected.reason, response.reason)
            no_evidence_stated = NO_EVIDENCE_LIMITATION in response.limitations
            observed.update(
                status=response.status,
                reason=response.reason,
                evidence_available=response.evidence_available,
                no_evidence_limitation=no_evidence_stated,
            )
            if response.status != "insufficient_information":
                compare(
                    failures,
                    "evidence_available",
                    expected.evidence_available,
                    response.evidence_available,
                )
                if not response.evidence_available and not no_evidence_stated:
                    failures.append("limitations: no-evidence limitation missing")
            review = response.plan_review
            if review is not None:
                final = review.final_plan
                codes = [v.code for v in review.final_validation.violations]
                preserved = (final.resources, final.shelters) == (
                    request.resources,
                    request.shelters,
                )
                agrees = review.final_validation == validate_plan(
                    final.resources, final.allocations, final.shelters
                )
                drafts.append((case, response, preserved, agrees))
                observed.update(
                    final_codes=codes,
                    uncorrectable_codes=review.uncorrectable_codes,
                    correction_attempts=review.correction_attempts,
                    corrected=review.corrected,
                    inventory_preserved=preserved,
                    validator_agreement=agrees,
                )
                compare(failures, "final_codes", expected.final_codes, codes)
                compare(
                    failures,
                    "uncorrectable_codes",
                    expected.uncorrectable_codes,
                    review.uncorrectable_codes,
                )
                compare(
                    failures,
                    "correction_attempts",
                    expected.correction_attempts,
                    review.correction_attempts,
                )
                compare(failures, "corrected", expected.corrected, review.corrected)
                if not preserved:
                    failures.append("inventory: supplied stock or shelters changed")
                if not agrees:
                    failures.append("validator: result differs from validate_plan")
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
    cases = loaded.dataset.drafting
    final_codes = [
        [v.code for v in r.plan_review.final_validation.violations]
        for _, r, _, _ in drafts
    ]
    violations = Counter(code for codes in final_codes for code in codes)
    metrics = {
        "drafts_produced": count_ratio(
            by_id[c.id].observed.get("status") in ("draft_valid", "draft_invalid")
            for c in cases
        ),
        "drafts_passing_validator": count_ratio(
            r.plan_review.final_validation.valid for _, r, _, _ in drafts
        ),
        "unresolved_violations_by_code": dict(sorted(violations.items())),
        "unresolved_violations_total": sum(violations.values()),
        "drafts_with_unknown_references": count_ratio(
            bool(UNKNOWN_REFERENCE_CODES & set(codes)) for codes in final_codes
        ),
        "drafts_exceeding_inventory": count_ratio(
            "DOM-04" in codes for codes in final_codes
        ),
        "inventory_and_capacity_preserved": count_ratio(p for *_, p, _ in drafts),
        "validator_agreement": count_ratio(a for *_, a in drafts),
        "insufficient_information_handled": count_ratio(
            by_id[c.id].observed.get("status") == "insufficient_information"
            for c in cases
            if "insufficient_information" in c.tags
        ),
        "no_evidence_handled": count_ratio(
            by_id[c.id].observed.get("evidence_available") is False
            and by_id[c.id].observed.get("no_evidence_limitation") is True
            for c in cases
            if "no_evidence" in c.tags
        ),
        "model_errors": count_ratio(
            by_id[c.id].observed["error"] is not None for c in cases
        ),
    }
    return track_from_cases(
        track="plan_drafting",
        description=(
            "Plan drafting through the real DraftPlanWorkflow with fixture "
            "retrieval and scripted drafts. drafts_passing_validator reflects the "
            "scripted drafts, not model quality."
        ),
        results=results,
        metrics=metrics,
        limitations=[
            "Scripted drafts stand in for the model; validator pass rates here are "
            "set by the fixtures and measure handling, not drafting quality.",
            "Passing the validator means only that RESQIVO's configured rules pass. "
            "It is not evidence of operational safety, optimality, or that needs "
            "and constraints are met.",
            "Needs and free-text constraints are not validated by any rule.",
        ],
    )
