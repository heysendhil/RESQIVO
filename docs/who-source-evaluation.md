# RESQIVO — WHO-01 Real-Source Retrieval Evaluation

**Date:** 2026-10-21
**Status: COMPLETED (initial, small dataset).** A first offline retrieval evaluation on WHO-01 ran on 2026-10-21 for both providers, using 28 questions (section 4.1). The index was built in memory only; nothing was persisted, and WHO-01 has not been indexed for `/answer`. The results are indicative only and do not validate retrieval quality in general.

## 1. Source Readiness

| Item | State |
|---|---|
| Source | WHO-01, *Health Emergency and Disaster Risk Management Framework*, World Health Organization, 30 July 2019, ISBN 9789241516181 (`knowledge/seed/sources.json`) |
| Approved for indexing | Yes (`include_in_index: true`, `reuse: open_licence`) |
| Expected source text | `knowledge/local/WHO-01.txt` (repository root) |
| Expected question set | `knowledge/local/WHO-01.eval.json` |
| Source text present | **Yes**, since 2026-10-21. Extracted from the user-supplied official PDF (1,688,353 bytes, the same size as the file verified in Task 4.1) with `pypdf` 6.19.0 in a disposable environment, not a project dependency. Result: 48 pages separated by form-feeds, 15,551 words, SHA-256 `0ad86c42fa481a6036c24ab5a74e68eb6a01536bd6a5f277d515e393e6ab6633`. |
| Question set present | **Yes**, since 2026-10-21: `knowledge/local/WHO-01.eval.json`, 28 questions, version 1 (section 4.1) |
| Source verification on 2026-10-21 | The text contains the document's own title and ISBN line ("Health Emergency and Disaster Risk Management Framework ISBN 978-92-4-151618-1"), "© World Health Organization 2019", the CC BY-NC-SA 3.0 IGO licence statement, and WHO's suggested citation ("Health Emergency and Disaster Risk Management Framework. Geneva: World Health Organization; 2019. Licence: CC BY-NC-SA 3.0 IGO."). SHA-256 unchanged since extraction. All characters printable; UTF-8. |

The WHO-01 text was not reconstructed or written from memory, and no WHO-01 questions or answers were invented. Known extraction characteristics:

- 166 words are broken across lines (for example `emer-` / `gencies`). The text was left unchanged.
- 18 of its 130 chunks exceed the `onnx-minilm` limit of 256 word pieces.
- The document's own licence statement matches the manifest (CC BY-NC-SA 3.0 IGO). Both expected files are ignored by Git (`knowledge/local/`), as are PDFs under `knowledge/` and generated indexes (`data/index/`).

### Preparing the source text (manual step)

1. Download the official PDF yourself from the publication page, https://www.who.int/publications/i/item/9789241516181 (official file URL in the manifest).
2. Extract its text into `knowledge/local/WHO-01.txt` (UTF-8 plain text). No PDF library is part of the verified dependencies, so use a separate tool or copy the text by hand.
3. Keep the text faithful to the PDF. Do not summarise or rewrite it, because the evaluation checks evidence spans against this exact text.

**Page and section metadata are not preserved.** The ingestion pipeline stores plain text, so chunks carry source-level attribution (ID, title, publisher, URL) and a chunk index, but not page or section numbers. The question set can record a page and section for each question (section 3), but retrieved citations cannot. Adding page-aware ingestion would be a separate code change.

## 2. Licence and Attribution

WHO-01 is published under **CC BY-NC-SA 3.0 IGO**, verified on the WHO publication page and WHO's copyright policy (`docs/knowledge-sources.md` section 3). That permits copying, redistribution and adaptation for **non-commercial** purposes without asking WHO's permission, subject to:

