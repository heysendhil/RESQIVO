"""Structured operational events, request correlation and in-process metrics.

Standard library only, so importing it does not load LangGraph, ChromaDB or the
Claude client.

Events are single-line ``event=<name> request_id=<id> key=value ...`` records on
the ``resqivo.*`` loggers. Values are bounded and restricted to a safe character
set, so user input cannot add fields or lines. Callers pass only metadata
(counts, codes, booleans and durations), never questions, narratives, passages,
prompts, model output, resource details or secrets.

Recording never raises: a failing handler or formatter cannot change a response,
a validation result, or a safety check.
"""

import contextvars
import logging
import math
import re
import threading
import uuid
from collections import Counter
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_KEY = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_UNSAFE = re.compile(r"[^A-Za-z0-9._:/@+-]")
MAX_VALUE_CHARS = 64
MAX_LIST_ITEMS = 10

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "resqivo_request_id", default=None
)
_run_stats: contextvars.ContextVar[RunStats | None] = contextvars.ContextVar(
    "resqivo_run_stats", default=None
)


# Request IDs -------------------------------------------------------------------


def new_request_id() -> str:
    return uuid.uuid4().hex


def accept_request_id(candidate: str | None) -> str:
    """Reuse a client-supplied ID only if it is 8-64 characters of letters,
    digits, '.', '_' or '-'; otherwise generate one."""
    if candidate and _VALID_REQUEST_ID.match(candidate):
        return candidate
    return new_request_id()


def current_request_id() -> str | None:
    return _request_id.get()


# Event formatting --------------------------------------------------------------


def safe_value(value: Any) -> str:
    """Render a value as one bounded token with no spaces, '=' or line breaks."""
    if value is None or isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(round(value, 3)) if math.isfinite(value) else "nan"
    if isinstance(value, list | tuple | set | frozenset):
        items = sorted(value) if isinstance(value, set | frozenset) else list(value)
        shown = [safe_value(item) for item in items[:MAX_LIST_ITEMS]]
        suffix = ",+more" if len(items) > MAX_LIST_ITEMS else ""
        return "[" + ",".join(shown) + suffix + "]"
    text = _UNSAFE.sub("?", str(value))
    if len(text) > MAX_VALUE_CHARS:
        text = text[: MAX_VALUE_CHARS - 3] + "..."
    return text


def format_event(event: str, fields: Mapping[str, Any]) -> str:
    parts = [
        f"event={safe_value(event)}",
        f"request_id={safe_value(current_request_id())}",
    ]
    for key, value in fields.items():
        if key in ("event", "request_id") or not _KEY.match(key):
            continue  # keys are fixed in code; anything else is dropped
        parts.append(f"{key}={safe_value(value)}")
    return " ".join(parts)


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Emit a structured event. Never raises."""
    try:
        if logger.isEnabledFor(logging.INFO):
            logger.info(format_event(event, fields))
    except Exception:  # a failing handler must not affect the request
        METRICS.increment("logging_errors_total")


# Metrics -----------------------------------------------------------------------

DURATION_BUCKETS_MS = (50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000)


class MetricsRegistry:
    """Thread-safe, in-process counters and duration histograms. Not exposed over
    HTTP; snapshot() is for operators and tests. Label values are sanitised and
    come from fixed code sets, so cardinality stays bounded."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Counter[tuple[str, tuple[tuple[str, str], ...]]] = Counter()
        self._durations: dict[tuple[str, tuple[tuple[str, str], ...]], dict] = {}

    @staticmethod
    def _key(name: str, labels: Mapping[str, Any]):
        return name, tuple(sorted((k, safe_value(v)) for k, v in labels.items()))

    def increment(self, name: str, amount: int = 1, **labels: Any) -> None:
        try:
            with self._lock:
                self._counters[self._key(name, labels)] += amount
        except Exception:
            pass

    def observe_ms(self, name: str, value_ms: float, **labels: Any) -> None:
        try:
            key = self._key(name, labels)
            with self._lock:
                entry = self._durations.setdefault(
                    key,
                    {
                        "count": 0,
                        "sum_ms": 0.0,
                        "max_ms": 0.0,
                        "buckets": dict.fromkeys(DURATION_BUCKETS_MS, 0) | {"inf": 0},
                    },
                )
                entry["count"] += 1
                entry["sum_ms"] += value_ms
                entry["max_ms"] = max(entry["max_ms"], value_ms)
                bucket = next((b for b in DURATION_BUCKETS_MS if value_ms <= b), "inf")
                entry["buckets"][bucket] += 1
        except Exception:
            pass

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        with self._lock:
            counters = [
                {"name": n, "labels": dict(labels), "value": v}
                for (n, labels), v in sorted(self._counters.items())
            ]
            durations = [
                {
                    "name": n,
                    "labels": dict(labels),
                    "count": e["count"],
                    "sum_ms": round(e["sum_ms"], 3),
                    "max_ms": round(e["max_ms"], 3),
                    "buckets": {str(k): v for k, v in e["buckets"].items()},
                }
                for (n, labels), e in sorted(self._durations.items())
            ]
        return {"counters": counters, "durations": durations}

    def value(self, name: str, **labels: Any) -> int:
        with self._lock:
            return self._counters.get(self._key(name, labels), 0)

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._durations.clear()


