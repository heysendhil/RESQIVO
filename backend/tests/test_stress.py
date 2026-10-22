"""Offline stress, concurrency, failure, timeout and request-size tests.

Requests run concurrently through the real ASGI app with httpx2's ASGITransport;
synchronous endpoints execute in Starlette's thread pool. Concurrency is
bounded by a semaphore and inputs are deterministic. Fake models only.
"""

import asyncio
import json
import logging
import re
import threading
import time

import httpx2
import pytest

from app.evaluation.loadtest import (
    FAIL_MARKER,
    DeterministicModel,
    EchoRetriever,
    draft_body,
    install_offline_overrides,
    plan_body,
)
from app.limits import (
    HARD_MAX_BODY_BYTES,
    BodySizeLimitMiddleware,
    LimitSettings,
    RequestTimeoutError,
    deadline,
)
from app.main import (
    app,
    get_draft_workflow,
    get_qa_service,
    get_review_workflow,
)
from app.observability import METRICS, MetricsRegistry
from app.qa.errors import QAConfigurationError
from app.qa.service import QuestionAnsweringService
from app.rag.store import RetrievalError
from app.workflow.graph import ReviewWorkflow
from app.workflow.schemas import MAX_DRAFT_CONSTRAINTS, MAX_DRAFT_RESOURCES
from app.workflow.tools import make_search_guidance_tool, make_validate_plan_tool
from tests.test_draft_plan import DraftModel
from tests.test_draft_plan import workflow as draft_workflow
from tests.test_qa_service import RecordingModel
from tests.test_tool_calling import ToolModel, call, search, tool_turn
from tests.test_tool_calling import review_workflow as tool_review_workflow
from tests.test_workflow import FakeRetriever, ScriptedModel
from tests.test_workflow import workflow as review_workflow

pytestmark = pytest.mark.usefixtures("no_network")

EVENT_LINE = re.compile(r"^event=\S+ request_id=\S+( [a-z][a-z0-9_]*=\S+)*$")
CONCURRENCY = 16


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    for name in (
        "ANTHROPIC_API_KEY",
        "RESQIVO_MAX_BODY_BYTES",
        "RESQIVO_REQUEST_TIMEOUT_SECONDS",
        "RESQIVO_MAX_TOOL_CALLS",
        "RESQIVO_TOOL_CALLING",
    ):
        monkeypatch.delenv(name, raising=False)
    METRICS.reset()
    yield
    app.dependency_overrides.clear()
    METRICS.reset()


@pytest.fixture
def events(caplog):
    caplog.set_level(logging.INFO, logger="resqivo")

    def collect():
        parsed = []
        for record in caplog.records:
            if record.name.startswith("resqivo"):
                message = record.getMessage()
                assert EVENT_LINE.match(message), message
                parsed.append(dict(part.split("=", 1) for part in message.split(" ")))
        return parsed

    return collect


async def _send(client, semaphore, method, path, **kwargs):
    async with semaphore:
        return await client.request(method, path, **kwargs)


def run_concurrently(requests, concurrency=CONCURRENCY):
    """requests: list of (method, path, kwargs). Returns responses in order."""

    async def main():
        semaphore = asyncio.Semaphore(concurrency)
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(
            transport=transport, base_url="http://test", timeout=30
        ) as client:
            return await asyncio.gather(
                *(_send(client, semaphore, m, p, **kw) for m, p, kw in requests)
            )

    return asyncio.run(main())


def by_request(parsed):
    grouped: dict[str, list[dict]] = {}
    for event in parsed:
        grouped.setdefault(event["request_id"], []).append(event)
    return grouped


# Mixed concurrent load ---------------------------------------------------------


