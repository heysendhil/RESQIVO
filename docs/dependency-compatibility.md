# RESQIVO — Dependency Compatibility Report (Task 4.0)

**Date:** 2026-10-21
> **Update 2026-10-23:** the model provider changed from Anthropic Claude to Google Gemini. `langchain-anthropic` and `anthropic` were removed and replaced by `langchain-google-genai` 4.4.0 and `google-genai` 2.29.0. See `docs/model-provider.md` for the versions, their release dates and the offline checks. The Claude findings below are kept as the Task 4.0 record.

**Status:** Complete. No application code, requirements file, lockfile, or test was changed. All installs were made in disposable virtual environments outside the repository. No paid API was called and no API key was used.

## 1. Summary

| Area | Verdict |
|---|---|
| A. Python 3.14 support for LangChain, LangGraph, `langchain-anthropic`, ChromaDB, LangSmith | **Compatible.** Installed, imported, and exercised offline on Python 3.14.6. |
| B. RAGAS | **Compatible, with one required pin** (`langchain-community==0.4.1`). `scikit-network` built from source on macOS; the Linux build is **UNVERIFIED**. |
| C. Injectable embeddings in ChromaDB | **Compatible.** Verified offline with a deterministic fake embedding; no model download. |
| D. Claude tool-calling workflow | **Compatible offline.** Request payloads and a LangGraph tool-calling workflow verified with a fake model. Live acceptance by the Claude API is **UNVERIFIED**. |
| E. LangSmith disabled by default | **Verified.** Tracing is off unless `LANGSMITH_TRACING=true`. |
| F. Dependency organisation | **Separate requirements files recommended:** runtime, development, and evaluation. |
| G. Conflicts with existing constraints | **None found.** `pip check` is clean and all 64 existing backend tests pass with the AI stack and RAGAS installed. |

**RAGAS decision: compatible** on Python 3.14 (macOS arm64), provided `langchain-community` is pinned to `0.4.1`. Live metric scoring was not run.

## 2. Test Environment

| Item | Value |
|---|---|
| OS | macOS (Darwin 25.6.0), Apple Silicon (arm64) |
| Python | 3.14.6 (python.org framework build), the same interpreter as the project `.venv` |
| pip | 26.1.2 |
| C compiler (for source builds) | Apple clang 21.0.0 (Command Line Tools) |
| Network during functional checks | Blocked (sockets patched to raise on connect) |
| API keys | None set; `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` and LangSmith variables explicitly unset |

**Not tested:** Linux, including the `ubuntu-latest` CI runner; Python 3.13 (not installed on this machine).

### Version selection rule

New packages were resolved with `pip install --uploaded-prior-to 2026-10-07T00:00:00Z`, meaning only releases at least two weeks old (per `plan.md` Task 4.0).

The project's existing pins could not satisfy that rule. FastAPI 0.143.0 (uploaded 2026-10-08), Pydantic 2.14.1 (2026-10-11) and Ruff 0.17.1 (2026-10-15) are newer than the cutoff, so a single cutoff install failed (`No matching distribution found for fastapi<0.144,>=0.143.0`). The check therefore installed the project's exact current versions first, then added the AI packages under the cutoff, with the existing versions held as constraints. This tests the combination the project would actually use.

## 3. Verified Versions

### 3.1 Runtime environment: existing project versions plus AI stack

`pip check`: **No broken requirements found.**

| Package | Version | Role |
|---|---|---|
| fastapi | 0.143.0 | Existing (held) |
| starlette | 1.7.0 | Existing (held) |
| pydantic | 2.14.1 | Existing (held) |
| uvicorn | 0.54.0 | Existing (held) |
| httpx2 | 2.13.1 | Existing (held) |
| langchain-core | 1.6.7 | LLM and tool integration |
| langgraph | 1.2.14 | Workflow orchestration |
| langgraph-checkpoint | 4.2.0 | LangGraph dependency |
| langgraph-prebuilt | 1.1.0 | Provides `ToolNode` |
| langchain-anthropic | 1.7.5 | Claude integration |
| anthropic | 1.11.0 | Pulled in by `langchain-anthropic` |
| langchain-chroma | 1.1.0 | ChromaDB vector store integration |
| chromadb | 1.5.9 | Vector store |
| langsmith | 0.14.4 | Tracing |
| langchain | 1.4.3 | Installed for the check; **not required** by any check below |
| onnxruntime | 1.30.0 | ChromaDB dependency |
| numpy | 2.5.3 | ChromaDB dependency |
| grpcio | 1.84.0 | ChromaDB dependency |
| httpx | 0.28.1 | Reinstalled by ChromaDB (see section 5) |

