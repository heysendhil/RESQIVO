from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeDocument:
    """A document ready for ingestion, with the attribution to store alongside it."""

    source_id: str
    title: str
    publisher: str
    url: str
    text: str
    synthetic: bool


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    chunk_index: int
    text: str
    document: KnowledgeDocument

    def metadata(self) -> dict[str, str | int | bool]:
        return {
            "chunk_id": self.chunk_id,
            "chunk_index": self.chunk_index,
            "source_id": self.document.source_id,
            "title": self.document.title,
            "publisher": self.document.publisher,
            "url": self.document.url,
            "synthetic": self.document.synthetic,
        }
