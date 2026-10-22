"""The LangGraph review workflow.

retrieve_guidance -> generate_grounded_answer -> (plan supplied?)
    no:  return_result
    yes: validate_plan -> assess_result -> (correctable and attempts left?)
         yes: correct_plan -> validate_plan -> assess_result ...
         no:  return_result

By default the workflow calls its tools directly and the model never selects
tools. With tool_calling enabled, retrieve_guidance and generate_grounded_answer
are replaced by a bounded loop in which the model may request the tools allowed
for the stage (tool_calling.py):

call_model -> (structured tool calls?)
    yes: execute_tools -> call_model ...  (application authorizes and executes)
    no:  finalize_answer

The deterministic validate_plan and correct_plan nodes run unchanged
afterwards in both modes, so the model cannot skip validation. Validity
always comes from the deterministic validator. Correction runs only for
violations that changing allocations can fix, at most MAX_CORRECTION_ATTEMPTS
times. The drafting graph (drafting.py) reuses these nodes through
PlanWorkflowBase.
"""

import logging
import time
from typing import Any, Protocol, TypedDict

from langchain_core.messages import AnyMessage
from langchain_core.tools import BaseTool
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph

from app.limits import check_deadline
from app.models.plan import PlanValidationRequest
from app.observability import (
    METRICS,
    ensure_request_context,
    log_event,
    record_answer,
    record_correction,
    record_model_call,
    record_retrieval,
    record_validation,
    run_summary,
)
from app.qa.config import DEFAULT_MAX_TOOL_CALLS, HARD_MAX_TOOL_CALLS
from app.qa.errors import (
    ModelResponseError,
    QAConfigurationError,
    RetrievalUnavailableError,
    ToolCallLimitError,
)
from app.qa.prompt import INSUFFICIENT_EVIDENCE_MARKER
from app.qa.schemas import AnswerResponse
from app.qa.service import QuestionAnsweringService, grounded_citations
from app.rag.embeddings import EmbeddingModelUnavailableError
from app.rag.store import KnowledgeBaseEmptyError, RetrievalError, RetrievedPassage
from app.services.validation import ValidationResult
from app.workflow.correction import build_correction_messages, parse_corrected_plan
from app.workflow.schemas import (
    CORRECTABLE_CODES,
    MAX_CORRECTION_ATTEMPTS,
    PlanReview,
    ReviewResponse,
)
from app.workflow.tool_calling import (
    SEARCH_GUIDANCE,
    STAGE_TOOLS,
    VALIDATE_PLAN,
    Stage,
    ToolCallRecord,
    ToolExecutor,
    build_tool_messages,
    requested_calls,
    validate_tool_limit,
)

logger = logging.getLogger("resqivo.workflow")

# Backstop well above the longest legitimate path (about 10 steps).
RECURSION_LIMIT = 25
# With tool calling, each model turn that requests tools uses at least one of
# the at most HARD_MAX_TOOL_CALLS calls and adds two steps.
TOOL_RECURSION_LIMIT = RECURSION_LIMIT + 2 * HARD_MAX_TOOL_CALLS + 2


class ChatModel(Protocol):
    def invoke(self, input: Any) -> Any: ...


class ReviewState(TypedDict, total=False):
    question: str
    plan: PlanValidationRequest | None
    passages: list[RetrievedPassage]
    knowledge_base_empty: bool
    answer: AnswerResponse
    current_plan: PlanValidationRequest
    original_validation: ValidationResult
    validation: ValidationResult
    correction_attempts: int
    trace: list[str]
    request_id: str
    # Tool-calling mode only.
    tool_stage: Stage
    messages: list[AnyMessage]
    tool_call_count: int
    tool_records: list[ToolCallRecord]
    previous_calls: set[str]


def _codes(validation: ValidationResult) -> list[str]:
    return [v.code for v in validation.violations]


