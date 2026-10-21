"""Loading documents for ingestion. Nothing is downloaded.

Real sources are read only for manifest entries with include_in_index=true, from
plain-text files that a maintainer has prepared locally from the official
document. Synthetic fixtures are read from a clearly labelled JSON file.
"""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.rag.documents import KnowledgeDocument
from app.rag.manifest import SourceManifest, eligible_sources
from app.rag.store import IngestionError

SYNTHETIC_PUBLISHER = "RESQIVO synthetic test fixture (not an official source)"
SYNTHETIC_TITLE_PREFIX = "SYNTHETIC"
SYNTHETIC_URL_PREFIX = "urn:resqivo:synthetic:"


def load_approved_documents(
    manifest: SourceManifest, local_dir: Path
) -> list[KnowledgeDocument]:
    """Read local text for each approved source. Unapproved files are never read."""
    documents = []
    for source in eligible_sources(manifest):
        path = local_dir / f"{source.id}.txt"
        if not path.is_file():
            raise IngestionError(
                f"Approved source {source.id} has no local text file at {path}. "
                "Prepare it from the official document; see docs/rag.md."
            )
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            raise IngestionError(f"Local text file for {source.id} is empty: {path}")
        documents.append(
            KnowledgeDocument(
                source_id=source.id,
                title=source.title,
                publisher=source.publisher,
                url=source.source_url,
                text=text,
                synthetic=False,
            )
        )
    return documents


class SyntheticPassage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^SYN-\d{3}$")
    title: str
    publisher: str
    url: str
    topics: list[str] = Field(min_length=1)
    text: str = Field(min_length=1)

    @field_validator("title")
    @classmethod
    def title_is_labelled(cls, value: str) -> str:
        if not value.startswith(SYNTHETIC_TITLE_PREFIX):
            raise ValueError(f"must start with {SYNTHETIC_TITLE_PREFIX!r}")
        return value

    @field_validator("publisher")
    @classmethod
    def publisher_is_synthetic(cls, value: str) -> str:
        if value != SYNTHETIC_PUBLISHER:
            raise ValueError(f"must be {SYNTHETIC_PUBLISHER!r}")
        return value

    @field_validator("url")
    @classmethod
    def url_is_not_a_web_address(cls, value: str) -> str:
        if not value.startswith(SYNTHETIC_URL_PREFIX):
            raise ValueError(f"must start with {SYNTHETIC_URL_PREFIX!r}")
        return value


class SyntheticFixtureFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    synthetic: bool
    notice: str
    passages: list[SyntheticPassage] = Field(min_length=1)

    @field_validator("synthetic")
    @classmethod
    def must_be_synthetic(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("synthetic fixture files must set synthetic: true")
        return value


def load_synthetic_documents(path: Path) -> list[KnowledgeDocument]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        fixture = SyntheticFixtureFile.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise IngestionError(f"Invalid synthetic fixture file: {path}\n{exc}") from exc

    ids = [passage.id for passage in fixture.passages]
    duplicates = sorted({pid for pid in ids if ids.count(pid) > 1})
    if duplicates:
        raise IngestionError(f"Duplicate synthetic passage IDs: {duplicates}")

    return [
        KnowledgeDocument(
            source_id=passage.id,
            title=passage.title,
            publisher=passage.publisher,
            url=passage.url,
            text=passage.text,
            synthetic=True,
        )
        for passage in fixture.passages
    ]
