import pytest
from langchain_core.messages import HumanMessage

from app.qa.config import DEFAULT_LLM_MODEL, QASettings
from app.qa.errors import ModelNotConfiguredError, QAConfigurationError
from app.qa.llm import MAX_ANSWER_TOKENS, build_chat_model

pytestmark = pytest.mark.usefixtures("no_network")

DUMMY_KEY = "test-key-not-real-0000"


@pytest.mark.parametrize("environ", [{}, {"ANTHROPIC_API_KEY": "   "}])
def test_missing_credentials_are_reported(environ):
    with pytest.raises(ModelNotConfiguredError):
        build_chat_model(QASettings.from_env({}), environ)


def test_model_is_configured_from_environment_without_network():
    model = build_chat_model(QASettings.from_env({}), {"ANTHROPIC_API_KEY": DUMMY_KEY})

    assert model.model == DEFAULT_LLM_MODEL == "claude-opus-5-5"
    assert model.max_tokens == MAX_ANSWER_TOKENS
    assert DUMMY_KEY not in repr(model)
    assert DUMMY_KEY not in str(model.model_dump())


def test_request_payload_has_no_tools_or_unsupported_parameters():
    model = build_chat_model(QASettings.from_env({}), {"ANTHROPIC_API_KEY": DUMMY_KEY})

    payload = model._get_request_payload([HumanMessage("question")])

    for field in ("tools", "tool_choice", "temperature", "thinking", "top_p", "top_k"):
        assert field not in payload


def test_settings_defaults_and_overrides():
    defaults = QASettings.from_env({})
    custom = QASettings.from_env(
        {
            "RESQIVO_LLM_MODEL": "claude-sonnet-5-5",
            "RESQIVO_QA_TOP_K": "6",
            "RESQIVO_QA_MAX_DISTANCE": "0.8",
        }
    )

    assert (defaults.top_k, defaults.max_distance) == (4, 1.0)
    assert (custom.llm_model, custom.top_k, custom.max_distance) == (
        "claude-sonnet-5-5",
        6,
        0.8,
    )


@pytest.mark.parametrize(
    "environ",
    [
        {"RESQIVO_QA_TOP_K": "0"},
        {"RESQIVO_QA_TOP_K": "21"},
        {"RESQIVO_QA_TOP_K": "four"},
        {"RESQIVO_QA_MAX_DISTANCE": "0"},
        {"RESQIVO_QA_MAX_DISTANCE": "2.5"},
        {"RESQIVO_LLM_MODEL": "   "},
    ],
)
def test_invalid_settings_are_rejected(environ):
    with pytest.raises(QAConfigurationError):
        QASettings.from_env(environ)