def _mixed_requests(n):
    requests, expected = [], {}
    for i in range(n):
        kind = ("health", "validate", "answer", "review", "draft")[i % 5]
        rid = f"load-{kind}-{i:04d}"
        headers = {"X-Request-ID": rid}
        if kind == "health":
            requests.append(("GET", "/health", {"headers": headers}))
        elif kind == "validate":
            quantity = 990 + i
            body = plan_body(quantity)
            requests.append(("POST", "/validate", {"json": body, "headers": headers}))
        elif kind == "answer":
            quantity = None
            body = {"question": f"How is water stored for case-{i}?"}
            requests.append(("POST", "/answer", {"json": body, "headers": headers}))
        elif kind == "review":
            quantity = 1001 + i if i % 2 == 0 else 900 - i
            body = {"question": f"Review case-{i}", "plan": plan_body(quantity)}
            requests.append(("POST", "/review", {"json": body, "headers": headers}))
        else:
            quantity = 50 + i
            requests.append(
                (
                    "POST",
                    "/draft-plan",
                    {"json": draft_body(quantity), "headers": headers},
                )
            )
        expected[rid] = (kind, i, quantity if kind != "health" else None)
    return requests, expected


def test_mixed_concurrent_requests_are_isolated(events):
    install_offline_overrides(app, delay_seconds=0.005)
    requests, expected = _mixed_requests(60)

    responses = run_concurrently(requests)

    for (_, _, kwargs), response in zip(requests, responses, strict=True):
        rid = kwargs["headers"]["X-Request-ID"]
        kind, i, quantity = expected[rid]
        assert response.status_code == 200, (rid, response.text)
        assert response.headers["X-Request-ID"] == rid
        body = response.json()
        if kind == "validate":
            if quantity > 1000:
                (violation,) = body["violations"]
                assert violation["details"]["quantity_allocated"] == quantity
            else:
                assert body == {"valid": True, "violations": []}
        elif kind == "answer":
            assert f"case-{i} " in body["answer"]
            assert len(re.findall(r"case-\d+", body["answer"])) == 1
        elif kind == "review":
            assert f"case-{i} " in body["answer"]["answer"]
            review = body["plan_review"]
            original = review["original_validation"]
            if quantity > 1000:
                assert original["violations"][0]["details"]["quantity_allocated"] == (
                    quantity
                )
                assert review["correction_attempts"] == 1
                assert review["final_plan"]["allocations"][0]["quantity_allocated"] == (
                    1000
                )
            else:
                assert original["valid"] is True
                assert review["correction_attempts"] == 0
                assert review["final_plan"]["allocations"][0]["quantity_allocated"] == (
                    quantity
                )
            assert review["final_validation"]["valid"] is True
        elif kind == "draft":
            assert body["request_id"] == rid
            assert body["status"] == "draft_valid"
            (allocation,) = body["plan_review"]["final_plan"]["allocations"]
            assert allocation["quantity_allocated"] == quantity

    grouped = by_request(events())
    assert set(grouped) == set(expected)
    for rid, request_events in grouped.items():
        kind, i, quantity = expected[rid]
        names = [e["event"] for e in request_events]
        assert names.count("request.start") == names.count("request.end") == 1
        (end,) = [e for e in request_events if e["event"] == "request.end"]
        model_calls = {"health": 0, "validate": 0, "answer": 1, "draft": 2}.get(
            kind, 2 if kind == "review" and quantity > 1000 else 1
        )
        assert end["model_calls"] == str(model_calls), rid
        corrections = 1 if kind == "review" and quantity > 1000 else 0
        assert end["corrections"] == str(corrections), rid

    snapshot = METRICS.snapshot()
    total = sum(
        c["value"] for c in snapshot["counters"] if c["name"] == "requests_total"
    )
    durations = sum(
        d["count"] for d in snapshot["durations"] if d["name"] == "request_duration_ms"
    )
    validations = sum(
        c["value"] for c in snapshot["counters"] if c["name"] == "validations_total"
    )
    logged_validations = sum(
        int(e["validations"]) for e in events() if e["event"] == "request.end"
    )
    assert total == durations == 60
    assert validations == logged_validations