class PlanWorkflowBase:
    """Nodes shared by the review and drafting graphs: retrieval, the grounded
    answer, deterministic validation and bounded allocation-only correction.
    Subclasses define the graph in _build."""

    WORKFLOW = "workflow"

    def __init__(
        self,
        search_tool: BaseTool,
        validate_tool: BaseTool,
        answer_service: QuestionAnsweringService,
        model: ChatModel,
        top_k: int = 4,
        max_corrections: int = MAX_CORRECTION_ATTEMPTS,
        tool_calling: bool = False,
        max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
        max_distance: float = 1.0,
        recursion_limit: int | None = None,
    ) -> None:
        if not 0 <= max_corrections <= MAX_CORRECTION_ATTEMPTS:
            raise ValueError(
                f"max_corrections must be between 0 and {MAX_CORRECTION_ATTEMPTS}."
            )
        validate_tool_limit(max_tool_calls)
        default_limit = TOOL_RECURSION_LIMIT if tool_calling else RECURSION_LIMIT
        if recursion_limit is not None and not 1 <= recursion_limit <= default_limit:
            raise ValueError(f"recursion_limit must be between 1 and {default_limit}.")
        if (search_tool.name, validate_tool.name) != (SEARCH_GUIDANCE, VALIDATE_PLAN):
            raise ValueError("Unexpected tools supplied to the workflow.")
        self._search = search_tool
        self._validate = validate_tool
        self._answers = answer_service
        self._model = model
        self._top_k = top_k
        self._max_corrections = max_corrections
        self._tool_calling = tool_calling
        self._max_tool_calls = max_tool_calls
        self._max_distance = max_distance
        self._recursion_limit = recursion_limit or default_limit
        self._graph = self._build()

    # Nodes -----------------------------------------------------------------

    def _retrieve_guidance(self, state: ReviewState) -> dict:
        check_deadline()
        try:
            passages = self._search.invoke(
                {"query": state["question"], "k": self._top_k}
            )
            empty = False
        except KnowledgeBaseEmptyError:
            passages, empty = [], True
        except EmbeddingModelUnavailableError as exc:
            record_retrieval("configuration_error")
            raise QAConfigurationError("The embedding model is not available.") from exc
        except RetrievalError as exc:
            record_retrieval("failure")
            raise RetrievalUnavailableError("Knowledge retrieval failed.") from exc
        record_retrieval("empty_knowledge_base" if empty else "success")
        log_event(
            logger,
            "workflow.node",
            node="retrieve_guidance",
            passages=len(passages),
            empty=empty,
        )
        return {
            "passages": passages,
            "knowledge_base_empty": empty,
            "trace": [*state.get("trace", []), "retrieve_guidance"],
        }

    def _generate_grounded_answer(self, state: ReviewState) -> dict:
        if state["knowledge_base_empty"]:
            answer = AnswerResponse(
                status="insufficient_evidence", reason="knowledge_base_empty"
            )
            record_answer(answer.status, answer.reason)
        else:
            answer = self._answers.answer_from_passages(
                state["question"], state["passages"]
            )
        log_event(
            logger,
            "workflow.node",
            node="generate_grounded_answer",
            status=answer.status,
            reason=answer.reason,
            citations=len(answer.citations),
        )
        return self._answer_update(state, answer, "generate_grounded_answer")

    def _answer_update(self, state: ReviewState, answer: AnswerResponse, node: str):
        update: dict = {"answer": answer, "trace": [*state["trace"], node]}
        if state.get("plan") is not None:
            update["current_plan"] = state["plan"]
            update["correction_attempts"] = 0
        return update

    # Tool-calling nodes ------------------------------------------------------

    def _tool_stage(self, state: ReviewState) -> Stage:
        raise NotImplementedError

    def _call_model(self, state: ReviewState) -> dict:
        update: dict = {}
        if "messages" not in state:
            stage = self._tool_stage(state)
            plan = state.get("plan") if stage is Stage.PLAN_REVIEW else None
            update = {
                "tool_stage": stage,
                "messages": build_tool_messages(
                    state["question"], plan, self._max_tool_calls
                ),
                "passages": [],
                "knowledge_base_empty": False,
                "tool_call_count": 0,
                "tool_records": [],
                "previous_calls": set(),
            }
        stage = update.get("tool_stage") or state["tool_stage"]
        messages = update.get("messages") or state["messages"]
        tools = {SEARCH_GUIDANCE: self._search, VALIDATE_PLAN: self._validate}
        # Only the stage's tools are offered; authorization is enforced again
        # when calls are executed.
        bound = self._model.bind_tools([tools[name] for name in STAGE_TOOLS[stage]])
        check_deadline()
        try:
            reply = bound.invoke(messages)
        except Exception as exc:
            record_model_call("tool_turn", ok=False)
            raise ModelResponseError("The language model request failed.") from exc
        metadata = getattr(reply, "response_metadata", None) or {}
        refused = metadata.get("stop_reason") == "refusal"
        record_model_call("tool_turn", ok=not refused)
        if refused:
            raise ModelResponseError("The language model declined to answer.")
        calls = requested_calls(reply)
        log_event(
            logger,
            "workflow.node",
            node="call_model",
            stage=stage.value,
            requested_calls=len(calls),
        )
        return {
            **update,
            "messages": [*messages, reply],
            "trace": [*state["trace"], "call_model"],
        }

    def _execute_tools(self, state: ReviewState) -> dict:
        calls = requested_calls(state["messages"][-1])
        count = state["tool_call_count"]
        stage = state["tool_stage"]
        if count + len(calls) > self._max_tool_calls:
            METRICS.increment("tool_call_limit_total", stage=stage.value)
            log_event(
                logger,
                "workflow.node",
                node="execute_tools",
                stage=stage.value,
                outcome="tool_call_limit",
                used=count,
                requested=len(calls),
                limit=self._max_tool_calls,
            )
            raise ToolCallLimitError("The tool-call limit was reached.")
        executor = ToolExecutor(
            tools={SEARCH_GUIDANCE: self._search, VALIDATE_PLAN: self._validate},
            stage=stage,
            plan=state.get("plan"),
            max_distance=self._max_distance,
        )
        previous = set(state["previous_calls"])
        turn = executor.run_turn(calls, count + 1, state["passages"], previous)
        return {
            "messages": [*state["messages"], *turn.messages],
            "passages": turn.passages,
            "knowledge_base_empty": turn.knowledge_base_empty,
            "tool_call_count": count + len(calls),
            "tool_records": [*state["tool_records"], *turn.records],
            "previous_calls": previous,
            "trace": [*state["trace"], "execute_tools"],
        }

    def _finalize_answer(self, state: ReviewState) -> dict:
        answer = self._tool_answer(state)
        record_answer(answer.status, answer.reason)
        log_event(
            logger,
            "workflow.node",
            node="finalize_answer",
            stage=state["tool_stage"].value,
            tool_calls=state["tool_call_count"],
            status=answer.status,
            reason=answer.reason,
            citations=len(answer.citations),
        )
        return self._answer_update(state, answer, "finalize_answer")

    def _tool_answer(self, state: ReviewState) -> AnswerResponse:
        if state["knowledge_base_empty"]:
            return AnswerResponse(
                status="insufficient_evidence", reason="knowledge_base_empty"
            )
        text = (getattr(state["messages"][-1], "text", "") or "").strip()
        if not text:
            raise ModelResponseError("The language model returned no answer.")
        if INSUFFICIENT_EVIDENCE_MARKER in text:
            return AnswerResponse(
                status="insufficient_evidence",
                reason="model_reported_insufficient_evidence",
            )
        passages = state["passages"]
        searched = any(
            r.tool == SEARCH_GUIDANCE and r.status == "executed"
            for r in state["tool_records"]
        )
        if not passages:
            reason = "no_relevant_passages" if searched else "answer_not_grounded"
            return AnswerResponse(status="insufficient_evidence", reason=reason)
        citations = grounded_citations(text, passages, log_context="tool_calling")
        if citations is None:
            return AnswerResponse(
                status="insufficient_evidence", reason="answer_not_grounded"
            )
        return AnswerResponse(
            status="answered",
            answer=text,
            citations=citations,
            uses_synthetic_sources=any(c.synthetic for c in citations),
        )

    def _validate_plan(self, state: ReviewState) -> dict:
        plan = state["current_plan"]
        validation = self._validate.invoke(plan.model_dump())
        record_validation(validation.valid)
        log_event(
            logger,
            "workflow.node",
            node="validate_plan",
            valid=validation.valid,
            codes=_codes(validation),
            attempt=state["correction_attempts"],
        )
        update: dict = {
            "validation": validation,
            "trace": [*state["trace"], "validate_plan"],
        }
        if "original_validation" not in state:
            update["original_validation"] = validation
        return update

    def _assess_result(self, state: ReviewState) -> dict:
        return {"trace": [*state["trace"], "assess_result"]}

    def _correct_plan(self, state: ReviewState) -> dict:
        attempts = state["correction_attempts"] + 1
        plan = state["current_plan"]
        check_deadline()  # outside the try: a timeout is not a failed attempt
        try:
            reply = self._model.invoke(
                build_correction_messages(plan, state["validation"])
            )
            record_model_call("correction", ok=True)
            text = (getattr(reply, "text", "") or "").strip()
            corrected = parse_corrected_plan(text, state["plan"])
        except Exception:
            # A failed attempt still counts; the last validated plan is kept.
            record_model_call("correction", ok=False)
            corrected = None
        record_correction(parsed=corrected is not None)
        log_event(
            logger,
            "workflow.node",
            node="correct_plan",
            attempt=attempts,
            parsed=corrected is not None,
        )
        return {
            "current_plan": corrected or plan,
            "correction_attempts": attempts,
            "trace": [*state["trace"], "correct_plan"],
        }

    def _return_result(self, state: ReviewState) -> dict:
        return {"trace": [*state["trace"], "return_result"]}

    # Routing ---------------------------------------------------------------

    def _after_model(self, state: ReviewState) -> str:
        if requested_calls(state["messages"][-1]):
            return "execute_tools"
        return "finalize_answer"

    def _after_tools(self, state: ReviewState) -> str:
        return "finalize_answer" if state["knowledge_base_empty"] else "call_model"

    def _after_assessment(self, state: ReviewState) -> str:
        validation = state["validation"]
        correctable = CORRECTABLE_CODES.intersection(_codes(validation))
        if (
            not validation.valid
            and correctable
            and state["correction_attempts"] < self._max_corrections
        ):
            return "correct_plan"
        return "return_result"

    def _add_guidance(self, graph: StateGraph) -> tuple[str, str]:
        """Add the guidance nodes for the configured mode and return the names of
        the first and last of them."""
        if not self._tool_calling:
            graph.add_node("retrieve_guidance", self._retrieve_guidance)
            graph.add_node("generate_grounded_answer", self._generate_grounded_answer)
            graph.add_edge("retrieve_guidance", "generate_grounded_answer")
            return "retrieve_guidance", "generate_grounded_answer"
        graph.add_node("call_model", self._call_model)
        graph.add_node("execute_tools", self._execute_tools)
        graph.add_node("finalize_answer", self._finalize_answer)
        graph.add_conditional_edges(
            "call_model", self._after_model, ["execute_tools", "finalize_answer"]
        )
        graph.add_conditional_edges(
            "execute_tools", self._after_tools, ["call_model", "finalize_answer"]
        )
        return "call_model", "finalize_answer"

    def _invoke(self, initial: dict) -> Any:
        started = time.perf_counter()
        try:
            return self._graph.invoke(
                initial, {"recursion_limit": self._recursion_limit}
            )
        except GraphRecursionError as exc:
            self._log_failure("recursion_limit", started, limit=self._recursion_limit)
            raise ToolCallLimitError("The workflow step limit was reached.") from exc
        except Exception as exc:
            self._log_failure(type(exc).__name__, started)
            raise

    def _log_failure(self, error: str, started: float, **fields: Any) -> None:
        duration_ms = (time.perf_counter() - started) * 1000
        METRICS.increment(
            "workflow_runs_total", workflow=self.WORKFLOW, outcome="error"
        )
        log_event(
            logger,
            "workflow.failed",
            **{
                "workflow": self.WORKFLOW,
                "error": error,
                "duration_ms": duration_ms,
                **fields,
                **run_summary(),
            },
        )

    def _log_complete(self, outcome: str, started: float, **fields: Any) -> None:
        duration_ms = (time.perf_counter() - started) * 1000
        METRICS.increment(
            "workflow_runs_total", workflow=self.WORKFLOW, outcome=outcome
        )
        METRICS.observe_ms("workflow_duration_ms", duration_ms, workflow=self.WORKFLOW)
        log_event(
            logger,
            "workflow.complete",
            **{
                "workflow": self.WORKFLOW,
                "outcome": outcome,
                "duration_ms": duration_ms,
                **fields,
                **run_summary(),
            },
        )

    def _build(self):
        raise NotImplementedError


