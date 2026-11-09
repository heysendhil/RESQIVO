# RESQIVO — Model Provider: Google Gemini

**Status (2026-10-23):** migrated from Anthropic Claude to Google Gemini and tested offline with mocks. **No live Gemini request has been made**; live testing awaits separate approval.

Earlier documents and dated test records that mention Claude describe the project as it was at that time.

## 1. What changed

| Item | Before | Now |
|---|---|---|
| Integration | `langchain-anthropic` 1.7.5 (`ChatAnthropic`) | `langchain-google-genai` 4.4.0 (`ChatGoogleGenerativeAI`) on `google-genai` 2.29.0 |
| Backend API | Anthropic Messages API | Gemini Developer API (`vertexai=False`) |
| API key | `ANTHROPIC_API_KEY` | `GOOGLE_API_KEY` (backend only) |
| Default model | `claude-opus-5-5` | `gemini-3.8-flash` |
| Output limit | 4,096 tokens | 16,384 tokens (Gemini counts thinking tokens towards it) |
| Thinking | Not set | `thinking_level="low"` |
| Timeout and retries | 60 s, 2 retries | 90 s, 2 total attempts (1 request + 1 retry) |
| Blocked reply detection | `stop_reason == "refusal"` | `finish_reason` other than `STOP`, or a prompt `block_reason` (`app/qa/replies.py`) |

**Unchanged:**
- the five API routes and their Pydantic request and response models;
- the deterministic validator and its authority;
- grounding and citation checks;
- the two-correction limit;
- the tool allowlist, stage policy and limits, with tool calling off by default;
- request size and time limits;
- observability and redaction;
- the human-review labels;
- the frontend.

## 2. Choice of model and versions

