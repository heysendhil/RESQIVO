# RESQIVO — Stress, Concurrency and Performance Testing

**Status:** implemented and run offline on 2026-10-22. **No live Claude request was made**, nothing was downloaded, and no external service was contacted. Every model reply is produced by fake models.

> **Scope.** This document covers *load* testing: concurrency, failure under load, request limits and latency. The scenario stress tests in `plan.md` Phase 6 (STR-01 to STR-04, perturbing a plan's facts) are a different task and are **not** implemented here.

## 1. What was added

| Item | Location |
|---|---|
| Request-body size limit (new) | `backend/app/limits.py`, `BodySizeLimitMiddleware` |
| Per-request time budget (new) | `backend/app/limits.py`, `deadline` and `check_deadline` |
| Offline load components | `backend/app/evaluation/loadtest.py`: a content-driven fake model, an echoing retriever, per-request dependency overrides, and request builders |
| Concurrency, failure, timeout and size tests | `backend/tests/test_stress.py` (39 tests) |
| Benchmark | `scripts/benchmark.py` |

## 2. Gaps found, and the controls added

Inspection before the change showed:

- **No request-body size limit.** FastAPI, Starlette and uvicorn do not cap bodies. `POST /validate` and the `plan` in `/review` have **no list-length limits**. `/draft-plan` has its own limits (100 resources, 100 shelters, 200 needs, 10 constraints), and questions are limited to 1,000 characters.
- **No overall request time limit.** Each Claude call has a 60 s client timeout and up to 2 retries (`app/qa/llm.py`). A request can make up to 4 sequential model calls in fixed mode (answer, draft, two corrections), or up to 9 tool turns plus the draft and corrections in tool-calling mode.
- **Concurrency-relevant state.**
  - Workflows, services and the Claude client are built per request (`get_*` dependencies).
  - The only shared mutable state is the metrics registry, which is lock-protected, and per-request context variables (request ID, run statistics, deadline).
  - LangGraph runs a graph's nodes on the calling thread with its context.
  - Synchronous endpoints run in Starlette's thread pool.

### 2.1 Body size limit

| Setting | Default | Hard bounds | Behaviour |
|---|---|---|---|
| `RESQIVO_MAX_BODY_BYTES` | 1,048,576 (1 MiB) | 16 KiB – 8 MiB | Larger bodies get **413** `{"detail": "Request body too large."}` before any parsing |

- A declared `Content-Length` over the limit is rejected without reading the body.
- Bodies without a length, such as chunked uploads, are read up to the limit and replayed to the application. One byte more is rejected, so memory per request is bounded by the limit.
- A non-numeric `Content-Length` gets 400.
- **Nothing is ever truncated.** A body is either processed whole or rejected; a test checks that the validator never runs for a rejected body.
- **Why 1 MiB:** a valid `/draft-plan` request with every list and string at its maximum measured 174,561 bytes as compact JSON. Indented JSON is larger, so 1 MiB leaves room while still bounding `/validate`. A 5,000-allocation `/validate` request (574,197 bytes) fits and is validated in full.

### 2.2 Request time budget

| Setting | Default | Hard bounds | Behaviour |
|---|---|---|---|
| `RESQIVO_REQUEST_TIMEOUT_SECONDS` | 120 | 1 – 600 | Once the budget is used, the next retrieval or model call is not started and the request returns **504** `{"detail": "The request did not complete in time."}` |

- **Cooperative.** The deadline is checked before every retrieval and every model call: answer, draft, correction, tool turn and tool-requested search.
- **It cannot interrupt a call already in progress.** That call is bounded by the Claude client's own 60 s timeout (and retries), so the worst case is the budget plus one in-flight call.
- **A timeout is not counted as a failed correction.** The check sits outside the correction step's exception handler, so the two-correction limit and its semantics are unchanged.

**Invalid limit settings fail closed:** every endpoint, including `/health`, returns 503 until the settings are fixed. Tests cover this.

**API contract changes (additive):** 413 and 504 are new status codes. Response bodies for existing outcomes are unchanged.

## 3. Offline test strategy

`backend/tests/test_stress.py` sends **real concurrent requests** to the ASGI app through `httpx2.ASGITransport`, with `asyncio.gather` and a semaphore. Concurrency is 16 unless stated, and request sets are fixed.

The fake model derives its replies from each request's own prompt:
- answers echo the request's passage, which names the request's `case-N` token;
- drafts allocate the request's own stock;
- corrections clamp the request's own allocations.

A response can therefore be checked against the request that produced it. No timing assumption is needed beyond an optional fixed delay.

| Scenario | Requests | What is verified |
|---|---|---|
| Mixed load on all 5 endpoints | 60 (12 per endpoint), 5 ms model delay | Each response contains only its own quantities, case token, corrections and draft stock. `X-Request-ID` is echoed. Every request ID has exactly one start and one end event, with its own model-call and correction counts. `requests_total` = histogram count = 60. Validation counters equal the sum of per-request summaries. Every event line parses. |
| Failures mixed with successes | 30 concurrent (every third retrieval fails), then 10 more | Failed requests get a sanitized 503 while the others succeed with their own evidence. Per-request retrieval outcomes are correct, and later requests are unaffected. |
| Concurrent tool calling | 24 | Each request's `tool_calls`, rejections and reasons are its own (12 × 1 call, 12 × 2 calls with 1 rejection) |
| Metrics contention | 8 threads × 2,000 updates | Counters and histogram counts are exact |
| Logging failure under load | 20 concurrent `/validate` with a handler that raises | Results unchanged; `logging_errors_total` > 0 |
| Sensitive data under load | 15 | Questions, narratives, keys and passages never appear in events |
| Failures (8 concurrent each) | model exception, malformed draft, retrieval failure, tool execution failure, tool-call limit, recursion backstop | Fixed sanitized messages (502, 503 or 500), no success outcome, no secret in responses or events |
| Validator authority | 16 | A model claiming validity, and unparseable corrections, give final `DOM-04` and exactly 2 corrections |
| Hard tool-call cap | 4 | `RESQIVO_MAX_TOOL_CALLS=50` returns 503 |
| Slow model | 4 concurrent, 1.1 s model, 1 s budget | 504; one model call per request; correction never started; finishes in under 4 s |
| Size boundaries | 1 per case | 1,000- and 1,001-character questions, 100 and 101 resources, 10 and 11 constraints, 2,001-character description, malformed or empty JSON, oversized fixed-length and chunked bodies, bad `Content-Length`, 5,000 allocations |

## 4. Benchmark

```bash
cd backend
source ../.venv/bin/activate
python ../scripts/benchmark.py --output /tmp/resqivo-bench.json                  # defaults
python ../scripts/benchmark.py --requests 200 --concurrency 16 --delay-ms 50     # simulated slow model
```

**Method:**

1. **Startup:** time to `import app.main` in fresh interpreters (subprocesses).
2. **First request:** the first request to each endpoint in the process.
3. **Warm-up:** sequential requests, reported separately.
4. **Steady state:** N requests at concurrency C, in-process via `httpx2.ASGITransport`.

Network connections are blocked, `ANTHROPIC_API_KEY` is removed and tracing is forced off. The `resqivo` loggers are left unconfigured, as by default, so events are not formatted. Latencies are per request. p95 is reported when n ≥ 20 and p99 when n ≥ 100, using the nearest-rank method. Peak RSS is the process high-water mark.

### 4.1 Results (measured 2026-10-22)

**Environment:** macOS 26.6.2 on arm64, 10 CPUs, Python 3.14.6, a single process. Both runs used 200 requests per endpoint and 20 warm-up requests, with 0 failures and 0 timeouts.

**Run A: concurrency 8, fake-model delay 0 ms**

| Endpoint | First request (ms) | Throughput (req/s) | Median (ms) | p95 (ms) | p99 (ms) | Max (ms) |
|---|---|---|---|---|---|---|
| GET /health | 10.39 | 2,665.5 | 2.51 | 5.16 | 6.26 | 6.44 |
| POST /validate | 0.97 | 2,132.1 | 3.25 | 6.19 | 7.30 | 8.25 |
| POST /answer | 1.35 | 1,894.7 | 3.96 | 4.96 | 6.34 | 7.01 |
| POST /review (1 correction) | 8.44 | 212.1 | 35.53 | 43.31 | 45.62 | 51.56 |
| POST /draft-plan | 9.39 | 160.5 | 47.47 | 53.90 | 93.93 | 94.21 |

- Startup (`import app.main`, 5 runs): first 231.8 ms, median 145.2 ms.
- Peak RSS: 28.9 MB before requests, 134.9 MB after.

**Run B: concurrency 16, fake-model delay 50 ms per call**

| Endpoint | Throughput (req/s) | Median (ms) | p95 (ms) | p99 (ms) | Max (ms) |
|---|---|---|---|---|---|
| GET /health | 3,451.0 | 4.29 | 5.06 | 5.41 | 5.45 |
| POST /validate | 2,733.4 | 5.49 | 6.53 | 7.26 | 7.71 |
| POST /answer (1 call) | 227.3 | 67.01 | 76.17 | 78.04 | 80.70 |
| POST /review (2 calls) | 123.3 | 120.22 | 163.36 | 165.72 | 166.29 |
| POST /draft-plan (2 calls) | 110.1 | 125.67 | 240.73 | 248.95 | 249.99 |

- Startup (3 runs): median 142.6 ms.
- Peak RSS: 137.0 MB after requests.
- In both runs the metrics registry recorded exactly 1,105 requests: 5 endpoints × (1 first + 20 warm-up + 200 steady). This matches the requests sent.

### 4.2 Interpretation

These are measurements of the offline application with fake models. **They are not predictions of live Claude latency or production capacity.**

- **The workflow endpoints are CPU-bound in one process.** Built and run one at a time, a `/review` workflow took about 3 ms: graph construction 1.6 ms (median of 50) plus the run 1.6 ms. At concurrency 8 the median was 35 ms, while throughput (212 req/s) implies about 4.7 ms of CPU per request. So the latency mostly reflects queueing behind the interpreter lock. This is an inference from the measurements, not a profile.
- **With simulated model latency, requests overlap.** With a 50 ms fake model, `/answer` medians were about 67 ms at concurrency 16, so model waits ran concurrently in the thread pool. Starlette's thread pool (40 threads by default) bounds that overlap.
- **Live latency is dominated by Claude.** It would be roughly the sum of sequential model calls (1 for `/answer`, 2–4 for `/review` and `/draft-plan`, up to 9 more turns with tool calling) plus about 3–5 ms of application CPU. This is an estimate, not a measurement.

### 4.3 Provisional targets

None are proposed for the model-backed endpoints. Without a supervised live run there is no basis for them.

For the deterministic endpoints, the measured offline medians in Run A (`/health` 2.5 ms, `/validate` 3.3 ms) could serve as **provisional regression baselines** on similar hardware. They are not service-level targets.

## 5. Limitations

- **No live Claude, network or real server.** Benchmarks run in-process with no network, TLS, uvicorn workers or real vector store. A supervised live performance run would need an API key, an explicit decision to spend credit, and a separate procedure; it is not implemented.
- **The real `KnowledgeStore` (ChromaDB) was not load-tested.** Tests use in-memory fake retrievers, so concurrent access to a persistent Chroma index is untested.
- **The time budget is cooperative:** an in-flight model call is not cancelled.
- **The body limit is per process,** applied in the app. A reverse proxy should enforce its own limit in deployment.
- **No rate limiting or authentication.** Many concurrent requests with a key set would each make paid model calls.
- **Single machine.** Results come from one run per configuration on one machine; they vary with hardware and background load.
- **Metrics are per process and in memory,** and reset on restart (`docs/observability.md`).
