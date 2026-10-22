"""Offline tests for the onnx-minilm download guard. No model is downloaded:
ChromaDB's model class is replaced by a stand-in pointed at a temporary cache."""

import chromadb.utils.embedding_functions as chroma_functions
import pytest

from app.qa.errors import QAConfigurationError
from app.qa.service import QuestionAnsweringService
from app.rag.cli import main
from app.rag.config import RagSettings
from app.rag.embeddings import (
    ALLOW_MODEL_DOWNLOAD_ENV,
    ONNX_MODEL_FILES,
    EmbeddingModelUnavailableError,
    OnnxMiniLMEmbeddings,
    get_embeddings,
)
from app.rag.store import KnowledgeStore

pytestmark = pytest.mark.usefixtures("no_network")

VERIFIED_URL = (
    "https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz"
)
VERIFIED_SHA256 = "913d7300ceae3b2dbc2c50d1de4baacab4be7b9380491c27fab7418616a16ec3"


@pytest.fixture
def fake_onnx(tmp_path, monkeypatch):
    """Replace ChromaDB's ONNX model class with a stand-in using a temp cache."""

    class FakeOnnxModel:
        DOWNLOAD_PATH = tmp_path / "cache" / "all-MiniLM-L6-v2"
        EXTRACTED_FOLDER_NAME = "onnx"
        instances = 0

        def __init__(self):
            type(self).instances += 1

        def __call__(self, texts):
            return [[float(len(text) % 7 + 1), 1.0, 0.5, 0.25] for text in texts]

    monkeypatch.setattr(chroma_functions, "ONNXMiniLM_L6_V2", FakeOnnxModel)
    return FakeOnnxModel


def cache_model(fake, names=ONNX_MODEL_FILES):
    folder = fake.DOWNLOAD_PATH / fake.EXTRACTED_FOLDER_NAME
    folder.mkdir(parents=True)
    for name in names:
        (folder / name).write_text("placeholder", encoding="utf-8")


def test_missing_model_is_refused_by_default(fake_onnx):
    embeddings = OnnxMiniLMEmbeddings()

    with pytest.raises(EmbeddingModelUnavailableError) as exc_info:
        embeddings.embed_query("water")

    message = str(exc_info.value)
    assert ALLOW_MODEL_DOWNLOAD_ENV in message
    assert "--allow-model-download" in message
    assert str(fake_onnx.DOWNLOAD_PATH / "onnx") in message
    assert fake_onnx.instances == 0
    assert not fake_onnx.DOWNLOAD_PATH.exists()


def test_partially_cached_model_is_refused(fake_onnx):
    cache_model(fake_onnx, names=["model.onnx"])

    with pytest.raises(EmbeddingModelUnavailableError):
        OnnxMiniLMEmbeddings().embed_documents(["water"])
    assert fake_onnx.instances == 0


def test_cached_model_is_used_without_permission(fake_onnx):
    cache_model(fake_onnx)

    vectors = OnnxMiniLMEmbeddings().embed_documents(["water", "shelter"])

    assert len(vectors) == 2
    assert fake_onnx.instances == 1


def test_explicit_permission_hands_over_to_chromadb(fake_onnx):
    vector = get_embeddings("onnx-minilm", allow_model_download=True).embed_query("x")

    assert len(vector) == 4
    assert fake_onnx.instances == 1


def test_construction_alone_never_checks_or_loads(fake_onnx):
    get_embeddings("onnx-minilm")

    assert fake_onnx.instances == 0


def test_hashing_remains_the_default_and_ignores_the_flag():
    settings = RagSettings.from_env({})

    assert settings.embedding_provider == "hashing"
    assert settings.allow_model_download is False
    assert type(get_embeddings("hashing", allow_model_download=True)).__name__ == (
        "HashingEmbeddings"
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [("", False), ("0", False), ("false", False), ("NO", False), ("1", True),
     ("true", True), ("Yes", True)],
)  # fmt: skip
def test_download_flag_parsing(value, expected):
    settings = RagSettings.from_env({ALLOW_MODEL_DOWNLOAD_ENV: value})

    assert settings.allow_model_download is expected


def test_invalid_download_flag_is_rejected():
    with pytest.raises(ValueError, match=ALLOW_MODEL_DOWNLOAD_ENV):
        RagSettings.from_env({ALLOW_MODEL_DOWNLOAD_ENV: "maybe"})


def test_cli_refuses_download_without_option(fake_onnx, tmp_path, capsys, monkeypatch):
    monkeypatch.delenv(ALLOW_MODEL_DOWNLOAD_ENV, raising=False)
    common = ["--chroma-dir", str(tmp_path / "idx"), "--collection", "onnx_cli"]

    code = main(
        [*common, "--embedding", "onnx-minilm", "build", "--corpus", "synthetic"]
    )

    assert code == 1
    error = capsys.readouterr().err
    assert "not in the local cache" in error
    assert "--allow-model-download" in error
    assert fake_onnx.instances == 0


def test_cli_option_allows_download(fake_onnx, tmp_path, capsys, monkeypatch):
    monkeypatch.delenv(ALLOW_MODEL_DOWNLOAD_ENV, raising=False)
    common = ["--chroma-dir", str(tmp_path / "idx"), "--collection", "onnx_cli"]

    code = main(
        [*common, "--embedding", "onnx-minilm", "--allow-model-download",
         "build", "--corpus", "synthetic"]
    )  # fmt: skip

    assert code == 0
    assert "Indexed 6 document(s)" in capsys.readouterr().out
    assert fake_onnx.instances == 1


def test_environment_setting_allows_download(fake_onnx, tmp_path, monkeypatch):
    monkeypatch.setenv(ALLOW_MODEL_DOWNLOAD_ENV, "true")
    common = ["--chroma-dir", str(tmp_path / "idx"), "--collection", "onnx_env"]

    assert (
        main([*common, "--embedding", "onnx-minilm", "build", "--corpus", "synthetic"])
        == 0
    )
    assert fake_onnx.instances == 1


def test_retrieval_reports_missing_model_instead_of_generic_failure(
    fake_onnx, tmp_path, synthetic_documents
):
    directory = tmp_path / "idx"
    KnowledgeStore(
        OnnxMiniLMEmbeddings(allow_download=True), "onnx_store", directory
    ).ingest(synthetic_documents)
    fresh = KnowledgeStore(OnnxMiniLMEmbeddings(), "onnx_store", directory)
    fake_onnx.DOWNLOAD_PATH = tmp_path / "empty-cache"

    with pytest.raises(EmbeddingModelUnavailableError):
        fresh.retrieve("water")


def test_answer_service_reports_missing_model_as_configuration_error():
    class MissingModelRetriever:
        def retrieve(self, query, k=4):
            raise EmbeddingModelUnavailableError("not cached")

    class UnusedModel:
        def invoke(self, messages):
            raise AssertionError("the model must not be called")

    service = QuestionAnsweringService(MissingModelRetriever(), UnusedModel())

    with pytest.raises(QAConfigurationError):
        service.answer("How is water stored?")


def test_chromadb_still_pins_the_verified_model_source():
    pinned = chroma_functions.ONNXMiniLM_L6_V2

    assert pinned.MODEL_DOWNLOAD_URL == VERIFIED_URL
    assert pinned._MODEL_SHA256 == VERIFIED_SHA256
