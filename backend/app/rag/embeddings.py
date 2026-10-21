"""Embedding providers. Providers are injectable; see docs/rag.md for selection."""

import hashlib
import math
import re

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


class OnnxMiniLMEmbeddings(Embeddings):
    """ChromaDB's bundled all-MiniLM-L6-v2 (ONNX) model, run locally on CPU.

    Opt-in only. On first use ChromaDB downloads the model archive (verified by
    SHA-256) into ~/.cache/chroma/onnx_models; text is not sent to any external
    service. Never used by the automated tests.
    """

    def __init__(self) -> None:
        self._function = None

    def _get_function(self):
        if self._function is None:
            from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

            self._function = ONNXMiniLM_L6_V2()
        return self._function

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, vector)) for vector in self._get_function()(texts)]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


_PROVIDERS = {
    "hashing": HashingEmbeddings,
    "onnx-minilm": OnnxMiniLMEmbeddings,
}


def get_embeddings(provider: str) -> Embeddings:
    try:
        factory = _PROVIDERS[provider]
    except KeyError:
        raise ValueError(
            f"Unknown embedding provider {provider!r}. "
            f"Choose one of: {', '.join(sorted(_PROVIDERS))}."
        ) from None
    return factory()
