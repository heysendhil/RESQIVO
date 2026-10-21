import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_MANIFEST_PATH = REPO_ROOT / "knowledge" / "seed" / "sources.json"
DEFAULT_LOCAL_SOURCES_DIR = REPO_ROOT / "knowledge" / "local"
DEFAULT_SYNTHETIC_FIXTURES_PATH = (
    REPO_ROOT / "data" / "synthetic" / "knowledge_passages.json"
)
DEFAULT_CHROMA_DIR = REPO_ROOT / "data" / "index" / "chroma"
DEFAULT_COLLECTION_NAME = "resqivo_knowledge"
DEFAULT_EMBEDDING_PROVIDER = "hashing"

# ChromaDB collection names: 3-512 characters, starting and ending with a
# letter or digit, containing only letters, digits, ".", "_" and "-".
_COLLECTION_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,510}[A-Za-z0-9]$")


@dataclass(frozen=True)
class RagSettings:
    """Retrieval settings, read from environment variables."""

    chroma_dir: Path
    collection_name: str
    embedding_provider: str

    def __post_init__(self) -> None:
        if not _COLLECTION_NAME.match(self.collection_name):
            raise ValueError(
                "Collection name must be 3-512 characters of letters, digits, "
                "'.', '_' or '-', starting and ending with a letter or digit."
            )

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> RagSettings:
        return cls(
            chroma_dir=Path(environ.get("RESQIVO_CHROMA_DIR") or DEFAULT_CHROMA_DIR),
            collection_name=(
                environ.get("RESQIVO_CHROMA_COLLECTION") or DEFAULT_COLLECTION_NAME
            ),
            embedding_provider=(
                environ.get("RESQIVO_EMBEDDING_PROVIDER") or DEFAULT_EMBEDDING_PROVIDER
            ),
        )
