"""Tool-calling track: runs the review and drafting workflows with tool calling
enabled, using scripted structured tool calls. Guardrail metrics compare what
the application did with what the dataset says it must do; the allowlist and
stage policy are used unchanged."""

import copy
from typing import Any

from app.evaluation.dataset import LoadedDataset, ToolCallingCase
from app.evaluation.drafting import build_request, fixture_passages
from app.evaluation.fakes import FixtureRetriever, ScriptedChatModel, retrieval_error
from app.evaluation.metrics import count_ratio
from app.evaluation.report import CaseResult, TrackResult, compare, track_from_cases
from app.models.plan import PlanValidationRequest
from app.qa.config import DEFAULT_MAX_DISTANCE, DEFAULT_TOP_K
from app.qa.errors import QAError
from app.qa.service import QuestionAnsweringService
from app.workflow.drafting import DraftPlanWorkflow
from app.workflow.graph import ReviewWorkflow
from app.workflow.tool_calling import STAGE_TOOLS, Stage
from app.workflow.tools import make_search_guidance_tool, make_validate_plan_tool

UNAUTHORIZED_REASONS = {"unknown_tool", "unauthorized_tool"}
PRE_SCHEMA_REASONS = UNAUTHORIZED_REASONS | {"malformed_call"}


def _plan(loaded: LoadedDataset, allocations_name: str) -> PlanValidationRequest:
    base = loaded.dataset.base_request
    return PlanValidationRequest.model_validate(
        {
            "resources": base["resources"],
            "shelters": base["shelters"],
            "allocations": loaded.dataset.review_plans[allocations_name],
        }
    )


def _resolve_args(args: Any, loaded: LoadedDataset, plan) -> Any:
    if args == "$plan":
        return plan.model_dump(mode="json")
    if args == "$base_plan":
        return _plan(loaded, "within_stock").model_dump(mode="json")
    if args == "$plan_inflated_stock":
        inflated = plan.model_dump(mode="json")
        inflated["resources"][0]["quantity_available"] = 999999
        return inflated
    return copy.deepcopy(args)


def _stage(case: ToolCallingCase) -> Stage:
    if case.workflow == "draft":
        return Stage.DRAFT_GUIDANCE
    return Stage.PLAN_REVIEW if case.plan else Stage.GUIDANCE


def _run_case(case: ToolCallingCase, loaded: LoadedDataset, top_k, max_distance):
    plan = _plan(loaded, case.plan) if case.plan else None
    turns = [
        {
            "text": turn.text,
            "tool_calls": [
                {"name": c.name, "args": _resolve_args(c.args, loaded, plan)}
                for c in turn.tool_calls
            ],
            "invalid_tool_calls": [
                {"name": c.name, "args": c.args} for c in turn.invalid_tool_calls
            ],
        }
        for turn in case.turns
    ]
    model = ScriptedChatModel(
        draft=loaded.dataset.default_draft,
        corrections=case.scripted_corrections,
        turns=turns,
    )
    retriever = FixtureRetriever(
        fixture_passages(loaded, case),
        retrieval_error() if case.retrieval_error else None,
    )
    workflow_type = DraftPlanWorkflow if case.workflow == "draft" else ReviewWorkflow
    workflow = workflow_type(
        search_tool=make_search_guidance_tool(retriever),
        validate_tool=make_validate_plan_tool(),
        answer_service=QuestionAnsweringService(
            retriever, model, top_k=top_k, max_distance=max_distance
        ),
        model=model,
        top_k=top_k,
        tool_calling=True,
        max_tool_calls=case.max_tool_calls,
        max_distance=max_distance,
    )
    request_id = f"eval-{case.id}"
    try:
        if case.workflow == "draft":
            state = workflow.run_state(build_request(loaded, {}), request_id)
        else:
            state = workflow.run_state(case.question, plan, request_id)
        return state, None, model, retriever
    except QAError as exc:
        return None, type(exc).__name__, model, retriever
    except Exception as exc:  # reported as a failed case, never dropped
        return None, f"unexpected:{type(exc).__name__}", model, retriever


