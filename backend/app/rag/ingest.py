"""Loading documents for ingestion. Nothing is downloaded.

Real sources are read only for manifest entries with include_in_index=true, from
a local copy of the official document: a prepared plain-text file
(<SOURCE-ID>.txt) or the PDF itself (<SOURCE-ID>.pdf). Synthetic fixtures are
read from a clearly labelled JSON file.
"""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.rag.documents import KnowledgeDocument
from app.rag.manifest import SourceEntry, SourceManifest, eligible_sources
from app.rag.pdf import extract_pdf_text
from app.rag.store import IngestionError

SYNTHETIC_PUBLISHER = "RESQIVO synthetic test fixture (not an official source)"
SYNTHETIC_TITLE_PREFIX = "SYNTHETIC"
SYNTHETIC_URL_PREFIX = "urn:resqivo:synthetic:"


def load_approved_documents(
    manifest: SourceManifest, local_dir: Path
) -> list[KnowledgeDocument]:
    """Read the local copy of each approved source. Unapproved files are never read."""
    documents = []
    for source in eligible_sources(manifest):
        text_path = local_dir / f"{source.id}.txt"
        pdf_path = local_dir / f"{source.id}.pdf"
        if text_path.is_file() and pdf_path.is_file():
            raise IngestionError(
                f"Approved source {source.id} has both {text_path.name} and "
                f"{pdf_path.name} in {local_dir}. Keep only one."
            )
        if pdf_path.is_file():
            documents.append(_pdf_document(source, pdf_path))
        elif text_path.is_file():
            documents.append(_text_document(source, text_path))
        else:
            raise IngestionError(
                f"Approved source {source.id} has no local text file at {text_path} "
                f"or PDF at {pdf_path}. Save the official document there; see "
                "docs/rag.md."
            )
    return documents


def _text_document(source: SourceEntry, path: Path) -> KnowledgeDocument:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise IngestionError(f"Local text file for {source.id} is empty: {path}")
    return KnowledgeDocument(
        source_id=source.id,
        title=source.title,
        publisher=source.publisher,
        url=source.source_url,
        text=text,
        synthetic=False,
        source_file=path.name,
    )


def _pdf_document(source: SourceEntry, path: Path) -> KnowledgeDocument:
    extracted = extract_pdf_text(path)
    return KnowledgeDocument(
        source_id=source.id,
        title=source.title,
        publisher=source.publisher,
        url=source.source_url,
        text="\n\n".join(page.text for page in extracted.pages),
        synthetic=False,
        source_file=path.name,
        pages=extracted.pages,
        page_count=extracted.page_count,
    )


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
