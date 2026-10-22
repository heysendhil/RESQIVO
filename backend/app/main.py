import logging
import os
import time
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.limits import (
    BodySizeLimitMiddleware,
    LimitSettings,
    RequestTimeoutError,
    deadline,
)
from app.models.plan import PlanValidationRequest
from app.observability import (
    METRICS,
    REQUEST_ID_HEADER,
    accept_request_id,
    current_request_id,
    log_event,
    record_validation,
    request_context,
    run_summary,
    tracing_privacy_defaults,
)
from app.qa.errors import (
    ModelResponseError,
    QAConfigurationError,
    QAError,
    RetrievalUnavailableError,
)
from app.qa.schemas import AnswerResponse, QuestionRequest
from app.services.validation import ValidationResult, validate_plan
from app.workflow.schemas import (
    DraftPlanRequest,
    DraftPlanResponse,
    ReviewRequest,
    ReviewResponse,
)

# Local Next.js development server. Hosted origins are added when deployed.
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app = FastAPI(
    title="RESQIVO",
    description="Disaster-response planning and resource optimization.",
    version="0.1.0",
)

logger = logging.getLogger("resqivo.api")

# Added first, so it runs inside observe_request and its 413s are logged.
app.add_middleware(BodySizeLimitMiddleware)

_OUTCOMES = {
    413: "payload_too_large",
    422: "invalid_request",
    500: "error",
    502: "model_error",
    503: "unavailable",
    504: "timeout",
}


def _outcome(status: int) -> str:
    if status < 400:
        return "success"
    return _OUTCOMES.get(status, "client_error" if status < 500 else "error")


