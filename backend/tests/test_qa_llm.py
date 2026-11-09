"""Gemini provider integration, tested offline.

The real ChatGoogleGenerativeAI adapter is used; only the google-genai SDK's
network method (client.models.generate_content) is replaced, so LangChain's own
response parsing (text, finish reasons, prompt feedback, function calls) runs
for real. No request leaves the process and no real key is used.
"""

import json
import logging

import pytest
from google.genai import errors as genai_errors
from google.genai import types
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.models.plan import PlanValidationRequest
from app.qa.config import DEFAULT_LLM_MODEL, QASettings
from app.qa.errors import (
    ModelNotConfiguredError,
    ModelResponseError,
    QAConfigurationError,
)
from app.qa.llm import (
    MAX_ATTEMPTS,
    MAX_OUTPUT_TOKENS,
    REQUEST_TIMEOUT_SECONDS,
    THINKING_LEVEL,
    build_chat_model,
)
from app.qa.replies import unusable_reply
from app.qa.service import QuestionAnsweringService
from app.workflow.drafting import DraftPlanWorkflow
from app.workflow.graph import ReviewWorkflow
from app.workflow.tools import make_search_guidance_tool, make_validate_plan_tool
from tests.test_draft_plan import VALID_DRAFT, draft_request
from tests.test_workflow import FakeRetriever, passage

pytestmark = pytest.mark.usefixtures("no_network")

DUMMY_KEY = "test-key-not-real-0000"
SUPPORTED = "Store water in covered containers [P1]."


def gemini(environ=None, **settings):
    env = {"GOOGLE_API_KEY": DUMMY_KEY, **(environ or {})}
    return build_chat_model(QASettings.from_env(settings), env)


def response(*parts, finish_reason="STOP", block_reason=None):
    """A GenerateContentResponse as the SDK would return it."""
    data: dict = {
        "usage_metadata": {"prompt_token_count": 10, "candidates_token_count": 5}
    }
    if block_reason:
        data["prompt_feedback"] = {"block_reason": block_reason}
    else:
        data["candidates"] = [
            {
                "content": {"role": "model", "parts": list(parts)},
                "finish_reason": finish_reason,
            }
        ]
    return types.GenerateContentResponse.model_validate(data)


def text(value):
    return {"text": value}


def function_call(name, args):
    return {"function_call": {"name": name, "args": args}}


def script(model, monkeypatch, *replies):
    """Replace the SDK call with scripted responses or exceptions."""
    calls = []
    queue = list(replies)

    def fake_generate_content(**kwargs):
        calls.append(kwargs)
        reply = queue.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(model.client.models, "generate_content", fake_generate_content)
    return calls


# Configuration -----------------------------------------------------------------


@pytest.mark.parametrize(
    "environ",
    [
        {},
        {"GOOGLE_API_KEY": "   "},
        {"GEMINI_API_KEY": DUMMY_KEY},  # only GOOGLE_API_KEY is used
        {"ANTHROPIC_API_KEY": DUMMY_KEY},  # the previous provider's key is ignored
    ],
)
def test_missing_google_api_key_is_reported(environ, monkeypatch):
    for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ModelNotConfiguredError, match="GOOGLE_API_KEY is not set"):
        build_chat_model(QASettings.from_env({}), environ)


def test_model_is_configured_without_network_or_exposing_the_key():
    model = gemini()

    assert model.model == DEFAULT_LLM_MODEL == "gemini-3.8-flash"
    assert model.max_output_tokens == MAX_OUTPUT_TOKENS == 16384
    assert model.thinking_level == THINKING_LEVEL == "low"
    assert model.timeout == REQUEST_TIMEOUT_SECONDS == 90.0
    assert model.max_retries == MAX_ATTEMPTS == 2
    assert model.temperature is None  # Gemini 3+: model default
    assert DUMMY_KEY not in repr(model)
    assert DUMMY_KEY not in str(model.model_dump())


def test_vertex_environment_cannot_switch_backend_or_leak_the_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "some-project")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    model = gemini()

    assert model._use_vertexai is False
    import os

    assert "GOOGLE_API_KEY" not in os.environ


