"""Request-body size limit and per-request time budget.

Both are read from the environment within hard bounds; values outside the
bounds are rejected at startup of each request with a configuration error
rather than silently clamped.

- RESQIVO_MAX_BODY_BYTES (default 1 MiB, 16 KiB-8 MiB): larger bodies get
  413 before any parsing. The body is read at most to the limit, so memory per
  request is bounded. Bodies are never truncated and then processed.
- RESQIVO_REQUEST_TIMEOUT_SECONDS (default 120, 1-600): a cooperative deadline
  checked before every retrieval and model call. Once it has passed, no further
  calls are made and the request fails with 504. A model call already in
  progress is bounded by the client's own timeout, not interrupted.
"""

import contextvars
import json
import os
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass

from app.qa.errors import QAConfigurationError, QAError

DEFAULT_MAX_BODY_BYTES = 1024 * 1024
MIN_BODY_BYTES, HARD_MAX_BODY_BYTES = 16 * 1024, 8 * 1024 * 1024
DEFAULT_REQUEST_TIMEOUT_SECONDS = 120.0
MIN_TIMEOUT_SECONDS, HARD_MAX_TIMEOUT_SECONDS = 1.0, 600.0


class RequestTimeoutError(QAError):
    """The request's time budget ran out before the work completed."""


@dataclass(frozen=True)
class LimitSettings:
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if not MIN_BODY_BYTES <= self.max_body_bytes <= HARD_MAX_BODY_BYTES:
            raise QAConfigurationError(
                f"RESQIVO_MAX_BODY_BYTES must be between {MIN_BODY_BYTES} and "
                f"{HARD_MAX_BODY_BYTES}."
            )
        if not (
            MIN_TIMEOUT_SECONDS
            <= self.request_timeout_seconds
            <= HARD_MAX_TIMEOUT_SECONDS
        ):
            raise QAConfigurationError(
                "RESQIVO_REQUEST_TIMEOUT_SECONDS must be between "
                f"{MIN_TIMEOUT_SECONDS:g} and {HARD_MAX_TIMEOUT_SECONDS:g}."
            )

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> LimitSettings:
        try:
            return cls(
                max_body_bytes=int(
                    environ.get("RESQIVO_MAX_BODY_BYTES") or DEFAULT_MAX_BODY_BYTES
                ),
                request_timeout_seconds=float(
                    environ.get("RESQIVO_REQUEST_TIMEOUT_SECONDS")
                    or DEFAULT_REQUEST_TIMEOUT_SECONDS
                ),
            )
        except ValueError as exc:
            raise QAConfigurationError(
                "RESQIVO_MAX_BODY_BYTES and RESQIVO_REQUEST_TIMEOUT_SECONDS must be "
                "numbers."
            ) from exc


# Deadline ----------------------------------------------------------------------

_deadline: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "resqivo_deadline", default=None
)


@contextmanager
def deadline(seconds: float) -> Iterator[None]:
    """Set a deadline for the work done inside this block (nested deadlines
    keep the earlier one)."""
    new = time.monotonic() + seconds
    current = _deadline.get()
    token = _deadline.set(new if current is None else min(current, new))
    try:
        yield
    finally:
        _deadline.reset(token)


def check_deadline() -> None:
    """Raise RequestTimeoutError if the current request's deadline has passed."""
    expires = _deadline.get()
    if expires is not None and time.monotonic() > expires:
        raise RequestTimeoutError("The request time budget was exhausted.")


# Body size (pure ASGI middleware) ----------------------------------------------


class BodySizeLimitMiddleware:
    """Reject request bodies larger than the configured limit with 413.

    A declared Content-Length over the limit is rejected without reading. Other
    bodies (including chunked ones) are read up to the limit and replayed to
    the application; one byte more and the request is rejected. Nothing is
    truncated.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        try:
            limit = LimitSettings.from_env().max_body_bytes
        except QAConfigurationError:
            await _respond(send, 503, "Question answering is not configured.")
            return

        headers = dict(scope.get("headers") or [])
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                length = int(declared)
            except ValueError:
                await _respond(send, 400, "Invalid Content-Length header.")
                return
            if length > limit:
                await _respond(send, 413, "Request body too large.")
                return

        chunks, size, more = [], 0, True
        while more:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > limit:
                await _respond(send, 413, "Request body too large.")
                return
            chunks.append(chunk)
            more = message.get("more_body", False)

        body = b"".join(chunks)
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


async def _respond(send, status: int, detail: str) -> None:
    payload = json.dumps({"detail": detail}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})
