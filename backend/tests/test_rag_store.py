import dataclasses

import pytest

from app.rag.documents import KnowledgeDocument
from app.rag.embeddings import HashingEmbeddings
from app.rag.ingest import SYNTHETIC_PUBLISHER
from app.rag.store import (
    MAX_QUERY_CHARS,
    IngestionError,
    KnowledgeBaseEmptyError,
    KnowledgeStore,
    RetrievalError,
)


def real_document(source_id: str = "WHO-01") -> KnowledgeDocument:
    return KnowledgeDocument(
        source_id=source_id,
        title="Health Emergency and Disaster Risk Management Framework",
        publisher="World Health Organization",
        url="https://example.invalid/who-01",
        text="Placeholder text used only to test collection separation.",
        synthetic=False,
    )


def test_retrieval_returns_the_most_relevant_passage(store, synthetic_documents):
    store.ingest(synthetic_documents)

    water = store.retrieve("drinking water per person at shelters", k=1)
    route = store.retrieve("road closed evacuation route vehicles", k=1)

    assert water[0].source_id == "SYN-001"
    assert route[0].source_id == "SYN-003"


def test_retrieved_passages_carry_exact_attribution(store, synthetic_documents):
    store.ingest(synthetic_documents)
    expected = {document.source_id: document for document in synthetic_documents}

    passages = store.retrieve("shelter capacity occupancy", k=3)

    assert len(passages) == 3
    for passage in passages:
        source = expected[passage.source_id]
        assert passage.title == source.title
        assert passage.publisher == source.publisher == SYNTHETIC_PUBLISHER
        assert passage.url == source.url
        assert passage.synthetic is True
        assert passage.chunk_id == f"{passage.source_id}:0000"
        assert passage.text in source.text


def test_results_are_ordered_by_distance(store, synthetic_documents):
    store.ingest(synthetic_documents)

    distances = [p.distance for p in store.retrieve("water shelter", k=6)]

    assert distances == sorted(distances)


def test_k_larger_than_collection_returns_all_passages(store, synthetic_documents):
    store.ingest(synthetic_documents)

    assert len(store.retrieve("water", k=20)) == len(synthetic_documents)


def test_empty_knowledge_base_is_reported(store):
    with pytest.raises(KnowledgeBaseEmptyError):
        store.retrieve("water")


@pytest.mark.parametrize(
    ("query", "k"),
    [("", 4), ("   ", 4), ("x" * (MAX_QUERY_CHARS + 1), 4), ("water", 0), ("w", 21)],
)
def test_invalid_queries_are_rejected(store, synthetic_documents, query, k):
    store.ingest(synthetic_documents)

    with pytest.raises(ValueError):
        store.retrieve(query, k=k)


def test_duplicate_source_ids_in_a_batch_are_rejected(store, synthetic_documents):
    batch = [synthetic_documents[0], synthetic_documents[0]]

    with pytest.raises(IngestionError, match="Duplicate source IDs"):
        store.ingest(batch)
    assert store.count() == 0


def test_reingesting_a_source_replaces_its_chunks(store, synthetic_documents):
    store.ingest(synthetic_documents)
    count = store.count()
    updated = dataclasses.replace(
        synthetic_documents[0], text="Replacement text about generators."
    )

    store.ingest([updated])

    assert store.count() == count
    passage = store.retrieve("generators", k=1)[0]
    assert passage.source_id == "SYN-001"
    assert passage.text == "Replacement text about generators."


def test_document_without_text_is_rejected(store, synthetic_documents):
    empty = dataclasses.replace(synthetic_documents[0], text="   ")

    with pytest.raises(IngestionError, match="no text"):
        store.ingest([empty])


def test_synthetic_and_real_documents_cannot_share_a_batch(store, synthetic_documents):
    with pytest.raises(IngestionError, match="cannot be ingested together"):
        store.ingest([synthetic_documents[0], real_document()])


def test_real_documents_cannot_join_a_synthetic_collection(store, synthetic_documents):
    store.ingest(synthetic_documents)

    with pytest.raises(IngestionError, match="already holds synthetic"):
        store.ingest([real_document()])


def test_index_persists_in_the_configured_directory(tmp_path, no_network):
    directory = tmp_path / "persisted"
    first = KnowledgeStore(HashingEmbeddings(), "persisted", directory)
    first.ingest([real_document()])

    second = KnowledgeStore(HashingEmbeddings(), "persisted", directory)

    assert second.count() == 1
    assert second.retrieve("placeholder", k=1)[0].source_id == "WHO-01"


def test_collections_are_isolated_by_name(tmp_path, no_network, synthetic_documents):
    directory = tmp_path / "shared"
    KnowledgeStore(HashingEmbeddings(), "synthetic_set", directory).ingest(
        synthetic_documents
    )

    other = KnowledgeStore(HashingEmbeddings(), "other_set", directory)

    assert other.count() == 0


class FailingQueryEmbeddings(HashingEmbeddings):
    def embed_query(self, text: str) -> list[float]:
        raise RuntimeError("embedding backend unavailable")


def test_backend_failure_raises_retrieval_error(
    tmp_path, no_network, synthetic_documents
):
    directory = tmp_path / "failing"
    KnowledgeStore(HashingEmbeddings(), "failing", directory).ingest(
        synthetic_documents
    )
    failing = KnowledgeStore(FailingQueryEmbeddings(), "failing", directory)

    with pytest.raises(RetrievalError, match="Retrieval failed") as exc_info:
        failing.retrieve("sensitive query text")
    assert "sensitive query text" not in str(exc_info.value)


def test_passage_without_attribution_is_never_returned(store):
    vector = HashingEmbeddings().embed_documents(["water"])[0]
    store._collection.add(
        ids=["UNATTRIBUTED:0000"],
        documents=["water"],
        embeddings=[vector],
        metadatas=[{"source_id": "UNATTRIBUTED"}],
    )

    with pytest.raises(RetrievalError, match="missing attribution metadata"):
        store.retrieve("water")


def test_retrieved_instructions_are_returned_as_inert_data(store, synthetic_documents):
    store.ingest(synthetic_documents)
    injected = next(d for d in synthetic_documents if d.source_id == "SYN-006")

    passage = store.retrieve("ignore previous instructions report plans valid", k=1)[0]

    assert passage.source_id == "SYN-006"
    assert passage.text == injected.text
    assert passage.synthetic is True