- **Attribution:** every citation carries the title, publisher and official URL from the manifest. A UI or report that shows WHO-01 text must name WHO as the source.
- **Share-alike:** adaptations, such as extracted text or excerpts in a question set, must be shared under the same licence if they are distributed.
- **Non-commercial use only.** Commercial use needs WHO's permission.
- **Third-party material inside the document,** such as figures or tables credited to others, is not covered by WHO's licence. It was not checked, because the document has not been processed.

The question set contains short verbatim excerpts. It stays in `knowledge/local/` (ignored by Git) unless a decision is made to publish it with attribution under the same licence.

This is a record of the published terms, not legal advice.

## 3. Evaluation Procedure

### 3.1 Question set format

`knowledge/local/WHO-01.eval.json`, written by a person reading the actual document:

```json
{
  "source_id": "WHO-01",
  "version": 1,
  "prepared_by": "<name>",
  "prepared_on": "YYYY-MM-DD",
  "source_text_sha256": "<SHA-256 of knowledge/local/WHO-01.txt>",
  "questions": [
    {
      "id": "W01",
      "question": "<a planning question in your own words>",
      "evidence": "<3 to 30 words copied exactly from WHO-01.txt that answer it>",
      "page": "<optional printed page number>",
      "section": "<optional section heading>"
    }
  ]
}
```

Rules enforced by the harness, which refuses to run if any is broken:

- `source_id` must be `WHO-01`.
- `source_text_sha256` must match the SHA-256 of the local text file, so the questions are tied to the exact text they were written from. Compute it with `shasum -a 256 knowledge/local/WHO-01.txt`.
- Each `evidence` span must appear **verbatim** in the text (ignoring case and whitespace), so evidence cannot be invented.
- Each `evidence` span must be **3–30 words**. Chunks are 150 words with a 30-word overlap, so a span of 30 words or fewer always lies entirely within at least one chunk.
- Question IDs (`W01`, `W02`, …) must be unique.

Write questions in your own words, not copied from the text. Include some phrased differently from the document, since paraphrase is where the providers differed most (`docs/embedding-evaluation.md`). Twenty or more questions are recommended; fewer give unstable numbers.

### 3.2 Running it

From `backend/` with the project virtual environment active:

```bash
# Baseline (offline)
python ../scripts/evaluate_who_retrieval.py --provider hashing

# Candidate, using the verified isolated model cache (offline; never downloads)
HOME=<isolated home with the cached model> \
  python ../scripts/evaluate_who_retrieval.py --provider onnx-minilm
```

The script:

1. Reports `{"status": "BLOCKED", "missing_files": [...]}` and exits with code 2 if either input file is missing.
2. Validates the question set (section 3.1).
3. Blocks all network connections. The script's `--allow-download` option lifts only this network block. **It does not permit a model download:** the script creates the embedding provider without download permission and does not read `RESQIVO_ALLOW_MODEL_DOWNLOAD`. So `onnx-minilm` needs an already-cached model, and otherwise stops with a configuration error (section 5).
4. Loads WHO-01 through the normal approved-source path (`load_approved_documents`), which attaches the manifest's title, publisher and URL.
5. Builds an **in-memory** index, so nothing is written to disk.
6. Retrieves up to 20 chunks per question.

A retrieved chunk is **relevant** if it contains the question's evidence span.

### 3.3 Results recorded

| Field | Meaning |
|---|---|
| `top1` | Questions whose first retrieved chunk contains the evidence |
| `top3` | Questions with the evidence in the first three chunks |
| `mrr_at_k` | Mean reciprocal rank of the first relevant chunk; 0 when not found in the top `k` |
| `not_found_in_top_k` | Questions with no relevant chunk in the top `k` |
| Per question | Rank, distance of the relevant chunk, distance and ID of the top chunk, page and section |
| Provenance | Provider, run date, SHA-256 of the source text and of the question file, chunking parameters, chunk count |

Every result is marked `"synthetic": false` and `"source_id": "WHO-01"`. Record WHO-01 results in this document's section 4, separately from the synthetic results in `docs/embedding-evaluation.md`.

## 4. Results

