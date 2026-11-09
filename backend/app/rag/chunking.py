"""Deterministic word-window chunking."""

from app.rag.documents import Chunk, KnowledgeDocument

DEFAULT_CHUNK_WORDS = 150
DEFAULT_OVERLAP_WORDS = 30


def chunk_text(
    text: str,
    max_words: int = DEFAULT_CHUNK_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
) -> list[str]:
    """Split text into overlapping windows of at most max_words words.

    Whitespace is normalised. Empty or whitespace-only text yields no chunks.
    """
    if max_words < 1:
        raise ValueError("max_words must be at least 1.")
    if not 0 <= overlap_words < max_words:
        raise ValueError("overlap_words must be at least 0 and less than max_words.")

    words = text.split()
    if not words:
        return []

    step = max_words - overlap_words
    chunks = []
    for start in range(0, len(words), step):
        chunks.append(" ".join(words[start : start + max_words]))
        if start + max_words >= len(words):
            break
    return chunks


def chunk_document(
    document: KnowledgeDocument,
    max_words: int = DEFAULT_CHUNK_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
) -> list[Chunk]:
    """Chunk a document. A document with pages is chunked page by page, so no
    chunk spans two pages; chunk indexes still run through the whole document."""
    if document.pages:
        windows = [
            (page.page_number, text)
            for page in document.pages
            for text in chunk_text(page.text, max_words, overlap_words)
        ]
    else:
        windows = [
            (None, text) for text in chunk_text(document.text, max_words, overlap_words)
        ]
    return [
        Chunk(
            chunk_id=f"{document.source_id}:{index:04d}",
            chunk_index=index,
            text=text,
            document=document,
            page=page,
        )
        for index, (page, text) in enumerate(windows)
    ]
