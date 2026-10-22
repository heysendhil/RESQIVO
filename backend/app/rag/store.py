"""ChromaDB-backed knowledge store with attributed retrieval.

Retrieved text is untrusted reference material: it is returned as data, never
interpreted as instructions, and never replaces deterministic validation.
"""

from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.config import Settings
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings

from app.rag.chunking import chunk_document
from app.rag.documents import KnowledgeDocument
from app.rag.embeddings import EmbeddingModelUnavailableError

MAX_QUERY_CHARS = 1000
MAX_RESULTS = 20

_REQUIRED_METADATA = {
    "chunk_id": str,
    "chunk_index": int,
    "source_id": str,
    "title": str,
    "publisher": str,
    "url": str,
    "synthetic": bool,
}


class IngestionError(Exception):
    """Documents could not be ingested."""


class RetrievalError(Exception):
    """Retrieval failed; no result is returned rather than an unattributed one."""


class KnowledgeBaseEmptyError(RetrievalError):
    """The collection contains no documents."""


@dataclass(frozen=True)
class RetrievedPassage:
    text: str
    source_id: str
    title: str
    publisher: str
    url: str
    chunk_id: str
    chunk_index: int
    synthetic: bool
    distance: float


class KnowledgeStore:
    """A single ChromaDB collection of attributed document chunks.

    A collection holds either synthetic fixtures or real sources, never both,
    so synthetic text cannot be returned as production guidance.
    """

    def __init__(
        self,
        embeddings: Embeddings,
        collection_name: str,
        persist_directory: Path | None = None,
    ) -> None:
        settings = Settings(anonymized_telemetry=False)
        if persist_directory is None:
            client = chromadb.EphemeralClient(settings=settings)
        else:
            persist_directory.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(
                path=str(persist_directory), settings=settings
            )
        self._vectorstore = Chroma(
            client=client,
            collection_name=collection_name,
            embedding_function=embeddings,
            collection_configuration={"hnsw": {"space": "cosine"}},
        )
        self._collection = client.get_collection(collection_name)

    def count(self) -> int:
        return self._collection.count()

    def _stored_synthetic_flags(self) -> set[bool]:
        metadatas = self._collection.get(include=["metadatas"])["metadatas"] or []
        return {bool(metadata.get("synthetic")) for metadata in metadatas}

    def ingest(self, documents: list[KnowledgeDocument]) -> int:
        """Store documents as chunks, replacing earlier chunks of the same source.

        Returns the number of chunks stored.
        """
        if not documents:
            return 0

        source_ids = [document.source_id for document in documents]
        duplicates = sorted({sid for sid in source_ids if source_ids.count(sid) > 1})
        if duplicates:
            raise IngestionError(f"Duplicate source IDs in batch: {duplicates}")

        flags = {document.synthetic for document in documents}
        if len(flags) > 1:
            raise IngestionError(
                "Synthetic and real documents cannot be ingested together."
            )
        existing = self._stored_synthetic_flags()
        if existing and existing != flags:
            raise IngestionError(
                "This collection already holds "
                + ("synthetic" if True in existing else "real")
                + " documents; use a separate collection."
            )

        chunks = []
        for document in documents:
            document_chunks = chunk_document(document)
            if not document_chunks:
                raise IngestionError(f"{document.source_id} has no text to index.")
            chunks.extend(document_chunks)

        for source_id in source_ids:
            self._vectorstore.delete(where={"source_id": source_id})
        self._vectorstore.add_texts(
            texts=[chunk.text for chunk in chunks],
            metadatas=[chunk.metadata() for chunk in chunks],
            ids=[chunk.chunk_id for chunk in chunks],
        )
        return len(chunks)

    def retrieve(self, query: str, k: int = 4) -> list[RetrievedPassage]:
        """Return up to k passages most similar to the query, with attribution."""
        if not query.strip():
            raise ValueError("Query must not be empty.")
        if len(query) > MAX_QUERY_CHARS:
            raise ValueError(f"Query must be at most {MAX_QUERY_CHARS} characters.")
        if not 1 <= k <= MAX_RESULTS:
            raise ValueError(f"k must be between 1 and {MAX_RESULTS}.")

        total = self.count()
        if total == 0:
            raise KnowledgeBaseEmptyError("The knowledge base is empty.")

        try:
            results = self._vectorstore.similarity_search_with_score(
                query, k=min(k, total)
            )
        except EmbeddingModelUnavailableError:
            # A configuration problem with an actionable message, not an outage.
            raise
        except Exception as exc:
            # The query text is deliberately left out of the message.
            raise RetrievalError("Retrieval failed.") from exc

        return [_to_passage(document, score) for document, score in results]


def _to_passage(document, score: float) -> RetrievedPassage:
    metadata = document.metadata or {}
    missing = [
        key
        for key, expected in _REQUIRED_METADATA.items()
        if not isinstance(metadata.get(key), expected)
        or (expected is str and not metadata.get(key))
    ]
    if missing:
        raise RetrievalError(
            f"A stored passage is missing attribution metadata: {sorted(missing)}"
        )
    return RetrievedPassage(
        text=document.page_content,
        source_id=metadata["source_id"],
        title=metadata["title"],
        publisher=metadata["publisher"],
        url=metadata["url"],
        chunk_id=metadata["chunk_id"],
        chunk_index=metadata["chunk_index"],
        synthetic=metadata["synthetic"],
        distance=float(score),
    )
