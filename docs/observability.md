# RESQIVO — Observability

**Status:** implemented and tested offline on 2026-10-22 (`backend/tests/test_observability.py`, 39 tests). **No live Claude request was made, and tracing was not enabled during testing.**

Code is in `backend/app/observability.py`, which uses only the standard library. It records:

- the request middleware in `backend/app/main.py`;
- the QA service;
- workflow nodes and summaries;
- tool executions;
- grounding rejections.

No dependency, metrics server or monitoring framework was added.

## 1. Events

Every event is one log line in this form:

```text
event=<name> request_id=<id> key=value key=value ...
```

| Logger | Event | When | Main fields |
|---|---|---|---|
| `resqivo.api` | `request.start` | A request arrives | `method` |
| `resqivo.api` | `request.end` | A response is sent, including errors | `method`, `endpoint` (route template, or `unmatched`), `status`, `outcome`, `error`, `duration_ms`, plus the request summary (section 2) |
| `resqivo.api` | `validation.result` | `/validate` ran the validator | `valid`, `codes` |
| `resqivo.qa` | `qa.answer` | A grounded answer is finished | `status`, `reason`, `passages` (number shown to the model), `citations` |
| `resqivo.qa` | `grounding.rejected` | An answer failed grounding validation | `context` (`qa` or `tool_calling`), `rule`, `sentence`, `sentences` |
| `resqivo.workflow` | `workflow.node` | A graph node ran | `node`, plus node-specific counts and codes (passages, status, valid, codes, attempt, parsed, stage, requested_calls, …) |
| `resqivo.workflow` | `tool.call` | The application handled one model-requested tool call | `stage`, `call`, `tool` (`unknown` for unapproved names), `status` (`executed`, `rejected` or `failed`), `reason` |
| `resqivo.workflow` | `workflow.complete` | `/review` or `/draft-plan` finished | `workflow`, `outcome`, `duration_ms`, workflow fields (for example `final_valid`, `correction_attempts`, `codes`), plus the request summary |
| `resqivo.workflow` | `workflow.failed` | A workflow raised | `workflow`, `error` (exception class name or `recursion_limit`), `duration_ms`, plus the request summary |

### `request.end` outcomes

| Status | `outcome` |
|---|---|
| < 400 | `success` |
| 422 | `invalid_request` |
| other 4xx | `client_error` |
| 500 | `error` |
| 502 | `model_error` |
| 413 | `payload_too_large` |
| 503 | `unavailable` |
| 504 | `timeout` |

`error` holds the exception class name, for example `RetrievalUnavailableError`, `ModelNotConfiguredError` (configuration or dependency failure), `ToolCallLimitError` or `RuntimeError`. It is never the exception message.

An unhandled exception now returns HTTP 500 with `{"detail": "Internal server error."}` and the request-ID header. Before this change, FastAPI's plain-text 500 was returned. In both cases no stack trace is exposed.

## 2. Per-request summary

These counts are gathered across all components during one request. They are attached to `request.end`, `workflow.complete` and `workflow.failed`.

| Field | Meaning |
|---|---|
| `model_calls`, `model_failures` | Model invocations made by RESQIVO code (answer, draft, correction, tool turn), and how many failed: an exception, a refusal, an empty answer, or an unusable draft. A failed correction parse is not a model failure; see `corrections`. |
| `retrieval` | Retrieval outcomes in order: `success`, `empty_knowledge_base`, `failure`, `configuration_error` |
| `answer_outcomes` | `answered`, or the insufficient-evidence reason (`no_relevant_passages`, `knowledge_base_empty`, `model_reported_insufficient_evidence`, `answer_not_grounded`) |
| `grounding_rejections` | Grounding rules that rejected an answer |
| `tool_calls`, `tool_rejections`, `tool_rejection_reasons`, `tool_failures` | Model-requested tool calls (tool-calling mode only) |
| `validations`, `invalid_validations` | Validator runs, and how many found violations |
| `corrections` | Correction attempts; at most 2 per plan |

## 3. Metrics

`app.observability.METRICS` is an in-process, thread-safe registry. **It is not exposed over HTTP.** It can be read in-process with `METRICS.snapshot()`, which tests use. In production, the `request.end` and `workflow.*` events carry the same information for a log pipeline to aggregate. Counters reset when the process restarts. **This is not a distributed metrics backend:** with several workers or instances, each keeps its own counters, and only log aggregation gives a combined view.

| Metric | Labels |
|---|---|
| `requests_total` | `endpoint`, `method`, `outcome` |
| `request_duration_ms` (histogram) | `endpoint` |
| `request_errors_total` | `endpoint`, `error` |
| `retrieval_total` | `outcome` |
| `answers_total` | `status`, `reason` |
| `grounding_rejections_total` | `rule` |
| `model_calls_total` | `purpose` (`answer`, `draft`, `correction`, `tool_turn`), `outcome` |
| `tool_calls_total` | `tool`, `status`, `reason` |
| `tool_call_limit_total` | `stage` |
| `validations_total` | `valid` |
| `correction_attempts_total` | `parsed` |
| `workflow_runs_total` | `workflow`, `outcome` |
| `workflow_duration_ms` (histogram) | `workflow` |
| `logging_errors_total` | — |