def test_request_has_no_tools_forced_choice_or_sampling_parameters():
    model = gemini()

    request = model._prepare_request([SystemMessage("rules"), HumanMessage("question")])

    config = request["config"]
    assert request["model"] == "gemini-3.8-flash"
    assert config.tools is None and config.tool_config is None
    assert config.temperature is None and config.top_p is None and config.top_k is None
    assert config.max_output_tokens == 16384
    assert config.thinking_config.thinking_level == types.ThinkingLevel.LOW
    assert config.http_options.timeout == 90_000
    assert config.http_options.retry_options.attempts == 2
    assert config.system_instruction is not None  # rules kept out of the user turn
    assert DUMMY_KEY not in json.dumps(request["contents"], default=str)


def test_settings_defaults_and_overrides():
    defaults = QASettings.from_env({})
    custom = QASettings.from_env(
        {
            "RESQIVO_LLM_MODEL": "gemini-3.6-flash",
            "RESQIVO_QA_TOP_K": "6",
            "RESQIVO_QA_MAX_DISTANCE": "0.8",
        }
    )

    assert (defaults.llm_model, defaults.top_k, defaults.max_distance) == (
        "gemini-3.8-flash",
        4,
        1.0,
    )
    assert (custom.llm_model, custom.top_k, custom.max_distance) == (
        "gemini-3.6-flash",
        6,
        0.8,
    )
    assert gemini(RESQIVO_LLM_MODEL="gemini-3.6-flash").model == "gemini-3.6-flash"


@pytest.mark.parametrize(
    "environ",
    [
        {"RESQIVO_QA_TOP_K": "0"},
        {"RESQIVO_QA_TOP_K": "21"},
        {"RESQIVO_QA_TOP_K": "four"},
        {"RESQIVO_QA_MAX_DISTANCE": "0"},
        {"RESQIVO_QA_MAX_DISTANCE": "2.5"},
        {"RESQIVO_LLM_MODEL": "   "},
        {"RESQIVO_LLM_MODEL": "claude-opus-5-5"},  # leftover from the old provider
        {"RESQIVO_LLM_MODEL": "gpt-5"},
        {"RESQIVO_LLM_MODEL": "models/claude-opus-5-5"},
    ],
)
def test_invalid_settings_are_rejected(environ):
    with pytest.raises(QAConfigurationError):
        QASettings.from_env(environ)


@pytest.mark.parametrize(
    "name", ["gemini-3.8-flash", "gemini-4-argon", "models/gemini-3.6-flash"]
)
def test_gemini_model_ids_are_accepted(name):
    assert QASettings.from_env({"RESQIVO_LLM_MODEL": name}).llm_model == name


