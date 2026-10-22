# RESQIVO — Embedding Model Evaluation: all-MiniLM-L6-v2

**Date:** 2026-10-21
**Candidate:** `all-MiniLM-L6-v2`, ONNX export bundled with ChromaDB, used through the existing `onnx-minilm` provider (`backend/app/rag/embeddings.py`)
**Baseline:** the existing `hashing` provider
**Scope:** report only. No production code, default, or dependency was changed. No real document was indexed. No Claude or other paid API was called.

## 1. Summary

| Question | Answer |
|---|---|
| Licence | **Apache-2.0** for the model and for Chroma's ONNX conversion code |
| Download | **83,178,821 bytes** (79.3 MiB), one archive from Chroma's S3 bucket, verified against a SHA-256 pinned in ChromaDB 1.5.9 |
| New dependencies | **None.** `onnxruntime` 1.30.0, `tokenizers` 0.23.2 and `numpy` 2.5.3 are already installed. |
| Runs offline after download | **Yes**, verified with network access blocked |
| Deterministic | **Yes**, two runs gave identical rankings and distances |
| Retrieval vs hashing | Correct passage ranked first for **22 of 26** questions vs **12 of 26**; on paraphrased questions **10 of 14** vs **2 of 14** |
| Memory | Peak resident memory **503 MB** vs **134 MB** for hashing, in the same evaluation process |
| Recommendation | **Approve for opt-in use** to index and evaluate WHO-01. Keep `hashing` as the default until retrieval is checked on WHO-01 questions (section 7). |

## 2. Model and Licence Evidence

| Item | Finding | Evidence |
|---|---|---|
| Source model | `sentence-transformers/all-MiniLM-L6-v2` | Model card, https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2 (read 2026-10-21) |
| Model licence | Apache-2.0 | Model card licence label "apache-2.0" |
| Output | 384-dimensional vectors | Model card ("maps sentences & paragraphs to a 384 dimensional dense vector space") |
| Size | 22.7M parameters | Model card |
| Input limit | Input longer than 256 word pieces is truncated | Model card; ChromaDB sets `enable_truncation(max_length=256)` |
| Intended use | Sentence and short-paragraph embeddings for retrieval, clustering and similarity | Model card |
| ONNX conversion | Chroma's `chroma-core/onnx-embedding` repository converts the model and includes `compare_onnx.py`, which compares ONNX output with sentence-transformers output on STS-B | https://github.com/chroma-core/onnx-embedding (Apache-2.0, read 2026-10-21) |
| Download source | `https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz`; HTTP HEAD: 200, 83,178,821 bytes, last modified 30 March 2023 | Installed ChromaDB 1.5.9 source; HEAD request on 2026-10-21 |
| Integrity | Downloaded archive SHA-256 `913d7300ceae3b2dbc2c50d1de4baacab4be7b9380491c27fab7418616a16ec3`, identical to the value pinned in ChromaDB 1.5.9 (`_MODEL_SHA256`) | `shasum -a 256` on the downloaded archive |

**Not verified:** that the ONNX export produces the same embeddings as the original sentence-transformers model. Chroma provides a comparison script, but it was not run, because it would need PyTorch and sentence-transformers, which are not project dependencies.

## 3. Installation and Runtime

- **Environment:** macOS (Apple Silicon), Python 3.14.6, the project `.venv` with the existing verified dependencies. Nothing was installed.
- **Dependencies used:** `onnxruntime` 1.30.0, `tokenizers` 0.23.2, `numpy` 2.5.3, `httpx` 0.28.1 (download only). All were already present, pulled in by `chromadb` 1.5.9.
- **Isolated cache:** the model was downloaded with `HOME` set to a temporary directory, so it went to `<temporary HOME>/.cache/chroma/onnx_models/all-MiniLM-L6-v2`. The user's own `~/.cache/chroma` was not modified. That directory already existed, dated 11 September 2026, and contains an `onnx_models` folder that was not inspected.
- **First run:** downloaded 79.3 MiB in about 14 seconds (17 seconds wall time including evaluation).
- **Disk use after download:** 167 MB. The 83 MB archive is kept alongside the extracted files: `model.onnx` 90,387,606 bytes, `tokenizer.json` 711,661 bytes, `vocab.txt` 231,508 bytes, and small configuration files.
- **Offline:** a second run with all network connections blocked completed normally.
- **CPU only:** ONNX Runtime ran on CPU; no GPU was used or needed.
- **Not tested:** Linux, including the CI runner, and Python versions other than 3.14.6.

## 4. Evaluation Method

### 4.1 Corpus

`data/synthetic/embedding_eval.json`, version 1, synthetic and labelled as such:

