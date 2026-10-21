import pytest

from app.rag.chunking import chunk_document, chunk_text
from app.rag.documents import KnowledgeDocument


def words(n: int) -> str:
    return " ".join(f"w{i}" for i in range(n))


def test_empty_text_has_no_chunks() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n\t ") == []


def test_short_text_is_one_chunk_with_normalised_whitespace() -> None:
    assert chunk_text("Store  water\n\nsafely.") == ["Store water safely."]


def test_long_text_is_split_with_overlap() -> None:
    chunks = chunk_text(words(25), max_words=10, overlap_words=3)

    assert [len(chunk.split()) for chunk in chunks] == [10, 10, 10, 4]
    assert chunks[0].split()[-3:] == chunks[1].split()[:3]
    assert chunks[-1].split()[-1] == "w24"


def test_chunking_is_deterministic() -> None:
    assert chunk_text(words(400)) == chunk_text(words(400))


@pytest.mark.parametrize(("max_words", "overlap"), [(0, 0), (10, 10), (10, -1)])
def test_invalid_chunk_parameters_are_rejected(max_words, overlap) -> None:
    with pytest.raises(ValueError):
        chunk_text("text", max_words=max_words, overlap_words=overlap)


def test_chunk_ids_and_metadata_carry_attribution() -> None:
    document = KnowledgeDocument(
        source_id="SYN-900",
        title="SYNTHETIC: chunk test",
        publisher="RESQIVO synthetic test fixture (not an official source)",
        url="urn:resqivo:synthetic:SYN-900",
        text=words(25),
        synthetic=True,
    )

    chunks = chunk_document(document, max_words=10, overlap_words=0)

    assert [chunk.chunk_id for chunk in chunks] == [
        "SYN-900:0000",
        "SYN-900:0001",
        "SYN-900:0002",
    ]
    assert chunks[1].metadata() == {
        "chunk_id": "SYN-900:0001",
        "chunk_index": 1,
        "source_id": "SYN-900",
        "title": "SYNTHETIC: chunk test",
        "publisher": "RESQIVO synthetic test fixture (not an official source)",
        "url": "urn:resqivo:synthetic:SYN-900",
        "synthetic": True,
    }