def test_non_gemini_model_is_a_503_before_any_request(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("GOOGLE_API_KEY", DUMMY_KEY)
    monkeypatch.setenv("RESQIVO_LLM_MODEL", "claude-opus-5-5")
    monkeypatch.setenv("RESQIVO_CHROMA_DIR", str(tmp_path / "chroma"))

    response = TestClient(app).post("/answer", json={"question": "Water?"})

    assert response.status_code == 503
    assert response.json() == {"detail": "Question answering is not configured."}


# Replies through the real adapter ----------------------------------------------


def answer_with(model):
    return QuestionAnsweringService(FakeRetriever([passage()]), model).answer("q")


def test_grounded_answer_through_the_adapter(monkeypatch):
    model = gemini()
    calls = script(model, monkeypatch, response(text(SUPPORTED)))

    result = answer_with(model)

    assert result.status == "answered"
    assert [c.source_id for c in result.citations] == ["SYN-001"]
    assert calls[0]["model"] == "gemini-3.8-flash"


@pytest.mark.parametrize(
    ("finish_reason", "block_reason"),
    [
        ("SAFETY", None),
        ("RECITATION", None),
        ("PROHIBITED_CONTENT", None),
        ("BLOCKLIST", None),
        ("MAX_TOKENS", None),  # truncated: never treated as complete
        ("OTHER", None),
        ("STOP", "SAFETY"),  # prompt blocked: no candidates at all
    ],
)
def test_blocked_or_truncated_replies_are_model_errors(
    monkeypatch, finish_reason, block_reason, caplog
):
    model = gemini()
    script(
        model,
        monkeypatch,
        response(
            text(SUPPORTED), finish_reason=finish_reason, block_reason=block_reason
        ),
    )

    with caplog.at_level(logging.INFO), pytest.raises(ModelResponseError):
        answer_with(model)


@pytest.mark.parametrize(
    "error",
    [
        genai_errors.ClientError(
            400,
            {
                "error": {
                    "code": 400,
                    "message": "API key not valid: sk-not-real",
                    "status": "INVALID_ARGUMENT",
                }
            },
        ),
        genai_errors.ClientError(
            403,
            {
                "error": {
                    "code": 403,
                    "message": "Permission denied",
                    "status": "PERMISSION_DENIED",
                }
            },
        ),
        genai_errors.ClientError(
            404,
            {
                "error": {
                    "code": 404,
                    "message": "model not found",
                    "status": "NOT_FOUND",
                }
            },
        ),
        genai_errors.ClientError(
            429,
            {
                "error": {
                    "code": 429,
                    "message": "quota exceeded",
                    "status": "RESOURCE_EXHAUSTED",
                }
            },
        ),
        genai_errors.ServerError(
            503,
            {"error": {"code": 503, "message": "overloaded", "status": "UNAVAILABLE"}},
        ),
        TimeoutError("timed out after 60 s, key=sk-not-real"),
    ],
)
def test_provider_errors_are_sanitized_model_errors(monkeypatch, error, caplog):
    model = gemini()
    script(model, monkeypatch, error)

    with (
        caplog.at_level(logging.INFO, logger="resqivo"),
        pytest.raises(ModelResponseError) as info,
    ):
        answer_with(model)

    assert str(info.value) == "The language model request failed."
    assert "sk-not-real" not in caplog.text
    assert DUMMY_KEY not in caplog.text


# Structured output (JSON drafts) through the adapter ---------------------------


def draft_workflow(model):
    retriever = FakeRetriever([passage()])
    return DraftPlanWorkflow(
        search_tool=make_search_guidance_tool(retriever),
        validate_tool=make_validate_plan_tool(),
        answer_service=QuestionAnsweringService(retriever, model),
        model=model,
    )


def test_json_draft_through_the_adapter_is_validated(monkeypatch):
    model = gemini()
    script(model, monkeypatch, response(text(SUPPORTED)), response(text(VALID_DRAFT)))

    result = draft_workflow(model).run(draft_request(), "req-gemini-1")

    assert result.status == "draft_valid"
    assert result.evidence_available is True
    assert len(result.plan_review.final_plan.allocations) == 3


def test_fenced_json_draft_is_parsed(monkeypatch):
    model = gemini()
    fenced = "```json\n" + VALID_DRAFT + "\n```"
    script(model, monkeypatch, response(text(SUPPORTED)), response(text(fenced)))

    assert (
        draft_workflow(model).run(draft_request(), "req-gemini-2").status
        == "draft_valid"
    )


def test_truncated_draft_is_never_accepted(monkeypatch):
    model = gemini()
    script(
        model,
        monkeypatch,
        response(text(SUPPORTED)),
        response(text(VALID_DRAFT), finish_reason="MAX_TOKENS"),
    )

    with pytest.raises(ModelResponseError, match="did not complete a draft"):
        draft_workflow(model).run(draft_request(), "req-gemini-3")


def test_blocked_correction_counts_as_a_failed_attempt(monkeypatch):
    model = gemini()
    over = json.dumps(
        {
            "allocations": [
                {
                    "allocation_id": "a-1",
                    "resource_id": "water-001",
                    "destination_id": "shelter-001",
                    "quantity_allocated": 5000,
                }
            ]
        }
    )
    fixed = over.replace("5000", "900")
    script(
        model,
        monkeypatch,
        response(text(SUPPORTED)),
        response(text(over)),
        response(text(fixed), finish_reason="SAFETY"),  # would fix it, but blocked
        response(
            text(fixed), finish_reason="MAX_TOKENS"
        ),  # would fix it, but truncated
    )

    result = draft_workflow(model).run(draft_request(), "req-gemini-4")

    assert result.status == "draft_invalid"
    assert result.plan_review.correction_attempts == 2
    assert [v.code for v in result.plan_review.final_validation.violations] == [
        "DOM-04"
    ]


# Tool calling through the adapter ----------------------------------------------


def tool_workflow(model, retriever=None, **kwargs):
    retriever = retriever or FakeRetriever([passage()])
    return ReviewWorkflow(
        search_tool=make_search_guidance_tool(retriever),
        validate_tool=make_validate_plan_tool(),
        answer_service=QuestionAnsweringService(retriever, model),
        model=model,
        tool_calling=True,
        **kwargs,
    )


def test_gemini_function_call_is_authorized_and_executed(monkeypatch):
    model = gemini()
    retriever = FakeRetriever([passage()])
    calls = script(
        model,
        monkeypatch,
        response(function_call("search_guidance", {"query": "water storage"})),
        response(text(SUPPORTED)),
    )

    state = tool_workflow(model, retriever).run_state(
        "How is water stored?", None, "r1"
    )

    assert retriever.calls == [("water storage", 4)]
    assert [(r.tool, r.status) for r in state["tool_records"]] == [
        ("search_guidance", "executed")
    ]
    assert state["answer"].status == "answered"
    # Only the stage's tools were declared, and the model was not forced to call one.
    declared = [
        d.name for t in calls[0]["config"].tools for d in t.function_declarations
    ]
    assert declared == ["search_guidance"]
    assert calls[0]["config"].tool_config is None
    # The tool result went back to the model as a function response, not as text.
    second_turn = calls[1]["contents"]
    assert any(
        part.function_response is not None
        for content in second_turn
        for part in (content.parts or [])
    )


def test_gemini_unknown_and_invalid_calls_are_rejected(monkeypatch):
    model = gemini()
    retriever = FakeRetriever([passage()])
    script(
        model,
        monkeypatch,
        response(
            function_call("run_shell", {"command": "env"}),
            function_call("search_guidance", {"query": "water", "url": "http://x"}),
        ),
        response(text("INSUFFICIENT_EVIDENCE")),
    )

    state = tool_workflow(model, retriever).run_state("Water?", None, "r2")

    assert retriever.calls == []
    assert [(r.tool, r.status, r.reason) for r in state["tool_records"]] == [
        ("unknown", "rejected", "unknown_tool"),
        ("search_guidance", "rejected", "invalid_arguments"),
    ]


def test_gemini_validate_plan_call_uses_the_real_validator(monkeypatch):
    plan = PlanValidationRequest.model_validate(
        {
            "resources": [
                {
                    "resource_id": "water-001",
                    "name": "Water",
                    "resource_type": "drinking_water",
                    "quantity_available": 1000,
                    "unit": "litres",
                    "location": "Depot",
                }
            ],
            "allocations": [
                {
                    "allocation_id": "a-1",
                    "resource_id": "water-001",
                    "destination_id": "shelter-001",
                    "quantity_allocated": 1100,
                }
            ],
            "shelters": [
                {
                    "shelter_id": "shelter-001",
                    "name": "Hall",
                    "location": "Zone A",
                    "capacity": 500,
                    "current_occupancy": 200,
                }
            ],
        }
    )
    model = gemini()
    script(
        model,
        monkeypatch,
        response(function_call("validate_plan", plan.model_dump(mode="json"))),
        response(text(SUPPORTED)),
        response(text("not json")),  # correction 1
        response(text("not json")),  # correction 2
    )

    state = tool_workflow(model).run_state("Valid?", plan, "r3")

    assert [(r.tool, r.status) for r in state["tool_records"]] == [
        ("validate_plan", "executed")
    ]
    assert state["validation"].valid is False  # the fixed validator decides
    assert state["correction_attempts"] == 2


def test_malformed_function_call_finish_is_a_model_error(monkeypatch):
    model = gemini()
    script(
        model, monkeypatch, response(text(""), finish_reason="MALFORMED_FUNCTION_CALL")
    )

    with pytest.raises(ModelResponseError, match="did not complete a reply"):
        tool_workflow(model).run_state("Water?", None, "r4")


def test_tool_messages_convert_to_gemini_function_responses():
    model = gemini()
    history = [
        SystemMessage("rules"),
        HumanMessage("question"),
        AIMessage(
            content="",
            tool_calls=[
                {"name": "search_guidance", "args": {"query": "x"}, "id": "call-1"}
            ],
        ),
        ToolMessage(
            content="Error: invalid arguments.", tool_call_id="call-1", status="error"
        ),
    ]

    request = model._prepare_request(history)

    parts = [part for content in request["contents"] for part in (content.parts or [])]
    assert any(
        part.function_call and part.function_call.name == "search_guidance"
        for part in parts
    )
    assert any(part.function_response is not None for part in parts)


# Reply checks ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("metadata", "unusable"),
    [
        ({}, False),
        ({"finish_reason": "STOP"}, False),
        ({"finish_reason": "MAX_TOKENS"}, True),
        ({"finish_reason": "SAFETY"}, True),
        ({"finish_reason": "FINISH_REASON_UNSPECIFIED"}, True),
        ({"prompt_feedback": {"block_reason": "SAFETY"}}, True),
        ({"prompt_feedback": {"block_reason": 0}, "finish_reason": "STOP"}, False),
    ],
)
def test_unusable_reply(metadata, unusable):
    assert (
        unusable_reply(AIMessage(content="x", response_metadata=metadata)) is unusable
    )