### 4.1 WHO-01 (real source)

**Completed 2026-10-21. Real-source results, kept separate from the synthetic results in section 4.2 and in `docs/embedding-evaluation.md`.** Earlier the same day the harness reported BLOCKED: first with both input files missing, then with only the question set missing.

#### Dataset

| Item | Value |
|---|---|
| Question set | `knowledge/local/WHO-01.eval.json`, version 1, 28 questions (`W01`–`W28`), SHA-256 `47dcf63abfa8d0586a9dfb9bc384c4d08a41c6f65232a20930547c915934181d` |
| Source text | `knowledge/local/WHO-01.txt`, SHA-256 `0ad86c42fa481a6036c24ab5a74e68eb6a01536bd6a5f277d515e393e6ab6633`, 130 chunks of 150 words with a 30-word overlap |
| Authorship | Written by Claude (an AI assistant) at the project owner's request. **Not yet reviewed by a domain expert.** |
| Evidence | Each span is 3–30 words, copied verbatim from the text and checked programmatically before the file was written. Each span occurs **exactly once** in the text. |
| Page and section | `null` for every question; none were assigned, to avoid unverified references |
| Question styles | 12 **lexical**, reusing the document's key words: W01, W04, W08, W09, W11, W14, W16, W19, W20, W21, W23, W25. 16 **paraphrase**, written in different words: W02, W03, W05, W06, W07, W10, W12, W13, W15, W17, W18, W22, W24, W26, W27, W28. The style labels are recorded here only; the harness's schema has no field for them. |

**Topic coverage** (sections as headed in the document): the scale and cost of emergencies (W01–W03); risk concepts (W04, W05); guiding principles, namely all-hazards, One Health, ethics, and Build Back Better (W06, W09, W10, W28); community and local response (W07, W20, W26); multisectoral roles (W08); policy (W11); planning and coordination (W12, W13); human and financial resources (W14, W15); information and risk communication (W16, W17); infrastructure and logistics (W18); health services surge (W19); the emergency operations centre (W21); resilient and safe hospitals (W22, W23); roles of the Ministry of Health, the NDMA and WHO (W24, W25, W27). The annexes and reference list are not covered.

**Bias risk:** the questions were written by someone who had read the text, which tends to favour wording that matches it. The paraphrase questions partly offset this, but an independent review by a domain expert is recommended.

#### Metrics

Commands from section 3.2: network blocked, download not allowed, `onnx-minilm` from the verified isolated cache, index in memory, `k` = 20 of 130 chunks.

Each provider was run 4 times. The ranges below cover all runs.

| Provider | Top-1 | Top-3 | MRR@20 | Not in top 20 |
|---|---|---|---|---|
| `hashing` | 10 / 28 | 12 / 28 | 0.427–0.429 | 7–8 |
| `onnx-minilm` | **12 / 28** | **19 / 28** | **0.568** | **2** |

| Provider | Lexical (12): top-1 / top-3 / MRR | Paraphrase (16): top-1 / top-3 / MRR / not found |
|---|---|---|
| `hashing` | 7 / 8 / 0.666 | 3 / 4 / 0.248–0.252 / 7–8 |
| `onnx-minilm` | 6 / 11 / 0.689 | 6 / 8 / 0.477 / 2 |

**Run-to-run variation.** The `onnx-minilm` results were identical in all 4 runs. `hashing` varied slightly:

- W17 was not in the top 20 in run 1 but ranked 20th in runs 2–4;
- W15 ranked 11th in one run and 12th in the others.

Top-1 and top-3 did not change. `hashing` embeddings are deterministic, so the variation comes from ChromaDB's approximate nearest-neighbour search (HNSW), whose index can differ between builds. It affects results near the `k` = 20 boundary. Record several runs when comparing small differences.

#### Rank of the relevant chunk per question

From the first run of each provider. "—" means not in the top 20; see "Run-to-run variation" above for W15 and W17.