def test_failures_do_not_corrupt_concurrent_or_later_requests(events):
    install_offline_overrides(app)
    requests = []
    for i in range(30):
        marker = f" {FAIL_MARKER}" if i % 3 == 0 else ""
        requests.append(
            (
                "POST",
                "/answer",
                {
                    "json": {"question": f"Water for case-{i}?{marker}"},
                    "headers": {"X-Request-ID": f"fail-mix-{i:04d}"},
                },
            )
        )

    responses = run_concurrently(requests)
    later = run_concurrently(
        [("POST", "/answer", {"json": {"question": f"case-{i}?"}}) for i in range(10)]
    )

    for i, response in enumerate(responses):
        if i % 3 == 0:
            assert response.status_code == 503
            assert response.json() == {"detail": "Knowledge retrieval is unavailable."}
        else:
            assert response.status_code == 200
            assert f"case-{i} " in response.json()["answer"]
    assert all(r.status_code == 200 for r in later)
    ends = {e["request_id"]: e for e in events() if e["event"] == "request.end"}
    for i in range(30):
        end = ends[f"fail-mix-{i:04d}"]
        assert end["retrieval"] == ("[failure]" if i % 3 == 0 else "[success]")
        assert end["outcome"] == ("unavailable" if i % 3 == 0 else "success")


def test_concurrent_tool_calling_requests_keep_their_own_tool_records(events):
    counter = iter(range(1000))
    lock = threading.Lock()

    def factory():
        with lock:
            n = next(counter)
        turns = [tool_turn(search(f"water {n}"))]
        if n % 2:
            turns.append(tool_turn(call("run_shell", {"command": "env"})))
        turns.append("Store water in covered containers [P1].")
        return tool_review_workflow(ToolModel(turns))

    app.dependency_overrides[get_review_workflow] = factory

    responses = run_concurrently(
        [("POST", "/review", {"json": {"question": "Water?"}}) for _ in range(24)]
    )

    assert all(r.status_code == 200 for r in responses)
    ends = [e for e in events() if e["event"] == "request.end"]
    profiles = sorted((e["tool_calls"], e["tool_rejections"]) for e in ends)
    assert profiles == [("1", "0")] * 12 + [("2", "1")] * 12
    for end in ends:
        if end["tool_rejections"] == "1":
            assert end["tool_rejection_reasons"] == "[unknown_tool]"


