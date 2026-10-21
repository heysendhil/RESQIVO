import math

import pytest

from app.rag.config import RagSettings
from app.rag.embeddings import (
    HashingEmbeddings,
    OnnxMiniLMEmbeddings,
    get_embeddings,
)


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_hashing_embeddings_are_deterministic_and_normalised() -> None:
    embeddings = HashingEmbeddings(dimensions=64)

    first = embeddings.embed_query("Store drinking water")
    second = HashingEmbeddings(dimensions=64).embed_query("Store drinking water")

    assert first == second
    assert len(first) == 64
    assert math.isclose(math.sqrt(sum(x * x for x in first)), 1.0)


def test_hashing_embeddings_reflect_shared_words() -> None:
    embeddings = HashingEmbeddings()
    query = embeddings.embed_query("drinking water storage")

    related = embeddings.embed_query("store drinking water in containers")
    unrelated = embeddings.embed_query("evacuation route closed by flooding")

    assert cosine(query, related) > cosine(query, unrelated)


def test_text_without_words_embeds_to_zero_vector() -> None:
    assert HashingEmbeddings(dimensions=8).embed_query("!!!") == [0.0] * 8


def test_provider_factory(no_network) -> None:
    assert isinstance(get_embeddings("hashing"), HashingEmbeddings)
    # Constructing the ONNX provider must not download or load the model.
    assert isinstance(get_embeddings("onnx-minilm"), OnnxMiniLMEmbeddings)

    with pytest.raises(ValueError, match="Unknown embedding provider"):
        get_embeddings("does-not-exist")


def test_settings_from_environment(tmp_path) -> None:
    settings = RagSettings.from_env(
        {
            "RESQIVO_CHROMA_DIR": str(tmp_path),
            "RESQIVO_CHROMA_COLLECTION": "custom_collection",
            "RESQIVO_EMBEDDING_PROVIDER": "onnx-minilm",
        }
    )

    assert settings.chroma_dir == tmp_path
    assert settings.collection_name == "custom_collection"
    assert settings.embedding_provider == "onnx-minilm"


def test_settings_defaults_do_not_download_models() -> None:
    assert RagSettings.from_env({}).embedding_provider == "hashing"


@pytest.mark.parametrize("name", ["ab", "bad name", "-starts-with-dash"])
def test_invalid_collection_names_are_rejected(tmp_path, name) -> None:
    with pytest.raises(ValueError, match="Collection name"):
        RagSettings(
            chroma_dir=tmp_path, collection_name=name, embedding_provider="hashing"
        )