class ReviewWorkflow(PlanWorkflowBase):
    WORKFLOW = "review"

    def _tool_stage(self, state: ReviewState) -> Stage:
        return Stage.GUIDANCE if state.get("plan") is None else Stage.PLAN_REVIEW

    def _after_answer(self, state: ReviewState) -> str:
        return "validate_plan" if state.get("plan") is not None else "return_result"

    def _build(self):
        graph = StateGraph(ReviewState)
        first, last = self._add_guidance(graph)
        graph.add_node("validate_plan", self._validate_plan)
        graph.add_node("assess_result", self._assess_result)
        graph.add_node("correct_plan", self._correct_plan)
        graph.add_node("return_result", self._return_result)
        graph.add_edge(START, first)
        graph.add_conditional_edges(
            last,
            self._after_answer,
            ["validate_plan", "return_result"],
        )
        graph.add_edge("validate_plan", "assess_result")
        graph.add_conditional_edges(
            "assess_result", self._after_assessment, ["correct_plan", "return_result"]
        )
        graph.add_edge("correct_plan", "validate_plan")
        graph.add_edge("return_result", END)
        return graph.compile()

    # Entry point -----------------------------------------------------------

    def run_state(
        self,
        question: str,
        plan: PlanValidationRequest | None = None,
        request_id: str | None = None,
    ) -> ReviewState:
        with ensure_request_context(request_id) as active_id:
            return self._invoke(
                {
                    "question": question,
                    "plan": plan,
                    "trace": [],
                    "request_id": active_id,
                }
            )

    def run(
        self,
        question: str,
        plan: PlanValidationRequest | None = None,
        request_id: str | None = None,
    ) -> ReviewResponse:
        with ensure_request_context(request_id) as active_id:
            started = time.perf_counter()
            state = self.run_state(question, plan, active_id)
            review = None
            if plan is not None:
                original, final = state["original_validation"], state["validation"]
                review = PlanReview(
                    original_validation=original,
                    final_plan=state["current_plan"],
                    final_validation=final,
                    correction_attempts=state["correction_attempts"],
                    corrected=(not original.valid) and final.valid,
                    uncorrectable_codes=sorted(set(_codes(final)) - CORRECTABLE_CODES),
                )
            self._log_complete(
                state["answer"].status,
                started,
                answer_reason=state["answer"].reason,
                plan_supplied=plan is not None,
                final_valid=review.final_validation.valid if review else None,
                correction_attempts=review.correction_attempts if review else 0,
                final_codes=_codes(review.final_validation) if review else [],
            )
            return ReviewResponse(answer=state["answer"], plan_review=review)
