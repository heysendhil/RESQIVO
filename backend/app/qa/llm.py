"""Gemini chat model construction. Credentials come only from
the environment (GOOGLE_API_KEY), and are never logged or returned."""

import os
from collections.abc import Mapping

from langchain_google_genai import ChatGoogleGenerativeAI

from app.qa.config import QASettings
from app.qa.errors import ModelNotConfiguredError

API_KEY_ENV = "GOOGLE_API_KEY"
# Gemini counts thinking tokens towards this limit, so it leaves room for low-level
# thinking plus the answer or JSON draft.
MAX_OUTPUT_TOKENS = 16384
THINKING_LEVEL = "low"
# Per attempt. google-genai also sends this to Google as X-Server-Timeout, so a
# generation still running at this point is ended with HTTP 504. 90 s leaves room
# for slow responses (60 s produced repeated 504s on 2026-10-23).
REQUEST_TIMEOUT_SECONDS = 90.0
# Total attempts including the first request (google-genai HttpRetryOptions):
# one request plus at most one retry, so a slow call is not repeated (and billed)
# twice more. Worst case is about 2 x 90 s.
MAX_ATTEMPTS = 2


def build_chat_model(
    settings: QASettings, environ: Mapping[str, str] = os.environ
) -> ChatGoogleGenerativeAI:
    """Build the Gemini client. Raises ModelNotConfiguredError without an API key.

    Construction makes no network request. The Gemini Developer API is selected
    explicitly (vertexai=False), so Vertex AI environment variables cannot switch
    the backend, and only GOOGLE_API_KEY is used. No temperature or tool choice is
    set: Gemini 3+ models use their default temperature, and tools are bound
    only in tool-calling mode, without forcing a call.
    """
    api_key = environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        raise ModelNotConfiguredError(f"{API_KEY_ENV} is not set.")
    return ChatGoogleGenerativeAI(
        model=settings.llm_model,
        api_key=api_key,
        vertexai=False,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        thinking_level=THINKING_LEVEL,
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=MAX_ATTEMPTS,
    )