### 3.2 Evaluation additions

Installed on top of the runtime environment. `pip check` is clean, and the existing tests still pass.

| Package | Version | Note |
|---|---|---|
| ragas | 0.4.3 | Latest release (2026-01-13) |
| langchain-community | 0.4.1 | **Must be pinned**; see section 5 |
| scikit-network | 0.33.5 | No published Python 3.14 wheel; built from source |
| scipy | 1.18.1 | |
| datasets | 5.1.0 | |
| openai | 1.109.1 | Hard dependency of RAGAS, even when Claude is the judge |
| langchain-openai | 1.1.9 | Hard dependency of RAGAS |
| instructor | 1.3.2 | Hard dependency of RAGAS; older than the latest 1.17.0 (see section 5) |
| tiktoken | 0.14.0 | |

## 4. Findings and Evidence

### A. Python 3.14 compatibility — Compatible

- Every runtime package imported successfully on Python 3.14.6: `langchain_core`, `langgraph.graph`, `langgraph.prebuilt`, `langchain_anthropic`, `langchain_chroma`, `chromadb`, `langsmith`, `anthropic`.
- PyPI metadata (checked 2026-10-21) shows Python 3.14 (`cp314` or `abi3`) wheels for macOS arm64 and Linux x86-64 for every native dependency checked: `chromadb`, `onnxruntime`, `numpy`, `tokenizers`, `grpcio`, `orjson`, `mmh3`, `bcrypt`, `pybase64`, `pillow`, `tiktoken`, `pyarrow`. The LangChain packages, LangGraph, LangSmith and `anthropic` are pure Python.
- **Non-blocking warning:** `langsmith` (`_internal/_beta_decorator.py:70`) and `chromadb` (`telemetry/opentelemetry/__init__.py:128`) call `asyncio.iscoroutinefunction`. This raises a `DeprecationWarning` on Python 3.14, and the function is scheduled for removal in Python 3.16.

### B. RAGAS — Compatible, with a pin

- **`scikit-network`** publishes wheels only for CPython 3.10–3.13 (version 0.33.5, uploaded 2025-11-19). On Python 3.14, pip downloaded the source distribution and built `scikit_network-0.33.5-cp314-cp314-macosx_10_15_universal2.whl` with Apple clang. The whole RAGAS install took about 77 seconds. **Building on Linux is UNVERIFIED**; it needs a C compiler.
- **Import failure without a pin:** with the default resolution (`langchain-community` 0.4.2), `import ragas` fails with `ModuleNotFoundError: No module named 'langchain_community.chat_models.vertexai'`. RAGAS 0.4.3 imports that module (`ragas/llms/base.py:12`) and declares `langchain-community` with no upper bound.
- **Which versions have the module:** inspecting the published wheels shows `chat_models/vertexai.py` is present in `langchain-community` 0.3.26–0.3.31 and 0.4.1, and absent in 0.4.2 (uploaded 2026-05-22). Version 0.4.1 accepts `langchain-core>=1.0.1,<2.0.0`, so it is compatible with `langchain-core` 1.6.7.
- **With `langchain-community==0.4.1`:**
  - `import ragas` succeeds.
  - `EvaluationDataset` and `SingleTurnSample` build correctly.
  - `Faithfulness`, `ResponseRelevancy`, `ContextPrecision` and `ContextRecall` construct.
  - `LangchainLLMWrapper(ChatAnthropic(...))` and `LangchainEmbeddingsWrapper(DeterministicFakeEmbedding(...))` construct.
  - All of this ran offline with no API keys.