def run_tool_calling(
    loaded: LoadedDataset,
    top_k: int = DEFAULT_TOP_K,
    max_distance: float = DEFAULT_MAX_DISTANCE,
) -> TrackResult:
    results: list[CaseResult] = []
    observed_records: list[tuple[ToolCallingCase, list[tuple]]] = []

    for case in loaded.dataset.tool_calling:
        state, error, model, retriever = _run_case(case, loaded, top_k, max_distance)
        expected = case.expected
        stage = _stage(case)
        failures: list[str] = []
        bound_ok = all(tools == list(STAGE_TOOLS[stage]) for tools in model.bound_tools)
        observed: dict = {
            "stage": stage.value,
            "error": error,
            "bound_tools": model.bound_tools,
            "bound_tools_match_stage": bound_ok,
            "executed_searches": retriever.calls,
            "model_calls": dict(model.calls),
        }
        if not bound_ok:
            failures.append("bound tools differ from the stage policy")
        compare(
            failures, "bound_tools_unchanged", expected.bound_tools_unchanged, bound_ok
        )
        compare(
            failures, "executed_searches", expected.executed_searches, retriever.calls
        )
        if expected.outcome == "error":
            compare(failures, "error", expected.error, error)
        elif error is not None:
            failures.append(f"error: unexpected {error}")

        if state is not None:
            answer = state["answer"]
            records = [(r.tool, r.status, r.reason) for r in state["tool_records"]]
            observed_records.append((case, records))
            observed.update(
                outcome=answer.status,
                reason=answer.reason,
                records=[list(r) for r in records],
                tool_call_count=state["tool_call_count"],
            )
            compare(failures, "outcome", expected.outcome, answer.status)
            compare(failures, "reason", expected.reason, answer.reason)
            if expected.records is not None:
                compare(
                    failures, "records", [tuple(r) for r in expected.records], records
                )
            if "validation" in state:
                valid = state["validation"].valid
                observed["final_valid"] = valid
                compare(failures, "final_valid", expected.final_valid, valid)
                if case.workflow == "draft":
                    status = "draft_valid" if valid else "draft_invalid"
                    observed["draft_status"] = status
                    compare(failures, "draft_status", expected.draft_status, status)
            stage_tools = set(STAGE_TOOLS[stage])
            if any(t not in stage_tools for t, s, _ in records if s == "executed"):
                failures.append("a tool not allowed at this stage was executed")
        else:
            observed["outcome"] = "error"
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
    all_records = [r for _, records in observed_records for r in records]
    expected_vs_observed = [
        (tuple(exp), obs[i] if i < len(obs) else None)
        for case, obs in observed_records
        for i, exp in enumerate(case.expected.records or [])
    ]

    def enforced(reasons: set[str]):
        return count_ratio(
            exp == obs for exp, obs in expected_vs_observed if exp[2] in reasons
        )

    cases = loaded.dataset.tool_calling
    metrics = {
        "requested_calls": len(all_records),
        "requests_authorized_for_stage": count_ratio(
            reason not in UNAUTHORIZED_REASONS for _, _, reason in all_records
        ),
        "requests_with_valid_arguments": count_ratio(
            reason != "invalid_arguments"
            for _, _, reason in all_records
            if reason not in PRE_SCHEMA_REASONS
        ),
        "executions_succeeded": count_ratio(
            status == "executed"
            for _, status, _ in all_records
            if status in ("executed", "failed")
        ),
        "unauthorized_tools_executed": sum(
            1
            for case, records in observed_records
            for tool, status, _ in records
            if status == "executed" and tool not in STAGE_TOOLS[_stage(case)]
        ),
        "expected_unauthorized_rejected": enforced(UNAUTHORIZED_REASONS),
        "expected_invalid_arguments_rejected": enforced({"invalid_arguments"}),
        "expected_malformed_or_repeated_rejected": enforced(
            {"malformed_call", "duplicate_call"}
        ),
        "expected_fact_changes_rejected": enforced({"plan_facts_mismatch"}),
        "expected_executions_performed": count_ratio(
            exp == obs for exp, obs in expected_vs_observed if exp[1] == "executed"
        ),
        "tool_call_limit_enforced": count_ratio(
            by_id[c.id].observed["error"] == "ToolCallLimitError"
            for c in cases
            if "limit" in c.tags and c.expected.error == "ToolCallLimitError"
        ),
        "prompt_injection_resisted": count_ratio(
            by_id[c.id].passed for c in cases if "prompt_injection" in c.tags
        ),
        "final_answer_without_tool": count_ratio(
            by_id[c.id].observed.get("records") == []
            and by_id[c.id].observed["error"] is None
            for c in cases
            if "no_tool_needed" in c.tags
        ),
        "bound_tools_match_stage": count_ratio(
            r.observed["bound_tools_match_stage"] for r in results
        ),
    }
    return track_from_cases(
        track="tool_calling",
        description=(
            "Model-initiated tool calling with the production allowlist, stage "
            "policy, argument checks and limits, driven by scripted structured "
            "tool calls. Guardrail metrics compare behaviour with the dataset."
        ),
        results=results,
        metrics=metrics,
        limitations=[
            "Scripted tool calls stand in for Claude, so requests_authorized_for_stage "
            "and requests_with_valid_arguments describe the fixtures (which include "
            "deliberately bad calls), not model behaviour.",
            "Whether Claude selects tools sensibly needs a supervised live run.",
        ],
    )
