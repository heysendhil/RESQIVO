"""Structured events, request correlation, metrics, redaction and tracing
controls. Offline: fake models and retrievers, network blocked."""

import logging
import re
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from langsmith import utils as langsmith_utils

from app.main import (
    app,
    get_draft_workflow,
    get_qa_service,
    get_review_workflow,
)
from app.observability import (
    METRICS,
    accept_request_id,
    format_event,
    log_event,
    safe_value,
    tracing_privacy_defaults,
)
from app.qa.service import QuestionAnsweringService
from app.rag.store import KnowledgeBaseEmptyError, RetrievalError
from tests.test_draft_plan import DraftModel, draft_request
from tests.test_draft_plan import workflow as draft_workflow
from tests.test_qa_service import FakeRetriever as QAFakeRetriever
from tests.test_qa_service import RecordingModel
from tests.test_qa_service import passage as qa_passage
from tests.test_tool_calling import ToolModel, call, search, tool_turn
from tests.test_tool_calling import review_workflow as tool_review_workflow
from tests.test_workflow import FakeRetriever, ScriptedModel, allocations_json, plan
from tests.test_workflow import workflow as review_workflow

pytestmark = pytest.mark.usefixtures("no_network")

client = TestClient(app)
WATER = qa_passage("SYN-001", "Store drinking water in clean covered containers.")
SUPPORTED = "Store drinking water in clean covered containers [P1]."


@pytest.fixture(autouse=True)
def clean_state():
    METRICS.reset()
    yield
    app.dependency_overrides.clear()
    METRICS.reset()


@pytest.fixture
def events(caplog):
    caplog.set_level(logging.INFO, logger="resqivo")

    def parse(name=None):
        parsed = []
        for record in caplog.records:
            if not record.name.startswith("resqivo"):
                continue
            message = record.getMessage()
            fields = dict(part.split("=", 1) for part in message.split(" "))
            if name is None or fields.get("event") == name:
                parsed.append(fields)
        return parsed

    return parse


def qa_service(retriever=None, text=SUPPORTED, error=None):
    return QuestionAnsweringService(
        retriever or QAFakeRetriever([WATER]), RecordingModel(text, error=error)
    )


# Request IDs -------------------------------------------------------------------


def test_request_id_is_generated_and_returned(events):
    response = client.get("/health")

    request_id = response.headers["X-Request-ID"]
    assert re.fullmatch(r"[0-9a-f]{32}", request_id)
    (start,) = events("request.start")
    (end,) = events("request.end")
    assert start["request_id"] == end["request_id"] == request_id
    assert end["endpoint"] == "/health"
    assert end["status"] == "200"
    assert end["outcome"] == "success"


def test_valid_client_request_id_is_reused(events):
    response = client.get("/health", headers={"X-Request-ID": "client-req.0001_A"})

    assert response.headers["X-Request-ID"] == "client-req.0001_A"
    assert events("request.end")[0]["request_id"] == "client-req.0001_A"


@pytest.mark.parametrize(
    "candidate",
    ["short", "x" * 65, "has space inside", "semi;colon-0001", "new\nline-0001", ""],
)
def test_invalid_client_request_ids_are_replaced(candidate):
    accepted = accept_request_id(candidate)

    assert accepted != candidate
    assert re.fullmatch(r"[0-9a-f]{32}", accepted)


def test_request_id_propagates_through_workflow_nodes(events):
    model = ScriptedModel(
        answer="Use covered containers [P1].", corrections=[allocations_json(900)]
    )
    app.dependency_overrides[get_review_workflow] = lambda: review_workflow(model=model)

    response = client.post(
        "/review",
        json={"question": "Review", "plan": plan(quantity=1100).model_dump()},
        headers={"X-Request-ID": "trace-review-0001"},
    )

    assert response.status_code == 200
    nodes = events("workflow.node")
    assert {e["node"] for e in nodes} >= {
        "retrieve_guidance",
        "generate_grounded_answer",
        "validate_plan",
        "correct_plan",
    }
    resqivo_events = events()
    assert resqivo_events
    assert {e["request_id"] for e in resqivo_events} == {"trace-review-0001"}


