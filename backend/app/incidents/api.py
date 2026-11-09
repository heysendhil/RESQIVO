"""Incident feed endpoints: list, create, change status, simulate, clear,
stream changes, and AI intake of simulated call transcripts.

Every incident is simulated. Status changes are made only by an operator;
nothing here dispatches, books or contacts anyone.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import StreamingResponse

from app.incidents.intake import IntakeRequest, IntakeResponse, extract_incident
from app.incidents.models import (
    INCIDENT_ID_PATTERN,
    MAX_INCIDENTS,
    DeleteResult,
    Incident,
    IncidentCreate,
    IncidentList,
    IncidentStatus,
    SimulationRequest,
    StatusUpdate,
)
from app.incidents.simulation import simulate_incidents
from app.incidents.store import IncidentLimitError, IncidentStore, get_incident_store
from app.incidents.stream import incident_events
from app.observability import log_event

logger = logging.getLogger("resqivo.incidents")

router = APIRouter(prefix="/incidents", tags=["incidents"])


def incident_store() -> IncidentStore:
    """The configured store. A parameterless wrapper, so that FastAPI does not
    read get_incident_store's arguments as request fields."""
    return get_incident_store()


Store = Annotated[IncidentStore, Depends(incident_store)]


def get_intake_model() -> Any:
    """Build the chat model for call intake. Imported lazily so that API
    startup does not load the model client; configuration errors become 503."""
    from app.qa.config import QASettings
    from app.qa.llm import build_chat_model

    return build_chat_model(QASettings.from_env())


def _limit_error(exc: IncidentLimitError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


@router.get("")
def list_incidents(
    store: Store,
    status: IncidentStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_INCIDENTS)] = 200,
) -> IncidentList:
    """Simulated incidents, newest first."""
    return IncidentList(incidents=store.list(status, limit), version=store.version)


@router.post("", status_code=201)
def create_incident(request: IncidentCreate, store: Store) -> Incident:
    """Create an incident from an operator's entry or a reviewed call intake."""
    try:
        incident = store.add(request, source=request.source)
    except IncidentLimitError as exc:
        raise _limit_error(exc) from exc
    log_event(logger, "incident.created", source=request.source)
    return incident


@router.patch("/{incident_id}")
def update_status(
    incident_id: Annotated[str, Path(pattern=INCIDENT_ID_PATTERN)],
    request: StatusUpdate,
    store: Store,
) -> Incident:
    """Record an operator's status change (new, acknowledged or closed)."""
    incident = store.set_status(incident_id, request.status)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    log_event(logger, "incident.status", status=request.status)
    return incident


@router.post("/simulate", status_code=201)
def simulate(request: SimulationRequest, store: Store) -> IncidentList:
    """Generate synthetic Chennai flood or cyclone incidents."""
    if request.reset_existing:
        store.clear()
    elif store.count() + request.count > MAX_INCIDENTS:
        raise HTTPException(
            status_code=409,
            detail=f"At most {MAX_INCIDENTS} incidents can be held; clear some first.",
        )
    generated = simulate_incidents(request.scenario, request.count, request.seed)
    now = datetime.now(UTC)
    try:
        # Staggered by a second each, so the queue shows them in order.
        for offset, fields in enumerate(reversed(generated)):
            store.add(
                fields, source="simulation", created_at=now - timedelta(seconds=offset)
            )
    except IncidentLimitError as exc:
        raise _limit_error(exc) from exc
    log_event(
        logger, "incident.simulated", scenario=request.scenario, count=request.count
    )
    return IncidentList(incidents=store.list(), version=store.version)


@router.delete("")
def clear_incidents(store: Store) -> DeleteResult:
    """Delete every incident (all are simulated)."""
    deleted = store.clear()
    log_event(logger, "incident.cleared", deleted=deleted)
    return DeleteResult(deleted=deleted)


@router.get("/stream")
async def stream(request: Request, store: Store) -> StreamingResponse:
    """Server-sent events: an "incidents" event whenever the feed changes."""
    return StreamingResponse(
        incident_events(store, request.is_disconnected),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/intake")
def intake(
    request: IntakeRequest,
    model: Annotated[Any, Depends(get_intake_model)],
) -> IntakeResponse:
    """Extract a draft incident from a simulated call transcript. Nothing is
    stored; the operator reviews the draft and creates the incident."""
    return extract_incident(request.transcript, model)
