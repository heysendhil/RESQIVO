from dataclasses import dataclass


@dataclass(frozen=True)
class PageText:
    """Text of one PDF page. page_number is 1-based, as shown in PDF viewers."""

    page_number: int
    text: str


@dataclass(frozen=True)
class KnowledgeDocument:
    """A document ready for ingestion, with the attribution to store alongside it.

    Documents read from a PDF also carry their pages, so that every chunk comes
    from a single page and can be cited with its page number.
    """

    source_id: str
    title: str
    publisher: str
    url: str
    text: str
    synthetic: bool
    source_file: str | None = None
    pages: tuple[PageText, ...] = ()
    # Pages in the PDF, including those without extractable text.
    page_count: int | None = None

    def pages_without_text(self) -> list[int]:
        if self.page_count is None:
            return []
        with_text = {page.page_number for page in self.pages}
        return [n for n in range(1, self.page_count + 1) if n not in with_text]


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    chunk_index: int
    text: str
    document: KnowledgeDocument
    page: int | None = None

    def metadata(self) -> dict[str, str | int | bool]:
        metadata: dict[str, str | int | bool] = {
            "chunk_id": self.chunk_id,
            "chunk_index": self.chunk_index,
            "source_id": self.document.source_id,
            "title": self.document.title,
            "publisher": self.document.publisher,
            "url": self.document.url,
            "synthetic": self.document.synthetic,
        }
        # ChromaDB metadata cannot hold None, so optional fields are omitted.
        if self.document.source_file:
            metadata["source_file"] = self.document.source_file
        if self.page is not None:
            metadata["page"] = self.page
            # PDF viewers open "#page=N" at that page; citations carry the URL.
            url = self.document.url
            if url.startswith("https://") and "#" not in url:
                metadata["url"] = f"{url}#page={self.page}"
        return metadata