| Question | Style | `hashing` | `onnx-minilm` | Question | Style | `hashing` | `onnx-minilm` |
|---|---|---|---|---|---|---|---|
| W01 | L | 1 | 1 | W15 | P | 12 | 1 |
| W02 | P | 1 | 1 | W16 | L | 1 | 2 |
| W03 | P | — | 4 | W17 | P | — | 1 |
| W04 | L | 1 | 1 | W18 | P | — | — |
| W05 | P | 4 | 1 | W19 | L | 1 | 2 |
| W06 | P | — | 3 | W20 | L | 1 | 2 |
| W07 | P | — | 13 | W21 | L | 14 | 1 |
| W08 | L | 1 | 10 | W22 | P | — | 1 |
| W09 | L | 5 | 3 | W23 | L | 7 | 1 |
| W10 | P | 4 | 6 | W24 | P | — | — |
| W11 | L | 13 | 1 | W25 | L | 2 | 3 |
| W12 | P | 1 | 3 | W26 | P | 1 | 1 |
| W13 | P | 20 | 9 | W27 | P | 3 | 6 |
| W14 | L | 1 | 1 | W28 | P | — | 5 |

#### Distances (cosine; lower is closer)

| Provider | Relevant chunk, when found | Nearest chunk per question |
|---|---|---|
| `hashing` | 0.397–0.936 (median 0.714) | 0.397–0.834 (median 0.700) |
| `onnx-minilm` | 0.241–0.563 (median 0.448) | 0.241–0.509 (median 0.417) |

No relevant chunk was farther than 1.0 for either provider.

#### Failures

