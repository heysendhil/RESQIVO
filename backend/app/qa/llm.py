"""Claude chat model construction. Credentials come only from the environment."""

import os
from collections.abc import Mapping

from langchain_anthropic import ChatAnthropic

from app.qa.config import QASettings
from app.qa.errors import ModelNotConfiguredError

MAX_ANSWER_TOKENS = 4096
REQUEST_TIMEOUT_SECONDS = 60.0


def build_chat_model(
    settings: QASettings, environ: Mapping[str, str] = os.environ
) -> ChatAnthropic:
    """Build the Claude client. Raises ModelNotConfiguredError without an API key.

    No tools, tool choice, temperature, or thinking settings are passed: the model
    only produces text, and the current Claude models reject forced tool choice
    and sampling parameters.
    """
    api_key = environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ModelNotConfiguredError("ANTHROPIC_API_KEY is not set.")
    return ChatAnthropic(
        model=settings.llm_model,
        api_key=api_key,
        max_tokens=MAX_ANSWER_TOKENS,
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=2,
    )