**Model: `gemini-3.8-flash`.** Checked on 2026-10-23 against Google's official documentation:
- **Stable, and recommended for new projects:** [ai.google.dev/gemini-api/docs/models](https://ai.google.dev/gemini-api/docs/models).
- **Capabilities:** function calling "Supported" and structured outputs "Supported"; thinking at low, medium or high ("minimal" is not supported); 1,048,576 input and 65,536 output tokens. Source: the model page.
- **No shutdown date announced:** [deprecations](https://ai.google.dev/gemini-api/docs/deprecations).
- **Why not the flagship:** `gemini-4-argon` is Google's flagship reasoning model, which is more than RESQIVO's short answers and JSON drafts need. It can be selected with `RESQIVO_LLM_MODEL` without a code change.

**Versions.** The project pins releases at least two weeks old (`docs/plan.md` Task 4.0):

| Package | Version | Released | Notes |
|---|---|---|---|
| `langchain-google-genai` | 4.4.0 | 2026-09-01 | Requires `langchain-core>=1.6.1` (the installed 1.6.7 fits) and `google-genai>=2.20.0`. 4.4.1 and 4.4.2 were under two weeks old. |
| `google-genai` | 2.29.0 | 2026-10-07 | The newest release over two weeks old. 2.30.0 to 2.32.0 were newer. |

Installing them added `google-auth`, `cryptography`, `cffi`, `pycparser`, `pyasn1`, `pyasn1-modules` and `filetype`. No existing package changed version, and `pip check` is clean. `langchain-anthropic` and `anthropic` were removed from `requirements.txt` and uninstalled from the project virtual environment.

## 3. How the client is built (`backend/app/qa/llm.py`)

- **Model name check:** `RESQIVO_LLM_MODEL` must be a Gemini model ID (`gemini-…`, optionally prefixed `models/`). Anything else, such as a leftover `claude-opus-5-5`, is a configuration error (HTTP 503) raised before any request, so a stale setting cannot cause paid failing calls.
- **Key:** read only from `GOOGLE_API_KEY` in the backend environment. A missing or blank key raises `ModelNotConfiguredError`, which the API returns as HTTP 503. `GEMINI_API_KEY`, the library's own fallback, is not used, because the key is passed explicitly.
- **Backend:** `vertexai=False` pins the Gemini Developer API. Otherwise `GOOGLE_GENAI_USE_VERTEXAI` or `GOOGLE_CLOUD_PROJECT` could switch backends, and in Vertex mode the library temporarily writes the key into `os.environ`.
- **No network at construction.** The client is built per request (`get_*` dependencies), and importing `app.main` loads neither `langchain_google_genai` nor `google.genai`. Tests check both.
- **No sampling parameters or forced tool choice.** Temperature is left unset, so Gemini 3+ uses its default. `tool_config` is never sent, so the model is never forced to call a tool.
- **Thinking and output limit.** Thinking cannot be switched off on this model, and it counts towards `max_output_tokens`. `thinking_level="low"` keeps answers fast, and the 16,384-token limit leaves room for thinking plus a JSON draft.
- **Timeout and retries:** 90 s per attempt and 2 total attempts (1 request plus 1 retry).
  - `google-genai` also sends the timeout to Google as `X-Server-Timeout`, so a generation still running at that point ends with HTTP 504 (`DEADLINE_EXCEEDED`).
  - **Why these values:** on 2026-10-23 the first live drafts with 60 s and 3 attempts failed with three consecutive 504s, taking 167 s in total. The diagnostic event was `event=model.failed stage=request cause_type=ServerError http_status=504`.
  - **Interaction with the request budget:** the cooperative per-request deadline (`RESQIVO_REQUEST_TIMEOUT_SECONDS`, default 120 s) still applies and cannot interrupt a call in progress. A draft that needs most of the budget leaves no time for corrections, and the request then returns 504. Raise the budget (up to 600 s) if slow drafts are common.

## 4. Reply handling

`app/qa/replies.py` imports nothing provider-specific. A reply is **usable only if `finish_reason` is `STOP`** and the prompt was not blocked.

**Rejected:**
- `SAFETY`, `RECITATION`, `BLOCKLIST`, `PROHIBITED_CONTENT`, `SPII`, `LANGUAGE`, `OTHER`;
- `MAX_TOKENS` (truncated);
- `MALFORMED_FUNCTION_CALL`, `UNEXPECTED_TOOL_CALL`, `TOO_MANY_TOOL_CALLS`;
- `FINISH_REASON_UNSPECIFIED`;
- any prompt `block_reason`.

| Call | An unusable reply means |
|---|---|
| Grounded answer (`/answer`, `/review`, draft guidance) | `ModelResponseError`, HTTP 502 |
| Draft (`/draft-plan`) | `ModelResponseError`, HTTP 502; a truncated JSON draft is never parsed |
| Correction | A failed attempt (counts towards the limit of 2); never parsed as a correction |
| Tool-calling turn | `ModelResponseError`, HTTP 502 |

**Provider errors** (`google.genai` `ClientError`/`ServerError` such as 400, 403, 404, 429 and 503, timeouts, network errors) become `ModelResponseError` with the fixed message "The language model request failed.". The API returns 502 with its fixed text. Provider messages, keys and headers are never logged or returned; tests inject errors containing secret-like text and check that it does not appear.

**Draft parsing is unchanged:** `{"allocations": [...]}` is extracted from the reply text and every allocation is validated strictly. Gemini's native structured-output mode (a response schema) is **not** used. The existing text-JSON contract and validation stay authoritative; a fenced ```json block is accepted, as before.

## 5. Tool calling (opt-in, `RESQIVO_TOOL_CALLING=true`)

`bind_tools` converts the two existing StructuredTools into Gemini function declarations; the nested `validate_plan` schema converts correctly. Checks against the real adapter, with only the SDK call mocked:

- only the stage's tools are declared, and `tool_config` is absent;
- Gemini function calls become LangChain tool calls with generated IDs, and the application authorizes, validates and executes them as before;
- unknown tools and extra arguments are rejected;
- tool results go back as Gemini function responses;
- a `MALFORMED_FUNCTION_CALL` finish is a model error.

**Thought signatures:** the reply message is appended to the history unchanged, so any signatures the adapter stores are sent back in later turns. This has not been verified live.

## 6. Local configuration

1. In `backend/.env` (ignored by Git) or your shell, set `GOOGLE_API_KEY=<your Gemini API key>`. Never put it in `frontend/` or in any `NEXT_PUBLIC_` variable.
2. Remove `ANTHROPIC_API_KEY` from `backend/.env` if it is still there; it is no longer used.
3. Set `RESQIVO_LLM_MODEL=gemini-3.8-flash`, or delete the line to use that default. A leftover `claude-…` value is rejected with HTTP 503.
4. Install the updated dependencies: `../.venv/bin/python -m pip install -r requirements-dev.txt`.
5. Restart the backend with the variables exported, because the app reads the environment and does not load `.env`:

```bash
cd backend
set -a; source .env; set +a
../.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## 7. Limitations

- **No live Gemini request has been made.** Whether `gemini-3.8-flash` follows the citation format, the `INSUFFICIENT_EVIDENCE` convention, the JSON draft format and the tool rules is unverified, and so are its latency and cost. The first live run should be supervised.
- **Thought signatures across tool turns** depend on the adapter preserving them in `AIMessage`; this is not verified live.
- **Safety settings use Google's defaults.** A disaster scenario could occasionally trigger a block (for example on medical content); RESQIVO reports it as a model error rather than an answer.
- **Rate limits (429):** the SDK retries with fixed backoff and ignores the server's suggested delay (a known upstream issue).
- **Deprecation warning:** `google-genai` 2.29.0 emits a Python 3.17 `DeprecationWarning` (`_UnionGenericAlias`) during tests. It comes from the library, not RESQIVO.

## 8. Failure diagnostics

Failed model calls are logged as one `event=model.failed` line on the `resqivo` loggers. The line records metadata only, never the prompt, the reply text, provider messages or credentials:

- **`stage=request`:** the API call failed. Logged with `error_type`, `cause_type` (for example `ServerError`) and `http_status` (for example 429 or 504).
- **`stage=reply`:** Gemini blocked or truncated the reply. Logged with `finish_reason`, `block_reason` and `output_tokens`.
- **`stage=parse`:** the reply was not a usable JSON draft. Logged with a `reason` code, for example `invalid_allocation:0.rationale:extra_forbidden` or `empty_allocations`.

The application does not configure Python logging. To see these events, start uvicorn with a `--log-config` file that gives the `resqivo` logger an INFO-level handler (`docs/observability.md` section 7).