- **`onnx-minilm` missed two paraphrase questions entirely (not in the top 20):**
  - W18, "How should drugs and equipment be readied before a disaster strikes?" (evidence: stockpiling and prepositioning of medicines and supplies);
  - W24, "Which part of government usually takes charge of epidemic risk measures?" (evidence: the Ministry of Health's leading role for outbreaks).

  It also ranked W07 13th, W08 10th and W13 9th. W08 is a lexical question about early warning of cyclones, a topic mentioned in several chunks, so other chunks outranked the right one.
- **`hashing` found no relevant chunk in the top 20 for 7–8 of the 16 paraphrase questions,** depending on the run.
- **Truncation was ruled out** as a cause. For every question, at least one chunk containing the evidence has it within the first 256 word pieces, so the misses are ranking failures.

### 4.2 Harness check on a synthetic stand-in (not WHO-01)

To confirm the harness works, it was run outside the repository on a **synthetic** stand-in. The stand-in was made from the 16 synthetic evaluation passages, padded with neutral filler text to 1,581 words (13 chunks), with the 26 synthetic questions. **These numbers describe the harness, not WHO-01.**

| Provider | Top-1 | Top-3 | MRR | Not found |
|---|---|---|---|---|
| `hashing` | 13 / 26 | 16 / 26 | 0.599 | 0 |
| `onnx-minilm` | 16 / 26 | 23 / 26 | 0.754 | 0 |

Both runs completed with network access blocked. Three deliberately invalid question sets were all rejected:

- invented evidence: "evidence not found verbatim in source text";
- a wrong hash: "source_text_sha256 does not match the local source text";
- a 31-word evidence span: "must be 3-30 words, got 31".

One observation: `onnx-minilm` scored 22 of 26 top-1 on the single-passage synthetic test, but 16 of 26 here. Here each 150-word chunk mixes several topics, which dilutes the match. Real multi-chunk documents may behave similarly. This is why WHO-01 must be measured rather than inferred from the synthetic results.

## 5. Embedding-Provider Configuration

| Setting | Value |
|---|---|
| Default | `RESQIVO_EMBEDDING_PROVIDER=hashing`, unchanged |
| Candidate | `RESQIVO_EMBEDDING_PROVIDER=onnx-minilm`, opt-in only |
| Model location | ChromaDB reads the model from `$HOME/.cache/chroma/onnx_models/all-MiniLM-L6-v2`. The code has no separate model-path setting; to use the verified isolated cache, set `HOME` for that command only. |
| Download behaviour | **The model must already be cached, or a download must be explicitly allowed.** On first use, `onnx-minilm` checks the cache for the six files ChromaDB requires. If any is missing and downloading is not allowed, it raises `EmbeddingModelUnavailableError` with instructions, before ChromaDB's download code runs (`docs/rag.md` section 5, "Download guard"). |
| Allowing a download | Set `RESQIVO_ALLOW_MODEL_DOWNLOAD=true` (also accepts `1` or `yes`; the default is off, and invalid values are a configuration error), or pass `--allow-model-download` to `python -m app.rag.cli`. ChromaDB then downloads from its pinned source (about 83 MB) and verifies its SHA-256. The CLI option only adds permission; it cannot turn off a download the environment allows. |
| Where a missing model is reported | CLI: printed as `Error: ...`, exit status 1. `/answer`: HTTP 503 "Question answering is not configured." Evaluation scripts: stop with an error (section 3.2). |

To populate an isolated cache deliberately, run a supervised CLI build with download permission, under a dedicated `HOME` and a throwaway collection. **This has not been run since the safeguard was added;** the isolated cache used in this project was populated earlier by the embedding evaluation.

```bash
HOME=<isolated home> RESQIVO_EMBEDDING_PROVIDER=onnx-minilm \
  python -m app.rag.cli --allow-model-download \
    --chroma-dir <temporary directory> --collection model_cache_warmup \
    build --corpus synthetic
```

To index WHO-01 for `/answer`, use a separate collection and the cached model. Do not set the download permission, so a missing model is reported rather than downloaded:

```bash
HOME=<isolated home with the cached model> \
RESQIVO_EMBEDDING_PROVIDER=onnx-minilm \
RESQIVO_CHROMA_COLLECTION=resqivo_who_onnx \
  python -m app.rag.cli build --corpus approved
```

The same `HOME`, provider and collection must be set when querying, because vectors from different providers are not comparable.

## 6. Distance Threshold

`/answer` drops passages whose cosine distance exceeds `RESQIVO_QA_MAX_DISTANCE` (default 1.0) before calling the model.

### 6.1 Synthetic passages

Measured on 2026-10-21 against the 16 synthetic passages, offline:

| Provider | Relevant passages | Closest irrelevant passage | Nearest passage for 6 off-topic questions |
|---|---|---|---|
| `hashing` | 0.333–1.089 (2 of 26 above 1.0) | 0.646–1.000 | 0.798–1.000 (6 of 6 within 1.0) |
| `onnx-minilm` | 0.123–0.807 (0 of 26 above 1.0) | 0.500–0.864 | 0.529–0.928 (6 of 6 within 1.0) |

The off-topic questions were about volcanoes, the capital of France, bread, football, tsunami warnings at sea, and home loans. For `onnx-minilm`, the nearest passage for "What is the capital of France?" was at 0.878.

On this synthetic data:

- **The 1.0 cut-off filtered out nothing for `onnx-minilm`:** every off-topic question still reached the model with passages.
- **No single threshold cleanly separated relevant from irrelevant passages.** Irrelevant passages came as close as 0.500, while relevant ones were as far as 0.807.

### 6.2 WHO-01

Measured on 2026-10-21 against the in-memory WHO-01 index (130 chunks), offline, as a diagnostic. The harness does not do this; nothing was persisted.

The 8 comparison questions are not answered by WHO-01. Six are off-topic: the capital of France, sourdough bread, football, home loans, volcanoes, and smartphones. Two are in-domain but too specific for this document: litres of drinking water per person per day, and the evacuation route for a village.

| Provider | Nearest chunk for the 28 evaluation questions | Nearest chunk for the 8 unanswered questions |
|---|---|---|
| `hashing` | 0.397–0.834 | 0.541–1.000 (**overlaps** the evaluation range) |
| `onnx-minilm` | **0.241–0.509** | **0.613–0.969** |

The closest unanswered question for `onnx-minilm` was "What is the evacuation route for my village?" at 0.613. Relevant chunks for the evaluation questions were at most 0.563 (W08, ranked 10th).

### 6.3 Conclusions

- **The 1.0 default filters nothing for either provider,** on synthetic or WHO-01 data.
- **On WHO-01, `onnx-minilm` showed a gap.** Answered questions had nearest chunks of at most 0.509, and unanswered ones at least 0.613. A cut-off of about 0.55–0.6 would have kept every relevant chunk found here and dropped every unanswered question. **This justifies investigating a provider-specific threshold.** It is not enough evidence to set one: the margin is about 0.05, it rests on 28 + 8 questions, and the synthetic data showed no such separation.
- **No usable threshold appears for `hashing`.**
- **The production cut-off was not changed.** A threshold would apply per provider and per collection, because distances from different providers are not comparable.

Until it is calibrated, `/answer` keeps out ungrounded answers through its later checks:

- the model's `INSUFFICIENT_EVIDENCE` reply;
- the requirement that every answer cites provided passages and only provided passages.

Neither has been exercised against a live model.

**Citation metadata** comes only from retrieved chunks. This is covered by `test_citations_exactly_match_retrieved_metadata` and `test_answers_from_the_chromadb_store_cite_stored_metadata` in `backend/tests/test_qa_service.py`, both passing. **Insufficient-evidence responses** remain explicit, with four documented reasons (`docs/rag.md` section 7.1).

## 7. Remaining Risks

1. **Small, single-author question set.** 28 questions, written by an AI assistant who had read the text and not yet reviewed by a domain expert. The metrics in section 4.1 are indicative only and do not validate retrieval quality in general.
2. **Off-topic questions are not filtered by distance** at the 1.0 default (section 6). Grounding then depends on model behaviour that has not been tested live. A lower `onnx-minilm` threshold looks promising but is unproven (section 6.3).
3. **No cached model on a new machine or CI runner.** `onnx-minilm` there stops with a configuration error until the model is cached or a download is explicitly allowed (section 5). It no longer downloads silently.
4. **No page or section citations,** only document-level attribution.
5. **Extraction artifacts.** 166 words are broken across lines, and headers and tables were not reviewed. These may affect chunking and retrieval.
6. **Truncated chunks.** 18 of 130 WHO-01 chunks exceed the 256-word-piece limit, so `onnx-minilm` ignores the end of those chunks. This did not affect the 28 evaluation questions (section 4.1, "Failures"), but it could affect other questions.
7. **Third-party content** inside WHO-01 has not been reviewed. The document's own third-party-materials clause applies.
8. **Ranking failures on paraphrased questions.** `onnx-minilm` found the relevant chunk outside the top 3 for 8 of 16 paraphrase questions, and not at all for 2. `/answer` retrieves 4 passages by default (`RESQIVO_QA_TOP_K`), so those answers would lack their best evidence.

## 8. Next Action

The source text and the initial question set are done, and the first evaluation has run (section 4.1). Next:

1. **Have a domain expert review `WHO-01.eval.json`,** and add independently written questions, particularly paraphrased ones and questions WHO-01 cannot answer. Rerun section 3.2 for both providers after any change.
2. **Investigate an `onnx-minilm` threshold** around 0.55–0.6 (section 6.3) on the larger question set, together with more unanswerable questions. Change `RESQIVO_QA_MAX_DISTANCE` only if the separation holds.
3. **Then decide on `onnx-minilm`** for WHO-01 indexing in `/answer`. Its retrieval was better than `hashing` here (19 of 28 versus 12 of 28 in the top 3).

The model-download safeguard proposed in an earlier version of this section has been implemented (section 5).
