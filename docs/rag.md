# RESQIVO — Retrieval (RAG) Pipeline

Task 4.2. This covers ingestion and retrieval only. LangGraph orchestration, Claude tool calling and RAGAS evaluation are later tasks.

Retrieved passages are **untrusted reference material**. They are advisory, are returned as data, never act as instructions, and never replace the deterministic validator (`understanding.md` section 7.4).

## 1. Components

All code is in `backend/app/rag/`:

| Module | Responsibility |
|---|---|
| `config.py` | Settings from environment variables; default paths |
| `manifest.py` | Validates `knowledge/seed/sources.json`; selects sources with `include_in_index: true` |
| `ingest.py` | Loads approved sources from local text files and synthetic fixtures; nothing is downloaded |
| `chunking.py` | Deterministic word-window chunking (150 words, 30-word overlap) |
| `embeddings.py` | Injectable embedding providers |
| `store.py` | ChromaDB storage and attributed retrieval (`KnowledgeStore`) |
| `cli.py` | Command line for building and querying the index |

The API (`app.main`) does not import any of these, so ingestion never runs at API startup. A test checks this.

## 2. Configuration

| Variable | Default | Purpose |
|---|---|---|
| `RESQIVO_CHROMA_DIR` | `data/index/chroma` (repository root) | Where the ChromaDB index is stored. Ignored by Git. |
| `RESQIVO_CHROMA_COLLECTION` | `resqivo_knowledge` | Collection name |
| `RESQIVO_EMBEDDING_PROVIDER` | `hashing` | `hashing` or `onnx-minilm` (section 5) |

The CLI options `--chroma-dir`, `--collection` and `--embedding` override these. `backend/.env.example` lists them with placeholder values; the application reads them from the environment and does not load `.env` files.

## 3. Building and Querying the Index

Run from `backend/` with the project virtual environment active.

**Synthetic corpus** (for development and demonstrations):

```bash
export RESQIVO_CHROMA_COLLECTION=resqivo_synthetic
python -m app.rag.cli build --corpus synthetic
python -m app.rag.cli query "How much drinking water do shelters need?" -k 2
```

**Approved real sources:**

```bash
export RESQIVO_CHROMA_COLLECTION=resqivo_knowledge
python -m app.rag.cli build --corpus approved
python -m app.rag.cli query "health emergency coordination" -k 3
```

Building the approved corpus reads only sources marked `include_in_index: true` in the manifest; currently that is **WHO-01** only. For each such source, a maintainer must first prepare a plain-text file at `knowledge/local/<SOURCE-ID>.txt` (for example `knowledge/local/WHO-01.txt`) from the official document listed in the manifest. The pipeline never downloads documents, and it reads no file for any other source, even if one is present. `knowledge/local/`, PDFs under `knowledge/`, and `data/index/` are ignored by Git.

There is currently no PDF text extraction: no PDF library is among the verified dependencies, so source text must be prepared outside the pipeline.

Rebuilding a source replaces its earlier chunks. Errors are printed as `Error: ...` with exit status 1.

## 4. Safety Rules Enforced in Code

- **Ingestion eligibility.** A manifest entry with `include_in_index: true` must also have `reuse: open_licence`, a recorded licence, verified access, and an official `source_url`, or the manifest is rejected. Source IDs must use a publisher prefix (`NDMA-`, `WHO-`, `UNDRR-`) and be unique.
- **Synthetic fixtures cannot pass as real sources.** Fixture IDs must use the `SYN-` prefix. Titles must start with `SYNTHETIC`, the publisher must be `RESQIVO synthetic test fixture (not an official source)`, and URLs must be `urn:resqivo:synthetic:` identifiers. The file must declare `"synthetic": true`.
- **No mixing.** A collection holds either synthetic or real documents, never both, so synthetic text cannot be returned as production guidance. Every passage carries a `synthetic` flag, and the CLI labels synthetic results.
- **No fabricated attribution.** If a stored passage lacks any attribution field (source ID, title, publisher, URL, chunk ID, chunk index, synthetic flag), retrieval raises `RetrievalError` instead of returning it.
- **Explicit failures.** An empty collection raises `KnowledgeBaseEmptyError`. Backend failures raise `RetrievalError` without including the query text. Invalid queries (empty, over 1,000 characters, `k` outside 1–20) raise `ValueError`.
- **Offline by default.** ChromaDB telemetry is disabled, and the default embedding provider needs no network.

## 5. Embedding Providers

| Provider | Use | Network | Notes |
|---|---|---|---|
| `hashing` | Tests and development (default) | None | Deterministic lexical hashing; matches shared words, with no semantic understanding |
| `onnx-minilm` | Candidate for real sources (opt-in) | Model download on first use | Not yet approved; not exercised by tests |

### Candidate real model: all-MiniLM-L6-v2 (ONNX)

This is ChromaDB's built-in model, used through `chromadb.utils.embedding_functions.ONNXMiniLM_L6_V2`.

| Aspect | Finding | Source |
|---|---|---|
| Licence | Apache-2.0 | Model card, https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2 (read 2026-10-21) |
| Size | 22.7M parameters; 384-dimensional vectors | Model card |
| Input limit | Text longer than 256 word pieces is truncated; the 150-word chunks are intended to stay near this limit, but this is not verified | Model card; ChromaDB source (`max_length=256`) |
| Download | `https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz`, checked against a fixed SHA-256, cached in `~/.cache/chroma/onnx_models/all-MiniLM-L6-v2` | Installed ChromaDB 1.5.9 source |
| Privacy | Inference runs locally with ONNX Runtime; document and query text is not sent to an external service | ChromaDB source (local ONNX Runtime session) |
| Hardware | CPU inference with ONNX Runtime; no GPU required | ChromaDB source; memory use and speed not measured |
| Deployment | Needs network access once to download the model, or a pre-populated cache; the download URL is a third-party host outside this project's control | ChromaDB source |

**Not verified:** download size, memory use, speed, and retrieval quality on the WHO-01 text. The model has not been downloaded or run in this project. Approving it, or choosing another model, is a separate decision; the index must be rebuilt whenever the provider changes, because vectors from different providers are not comparable.

## 6. Tests

All retrieval tests run offline. The tests that use ChromaDB or the CLI enable a fixture that fails if any network connection is attempted. They use temporary storage and need no API keys.

| File | Covers |
|---|---|
| `tests/test_rag_manifest.py` | Manifest validity, ingestion eligibility, duplicate IDs, required metadata, ID rules |
| `tests/test_rag_chunking.py` | Chunk sizes, overlap, determinism, invalid parameters, chunk IDs and metadata |
| `tests/test_rag_embeddings.py` | Hashing determinism and normalisation, provider factory, settings |
| `tests/test_rag_store.py` | Relevance, attribution, ordering, empty collection, invalid queries, duplicate sources, re-ingestion, no mixing, persistence, backend failure, missing attribution, untrusted text |
| `tests/test_rag_ingest.py` | Approved-source selection, missing or empty local text, fixture labelling, CLI build and query, API startup separation |

```bash
cd backend
source ../.venv/bin/activate
python -m pytest -q tests/test_rag_*.py   # retrieval tests only
python -m pytest -q                       # full suite
```