def test_metrics_are_exact_under_thread_contention():
    registry = MetricsRegistry()

    def work():
        for i in range(2000):
            registry.increment("hits", kind="a" if i % 2 else "b")
            registry.observe_ms("lat", float(i % 50))

    threads = [threading.Thread(target=work) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert registry.value("hits", kind="a") == registry.value("hits", kind="b") == 8000
    (lat,) = registry.snapshot()["durations"]
    assert lat["count"] == 16000
    assert sum(lat["buckets"].values()) == 16000


class ExplodingHandler(logging.Handler):
    def emit(self, record):
        raise RuntimeError("log sink down")


def test_logging_failures_under_load_do_not_change_results():
    loggers = [logging.getLogger(n) for n in ("resqivo.api", "resqivo.workflow")]
    handler = ExplodingHandler()
    levels = [lg.level for lg in loggers]
    for lg in loggers:
        lg.addHandler(handler)
        lg.setLevel(logging.INFO)
    try:
        responses = run_concurrently(
            [("POST", "/validate", {"json": plan_body(990 + i)}) for i in range(20)]
        )
    finally:
        for lg, level in zip(loggers, levels, strict=True):
            lg.removeHandler(handler)
            lg.setLevel(level)

    for i, response in enumerate(responses):
        assert response.status_code == 200
        assert response.json()["valid"] is (990 + i <= 1000)
    assert METRICS.value("logging_errors_total") > 0


def test_sensitive_fields_are_not_emitted_under_load(events, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-load-secret")
    install_offline_overrides(app)
    secret_question = "Family at 7 Hidden Lane case-1 needs insulin"

    run_concurrently(
        [("POST", "/answer", {"json": {"question": secret_question}})] * 10
        + [("POST", "/draft-plan", {"json": draft_body(5)})] * 5
    )

    logged = json.dumps(events())
    for secret in (
        "Hidden Lane",
        "insulin",
        "sk-ant-load-secret",
        "covered containers",
    ):
        assert secret not in logged


# Failure scenarios under concurrency -------------------------------------------


def _answer_model_error():
    return QuestionAnsweringService(
        EchoRetriever(), RecordingModel(error=RuntimeError("Traceback sk-not-real"))
    )


def _tool_failure():
    return tool_review_workflow(
        ToolModel([tool_turn(search()), "x"]),
        FakeRetriever(error=RuntimeError("disk exploded sk-not-real")),
    )


def _tool_limit():
    return tool_review_workflow(
        ToolModel([tool_turn(search(f"q{i}")) for i in range(5)]), max_tool_calls=2
    )


def _recursion():
    return tool_review_workflow(
        ToolModel([tool_turn(search(f"q{i}")) for i in range(9)]), recursion_limit=3
    )


@pytest.mark.parametrize(
    ("dependency", "factory", "path", "body", "status", "detail"),
    [
        (
            get_qa_service,
            _answer_model_error,
            "/answer",
            {"question": "Water?"},
            502,
            "The language model did not return a usable answer.",
        ),
        (
            get_draft_workflow,
            lambda: draft_workflow(model=DraftModel(draft="not json")),
            "/draft-plan",
            draft_body(10),
            502,
            "The language model did not return a usable answer.",
        ),
        (
            get_review_workflow,
            lambda: review_workflow(retriever=FakeRetriever(error=RetrievalError("x"))),
            "/review",
            {"question": "Water?"},
            503,
            "Knowledge retrieval is unavailable.",
        ),
        (
            get_review_workflow,
            _tool_failure,
            "/review",
            {"question": "Water?"},
            500,
            "Question answering failed.",
        ),
        (
            get_review_workflow,
            _tool_limit,
            "/review",
            {"question": "Water?"},
            502,
            "The language model did not return a usable answer.",
        ),
        (
            get_review_workflow,
            _recursion,
            "/review",
            {"question": "Water?"},
            502,
            "The language model did not return a usable answer.",
        ),
    ],
)
def test_concurrent_failures_are_sanitized_and_never_succeed(
    events, dependency, factory, path, body, status, detail
):
    app.dependency_overrides[dependency] = factory

    responses = run_concurrently([("POST", path, {"json": body})] * 8, concurrency=8)

    for response in responses:
        assert response.status_code == status
        assert response.json() == {"detail": detail}
        assert "sk-not-real" not in response.text
    ends = [e for e in events() if e["event"] == "request.end"]
    assert len(ends) == 8
    assert all(e["outcome"] != "success" for e in ends)
    assert "sk-not-real" not in json.dumps(events())


def test_validator_and_correction_cap_hold_under_concurrency():
    def factory():
        return review_workflow(
            model=ScriptedModel(
                answer="This plan is valid [P1].", corrections=["not json"] * 5
            )
        )

    app.dependency_overrides[get_review_workflow] = factory

    responses = run_concurrently(
        [
            (
                "POST",
                "/review",
                {"json": {"question": "Valid?", "plan": plan_body(1100)}},
            )
            for _ in range(16)
        ]
    )

    for response in responses:
        review = response.json()["plan_review"]
        assert review["final_validation"]["valid"] is False
        assert [v["code"] for v in review["final_validation"]["violations"]] == [
            "DOM-04"
        ]
        assert review["correction_attempts"] == review["max_correction_attempts"] == 2


def test_tool_call_limit_cannot_be_raised_by_configuration(monkeypatch):
    monkeypatch.setenv("RESQIVO_MAX_TOOL_CALLS", "50")

    responses = run_concurrently([("POST", "/review", {"json": {"question": "q"}})] * 4)

    assert {r.status_code for r in responses} == {503}


# Timeouts ----------------------------------------------------------------------


def test_slow_model_hits_the_request_deadline(events, monkeypatch):
    monkeypatch.setenv("RESQIVO_REQUEST_TIMEOUT_SECONDS", "1")
    install_offline_overrides(app, delay_seconds=1.1)

    started = time.perf_counter()
    responses = run_concurrently(
        [
            (
                "POST",
                "/review",
                {"json": {"question": "case-1", "plan": plan_body(1100)}},
            )
            for _ in range(4)
        ]
    )
    elapsed = time.perf_counter() - started

    for response in responses:
        assert response.status_code == 504
        assert response.json() == {"detail": "The request did not complete in time."}
    ends = [e for e in events() if e["event"] == "request.end"]
    assert {(e["outcome"], e["error"]) for e in ends} == {
        ("timeout", "RequestTimeoutError")
    }
    assert all(e["model_calls"] == "1" and e["corrections"] == "0" for e in ends)
    assert elapsed < 4  # the correction call was never started


def test_deadline_stops_further_model_calls():
    model = DeterministicModel(delay_seconds=0.1)
    workflow = ReviewWorkflow(
        search_tool=make_search_guidance_tool(EchoRetriever()),
        validate_tool=make_validate_plan_tool(),
        answer_service=QuestionAnsweringService(EchoRetriever(), model),
        model=model,
    )
    from app.models.plan import PlanValidationRequest

    with deadline(0.05), pytest.raises(RequestTimeoutError):
        workflow.run("case-1", PlanValidationRequest.model_validate(plan_body(1100)))

    assert model.calls == 1


def test_fast_requests_are_unaffected_by_the_deadline():
    install_offline_overrides(app)

    responses = run_concurrently(
        [("POST", "/answer", {"json": {"question": f"case-{i}"}}) for i in range(10)]
    )

    assert all(r.status_code == 200 for r in responses)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("RESQIVO_REQUEST_TIMEOUT_SECONDS", "0.5"),
        ("RESQIVO_REQUEST_TIMEOUT_SECONDS", "601"),
        ("RESQIVO_REQUEST_TIMEOUT_SECONDS", "soon"),
        ("RESQIVO_MAX_BODY_BYTES", "1024"),
        ("RESQIVO_MAX_BODY_BYTES", str(HARD_MAX_BODY_BYTES + 1)),
    ],
)
def test_limit_configuration_is_bounded(monkeypatch, name, value):
    with pytest.raises(QAConfigurationError):
        LimitSettings.from_env({name: value})
    monkeypatch.setenv(name, value)

    (response,) = run_concurrently([("GET", "/health", {})])

    assert response.status_code == 503  # fails closed


