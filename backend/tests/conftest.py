import socket

import pytest

from app.rag.config import DEFAULT_SYNTHETIC_FIXTURES_PATH
from app.rag.embeddings import HashingEmbeddings
from app.rag.ingest import load_synthetic_documents
from app.rag.store import KnowledgeStore


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the test if anything attempts a network connection."""

    def blocked(self, address):
        raise RuntimeError(f"Network access attempted: {address}")

    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture
def store(tmp_path, no_network) -> KnowledgeStore:
    return KnowledgeStore(
        embeddings=HashingEmbeddings(),
        collection_name="test_collection",
        persist_directory=tmp_path / "chroma",
    )


@pytest.fixture
def synthetic_documents():
    return load_synthetic_documents(DEFAULT_SYNTHETIC_FIXTURES_PATH)