def test_request_id_propagates_to_tool_executions(events):
    model = ToolModel(
        [
            tool_turn(search("water"), call("run_shell", {"command": "env"})),
            "Store water in covered containers [P1].",
        ]
    )
    app.dependency_overrides[get_review_workflow] = lambda: tool_review_workflow(model)

    client.post(
        "/review",
        json={"question": "Water?"},
        headers={"X-Request-ID": "tool-req-0001"},
    )

    tools = events("tool.call")
    assert [(e["tool"], e["status"], e["reason"]) for e in tools] == [
        ("search_guidance", "executed", "None"),
        ("unknown", "rejected", "unknown_tool"),
    ]
    assert {e["request_id"] for e in tools} == {"tool-req-0001"}
    (end,) = events("request.end")
    assert end["tool_calls"] == "2"
    assert end["tool_rejections"] == "1"
    assert end["tool_rejection_reasons"] == "[unknown_tool]"
    assert end["model_calls"] == "2"
    assert (
        METRICS.value(
            "tool_calls_total", tool="unknown", status="rejected", reason="unknown_tool"
        )
        == 1
    )


def test_draft_plan_response_uses_the_request_id(events):
    app.dependency_overrides[get_draft_workflow] = lambda: draft_workflow(
        model=DraftModel()
    )

    response = client.post(
        "/draft-plan",
        json=draft_request().model_dump(mode="json"),
        headers={"X-Request-ID": "draft-req-0001"},
    )

    assert response.json()["request_id"] == "draft-req-0001"
    assert response.headers["X-Request-ID"] == "draft-req-0001"
    (complete,) = events("workflow.complete")
    assert complete["workflow"] == "draft_plan"
    assert complete["outcome"] == "draft_valid"
    assert complete["request_id"] == "draft-req-0001"


def test_workflows_outside_the_api_get_a_request_id(events):
    review_workflow().run("How is water stored?")

    ids = {e["request_id"] for e in events()}
    assert len(ids) == 1
    assert re.fullmatch(r"[0-9a-f]{32}", ids.pop())


# Outcomes ----------------------------------------------------------------------


def test_successful_workflow_summary(events):
    model = ScriptedModel(corrections=[allocations_json(900)])
    review_workflow(model=model).run("Review", plan(quantity=1100))

    (complete,) = events("workflow.complete")
    assert complete["workflow"] == "review"
    assert complete["outcome"] == "answered"
    assert complete["validations"] == "2"
    assert complete["invalid_validations"] == "1"
    assert complete["corrections"] == "1"
    assert complete["final_valid"] == "True"
    assert complete["retrieval"] == "[success]"
    assert float(complete["duration_ms"]) >= 0
    assert METRICS.value("workflow_runs_total", workflow="review", outcome="answered")
    assert METRICS.value("correction_attempts_total", parsed=True) == 1


def test_failed_workflow_is_recorded(events):
    app.dependency_overrides[get_review_workflow] = lambda: review_workflow(
        retriever=FakeRetriever(error=RetrievalError("backend down at 10.0.0.1"))
    )

    response = client.post("/review", json={"question": "Water?"})

    assert response.status_code == 503
    (failed,) = events("workflow.failed")
    assert failed["error"] == "RetrievalUnavailableError"
    (end,) = events("request.end")
    assert (end["outcome"], end["error"]) == (
        "unavailable",
        "RetrievalUnavailableError",
    )
    assert end["retrieval"] == "[failure]"
    assert METRICS.value("retrieval_total", outcome="failure") == 1
    assert "10.0.0.1" not in str(events())


def test_insufficient_evidence_is_recorded(events):
    app.dependency_overrides[get_qa_service] = lambda: qa_service(
        QAFakeRetriever(error=KnowledgeBaseEmptyError("empty"))
    )

    client.post("/answer", json={"question": "Water?"})

    (answer,) = events("qa.answer")
    assert answer["status"] == "insufficient_evidence"
    assert answer["reason"] == "knowledge_base_empty"
    (end,) = events("request.end")
    assert end["retrieval"] == "[empty_knowledge_base]"
    assert end["answer_outcomes"] == "[knowledge_base_empty]"
    assert end["model_calls"] == "0"
    assert (
        METRICS.value(
            "answers_total",
            status="insufficient_evidence",
            reason="knowledge_base_empty",
        )
        == 1
    )


def test_grounding_rejection_is_recorded(events):
    app.dependency_overrides[get_qa_service] = lambda: qa_service(
        text="Store water in tanks of 40 litres [P1]."
    )

    client.post("/answer", json={"question": "Water?"})

    (rejected,) = events("grounding.rejected")
    assert rejected["rule"] == "number_not_in_cited_evidence"
    assert events("request.end")[0]["grounding_rejections"] == (
        "[number_not_in_cited_evidence]"
    )


def test_model_errors_are_recorded_without_details(events):
    app.dependency_overrides[get_qa_service] = lambda: qa_service(
        error=RuntimeError("Traceback api_key=sk-not-real")
    )

    response = client.post("/answer", json={"question": "Water?"})

    assert response.status_code == 502
    (end,) = events("request.end")
    assert (end["outcome"], end["error"]) == ("model_error", "ModelResponseError")
    assert (end["model_calls"], end["model_failures"]) == ("1", "1")
    assert METRICS.value("model_calls_total", purpose="answer", outcome="failure") == 1
    assert "sk-not-real" not in str(events())