# Request size ------------------------------------------------------------------


def test_oversized_body_is_rejected_before_parsing(events, monkeypatch):
    monkeypatch.setenv("RESQIVO_MAX_BODY_BYTES", str(16 * 1024))
    small = plan_body(10)
    big = plan_body(10)
    big["allocations"] = big["allocations"] * 200  # about 23 KB

    ok, too_big = run_concurrently(
        [("POST", "/validate", {"json": small}), ("POST", "/validate", {"json": big})]
    )

    assert ok.status_code == 200
    assert too_big.status_code == 413
    assert too_big.json() == {"detail": "Request body too large."}
    assert METRICS.value("validations_total", valid=True) == 1  # big never ran
    outcomes = sorted(e["outcome"] for e in events() if e["event"] == "request.end")
    assert outcomes == ["payload_too_large", "success"]


def test_chunked_oversized_body_is_rejected(monkeypatch):
    monkeypatch.setenv("RESQIVO_MAX_BODY_BYTES", str(16 * 1024))

    async def chunks():  # streamed without Content-Length
        for _ in range(20):
            yield b" " * 1024

    (response,) = run_concurrently(
        [
            (
                "POST",
                "/validate",
                {"content": chunks(), "headers": {"Content-Type": "application/json"}},
            )
        ]
    )

    assert response.status_code == 413


