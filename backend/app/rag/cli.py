"""Build and query the local knowledge index. Run from backend/:

    python -m app.rag.cli build --corpus synthetic
    python -m app.rag.cli build --corpus approved   # <ID>.txt or <ID>.pdf
    python -m app.rag.cli sources
    python -m app.rag.cli query "How should water be stored?"

Separate from API startup: app.main does not import this module.
"""

import argparse
import sys
from pathlib import Path

from app.rag.config import (
    DEFAULT_LOCAL_SOURCES_DIR,
    DEFAULT_MANIFEST_PATH,
    DEFAULT_SYNTHETIC_FIXTURES_PATH,
    RagSettings,
)
from app.rag.embeddings import EmbeddingModelUnavailableError, get_embeddings
from app.rag.ingest import load_approved_documents, load_synthetic_documents
from app.rag.manifest import ManifestError, load_manifest
from app.rag.store import IngestionError, KnowledgeStore, RetrievalError


def _store(args: argparse.Namespace) -> KnowledgeStore:
    environment = RagSettings.from_env()
    settings = RagSettings(
        chroma_dir=Path(args.chroma_dir or environment.chroma_dir),
        collection_name=args.collection or environment.collection_name,
        embedding_provider=args.embedding or environment.embedding_provider,
        allow_model_download=(
            args.allow_model_download or environment.allow_model_download
        ),
    )
    return KnowledgeStore(
        embeddings=get_embeddings(
            settings.embedding_provider, settings.allow_model_download
        ),
        collection_name=settings.collection_name,
        persist_directory=settings.chroma_dir,
    )


def _build(args: argparse.Namespace) -> int:
    if args.corpus == "synthetic":
        documents = load_synthetic_documents(Path(args.fixtures))
    else:
        manifest = load_manifest(Path(args.manifest))
        documents = load_approved_documents(manifest, Path(args.local_dir))
    for document in documents:
        if document.page_count is None:
            continue
        missing = document.pages_without_text()
        print(
            f"{document.source_id}: {document.source_file}, text extracted from "
            f"{len(document.pages)} of {document.page_count} page(s)."
        )
        if missing:
            print(
                f"  Warning: no text on page(s) {_page_ranges(missing)} (scanned "
                "images or blank pages; OCR is not supported). Not indexed."
            )
    stored = _store(args).ingest(documents)
    print(f"Indexed {len(documents)} document(s) as {stored} chunk(s).")
    return 0


def _page_ranges(pages: list[int] | tuple[int, ...]) -> str:
    """[1, 2, 3, 7] -> "1-3, 7"."""
    ranges = []
    for page in pages:
        if ranges and page == ranges[-1][1] + 1:
            ranges[-1][1] = page
        else:
            ranges.append([page, page])
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in ranges)


def _sources(args: argparse.Namespace) -> int:
    store = _store(args)
    indexed = store.sources()
    if not indexed:
        print("The collection is empty. Run the build command first.")
        return 0
    for source in indexed:
        label = " [SYNTHETIC]" if source.synthetic else ""
        print(f"{source.source_id}{label}: {source.chunks} chunk(s) - {source.title}")
        if source.source_file:
            print(f"   file: {source.source_file}")
        if source.pages:
            print(f"   pages: {_page_ranges(source.pages)}")
    print(f"Total: {store.count()} chunk(s) in {len(indexed)} source(s).")
    return 0


def _query(args: argparse.Namespace) -> int:
    for rank, passage in enumerate(_store(args).retrieve(args.text, k=args.k), 1):
        label = " [SYNTHETIC - not official guidance]" if passage.synthetic else ""
        print(f"{rank}. {passage.source_id}{label} distance={passage.distance:.3f}")
        print(f"   {passage.title} - {passage.publisher}")
        print(f"   {passage.url}")
        if passage.page is not None:
            print(f"   page {passage.page} of {passage.source_file}")
        print(f"   {passage.text[:300]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.rag.cli")
    parser.add_argument("--chroma-dir", help="Overrides RESQIVO_CHROMA_DIR.")
    parser.add_argument("--collection", help="Overrides RESQIVO_CHROMA_COLLECTION.")
    parser.add_argument("--embedding", help="Overrides RESQIVO_EMBEDDING_PROVIDER.")
    parser.add_argument(
        "--allow-model-download",
        action="store_true",
        help="Allow onnx-minilm to download its model (about 83 MB) if not cached. "
        "Equivalent to RESQIVO_ALLOW_MODEL_DOWNLOAD=true.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="Ingest documents into the index.")
    build.add_argument("--corpus", choices=["synthetic", "approved"], required=True)
    build.add_argument("--fixtures", default=str(DEFAULT_SYNTHETIC_FIXTURES_PATH))
    build.add_argument("--manifest", default=str(DEFAULT_MANIFEST_PATH))
    build.add_argument("--local-dir", default=str(DEFAULT_LOCAL_SOURCES_DIR))
    build.set_defaults(handler=_build)

    sources = commands.add_parser("sources", help="List the indexed sources.")
    sources.set_defaults(handler=_sources)

    query = commands.add_parser("query", help="Retrieve attributed passages.")
    query.add_argument("text")
    query.add_argument("-k", type=int, default=4)
    query.set_defaults(handler=_query)

    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (
        EmbeddingModelUnavailableError,
        ManifestError,
        IngestionError,
        RetrievalError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