# Failure diagnostics (metadata only) -------------------------------------------


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("", "empty_reply"),
        ("I cannot help with that.", "no_json_object"),
        ("{not json}", "invalid_json"),
        ('{"plan": []}', "missing_allocations"),
        ('{"allocations": "none"}', "allocations_not_a_list"),
        ('{"allocations": []}', "empty_allocations"),
        (
            '{"allocations": [{"allocation_id": "a", "resource_id": "r", '
            '"destination_id": "s", "quantity_allocated": 5, "rationale": "secret"}]}',
            "invalid_allocation:0.rationale:extra_forbidden",
        ),
        (VALID_DRAFT, "ok"),
    ],
)
def test_draft_parse_failures_are_classified(text, reason):
    from app.workflow.correction import diagnose_allocations_text

    assert diagnose_allocations_text(text) == reason


def test_failure_fields_never_include_messages():
    from app.qa.replies import failure_fields

    error = genai_errors.ClientError(
        429,
        {
            "error": {
                "code": 429,
                "message": "quota for sk-not-real",
                "status": "RESOURCE_EXHAUSTED",
            }
        },
    )
    try:
        try:
            raise error
        except Exception as exc:
            raise RuntimeError("wrapped sk-not-real") from exc
    except RuntimeError as wrapped:
        fields = failure_fields(wrapped)

    assert fields == {
        "error_type": "RuntimeError",
        "cause_type": "ClientError",
        "http_status": 429,
    }