- **16 passages** (`SYN-E01` to `SYN-E16`) on shelter water, capacity, route closures, coordination, first-aid kits, sanitation, rations, vulnerable residents, warnings, generators, volunteers, rescue, disease surveillance, heat, public information and family reunification.
- **26 questions**, each with exactly one relevant passage:
  - **12 lexical questions** (`L01`–`L12`) share key words with their passage.
  - **14 paraphrase questions** (`P01`–`P14`) avoid them. After removing common stop words, 13 of the 14 share no word with their passage, and `P01` shares one ("keep"). The script reports these overlaps for every question.

All passages and questions were written for this evaluation. They are not drawn from official guidance.

### 4.2 Procedure

`scripts/evaluate_embeddings.py` ingests the 16 passages into an in-memory collection through the production `KnowledgeStore`. It then retrieves all 16 passages for each question, ranked by cosine distance, and records:

- the rank of the relevant passage;
- its distance;
- the margin, meaning the closest irrelevant passage's distance minus the relevant passage's distance (positive means the relevant passage ranked above every irrelevant one).

Metrics:

- **Top-1:** questions whose relevant passage ranks above all irrelevant passages.
- **Recall@3:** questions whose relevant passage is in the top three.
- **MRR:** mean reciprocal rank, the average of 1 ÷ rank.

Timing and peak resident memory are measured in the same process.

## 5. Results

### 5.1 Retrieval quality

| Questions | Metric | `hashing` | `onnx-minilm` |
|---|---|---|---|
| All 26 | Top-1 | 12 | **22** |
| | Recall@3 | 16 | **25** |
| | MRR | 0.576 | **0.901** |
| | Mean rank (of 16) | 4.62 | **1.31** |
| Lexical (12) | Top-1 | 10 | **12** |
| | MRR | 0.896 | **1.000** |
| Paraphrase (14) | Top-1 | 2 | **10** |
| | Recall@3 | 5 | **13** |
| | MRR | 0.302 | **0.815** |

**Distances of the relevant passages:**
- **Hashing:** 0.333 to 1.089 (median 0.871). **Two relevant passages lie beyond 1.0**, so `/answer`'s default `RESQIVO_QA_MAX_DISTANCE` would discard them.
- **ONNX MiniLM:** 0.123 to 0.807 (median 0.459). **None lies beyond 1.0.**

### 5.2 Per-question ranks

| Question | Hashing | ONNX | Question | Hashing | ONNX |
|---|---|---|---|---|---|
| L01 | 1 | 1 | P01 | 2 | 1 |
| L02 | 1 | 1 | P02 | 14 | 1 |
| L03 | 1 | 1 | P03 | 3 | 1 |
| L04 | 1 | 1 | P04 | 9 | **3** |
| L05 | 1 | 1 | P05 | 7 | **2** |
| L06 | 4 | 1 | P06 | 1 | **3** |
| L07 | 2 | 1 | P07 | 9 | 1 |
| L08 | 1 | 1 | P08 | 10 | 1 |
| L09 | 1 | 1 | P09 | 10 | 1 |
| L10 | 1 | 1 | P10 | 10 | 1 |
| L11 | 1 | 1 | P11 | 13 | 1 |
| L12 | 1 | 1 | P12 | 13 | 1 |
| | | | P13 | 1 | **4** |
| | | | P14 | 2 | 1 |

**ONNX misses** (relevant passage not first):
- **P04** ("How do team heads stay in sync about gaps?") ranked the volunteer passage first.
- **P05** (bandage and medicine stock) ranked the sanitation passage first.
- **P06** (illness from toilets) ranked the disease-surveillance passage first.
- **P13** (where to pick up aid) ranked the first-aid kit passage first.

Several of these are near-misses on related topics, with margins between −0.03 and −0.10.

Hashing's two paraphrase successes (P06, P13) come from **stop words**. Hashing does not remove common words such as "how", "do", "where" and "to", so they still count as matches.

### 5.3 Speed and memory

| | `hashing` | `onnx-minilm` |
|---|---|---|
| Ingest 16 passages | 0.04–0.10 s | 0.28–0.32 s |
| 26 queries | 0.013 s | 0.26–0.27 s |
| Peak resident memory (whole process, including ChromaDB) | 134 MB | 503 MB |

The ONNX timings exclude the first-run download. Memory is the peak for the whole evaluation process, so the model's own share is roughly the difference, about 370 MB. That figure was not measured in isolation.

### 5.4 Chunk length

ChromaDB truncates input at 256 word pieces. With truncation switched off, the bundled tokenizer turned 150 words of the evaluation text into **179 word pieces** (100 words → 128; 200 words → 239). RESQIVO's 150-word chunks are therefore within the limit **for text like this corpus**. Technical documents may need more word pieces per word, so this must be re-checked on WHO-01.

The bundled `tokenizer.json` also contains its own 128-token truncation setting. ChromaDB overrides it with 256 at runtime, so it does not affect RESQIVO; it only matters when the tokenizer is used directly.