def test_invalid_content_length_is_rejected():
    sent = []

    async def app_stub(scope, receive, send):  # pragma: no cover - never reached
        raise AssertionError("application must not run")

    async def receive():
        return {"type": "http.request", "body": b"{}", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "headers": [(b"content-length", b"abc")]}
    asyncio.run(BodySizeLimitMiddleware(app_stub)(scope, receive, send))

    assert sent[0]["status"] == 400


def test_many_allocations_within_the_default_limit_are_validated_exactly():
    body = plan_body(0)
    body["allocations"] = [
        {
            "allocation_id": f"a-{i}",
            "resource_id": "water-001",
            "destination_id": "shelter-001",
            "quantity_allocated": 1,
        }
        for i in range(5000)
    ]
    assert len(json.dumps(body)) < 1024 * 1024

    (response,) = run_concurrently([("POST", "/validate", {"json": body})])

    (violation,) = response.json()["violations"]
    assert violation["code"] == "DOM-04"
    assert violation["details"]["quantity_allocated"] == 5000  # nothing truncated


def _answer_ok():
    install_offline_overrides(app)


@pytest.mark.parametrize(
    ("path", "body", "status"),
    [
        ("/answer", {"question": "x" * 1000}, 200),
        ("/answer", {"question": "x" * 1001}, 422),
        ("/review", {"question": "x" * 1001}, 422),
        (
            "/draft-plan",
            {**draft_body(5), "constraints": ["ok"] * MAX_DRAFT_CONSTRAINTS},
            200,
        ),
        (
            "/draft-plan",
            {**draft_body(5), "constraints": ["ok"] * (MAX_DRAFT_CONSTRAINTS + 1)},
            422,
        ),
        (
            "/draft-plan",
            {
                **draft_body(5),
                "scenario": {**draft_body(5)["scenario"], "description": "d" * 2001},
            },
            422,
        ),
    ],
)
def test_field_and_list_boundaries(path, body, status):
    _answer_ok()

    (response,) = run_concurrently([("POST", path, {"json": body})])

    assert response.status_code == status


@pytest.mark.parametrize("count", [MAX_DRAFT_RESOURCES, MAX_DRAFT_RESOURCES + 1])
def test_resource_list_boundary(count):
    install_offline_overrides(app)
    body = draft_body(5)
    body["resources"] = [
        {**body["resources"][0], "resource_id": f"r-{i}"} for i in range(count)
    ]

    (response,) = run_concurrently([("POST", "/draft-plan", {"json": body})])

    assert response.status_code == (200 if count == MAX_DRAFT_RESOURCES else 422)


@pytest.mark.parametrize("raw", [b"{not json", b"", b"[]", b'{"question": '])
def test_malformed_json_is_rejected(raw):
    install_offline_overrides(app)

    (response,) = run_concurrently(
        [
            (
                "POST",
                "/answer",
                {"content": raw, "headers": {"Content-Type": "application/json"}},
            )
        ]
    )

    assert response.status_code == 422


# Benchmark script --------------------------------------------------------------


def test_benchmark_script_runs_offline(tmp_path):
    import os
    import subprocess
    import sys

    from app.rag.config import REPO_ROOT

    output = tmp_path / "bench.json"
    env = {**os.environ, "ANTHROPIC_API_KEY": "sk-must-not-be-used"}
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "benchmark.py"),
            "--requests",
            "20",
            "--concurrency",
            "4",
            "--warmup",
            "2",
            "--startup-runs",
            "1",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT / "backend",
        timeout=300,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text())
    assert report["live_model_calls"] == 0
    assert set(report["endpoints"]) == {
        "GET /health",
        "POST /validate",
        "POST /answer",
        "POST /review",
        "POST /draft-plan",
    }
    for endpoint in report["endpoints"].values():
        steady = endpoint["steady_state"]
        assert (steady["requests"], steady["succeeded"], steady["failed"]) == (
            20,
            20,
            0,
        )
        assert "p95" in steady["latency_ms"] and "p99" not in steady["latency_ms"]
    assert report["requests_recorded_by_metrics"] == 5 * (1 + 2 + 20)
    assert "sk-must-not-be-used" not in output.read_text() + result.stderr