Histogram buckets are 50, 100, 250, 500, 1,000, 2,500, 5,000, 10,000 and 30,000 ms, plus an overflow bucket. Label values come from fixed code sets. The endpoint is the route template, so unknown URLs all count as `unmatched` and cannot create unbounded labels.

## 4. Request IDs

- A client may send `X-Request-ID`. It is reused only if it is **8–64 characters of letters, digits, `.`, `_` or `-`**; anything else is replaced with a generated 32-character hex ID. The ID in use is returned in the `X-Request-ID` response header.
- The ID is held in a context variable for the whole request. It appears in every event from the API, the QA service, every LangGraph node, tool executions and the workflow summaries. A test checks that LangGraph nodes see the same ID.
- `/draft-plan`'s existing `request_id` response field now carries the same ID. It is still a 32-character hex value unless the client supplied a valid ID.
- Workflows run outside the API, such as in tests and the evaluation runner, get their own ID.
- The CORS policy is unchanged (`Content-Type` only), so browser clients on other origins cannot send the header. Non-browser clients can.

## 5. Privacy boundaries

**Never logged:**
- API keys, credentials or tokens;
- questions, scenario narratives or names;
- locations;
- resource or shelter details;
- retrieved passages;
- prompts or model output;
- tool arguments;
- exception messages.

Events carry only counts, booleans, durations, fixed reason codes, violation codes, route templates and class names.

**Injection-safe formatting:**
- Keys must match `[a-z][a-z0-9_]{0,39}`; anything else is dropped, and `event` and `request_id` cannot be overridden.
- Every value is reduced to the characters `A–Z a–z 0–9 . _ : / @ + -`; anything else becomes `?`.
- Values are truncated to 64 characters, and lists to 10 items.
- No value can therefore contain a space, `=` or a line break, so user input cannot add fields or lines. A test sends a question and a header containing `\nevent=…`.
- Unapproved tool names are recorded as `unknown`.

**Failures are contained.** Formatting and logging errors are caught: a failing handler increments `logging_errors_total` and has no other effect. A test attaches a handler that raises on every record and checks that `/validate` and the review workflow return unchanged results.

## 6. Tracing

- LangSmith tracing stays **off** unless `LANGSMITH_TRACING` (or `LANGCHAIN_TRACING_V2`) is set to true. Nothing in RESQIVO enables it.
- With tracing off, no trace is exported and no tracing connection is made. Tests run with the network blocked and confirm `tracing_is_enabled()` is false.
- If tracing is enabled explicitly, the first `/answer`, `/review` or `/draft-plan` request sets `LANGSMITH_HIDE_INPUTS=true` and `LANGSMITH_HIDE_OUTPUTS=true`, unless the operator has set them. Traces then omit prompts, passages and model output by default. Run metadata (names, timing, errors) is still exported.
- To export payloads deliberately, set the hide variables to `false`.
- Tests check this defaulting logic, and that nothing changes when tracing is off. Tracing was never enabled during testing.

## 7. Configuration

Python logging is not configured by the application. Events appear only if the deployment configures a handler for the `resqivo` logger, for example:

```python
logging.basicConfig(level=logging.INFO)
```

## 8. Limitations

- **Metrics are per process and in memory.** There is no export endpoint, and counters reset on restart; aggregation depends on collecting the log events.
- **Model-call counts** cover calls made by RESQIVO code. Retries inside the Anthropic client (`max_retries=2`) are not visible. Token usage and cost are not recorded.
- **Timing:** request durations are measured in the middleware and include dependency construction. There are no per-node timings.
- **Preflight requests:** CORS preflight (`OPTIONS`) requests are answered by the CORS middleware and produce no events.
- **Duplicate request IDs:** a client can reuse the same valid ID for several requests. IDs are for correlation, not authentication.
- **Live tracing unverified:** tracing with LangSmith enabled has not been run, so the effect of the hide settings on real traces is unverified.

## 9. Behaviour under load (verified 2026-10-22)

`backend/tests/test_stress.py` sends up to 60 concurrent requests across all endpoints through the ASGI app. It verified that:
- request IDs stay correlated: exactly one start and one end event per ID, and every event carries its request's ID;
- per-request summaries (model calls, corrections, tool calls and rejections, retrieval outcomes) contain only that request's activity;
- every event line still parses as `event=… request_id=… key=value…`;
- registry totals equal the number of requests, and validation counters equal the sum of the per-request summaries;
- counters are exact under 8-thread contention;
- a failing log handler leaves results unchanged;
- no question, narrative, passage or key appears in any event.

Details are in `docs/stress-testing.md`.
