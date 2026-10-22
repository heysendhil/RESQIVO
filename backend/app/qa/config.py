import os
from collections.abc import Mapping
from dataclasses import dataclass

from app.qa.errors import QAConfigurationError

DEFAULT_LLM_MODEL = "claude-opus-5-5"
DEFAULT_TOP_K = 4
# Cosine distance: 0 is identical, 1 is unrelated (orthogonal), 2 is opposite.
# Passages farther than this are not shown to the model. Not yet calibrated
# against a real embedding model.
DEFAULT_MAX_DISTANCE = 1.0
# Model-initiated tool calls per workflow run. Configuration may lower the limit
# but can never exceed HARD_MAX_TOOL_CALLS.
DEFAULT_MAX_TOOL_CALLS = 4
HARD_MAX_TOOL_CALLS = 8

_TRUE = {"1", "true", "yes"}
_FALSE = {"", "0", "false", "no"}


@dataclass(frozen=True)
class QASettings:
    llm_model: str
    top_k: int
    max_distance: float
    tool_calling: bool = False
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS

    def __post_init__(self) -> None:
        if not self.llm_model.strip():
            raise QAConfigurationError("RESQIVO_LLM_MODEL must not be empty.")
        if not 1 <= self.top_k <= 20:
            raise QAConfigurationError("RESQIVO_QA_TOP_K must be between 1 and 20.")
        if not 0.0 < self.max_distance <= 2.0:
            raise QAConfigurationError(
                "RESQIVO_QA_MAX_DISTANCE must be greater than 0 and at most 2."
            )
        if not 1 <= self.max_tool_calls <= HARD_MAX_TOOL_CALLS:
            raise QAConfigurationError(
                f"RESQIVO_MAX_TOOL_CALLS must be between 1 and {HARD_MAX_TOOL_CALLS}."
            )

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> QASettings:
        try:
            top_k = int(environ.get("RESQIVO_QA_TOP_K") or DEFAULT_TOP_K)
            max_distance = float(
                environ.get("RESQIVO_QA_MAX_DISTANCE") or DEFAULT_MAX_DISTANCE
            )
            max_tool_calls = int(
                environ.get("RESQIVO_MAX_TOOL_CALLS") or DEFAULT_MAX_TOOL_CALLS
            )
        except ValueError as exc:
            raise QAConfigurationError(
                "RESQIVO_QA_TOP_K, RESQIVO_QA_MAX_DISTANCE and RESQIVO_MAX_TOOL_CALLS "
                "must be numbers."
            ) from exc
        tool_calling = environ.get("RESQIVO_TOOL_CALLING", "").strip().lower()
        if tool_calling not in _TRUE | _FALSE:
            raise QAConfigurationError(
                "RESQIVO_TOOL_CALLING must be one of: true, false, 1, 0, yes, no."
            )
        return cls(
            llm_model=environ.get("RESQIVO_LLM_MODEL") or DEFAULT_LLM_MODEL,
            top_k=top_k,
            max_distance=max_distance,
            tool_calling=tool_calling in _TRUE,
            max_tool_calls=max_tool_calls,
        )