def test_configuration_failures_are_recorded(events, monkeypatch, tmp_path):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("RESQIVO_CHROMA_DIR", str(tmp_path / "chroma"))

    response = client.post("/answer", json={"question": "Water?"})

    assert response.status_code == 503
    (end,) = events("request.end")
    assert (end["outcome"], end["error"]) == ("unavailable", "ModelNotConfiguredError")


def test_validation_endpoint_records_outcome(events):
    body = client.post("/validate", json=plan(quantity=1100).model_dump()).json()

    assert body["valid"] is False
    (result,) = events("validation.result")
    assert (result["valid"], result["codes"]) == ("False", "[DOM-04]")
    assert events("request.end")[0]["invalid_validations"] == "1"
    assert METRICS.value("validations_total", valid=False) == 1


def test_invalid_requests_are_recorded():
    app.dependency_overrides[get_qa_service] = lambda: qa_service()

    assert client.post("/answer", json={"question": ""}).status_code == 422

    assert (
        METRICS.value(
            "requests_total",
            endpoint="/answer",
            method="POST",
            outcome="invalid_request",
        )
        == 1
    )


def test_unhandled_errors_return_a_generic_500(events, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("secret internal detail sk-not-real")

    monkeypatch.setattr("app.main.validate_plan", broken)

    response = client.post("/validate", json=plan().model_dump())

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error."}
    assert "X-Request-ID" in response.headers
    (end,) = events("request.end")
    assert (end["outcome"], end["error"]) == ("error", "RuntimeError")
    assert "sk-not-real" not in response.text + str(events())


# Durations and metrics ---------------------------------------------------------


def test_request_duration_is_recorded(events):
    client.get("/health")
    client.get("/health")

    assert float(events("request.end")[0]["duration_ms"]) >= 0
    durations = [
        d
        for d in METRICS.snapshot()["durations"]
        if d["name"] == "request_duration_ms" and d["labels"] == {"endpoint": "/health"}
    ]
    (health,) = durations
    assert health["count"] == 2
    assert sum(health["buckets"].values()) == 2
    assert health["max_ms"] >= 0


def test_unknown_paths_do_not_create_unbounded_labels():
    client.get("/does-not-exist/" + "x" * 300)

    labels = {
        c["labels"].get("endpoint")
        for c in METRICS.snapshot()["counters"]
        if c["name"] == "requests_total"
    }
    assert labels == {"unmatched"}


# Privacy and injection ---------------------------------------------------------


def test_payloads_and_secrets_are_never_logged(events, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "AIza-test-secret-value")
    request = draft_request(
        scenario={
            "scenario_id": "SCN-PRIV",
            "name": "Private narrative",
            "disaster_type": "flood",
            "severity": "high",
            "affected_population": 40,
            "location": "12 Example Street",
            "description": "Family at 12 Example Street needs insulin urgently.",
        }
    )
    retriever = FakeRetriever([qa_passage("SYN-009", "Confidential passage text.")])
    app.dependency_overrides[get_draft_workflow] = lambda: draft_workflow(
        retriever, DraftModel(answer="Use the confidential passage text [P1].")
    )

    client.post("/draft-plan", json=request.model_dump(mode="json"))
    app.dependency_overrides[get_qa_service] = lambda: qa_service()
    client.post("/answer", json={"question": "My address is 12 Example Street"})

    logged = "\n".join(" ".join(f"{k}={v}" for k, v in e.items()) for e in events())
    assert "event=workflow.complete" in logged
    for secret in (
        "Example Street",
        "insulin",
        "Confidential passage",
        "Drinking Water",
        "Community Hall",
        "AIza-test-secret-value",
        "covered containers",
    ):
        assert secret not in logged


@pytest.mark.parametrize(
    "value",
    [
        "line one\nevent=forged request_id=evil",
        "tab\there key=value",
        "\r\nINFO fake log line",
        "x" * 500,
        "unicode separator",
    ],
)
def test_values_cannot_forge_fields_or_lines(value):
    rendered = safe_value(value)

    assert len(rendered) <= 64
    assert not re.search(r"[\s=]", rendered)
    message = format_event("test.event", {"field": value})
    assert len(message.split(" ")) == 3  # event, request_id, field
    assert "\n" not in message and "\r" not in message


def test_unexpected_keys_are_dropped():
    message = format_event(
        "test.event", {"ok": 1, "Bad Key": 2, "x=y": 3, "request_id": "forged"}
    )

    assert message == "event=test.event request_id=None ok=1"


def test_lists_are_bounded():
    rendered = safe_value([f"CODE-{i}" for i in range(20)])

    assert rendered.endswith(",+more]")
    assert rendered.count(",") == 10


def test_injected_header_and_question_cannot_add_log_lines(caplog):
    caplog.set_level(logging.INFO, logger="resqivo")
    app.dependency_overrides[get_qa_service] = lambda: qa_service()

    client.post(
        "/answer",
        json={"question": "Water?\nevent=request.end status=200 request_id=forged"},
        headers={"X-Request-ID": "x\nevent=forged"},
    )

    for record in caplog.records:
        if record.name.startswith("resqivo"):
            message = record.getMessage()
            assert "\n" not in message
            assert "forged" not in message


# Logging failures --------------------------------------------------------------


class ExplodingHandler(logging.Handler):
    def emit(self, record):
        raise RuntimeError("log sink down")


def test_logging_failures_do_not_change_results():
    loggers = [logging.getLogger(n) for n in ("resqivo.api", "resqivo.workflow")]
    handler = ExplodingHandler()
    previous = [(lg.level, lg.propagate) for lg in loggers]
    for lg in loggers:
        lg.addHandler(handler)
        lg.setLevel(logging.INFO)
    try:
        validate = client.post("/validate", json=plan(quantity=1100).model_dump())
        review = review_workflow().run("Review", plan(quantity=1100))
    finally:
        for lg, (level, propagate) in zip(loggers, previous, strict=True):
            lg.removeHandler(handler)
            lg.setLevel(level)
            lg.propagate = propagate

    assert validate.status_code == 200
    assert [v["code"] for v in validate.json()["violations"]] == ["DOM-04"]
    assert review.plan_review.final_validation.valid is False
    assert METRICS.value("logging_errors_total") > 0


def test_log_event_never_raises_on_bad_values():
    class Unprintable:
        def __str__(self):
            raise ValueError("cannot render")

    log_event(logging.getLogger("resqivo.test"), "test.event", value=Unprintable())


# Tracing -----------------------------------------------------------------------


def test_langsmith_tracing_is_disabled_by_default(monkeypatch):
    for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING"):
        monkeypatch.delenv(name, raising=False)

    assert langsmith_utils.tracing_is_enabled() is False
    client.post("/validate", json=plan().model_dump())  # network is blocked


def test_tracing_privacy_defaults():
    assert tracing_privacy_defaults({}) == {}
    assert tracing_privacy_defaults({"LANGSMITH_TRACING": "false"}) == {}
    assert tracing_privacy_defaults({"LANGSMITH_TRACING": "true"}) == {
        "LANGSMITH_HIDE_INPUTS": "true",
        "LANGSMITH_HIDE_OUTPUTS": "true",
    }
    assert tracing_privacy_defaults(
        {"LANGCHAIN_TRACING_V2": "1", "LANGSMITH_HIDE_OUTPUTS": "false"}
    ) == {"LANGSMITH_HIDE_INPUTS": "true"}


def test_disabled_tracing_leaves_environment_untouched(monkeypatch, tmp_path):
    for name in (
        "LANGSMITH_TRACING",
        "LANGCHAIN_TRACING_V2",
        "LANGSMITH_HIDE_INPUTS",
        "LANGSMITH_HIDE_OUTPUTS",
        "GOOGLE_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("RESQIVO_CHROMA_DIR", str(tmp_path / "chroma"))

    client.post("/answer", json={"question": "Water?"})  # 503: not configured

    import os

    assert "LANGSMITH_HIDE_INPUTS" not in os.environ


# Compatibility and startup -----------------------------------------------------


def test_existing_response_bodies_are_unchanged():
    assert client.get("/health").json() == {"status": "ok", "service": "RESQIVO"}
    body = client.post("/validate", json=plan(quantity=900).model_dump()).json()
    assert body == {"valid": True, "violations": []}
    paths = set(client.get("/openapi.json").json()["paths"])
    assert paths == {
        "/health",
        "/validate",
        "/answer",
        "/review",
        "/draft-plan",
        # Simulated incident feed (added with approval on 2026-10-23).
        "/incidents",
        "/incidents/{incident_id}",
        "/incidents/simulate",
        "/incidents/stream",
        "/incidents/intake",
    }


def test_startup_stays_lazy():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, app.main; print(sorted(m for m in sys.modules if "
            "m.startswith(('langgraph', 'chromadb', 'langchain_google_genai', "
            "'google.genai', 'app.rag', 'app.workflow.graph'))))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == "[]"