@app.middleware("http")
async def observe_request(request: Request, call_next):
    """Correlate, time and summarise every request. A valid X-Request-ID header
    is reused; otherwise an ID is generated. The ID is returned in the same
    header. Request and response bodies are never logged."""
    request_id = accept_request_id(request.headers.get(REQUEST_ID_HEADER))
    started = time.perf_counter()
    with request_context(request_id):
        log_event(logger, "request.start", method=request.method)
        try:
            timeout = LimitSettings.from_env().request_timeout_seconds
            with deadline(timeout):
                response = await call_next(request)
            status = response.status_code
        except QAConfigurationError:
            request.state.error_code = "LimitConfigurationError"
            response = JSONResponse(
                status_code=503,
                content={"detail": "Question answering is not configured."},
            )
            status = 503
        except Exception as exc:  # unhandled: answer generically, never leak details
            request.state.error_code = type(exc).__name__
            response = JSONResponse(
                status_code=500, content={"detail": "Internal server error."}
            )
            status = 500
        route = request.scope.get("route")
        endpoint = getattr(route, "path", "unmatched")
        duration_ms = (time.perf_counter() - started) * 1000
        outcome = _outcome(status)
        error = getattr(request.state, "error_code", None)
        METRICS.increment(
            "requests_total", endpoint=endpoint, method=request.method, outcome=outcome
        )
        METRICS.observe_ms("request_duration_ms", duration_ms, endpoint=endpoint)
        if error:
            METRICS.increment("request_errors_total", endpoint=endpoint, error=error)
        log_event(
            logger,
            "request.end",
            method=request.method,
            endpoint=endpoint,
            status=status,
            outcome=outcome,
            error=error,
            duration_ms=duration_ms,
            **run_summary(),
        )
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return the service health status."""
    return {
        "status": "ok",
        "service": "RESQIVO",
    }


@app.post("/validate")
def validate(request: PlanValidationRequest) -> ValidationResult:
    """Run deterministic validation on a resource-allocation plan.

    Returns 200 with the validation result, whether or not the plan is
    valid. Malformed request bodies are rejected with 422.
    """
    result = validate_plan(
        resources=request.resources,
        allocations=request.allocations,
        shelters=request.shelters,
    )
    record_validation(result.valid)
    log_event(
        logger,
        "validation.result",
        valid=result.valid,
        codes=[v.code for v in result.violations],
    )
    return result


def _build_qa_components():
    """Build the settings, model, retriever and QA service shared by /answer and
    /review. Imported lazily so that API startup does not load retrieval or the
    model client. Raises a QAConfigurationError if configuration is invalid."""
    from app.qa.config import QASettings
    from app.qa.llm import build_chat_model
    from app.qa.service import QuestionAnsweringService
    from app.rag.config import RagSettings
    from app.rag.embeddings import get_embeddings
    from app.rag.store import KnowledgeStore

    for name, value in tracing_privacy_defaults(os.environ).items():
        # Tracing was enabled explicitly: hide run inputs and outputs by default.
        os.environ.setdefault(name, value)
    try:
        qa_settings = QASettings.from_env()
        rag_settings = RagSettings.from_env()
        embeddings = get_embeddings(
            rag_settings.embedding_provider, rag_settings.allow_model_download
        )
    except ValueError as exc:
        raise QAConfigurationError(str(exc)) from exc

    model = build_chat_model(qa_settings)
    retriever = KnowledgeStore(
        embeddings=embeddings,
        collection_name=rag_settings.collection_name,
        persist_directory=rag_settings.chroma_dir,
    )
    service = QuestionAnsweringService(
        retriever=retriever,
        model=model,
        top_k=qa_settings.top_k,
        max_distance=qa_settings.max_distance,
    )
    return qa_settings, model, retriever, service


def get_qa_service():
    """Build the question-answering service for a request."""
    return _build_qa_components()[3]


def _workflow_options(qa_settings) -> dict[str, Any]:
    """Settings shared by the review and drafting workflows. Model-initiated tool
    calling is off unless RESQIVO_TOOL_CALLING is true."""
    return {
        "top_k": qa_settings.top_k,
        "tool_calling": qa_settings.tool_calling,
        "max_tool_calls": qa_settings.max_tool_calls,
        "max_distance": qa_settings.max_distance,
    }


def get_review_workflow():
    """Build the LangGraph review workflow for a request."""
    from app.workflow.graph import ReviewWorkflow
    from app.workflow.tools import make_search_guidance_tool, make_validate_plan_tool

    qa_settings, model, retriever, service = _build_qa_components()
    return ReviewWorkflow(
        search_tool=make_search_guidance_tool(retriever),
        validate_tool=make_validate_plan_tool(),
        answer_service=service,
        model=model,
        **_workflow_options(qa_settings),
    )


def get_draft_workflow():
    """Build the LangGraph drafting workflow for a request."""
    from app.workflow.drafting import DraftPlanWorkflow
    from app.workflow.tools import make_search_guidance_tool, make_validate_plan_tool

    qa_settings, model, retriever, service = _build_qa_components()
    return DraftPlanWorkflow(
        search_tool=make_search_guidance_tool(retriever),
        validate_tool=make_validate_plan_tool(),
        answer_service=service,
        model=model,
        **_workflow_options(qa_settings),
    )


_QA_ERRORS: list[tuple[type[QAError], int, str]] = [
    (QAConfigurationError, 503, "Question answering is not configured."),
    (RetrievalUnavailableError, 503, "Knowledge retrieval is unavailable."),
    (ModelResponseError, 502, "The language model did not return a usable answer."),
    (RequestTimeoutError, 504, "The request did not complete in time."),
]


@app.exception_handler(QAError)
def handle_qa_error(request: Request, exc: QAError) -> JSONResponse:
    """Report question-answering failures without internal details or secrets."""
    request.state.error_code = type(exc).__name__  # class name only, for logs
    for error_type, status_code, detail in _QA_ERRORS:
        if isinstance(exc, error_type):
            return JSONResponse(status_code=status_code, content={"detail": detail})
    return JSONResponse(
        status_code=500, content={"detail": "Question answering failed."}
    )


@app.post("/answer")
def answer(
    request: QuestionRequest,
    service: Annotated[Any, Depends(get_qa_service)],
) -> AnswerResponse:
    """Answer a disaster-response planning question from retrieved evidence.

    Returns 200 with status "answered" and citations taken from retrieval
    metadata, or status "insufficient_evidence" with a reason. Answers are
    advisory and never change plan validation results. Malformed requests are
    rejected with 422; configuration problems with 503; model failures with 502.
    """
    return service.answer(request.question)


@app.post("/review")
def review(
    request: ReviewRequest,
    workflow: Annotated[Any, Depends(get_review_workflow)],
) -> ReviewResponse:
    """Answer a planning question with grounded guidance and, if a plan is
    supplied, validate it deterministically with at most two bounded
    corrections of its allocations.

    The answer follows the same rules as /answer. Plan validity comes only from
    the deterministic validator; model statements about validity are ignored.
    Errors use the same status codes as /answer.
    """
    return workflow.run(request.question, request.plan)


@app.post("/draft-plan")
def draft_plan(
    request: DraftPlanRequest,
    workflow: Annotated[Any, Depends(get_draft_workflow)],
) -> DraftPlanResponse:
    """Draft a proposed resource allocation for human review.

    Uses only the supplied resources and shelters; nothing is dispatched.
    Returns 200 with status "insufficient_information" (no draft), "draft_invalid"
    or "draft_valid". Validity comes only from the deterministic validator, after
    at most two allocation-only corrections, and means only that the configured
    rules pass. Malformed requests are rejected with 422; errors use the same
    status codes as /answer.
    """
    return workflow.run(request, request_id=current_request_id())