- **Deprecations:**
  - Importing these metrics from `ragas.metrics` is deprecated.
  - `LangchainLLMWrapper` and `LangchainEmbeddingsWrapper` are deprecated in favour of `llm_factory` and `embedding_factory`.
  - `llm_factory` accepts `provider="anthropic"` (it uses `instructor.from_anthropic`).
- **Not run:** actual metric scoring, which requires LLM calls.

### C. Injectable embeddings — Compatible

- `langchain_chroma.Chroma(client=chromadb.EphemeralClient(...), embedding_function=DeterministicFakeEmbedding(size=64))` stored two documents with metadata and returned the expected document for an exact-text query.
- Repeated queries returned identical results.
- Sockets were blocked for the whole run, and ChromaDB's default ONNX model cache (`~/.cache/chroma/onnx_models`, under a fresh empty `HOME`) did not exist before or after. **No model was downloaded.**
- Conclusion: automated tests can run fully offline if the application always passes an explicit embedding function and never relies on ChromaDB's default.

### D. Claude tool-calling workflow — Compatible offline

**Request payloads.** These were built with `ChatAnthropic._get_request_payload` for `model="claude-opus-5-5"` and a dummy key; nothing was sent.

| Call | Payload |
|---|---|
| `bind_tools([search_guidance])` | Tool included; no `tool_choice`, so the API default applies |
| `bind_tools(..., tool_choice="auto")` | `tool_choice: {"type": "auto"}` |
| `with_structured_output(Schema)` (default `method="function_calling"`) | Tool included, **not forced** for this model. The library warns: *"forced tool calling ... is not supported when `thinking` is enabled or on claude-opus-5-5 ... may raise an OutputParserException ... Consider `method='json_schema'`"* |
| `with_structured_output(Schema, method="json_schema")` | No tools; `output_config.format` with a strict JSON schema (`additionalProperties: false`, `required`) |

`temperature` is omitted unless it is set explicitly.

**Workflow mechanics.** A LangGraph `StateGraph` was built using `FakeMessagesListChatModel` (from `langchain_core`), a `ToolNode` from `langgraph.prebuilt`, and the project's real `validate_plan`, imported read-only.

1. The fake model emitted a `search_guidance` tool call; `ToolNode` executed it and returned a `ToolMessage`.
2. The model proposed a plan allocating 1,100 litres against 1,000 available and claimed it was valid. The mandatory validation node, which is application code, returned `valid: False` with `DOM-04`. After one correction the next plan validated.
3. A model that kept proposing the same invalid plan stopped after exactly `MAX_CORRECTIONS = 2` attempts, with final validation `valid: False, codes: ['DOM-04']`. The model's own validity claim was ignored.

All of this ran with the network blocked.

**UNVERIFIED:** whether the live Claude API accepts these payloads and produces tool calls as expected. That requires an API key and was out of scope.

### E. LangSmith disabled by default — Verified

- No LangSmith or LangChain environment variables were set in the test shell.
- `langsmith.utils.tracing_is_enabled()` returned `False` by default and with `LANGSMITH_TRACING=false`, and `True` with `LANGSMITH_TRACING=true`.
- The LangGraph workflow in D ran with sockets blocked and tracing at its default, and made no network attempt.
- Conclusion: leaving `LANGSMITH_TRACING` unset (or `false`) keeps tracing off. CI should not set it.

### F. Dependency organisation — Separate requirements files

The project already uses `requirements.txt` (runtime) and `requirements-dev.txt` (`-r requirements.txt` plus tools). Continue that convention:

| File | Contents |
|---|---|
| `requirements.txt` | Runtime: existing packages plus the AI runtime stack |
| `requirements-dev.txt` | `-r requirements.txt` plus pytest, `httpx2`, Ruff (unchanged) |
| `requirements-eval.txt` (new) | `-r requirements.txt` plus RAGAS and the `langchain-community` pin |

