"""Embedding providers. Providers are injectable; see docs/rag.md for selection."""

import hashlib
import math
import re
from pathlib import Path

from langchain_core.embeddings import Embeddings

_TOKEN = re.compile(r"[a-z0-9]+")


class HashingEmbeddings(Embeddings):
    """Deterministic lexical embeddings for tests and development.

    Each lowercase word token is hashed into a fixed-size vector, which is then
    L2-normalised. Texts that share words are close; there is no semantic
    understanding. Runs offline with no model download.
    """

    def __init__(self, dimensions: int = 256) -> None:
        if dimensions < 8:
            raise ValueError("dimensions must be at least 8.")
        self.dimensions = dimensions

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _TOKEN.findall(text.lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            sign = 1.0 if value & 1 else -1.0
            vector[(value >> 1) % self.dimensions] += sign
        norm = math.sqrt(sum(component * component for component in vector))
        if norm == 0.0:
            return vector
        return [component / norm for component in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


ALLOW_MODEL_DOWNLOAD_ENV = "RESQIVO_ALLOW_MODEL_DOWNLOAD"

# The files ChromaDB checks before deciding to download the model.
ONNX_MODEL_FILES = (
    "config.json",
    "model.onnx",
    "special_tokens_map.json",
    "tokenizer_config.json",
    "tokenizer.json",
    "vocab.txt",
)


class EmbeddingModelUnavailableError(Exception):
    """The embedding model is not cached locally and downloading is not allowed."""


class OnnxMiniLMEmbeddings(Embeddings):
    """ChromaDB's bundled all-MiniLM-L6-v2 (ONNX) model, run locally on CPU.

    Opt-in only. The model must already be in ChromaDB's cache
    (~/.cache/chroma/onnx_models) unless allow_download is true, in which case
    ChromaDB downloads it from its pinned source and verifies its SHA-256.
    Nothing is checked or loaded until the first embedding request. Text is not
    sent to any external service.
    """

    def __init__(self, allow_download: bool = False) -> None:
        self._allow_download = allow_download
        self._function = None

    def _get_function(self):
        if self._function is None:
            from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

            model_dir = (
                Path(ONNXMiniLM_L6_V2.DOWNLOAD_PATH)
                / ONNXMiniLM_L6_V2.EXTRACTED_FOLDER_NAME
            )
            cached = all((model_dir / name).is_file() for name in ONNX_MODEL_FILES)
            if not cached and not self._allow_download:
                raise EmbeddingModelUnavailableError(
                    f"The onnx-minilm model is not in the local cache at {model_dir}. "
                    f"To download it (about 83 MB, SHA-256 verified by ChromaDB), set "
                    f"{ALLOW_MODEL_DOWNLOAD_ENV}=true or pass --allow-model-download "
                    "to the CLI. Alternatively, set HOME to a directory that already "
                    "contains the cached model, or use the hashing provider."
                )
            self._function = ONNXMiniLM_L6_V2()
        return self._function

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, vector)) for vector in self._get_function()(texts)]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


_PROVIDERS = ("hashing", "onnx-minilm")


def get_embeddings(provider: str, allow_model_download: bool = False) -> Embeddings:
    """Return the named provider. allow_model_download applies to onnx-minilm only."""
    if provider == "hashing":
        return HashingEmbeddings()
    if provider == "onnx-minilm":
        return OnnxMiniLMEmbeddings(allow_download=allow_model_download)
    raise ValueError(
        f"Unknown embedding provider {provider!r}. "
        f"Choose one of: {', '.join(_PROVIDERS)}."
    )