@pytest.mark.parametrize(
    ("replies", "expected"),
    [
        (
            [
                genai_errors.ClientError(
                    429, {"error": {"code": 429, "message": "sk-not-real"}}
                )
            ],
            {"stage": "request", "cause_type": "ClientError", "http_status": "429"},
        ),
        (
            [response(text(VALID_DRAFT), finish_reason="MAX_TOKENS")],
            {"stage": "reply", "finish_reason": "MAX_TOKENS"},
        ),
        (
            [
                response(
                    text(
                        '{"allocations": [{"allocation_id": "a", '
                        '"resource_id": "water-001", '
                        '"destination_id": "shelter-001", "quantity_allocated": 5, '
                        '"rationale": "private reasoning sk-not-real"}]}'
                    )
                )
            ],
            {
                "stage": "parse",
                "reason": "invalid_allocation:0.rationale:extra_forbidden",
                "finish_reason": "STOP",
            },
        ),
    ],
)
def test_draft_failures_log_the_cause_without_content(
    monkeypatch, caplog, replies, expected
):
    model = gemini()
    script(model, monkeypatch, response(text(SUPPORTED)), *replies)

    with (
        caplog.at_level(logging.INFO, logger="resqivo"),
        pytest.raises(ModelResponseError),
    ):
        draft_workflow(model).run(draft_request(), "req-diagnose")

    events = [
        r.getMessage() for r in caplog.records if "event=model.failed" in r.getMessage()
    ]
    assert len(events) == 1
    fields = dict(part.split("=", 1) for part in events[0].split(" "))
    for key, value in expected.items():
        assert fields[key] == value
    assert "sk-not-real" not in caplog.text
    assert "private reasoning" not in caplog.text
    assert DUMMY_KEY not in caplog.text