Keep RAGAS out of the runtime and CI installs. It adds `openai`, `langchain-openai`, `instructor`, `datasets`, `scipy`, and a source build of `scikit-network`, none of which the application needs. No other packaging tool is needed.

### G. Conflicts with existing constraints — None found

- `pip check` was clean in both environments.
- The existing backend suite (`python -m pytest -q`) passed **64 of 64** in the runtime environment, and again with RAGAS added. It ran with `-p no:cacheprovider` and `PYTHONDONTWRITEBYTECODE=1`, so nothing was written to the repository.
- The AI packages accepted the held versions of FastAPI 0.143.0, Starlette 1.7.0, Pydantic 2.14.1, Uvicorn 0.54.0 and `httpx2` 2.13.1.

## 5. Problems and Unresolved Questions

1. **The `langchain-community` pin is required for RAGAS.** Version 0.4.2 breaks `import ragas`. Pin `==0.4.1` in `requirements-eval.txt` until RAGAS releases a fix.
2. **The `scikit-network` Linux build is UNVERIFIED.** It built on macOS with clang. A Linux evaluation environment, including any future evaluation CI job, needs a C compiler and should be tested.
3. **Live Claude behaviour is UNVERIFIED.** Payloads look correct, but no request was sent. Confirm with one manual call when an API key is available, and prefer `method="json_schema"` for structured output.
4. **`instructor` resolved to 1.3.2**, not the latest 1.17.0. A dry run shows 1.17.0 would pull in `openai` 3.3.0, which `langchain-openai` 1.1.9 does not accept. RAGAS's `llm_factory(provider="anthropic")` path through `instructor` 1.3.2 with current Claude models is **UNVERIFIED**. The deprecated `LangchainLLMWrapper` path constructs correctly but was not run live.
5. **`httpx` returns as a dependency of ChromaDB.** This is harmless: Starlette's test client still prefers `httpx2`, and the existing tests showed no `httpx` deprecation warning. But `httpx` is back in the environment.
6. **`websockets` resolved to 16.1.1** in the cutoff install (the project `.venv` has 17.2), because it was not held as a constraint. `uvicorn[standard]` accepts both.
7. **Python 3.16 deprecations.** LangSmith and ChromaDB use `asyncio.iscoroutinefunction`. This is not blocking on 3.14; recheck before any move to 3.16.
8. **The two-week rule versus existing pins.** The current FastAPI, Pydantic and Ruff pins are newer than two weeks, but were already in use and tested. Apply the two-week rule to newly added packages.
9. **CI install time with ChromaDB is not measured.** ChromaDB brings `onnxruntime`, `grpcio`, `kubernetes` and the OpenTelemetry SDK. Its effect on the backend CI job duration on Linux is **UNVERIFIED**.
10. **The default embedding model is not chosen.** Tests do not need one (fake embeddings work), but the application needs a real local embedding model for Task 4.2. ChromaDB's default would download a model on first use, which was deliberately not tested.

## 6. Recommended Dependency Constraints

These are proposals for later tasks. **Do not apply them in Task 4.0.** Add the runtime lines when Task 4.2 introduces code that uses them.

`backend/requirements.txt` (additions):

```text
langchain-core>=1.6.7,<2
langgraph>=1.2.14,<1.3
langchain-anthropic>=1.7.5,<1.8   # replaced 2026-10-23 by langchain-google-genai>=4.4.0,<4.5 and google-genai>=2.29.0,<3
langchain-chroma>=1.1.0,<1.2
chromadb>=1.5.9,<1.6
langsmith>=0.14.4,<0.15
```

`backend/requirements-eval.txt` (new):

```text
-r requirements.txt

ragas==0.4.3
# 0.4.2 removed langchain_community.chat_models.vertexai, which ragas 0.4.3 imports.
langchain-community==0.4.1
```

- The lower bounds are the versions verified here. The upper bounds stop at the next minor release for the 0.x and fast-moving 1.x packages.
- The `langchain` meta-package is not proposed: none of the checks used it.
- `anthropic` is left to `langchain-anthropic`'s own range (`>=0.120.0,<2.0.0`).

