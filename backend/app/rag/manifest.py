"""Validation of the knowledge-source manifest (knowledge/seed/sources.json)."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class ManifestError(Exception):
    """The manifest is missing, unreadable, or invalid."""


class Verification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["verified", "verified_access_only", "partially_verified"]
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    evidence: str = Field(min_length=1)


class SourceEntry(BaseModel):
    """One official publisher document listed in the manifest."""

    model_config = ConfigDict(extra="forbid")

    # Publisher prefixes only; SYN- is reserved for synthetic fixtures.
    id: str = Field(pattern=r"^(NDMA|WHO|UNDRR)-\d{2}$")
    title: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    source_url: str | None = Field(default=None, pattern=r"^https://")
    landing_url: str = Field(pattern=r"^https?://")
    published: str = Field(min_length=1)
    isbn: str | None = None
    topics: list[str] = Field(min_length=1)
    intended_use: str = Field(min_length=1)
    access: Literal["verified", "unverified"]
    reuse: Literal["open_licence", "permission_required", "unverified"]
    licence: str | None = None
    reuse_terms_url: str = Field(pattern=r"^https?://")
    include_in_index: bool
    notes: str | None = None
    verification: Verification

    @model_validator(mode="after")
    def check_index_eligibility(self) -> SourceEntry:
        if self.include_in_index:
            problems = []
            if self.reuse != "open_licence":
                problems.append("reuse must be 'open_licence'")
            if self.licence is None:
                problems.append("a licence must be recorded")
            if self.access != "verified":
                problems.append("access must be 'verified'")
            if self.source_url is None:
                problems.append("an official source_url is required")
            if problems:
                raise ValueError(
                    f"{self.id} is marked include_in_index but " + "; ".join(problems)
                )
        return self


class SourceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_version: Literal[1]
    description: str
    verified_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    sources: list[SourceEntry]

    @model_validator(mode="after")
    def check_unique_ids(self) -> SourceManifest:
        seen: set[str] = set()
        duplicates = []
        for source in self.sources:
            if source.id in seen:
                duplicates.append(source.id)
            seen.add(source.id)
        if duplicates:
            raise ValueError(f"Duplicate source IDs: {sorted(set(duplicates))}")
        return self


def load_manifest(path: Path) -> SourceManifest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ManifestError(f"Manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestError(f"Manifest is not valid JSON: {path}") from exc
    try:
        return SourceManifest.model_validate(raw)
    except ValidationError as exc:
        raise ManifestError(f"Manifest is invalid: {path}\n{exc}") from exc


def eligible_sources(manifest: SourceManifest) -> list[SourceEntry]:
    """Return the sources approved for ingestion (include_in_index=true)."""
    return [source for source in manifest.sources if source.include_in_index]