## 6. Limitations

- **Small, self-written corpus.** 16 passages and 26 questions, written by the same author, cannot show real-world retrieval quality. Differences of one or two questions are not meaningful.
- **English only.** Both the corpus and the model are English. Hindi or other-language guidance was not tested.
- **No real documents.** WHO-01 was not indexed, as required. Retrieval on long, technical, multi-chunk documents is unmeasured.
- **ONNX fidelity unverified** against the original model (section 2).
- **One platform.** macOS arm64 only; Linux and CI untested.
- **Memory measured per process,** not per model.
- **Distance threshold:** the 1.0 default suits this corpus for both providers, but no calibration was done beyond these 26 questions.

## 7. Recommendation

**Approve `onnx-minilm` for opt-in use, conditionally.** It is the next step for indexing and evaluating WHO-01, set explicitly with `RESQIVO_EMBEDDING_PROVIDER=onnx-minilm`.

- **Do not change the default yet.** `hashing` stays the default and stays in place for offline tests and CI.

Reasons:

- **Licensing:** Apache-2.0 for both the model and the conversion code.
- **Integrity:** the download is pinned and verified by SHA-256.
- **No new dependencies.**
- **Privacy:** inference runs locally, so no document or query text leaves the machine.
- **Retrieval:** on this synthetic set it clearly beats `hashing`, most of all on paraphrased questions, which matter for real users.

Before making it the default:

1. Index WHO-01 with it, and check retrieval on a set of WHO-01 questions with known answer passages.
2. Re-check chunk word-piece counts on WHO-01 text against the 256 limit.
3. Confirm installation and the model download on Linux (the CI runner and any deployment host). Pre-populate or cache the model there, since the download host is outside the project's control.
4. Confirm that about 500 MB of process memory is acceptable on the deployment host.
5. Rebuild every index after switching providers, because vectors from different providers are not comparable.

## 8. Reproducing the Evaluation

Run all commands from `backend/` with the project virtual environment active.

**History.** The results in sections 3–5 were produced before the model-download safeguard was added (`docs/rag.md` section 5, "Download guard"). At that time, the script's first `onnx-minilm` run downloaded the model itself. **That no longer happens:** the steps below are the current procedure.

### 8.1 Baseline (offline)

```bash
python ../scripts/evaluate_embeddings.py --provider hashing
```

### 8.2 What the script's `--allow-download` does

`evaluate_embeddings.py` blocks all network connections by default. Its `--allow-download` option **only removes that network block for the script**. It does **not** authorise ChromaDB to download the model:

- the script creates the `onnx-minilm` provider without download permission;
- it does not read `RESQIVO_ALLOW_MODEL_DOWNLOAD`.

With an uncached model, the script stops with `EmbeddingModelUnavailableError`, exit status 1, whether or not `--allow-download` is given. Python prints this as a traceback, because the script does not catch the error. This was verified on 2026-10-21 with an empty `HOME` and the network blocked: no files were created.

### 8.3 Populating an isolated model cache (operator-authorised download)

> **This step downloads the model,** about 83 MB, from ChromaDB's pinned source (`https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz`). ChromaDB checks the archive against its pinned SHA-256. Run it only when the operator has explicitly decided to authorise the download.

Use the RESQIVO CLI with `--allow-model-download`, a dedicated `HOME` for the cache, and a throwaway index directory and collection. This is the command documented in `docs/who-source-evaluation.md` section 5:

```bash
export EVAL_HOME=$(mktemp -d)       # isolated cache; your real ~/.cache is not touched
export WARMUP_INDEX=$(mktemp -d)    # throwaway index, not used afterwards

HOME=$EVAL_HOME RESQIVO_EMBEDDING_PROVIDER=onnx-minilm \
  python -m app.rag.cli --allow-model-download \
    --chroma-dir $WARMUP_INDEX --collection model_cache_warmup \
    build --corpus synthetic
```

- **Where the model ends up:** in `$EVAL_HOME/.cache/chroma/onnx_models/all-MiniLM-L6-v2`. The command also indexes the six synthetic fixtures into the throwaway directory, which can then be deleted.
- **Not yet run with the safeguard in place.** The command's arguments have been checked, and the download hand-off is covered by offline tests. The cache used for the results above was populated by the earlier script behaviour described under "History".

### 8.4 Rerunning the evaluation with a cached model (offline)

Leave out `--allow-download`, so the script keeps all network connections blocked:

```bash
HOME=$EVAL_HOME python ../scripts/evaluate_embeddings.py --provider onnx-minilm
```

Each run prints JSON with the summary metrics and per-question ranks, distances, margins and shared words. If the cache under `$EVAL_HOME` is missing or incomplete, the run stops with `EmbeddingModelUnavailableError` (section 8.2); it never downloads.