METRICS = MetricsRegistry()


# Per-request run statistics ----------------------------------------------------


@dataclass
class RunStats:
    """Counts for one request, reported in its completion event."""

    model_calls: int = 0
    model_failures: int = 0
    retrieval: list[str] = field(default_factory=list)
    tool_calls: int = 0
    tool_rejections: Counter[str] = field(default_factory=Counter)
    tool_failures: int = 0
    validations: int = 0
    invalid_validations: int = 0
    corrections: int = 0
    grounding_rejections: Counter[str] = field(default_factory=Counter)
    answers: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "model_calls": self.model_calls,
            "model_failures": self.model_failures,
            "retrieval": self.retrieval,
            "tool_calls": self.tool_calls,
            "tool_rejections": sum(self.tool_rejections.values()),
            "tool_rejection_reasons": sorted(self.tool_rejections),
            "tool_failures": self.tool_failures,
            "validations": self.validations,
            "invalid_validations": self.invalid_validations,
            "corrections": self.corrections,
            "grounding_rejections": sorted(self.grounding_rejections),
            "answer_outcomes": self.answers,
        }


@contextmanager
def request_context(request_id: str) -> Iterator[RunStats]:
    """Bind a request ID and fresh run statistics for the duration of a request."""
    stats = RunStats()
    id_token = _request_id.set(request_id)
    stats_token = _run_stats.set(stats)
    try:
        yield stats
    finally:
        _run_stats.reset(stats_token)
        _request_id.reset(id_token)


@contextmanager
def ensure_request_context(request_id: str | None = None) -> Iterator[str]:
    """Reuse the active request context, or open one (for workflows run outside
    the API, such as tests and evaluation). Yields the request ID in use."""
    active = current_request_id()
    if active is not None and request_id in (None, active):
        yield active
        return
    with request_context(request_id or active or new_request_id()):
        yield current_request_id()


def _stats() -> RunStats | None:
    return _run_stats.get()


# Recording helpers (never raise) -----------------------------------------------


def record_model_call(purpose: str, ok: bool) -> None:
    try:
        METRICS.increment(
            "model_calls_total", purpose=purpose, outcome="success" if ok else "failure"
        )
        if stats := _stats():
            stats.model_calls += 1
            stats.model_failures += 0 if ok else 1
    except Exception:
        pass


def record_retrieval(outcome: str) -> None:
    """outcome: success, empty_knowledge_base, no_relevant_passages, failure or
    configuration_error."""
    try:
        METRICS.increment("retrieval_total", outcome=outcome)
        if stats := _stats():
            stats.retrieval.append(outcome)
    except Exception:
        pass


def record_tool_call(tool: str, status: str, reason: str | None) -> None:
    try:
        METRICS.increment("tool_calls_total", tool=tool, status=status, reason=reason)
        if stats := _stats():
            stats.tool_calls += 1
            if status == "rejected":
                stats.tool_rejections[reason or "unknown"] += 1
            elif status == "failed":
                stats.tool_failures += 1
    except Exception:
        pass


def record_validation(valid: bool) -> None:
    try:
        METRICS.increment("validations_total", valid=valid)
        if stats := _stats():
            stats.validations += 1
            stats.invalid_validations += 0 if valid else 1
    except Exception:
        pass


def record_correction(parsed: bool) -> None:
    try:
        METRICS.increment("correction_attempts_total", parsed=parsed)
        if stats := _stats():
            stats.corrections += 1
    except Exception:
        pass


def record_grounding_rejection(rule: str) -> None:
    try:
        METRICS.increment("grounding_rejections_total", rule=rule)
        if stats := _stats():
            stats.grounding_rejections[rule] += 1
    except Exception:
        pass


def record_answer(status: str, reason: str | None) -> None:
    """A finished grounded answer: answered, or insufficient_evidence with its
    reason (knowledge_base_empty, no_relevant_passages, ...)."""
    try:
        METRICS.increment("answers_total", status=status, reason=reason)
        if stats := _stats():
            stats.answers.append(reason or status)
    except Exception:
        pass


def run_summary() -> dict[str, Any]:
    stats = _stats()
    return stats.summary() if stats else {}


# Tracing -----------------------------------------------------------------------

_TRUE = {"1", "true", "yes"}


def tracing_enabled(environ: Mapping[str, str]) -> bool:
    return any(
        environ.get(name, "").strip().lower() in _TRUE
        for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING")
    )


def tracing_privacy_defaults(environ: Mapping[str, str]) -> dict[str, str]:
    """When tracing is explicitly enabled, the variables that make LangSmith hide
    run inputs and outputs, unless the operator has set them. Nothing when
    tracing is disabled."""
    if not tracing_enabled(environ):
        return {}
    return {
        name: "true"
        for name in ("LANGSMITH_HIDE_INPUTS", "LANGSMITH_HIDE_OUTPUTS")
        if not environ.get(name)
    }