## 7. Recommended Next Task

**Task 4.1 — Knowledge preparation.** Select specific NDMA India, WHO and UNDRR documents, record their metadata, and check each publisher's terms of use. It needs no new dependencies, and its output (the source list) is required before the retrieval pipeline can be tested meaningfully.

**Task 4.2 — Retrieval pipeline** then adds the runtime dependencies above, an injectable embedding function, and offline tests using `DeterministicFakeEmbedding`. Before Task 4.2, decide the real embedding model and confirm CI install time on Linux.

## 8. Reproducing the Checks

The functional checks were run as temporary scripts outside the repository. The commands below reproduce the environments; the essential test code is summarised after them.

```bash
PY=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14
WORK=$(mktemp -d)
cd ~/Documents/BlueTick_AI/Capstone_projects/resqivo

# 1. Runtime environment: project versions first, then the AI stack under the cutoff.
$PY -m venv "$WORK/venv-ai"
.venv/bin/python -m pip freeze > "$WORK/project-freeze.txt"
grep -iE "^(fastapi|starlette|pydantic|pydantic_core|uvicorn|httpx2|pytest|ruff|anyio|typing_extensions)==" \
  "$WORK/project-freeze.txt" > "$WORK/constraints.txt"
"$WORK/venv-ai/bin/python" -m pip install -r "$WORK/project-freeze.txt"
"$WORK/venv-ai/bin/python" -m pip install --uploaded-prior-to 2026-10-07T00:00:00Z \
  -c "$WORK/constraints.txt" \
  langchain langchain-core langgraph langchain-anthropic langchain-chroma chromadb langsmith
"$WORK/venv-ai/bin/python" -m pip check

# 2. Existing tests against the new environment (writes nothing to the repo).
cd backend
PYTHONDONTWRITEBYTECODE=1 "$WORK/venv-ai/bin/python" -m pytest -q -p no:cacheprovider
cd ..

# 3. RAGAS on top of the runtime environment.
"$WORK/venv-ai/bin/python" -m pip install --uploaded-prior-to 2026-10-07T00:00:00Z \
  ragas "langchain-community==0.4.1"
"$WORK/venv-ai/bin/python" -m pip check
"$WORK/venv-ai/bin/python" -I -c "import ragas; print(ragas.__version__)"

# 4. Tracing flag.
"$WORK/venv-ai/bin/python" -I -c "from langsmith import utils; print(utils.tracing_is_enabled())"
LANGSMITH_TRACING=true "$WORK/venv-ai/bin/python" -I -c "from langsmith import utils; print(utils.tracing_is_enabled())"
```

Summary of the functional check scripts. Each patched `socket.socket.connect` to raise, so any network attempt would fail the check:

- **C (embeddings):** `Chroma(client=chromadb.EphemeralClient(), embedding_function=DeterministicFakeEmbedding(size=64))`, `add_documents`, `similarity_search` twice, and a check that `~/.cache/chroma/onnx_models` was not created (with `HOME` set to an empty temporary directory).
- **D (payloads):** `ChatAnthropic(model="claude-opus-5-5", api_key="not-a-real-key")`, then `_get_request_payload([HumanMessage("hi")], **runnable.kwargs)` for `bind_tools`, `bind_tools(tool_choice="auto")`, and `with_structured_output` with both methods (using `.first` of the structured-output chain).
- **D/E (workflow):** a `StateGraph` with `agent` (`FakeMessagesListChatModel`), `tools` (`ToolNode`), `validate` (calls `validate_plan` on a `PlanValidationRequest`), and `correct` nodes. It was run with `PYTHONPATH=backend` and the LangSmith variables unset, with `MAX_CORRECTIONS = 2`.
- **B (RAGAS):** import `ragas`, build `EvaluationDataset([SingleTurnSample(...)])`, construct the four metrics, and wrap `ChatAnthropic` and `DeterministicFakeEmbedding` with the LangChain wrappers.
