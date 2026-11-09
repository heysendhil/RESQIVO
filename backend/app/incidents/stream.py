"""Server-sent events for the incident feed.

The stream carries only a change signal (the store version), never incident
data: clients fetch GET /incidents when it changes, so every client sees the
same validated list.
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable

from app.incidents.store import IncidentStore

POLL_SECONDS = 1.0
KEEPALIVE_SECONDS = 15.0
RETRY_MILLISECONDS = 3000


async def incident_events(
    store: IncidentStore,
    is_disconnected: Callable[[], Awaitable[bool]],
    poll_seconds: float = POLL_SECONDS,
    keepalive_seconds: float = KEEPALIVE_SECONDS,
) -> AsyncIterator[str]:
    """Yield an "incidents" event at the start and whenever the store changes,
    and a comment line as a keepalive. Ends when the client disconnects."""
    yield f"retry: {RETRY_MILLISECONDS}\n\n"
    last_version: int | None = None
    last_sent = time.monotonic()
    while not await is_disconnected():
        version = store.version
        if version != last_version:
            last_version = version
            last_sent = time.monotonic()
            yield f"event: incidents\ndata: {json.dumps({'version': version})}\n\n"
        elif time.monotonic() - last_sent >= keepalive_seconds:
            last_sent = time.monotonic()
            yield ": keepalive\n\n"
        await asyncio.sleep(poll_seconds)
