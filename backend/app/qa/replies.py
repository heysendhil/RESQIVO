"""Provider-level checks on model replies. Imports nothing provider-specific, so
the services and workflows that use it stay cheap to import."""

from collections.abc import Mapping
from typing import Any

# Only a normally finished Gemini reply is usable. Safety, recitation, blocklist
# or other blocks, truncation (MAX_TOKENS) and malformed function calls are all
# treated as a failed model call, never as an answer.
USABLE_FINISH_REASONS = frozenset({"STOP"})
_UNBLOCKED = (None, 0, "BLOCKED_REASON_UNSPECIFIED")


def unusable_reply(reply: Any) -> bool:
    """True if the provider blocked the prompt, or blocked, truncated or otherwise
    did not finish the reply. Replies without provider metadata (the fake models
    used in tests) are judged on their content by the caller."""
    metadata = getattr(reply, "response_metadata", None) or {}
    feedback = metadata.get("prompt_feedback") or {}
    if isinstance(feedback, Mapping) and feedback.get("block_reason") not in _UNBLOCKED:
        return True
    finish = metadata.get("finish_reason")
    return finish is not None and finish not in USABLE_FINISH_REASONS


# Diagnostics: metadata only, never prompt, reply text, message or credentials.


def failure_fields(exc: BaseException) -> dict[str, Any]:
    """Error class names and HTTP status of a failed model call. Exception
    messages are deliberately left out: provider messages can echo request
    details."""
    cause = exc.__cause__ or exc.__context__
    status = None
    for error in (exc, cause):
        for attribute in ("code", "status_code"):
            value = getattr(error, attribute, None)
            if isinstance(value, int) and status is None:
                status = value
    return {
        "error_type": type(exc).__name__,
        "cause_type": type(cause).__name__ if cause else None,
        "http_status": status,
    }


def reply_fields(reply: Any) -> dict[str, Any]:
    """Finish reason, block reason and output size of a reply."""
    metadata = getattr(reply, "response_metadata", None) or {}
    feedback = metadata.get("prompt_feedback") or {}
    usage = getattr(reply, "usage_metadata", None) or {}
    return {
        "finish_reason": metadata.get("finish_reason"),
        "block_reason": feedback.get("block_reason")
        if isinstance(feedback, Mapping)
        else None,
        "output_tokens": usage.get("output_tokens")
        if isinstance(usage, Mapping)
        else None,
    }
