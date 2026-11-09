"""SQLite-backed incident store (standard library only).

One connection is shared under a lock, so the store is safe to use from
FastAPI's thread pool. Incidents are stored as validated JSON documents.
"""

import os
import secrets
import sqlite3
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from app.incidents.models import (
    MAX_INCIDENTS,
    Incident,
    IncidentFields,
    IncidentSource,
    IncidentStatus,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INCIDENT_DB = REPO_ROOT / "data" / "incidents" / "incidents.db"
INCIDENT_DB_ENV = "RESQIVO_INCIDENT_DB"


class IncidentLimitError(Exception):
    """The store already holds the maximum number of incidents."""


class IncidentStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS incidents ("
            " incident_id TEXT PRIMARY KEY,"
            " created_at TEXT NOT NULL,"
            " document TEXT NOT NULL)"
        )
        self._db.commit()
        self._version = 0

    @property
    def version(self) -> int:
        return self._version

    def _changed(self) -> None:
        self._version += 1

    def count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]

    def list(
        self, status: IncidentStatus | None = None, limit: int = 200
    ) -> list[Incident]:
        """Newest first."""
        with self._lock:
            rows = self._db.execute(
                "SELECT document FROM incidents ORDER BY created_at DESC, incident_id"
            ).fetchall()
        incidents = [Incident.model_validate_json(row[0]) for row in rows]
        if status is not None:
            incidents = [i for i in incidents if i.status == status]
        return incidents[:limit]

    def get(self, incident_id: str) -> Incident | None:
        with self._lock:
            row = self._db.execute(
                "SELECT document FROM incidents WHERE incident_id = ?", (incident_id,)
            ).fetchone()
        return Incident.model_validate_json(row[0]) if row else None

    def add(
        self,
        fields: IncidentFields,
        source: IncidentSource,
        created_at: datetime | None = None,
    ) -> Incident:
        return self.add_many([fields], source, created_at)[0]

    def add_many(
        self,
        items: list[IncidentFields],
        source: IncidentSource,
        created_at: datetime | None = None,
    ) -> list[Incident]:
        now = created_at or datetime.now(UTC)
        incidents = []
        for fields in items:
            data = fields.model_dump(exclude={"source"})
            if fields.coordinates is None:
                confidence = "unconfirmed"
            elif source == "simulation":
                confidence = "simulated"
            else:
                confidence = "operator_entered"
            incidents.append(
                Incident(
                    **data,
                    incident_id=f"INC-{secrets.token_hex(4)}",
                    source=source,
                    location_confidence=confidence,
                    created_at=now,
                    updated_at=now,
                )
            )
        with self._lock:
            total = self._db.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
            if total + len(incidents) > MAX_INCIDENTS:
                raise IncidentLimitError(
                    f"At most {MAX_INCIDENTS} incidents can be held; clear some first."
                )
            self._db.executemany(
                "INSERT INTO incidents (incident_id, created_at, document) "
                "VALUES (?, ?, ?)",
                [
                    (i.incident_id, i.created_at.isoformat(), i.model_dump_json())
                    for i in incidents
                ],
            )
            self._db.commit()
            self._changed()
        return incidents

    def set_status(self, incident_id: str, status: IncidentStatus) -> Incident | None:
        with self._lock:
            row = self._db.execute(
                "SELECT document FROM incidents WHERE incident_id = ?", (incident_id,)
            ).fetchone()
            if row is None:
                return None
            incident = Incident.model_validate_json(row[0]).model_copy(
                update={"status": status, "updated_at": datetime.now(UTC)}
            )
            self._db.execute(
                "UPDATE incidents SET document = ? WHERE incident_id = ?",
                (incident.model_dump_json(), incident_id),
            )
            self._db.commit()
            self._changed()
        return incident

    def clear(self) -> int:
        with self._lock:
            deleted = self._db.execute("DELETE FROM incidents").rowcount
            self._db.commit()
            self._changed()
        return deleted


_stores: dict[str, IncidentStore] = {}
_stores_lock = threading.Lock()


def get_incident_store(environ: Mapping[str, str] = os.environ) -> IncidentStore:
    """The process-wide store for the configured path (RESQIVO_INCIDENT_DB)."""
    path = str(environ.get(INCIDENT_DB_ENV) or DEFAULT_INCIDENT_DB)
    with _stores_lock:
        if path not in _stores:
            _stores[path] = IncidentStore(path)
        return _stores[path]
