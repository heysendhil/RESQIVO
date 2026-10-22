# RESQIVO — Test and Evaluation Strategy

**Project tagline:** *Every Second. Every Life.*

## 1. Purpose

This document defines how RESQIVO will be tested as it is built. Tests must verify conventional application behaviour, deterministic resource calculations, retrieval quality, agent workflow behaviour, and safety boundaries.

A successful test run does not prove that RESQIVO is suitable for real emergency operations. The initial project is a simulated decision-support capstone.

## 2. Test Principles

- Prefer deterministic tests for calculations and hard constraints.
- Use synthetic scenario fixtures for automated tests.
- Test failure cases as deliberately as success cases.
- Validate all external and model-generated data before using it.
- Keep LLM quality evaluation separate from ordinary unit-test pass/fail results.
- Record the model, prompt/configuration version, dataset version, and evaluation date for AI evaluations.
- Never change tests merely to hide a product defect.
- Do not claim a test passed unless it was executed and its result recorded.

## 3. Test Levels

### 3.1 Unit Tests

Test isolated functions and models.

Examples:
- Scenario model accepts valid input and rejects malformed input.
- Resource quantities cannot be negative.
- Capacity and allocation calculations return expected results.
- Constraint validator detects resource shortages.
- Stress-test transformations apply the expected changes.
- Missing evidence is represented explicitly.

**Tool:** Pytest for backend Python code.

### 3.2 API Tests

Test FastAPI endpoints and response contracts.

Examples:
- `GET /health` returns a healthy status.
- Scenario list and detail endpoints return valid response models.
- Unknown scenario IDs return the documented error response.
- Invalid request payloads are rejected.
- API errors do not reveal secrets or internal stack traces.

### 3.3 Frontend Tests

Test key user interactions and interface states.

Examples:
- Scenario list and detail views render correctly.
- Loading, empty, and error states are visible and understandable.
- Validation findings and assumptions are displayed.
- The interface labels scenarios as simulated.
- The layout remains usable at desktop and mobile widths.
- Draft recommendations are not presented as authoritative instructions.

### 3.4 Integration Tests

Test interactions between components.

Examples:
- API loads the correct synthetic scenario.
- Retrieval returns passages with source metadata.
- Agent workflow receives validated inputs.
- Tool outputs are validated before they affect a draft plan.
- Deterministic validation findings appear in the final API response.
- A workflow failure is surfaced instead of silently returning a fabricated result.

Use test doubles or mocked external services where practical to keep tests repeatable and cost-controlled.

### 3.5 End-to-End Tests

Once the UI and API are connected, verify the main user journey:

1. Open RESQIVO.
2. Select a synthetic disaster scenario.
3. Review the scenario and resource inventory.
4. Request a draft response plan.
5. Review evidence and assumptions.
6. Run deterministic validation.
7. Apply a scenario perturbation.
8. Compare baseline and stressed outcomes.
9. Confirm the system shows warnings and the human-review boundary.

### 3.6 Running the Backend Checks

Ruff handles linting and formatting. Its configuration is in `backend/pyproject.toml`.

Dependencies are split into two files in `backend/`:

| File | Contents | Use |
|---|---|---|
| `requirements.txt` | Runtime only: `fastapi`, `pydantic`, `uvicorn[standard]`, `starlette`, plus the AI stack (`langchain-core`, `langgraph`, `langchain-anthropic`, `langchain-chroma`, `chromadb`, `langsmith`) verified in `docs/dependency-compatibility.md` | Running the API and retrieval |
| `requirements-dev.txt` | Includes `requirements.txt`, plus `pytest`, `httpx2` (HTTP client for FastAPI's `TestClient`) and `ruff` | Development and testing |
| `requirements-eval.txt` | Includes `requirements.txt`, plus `ragas` and the pinned `langchain-community` | RAG evaluation only; not installed by CI |

LangGraph requires `websockets<17`, so installing `requirements.txt` resolves `websockets` 16.x. Retrieval tests and commands are described in `docs/rag.md`.

Lower version bounds are the versions tested with the project; upper bounds stop at the next potentially breaking release.

To set up a clean environment (Python 3.14), from the repository root:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt       # runtime only
python -m pip install -r backend/requirements-dev.txt   # runtime + development tools
```

Run the checks from the `backend/` directory with the virtual environment active:

```bash
cd backend
source ../.venv/bin/activate

python -m ruff check .            # linting
python -m ruff format --check .   # formatting check (no changes made)
python -m ruff format .           # apply formatting
python -m pytest -v               # backend test suite
```

Run pytest from `backend/` so that the `app` package can be imported.

**Continuous integration:** `.github/workflows/ci.yml` runs on every push to `main` and every pull request targeting `main`. On `ubuntu-latest` with Python 3.14, it installs `backend/requirements-dev.txt`, then runs `python -m ruff check .`, `python -m ruff format --check .` and `python -m pytest -q` from `backend/`. Run the commands above to reproduce it locally.

The test run should show no warnings. An earlier `StarletteDeprecationWarning` ("Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead") was resolved by replacing `httpx` with `httpx2`. If it appears, `httpx` is installed but `httpx2` is not; reinstall from `requirements-dev.txt`.

### 3.7 Validation API

The FastAPI app (`backend/app/main.py`) exposes two endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /health` | Returns `{"status": "ok", "service": "RESQIVO"}` |
| `POST /validate` | Runs `validate_plan` on a plan and returns the result |
| `POST /answer` | Grounded question answering with citations; documented in `docs/rag.md` section 7. Tests: `tests/test_qa_service.py`, `tests/test_qa_api.py`, `tests/test_qa_llm.py` (offline, fake model, no API key) |
| `POST /review` | LangGraph workflow: grounded answer plus deterministic plan validation with at most 2 allocation-only corrections; documented in `docs/workflow.md`. Tests: `tests/test_workflow.py`, `tests/test_workflow_api.py` (offline, fake model, no API key) |
| `POST /draft-plan` | LangGraph drafting workflow: proposes allocations of the supplied resources to the supplied shelters, validated deterministically with at most 2 allocation-only corrections; returns `insufficient_information`, `draft_invalid` or `draft_valid`; documented in `docs/workflow.md` section 9. Tests: `tests/test_draft_plan.py`, `tests/test_draft_plan_api.py` (offline, fake model, no API key) |
| Tool calling (opt-in) | With `RESQIVO_TOOL_CALLING=true`, `/review` and `/draft-plan` let the model request `search_guidance` and `validate_plan` under application-enforced allowlist, stage, argument and limit checks; response schemas unchanged; documented in `docs/workflow.md` section 10. Tests: `tests/test_tool_calling.py` (offline, scripted fake model, no API key) |
| Grounding validation (all answer paths) | Sentence-level citation coverage, number and unit checks, lexical support and instruction-like text checks before any answer is returned; documented in `docs/rag.md` section 7.3.1. Tests: `tests/test_grounding_validation.py` |
| Observability (all endpoints) | Every response carries `X-Request-ID`; structured events and in-process metrics are documented in `docs/observability.md`. Response bodies are unchanged, except that an unhandled error now returns JSON `{"detail": "Internal server error."}`. Tests: `tests/test_observability.py` |
| Limits (all endpoints) | Bodies over `RESQIVO_MAX_BODY_BYTES` get 413; requests over `RESQIVO_REQUEST_TIMEOUT_SECONDS` get 504. Concurrency, failure and size tests and the benchmark are documented in `docs/stress-testing.md`. Tests: `tests/test_stress.py` |
| Evaluation (not an endpoint) | `python ../scripts/run_evaluation.py` runs the offline evaluation tracks and writes a JSON report; documented in `docs/evaluation.md`. Tests: `tests/test_evaluation.py`, `tests/test_evaluation_metrics.py` |

**Request:** a `PlanValidationRequest` (`backend/app/models/plan.py`) with three required lists, each of which may be empty. Items use the existing `Resource`, `ResourceAllocation` and `Shelter` models, and unknown keys are rejected at every level.

```json
{
  "resources": [
    {"resource_id": "water-001", "name": "Drinking Water", "resource_type": "drinking_water",
     "quantity_available": 1000, "unit": "litres", "location": "Warehouse A"}
  ],
  "allocations": [
    {"allocation_id": "alloc-001", "resource_id": "water-001",
     "destination_id": "shelter-001", "quantity_allocated": 1100}
  ],
  "shelters": [
    {"shelter_id": "shelter-001", "name": "Community Hall", "location": "Simulated Zone A",
     "capacity": 500, "current_occupancy": 200}
  ]
}
```

**Response (HTTP 200):** the `ValidationResult` from `validate_plan`, returned whether or not the plan is valid. Violation codes, entity IDs, details and ordering are unchanged (see section 4.1). For the request above:

```json
{
  "valid": false,
  "violations": [
    {"code": "DOM-04", "entity_id": "water-001",
     "message": "Resource allocation exceeds available stock.",
     "details": {"quantity_available": 1000, "quantity_allocated": 1100, "excess_quantity": 100}}
  ]
}
```

**HTTP 422:** a malformed body (a missing list, an invalid field value, an unknown key or non-JSON content) is rejected by FastAPI with its standard validation error. Interactive documentation is at `/docs` while the backend is running.

Tests: `backend/tests/test_validate_api.py` (endpoint behaviour) and `backend/tests/test_cors.py` (allowed origins).

### 3.8 Frontend

The Next.js app in `frontend/` (TypeScript, Tailwind CSS) shows two synthetic sample plans (`frontend/lib/sample-plans.ts`) and sends the selected plan to `POST /validate`. The displayed Valid/Invalid status and violations come from the backend response. `frontend/lib/api.ts` makes the request, checks the response shape, and reports an unreachable API or an unexpected response as an error.

To run it, with the backend running on port 8000:

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```

**API URL:** `NEXT_PUBLIC_API_BASE_URL` sets the backend base URL and defaults to `http://127.0.0.1:8000`. To override it, copy `frontend/.env.example` to `frontend/.env.local` and change the value. Next.js inlines it into the browser bundle at build time, so it must never contain a secret. `.env.local` is ignored by Git.

**CORS:** because the frontend and API are on different origins, the backend allows cross-origin requests only from `http://localhost:3000` and `http://127.0.0.1:3000`, only for `GET` and `POST`, and only the `Content-Type` request header. A hosted deployment must add its frontend origin explicitly to `ALLOWED_ORIGINS` in `backend/app/main.py`; requests from any other origin are refused.

Frontend checks, from `frontend/` (the CI workflow runs backend checks only):

```bash
npm run lint       # ESLint
npx tsc --noEmit   # type check (no package script; uses the installed TypeScript)
npm run build      # production build, which also type-checks
```

## 4. Domain and Constraint Test Cases

| ID | Scenario | Expected result |
|---|---|---|
| DOM-01 | Valid synthetic scenario | Scenario is accepted |
| DOM-02 | Missing required scenario field | Validation error is returned |
| DOM-03 | Negative resource quantity | Input is rejected |
| DOM-04 | Allocation exceeds available stock | Constraint violation is reported |
| DOM-05 | Allocation exceeds shelter capacity | Capacity violation is reported |
| DOM-06 | Required information is missing | Missing assumption is reported; no value is invented |
| DOM-07 | Valid plan within configured constraints | Validator reports no configured constraint violations |
| DOM-08 | Same inputs run twice | Deterministic calculations return the same result |
| STR-01 | Route is marked unavailable | Plan is re-evaluated against the changed condition |
| STR-02 | Shelter capacity is reduced | Capacity violation or revised allocation is reported |
| STR-03 | Resource stock is reduced | Shortage is identified |
| STR-04 | Demand is increased | Updated demand and resulting constraint findings are shown |

These tests validate the prototype's configured rules; they do not certify a plan for real-world use.

### 4.1 Implemented Violation Codes

The deterministic validator (`backend/app/services/validation.py`) reports these codes. Each code determines what kind of entity the violation's `entity_id` identifies.

| Code | Reported when | `entity_id` identifies | Granularity |
|---|---|---|---|
| DOM-04 | Total allocations of a resource exceed its available stock | Resource | One per resource |
| DOM-04-UNKNOWN-RESOURCE | Allocations reference a resource ID that does not exist | Resource ID referenced by the allocations | One per resource ID; allocated quantities are aggregated |
| DOM-04-DUPLICATE-RESOURCE | More than one resource has the same ID | Duplicated resource ID | One per duplicated ID; `details.occurrences` gives the count |
| DOM-04-DUPLICATE-ALLOCATION | More than one allocation has the same ID | Duplicated allocation ID | One per duplicated ID; `details.occurrences` gives the count |
| DOM-05 | Shelter occupancy exceeds shelter capacity | Shelter | One per shelter |
| DOM-05-DUPLICATE-SHELTER | More than one shelter has the same ID | Duplicated shelter ID | One per duplicated ID; `details.occurrences` gives the count |
| DOM-06-UNKNOWN-DESTINATION | An allocation's destination is not a known shelter | Allocation | One per allocation |

**Duplicate IDs:** duplicates are reported instead of letting a later entry silently replace an earlier one. Violations appear in order of each ID's first occurrence, before the other checks of the same validator. The stock of a duplicated resource ID is not compared with its allocations, because its available quantity is ambiguous. Capacity is still checked for every shelter entry. An allocation to a duplicated shelter ID is not reported as an unknown destination. Tests are in `backend/tests/test_duplicate_id_validation.py`.

**Duplicate allocation IDs:** these are reported by a separate check, without removing, merging or changing any allocation. Every allocation, duplicated or not, still counts towards resource stock (DOM-04) and is still checked for an unknown destination (DOM-06-UNKNOWN-DESTINATION). Because DOM-06 identifies allocations by ID, two DOM-06 violations can share an `entity_id` when allocation IDs are duplicated; the DOM-04-DUPLICATE-ALLOCATION violation flags that ambiguity. In the combined plan result, this check runs after resource validation and before destination validation. Tests are in `backend/tests/test_duplicate_allocation_id_validation.py`.

**Known limitation:** shelters are currently the only valid allocation destinations, because the domain model has no other destination types. An allocation sent anywhere else, such as a hospital or district, is reported as DOM-06-UNKNOWN-DESTINATION.

## 5. RAG Evaluation

The implemented framework, its datasets, metric definitions, commands and results are in `docs/evaluation.md`. This section and section 6 state the original strategy.

Maintain a small, versioned evaluation set containing:
- A user question.
- Expected source document(s) or evidence.
- Key facts that a grounded answer should preserve.
- Facts that must not be asserted without evidence.
- Whether the correct behaviour is to answer or to state that evidence is insufficient.

Evaluate:
- **Retrieval relevance:** Are retrieved passages useful for the question?
- **Source traceability:** Does each displayed source correspond to a retrieved document?
- **Groundedness:** Are material claims supported by retrieved evidence?
- **Evidence-gap handling:** Does the system admit when the knowledge base is insufficient?
- **Robustness:** Does irrelevant or conflicting content cause unsupported claims?

RAGAS or another evaluation framework may be added after a baseline test set exists. Record its version and configuration. Do not rely on a single aggregate score.

## 6. Agent and Tool-Calling Evaluation

Test that:
- Each agent receives only the inputs required for its task.
- Tool calls use approved tools and valid argument schemas.
- Invalid tool arguments are rejected.
- Tool results are checked before they influence the plan.
- Agents cannot bypass deterministic constraint validation.
- The workflow handles timeouts and tool failures explicitly.
- The final draft distinguishes evidence, assumptions, recommendations, and validation findings.
- Instructions found inside retrieved documents are treated as untrusted content and cannot override application rules.
- No agent can dispatch responders, issue public warnings, or execute real-world actions.

## 7. Safety and Human-Review Tests

| ID | Risk | Expected behaviour |
|---|---|---|
| SAFE-01 | Scenario data is synthetic | UI clearly labels it as simulated |
| SAFE-02 | Evidence is missing | System states the evidence gap |
| SAFE-03 | LLM proposes an invalid allocation | Deterministic validator flags the violation |
| SAFE-04 | Retrieved document contains malicious instructions | Content is treated as untrusted data |
| SAFE-05 | Plan has unresolved constraints | Findings are visible and human review is required |
| SAFE-06 | External action is requested | System does not execute real-world dispatch or warning actions |
| SAFE-07 | Secret-like value appears in a failure | Logs and API responses do not expose credentials |
| SAFE-08 | LLM provider or retrieval service fails | Error is reported clearly; no false success is returned |

## 8. Performance and Reliability Checks

As the prototype matures, record:
- API response latency for deterministic endpoints.
- End-to-end workflow latency.
- Retrieval latency and number of retrieved passages.
- External model calls, token usage, and estimated cost where available.
- Failure and timeout rates.
- Behaviour with empty, malformed, or unusually large inputs.

Set performance targets only after establishing a baseline and expected demo environment.

## 9. Evaluation Dataset and Reporting

Store synthetic test fixtures separately from application code where practical. Keep the dataset small enough for repeatable local runs.

Each evaluation report should record:
- Code revision.
- Dataset version.
- Model/provider and relevant configuration.
- Prompt or workflow version.
- Test command and execution date.
- Passed, failed, and skipped tests.
- RAG and agent-evaluation results.
- Known limitations and follow-up actions.

Do not store secrets or unnecessary personal data in fixtures, traces, or reports.

## 10. Initial Acceptance Criteria

The initial foundation is acceptable when:
- The FastAPI application starts and the health endpoint test passes.
- Input models have tests for valid and invalid values.
- Deterministic resource and constraint functions have reproducible tests.
- At least one synthetic scenario is available.
- The main user journey can be exercised locally once the interface is connected.
- AI-generated suggestions are separated from deterministic validation.
- Missing evidence, constraint failures, and service errors are clearly surfaced.
- The human-review and no-real-dispatch boundaries are documented and tested.

## 11. Test Execution Record

Update this section during implementation. Do not pre-fill results.

| Date | Revision | Command / test suite | Result | Notes |
|---|---|---|---|---|
| 2026-10-17 | None: repository has no commits yet | `python -m ruff check .` (Ruff 0.17.1) | Passed: no violations | Run from `backend/` |
| 2026-10-17 | None: repository has no commits yet | `python -m ruff format --check .` (Ruff 0.17.1) | Passed: 18 files already formatted | 4 files were reformatted first; layout only, syntax trees unchanged |
| 2026-10-17 | None: repository has no commits yet | `python -m pytest -v` (pytest 9.1.1, Python 3.14.6) | 32 passed, 0 failed, 1 warning | Warning: Starlette deprecation notice recommending `httpx2` instead of `httpx` |
| 2026-10-17 | None: repository has no commits yet | `python -m ruff check .` and `python -m ruff format --check .` (Ruff 0.17.1) | Passed: no violations; 19 files already formatted | After adding duplicate-ID validation |
| 2026-10-17 | None: repository has no commits yet | `python -m pytest -v` (pytest 9.1.1, Python 3.14.6) | 44 passed, 0 failed, 1 warning | Adds 12 duplicate-ID tests; the 9 duplicate-specific tests failed against the previous validator, as expected. Same `httpx2` warning |
| 2026-10-17 | None: repository has no commits yet | `python -m ruff check .` and `python -m ruff format --check .` (Ruff 0.17.1) | Passed: no violations; 20 files already formatted | After adding duplicate allocation-ID validation |
| 2026-10-17 | None: repository has no commits yet | `python -m pytest -v` (pytest 9.1.1, Python 3.14.6) | 52 passed, 0 failed, 1 warning | Adds 8 duplicate allocation-ID tests; all 44 earlier tests unchanged and passing. Same `httpx2` warning |
| 2026-10-17 | None: repository has no commits yet | Clean venv: `pip install -r requirements.txt`, then `/health` called directly and `validate_plan` imported | Passed: `pip check` clean; `/health` returned 200; pytest not installed, as expected | Resolved FastAPI 0.143.3, Starlette 1.8.0, Pydantic 2.14.1, Uvicorn 0.54.0 |
| 2026-10-17 | None: repository has no commits yet | Clean venv: `pip install -r requirements-dev.txt`, then Ruff checks and `python -m pytest -v -W error::DeprecationWarning` | Ruff passed (20 files formatted); 52 passed, 0 failed, 0 warnings | httpx2 2.13.1; `httpx` not installed |
| 2026-10-17 | None: repository has no commits yet | Project `.venv`: Ruff checks and `python -m pytest -v` | Ruff passed (20 files formatted); 52 passed, 0 failed, 0 warnings | FastAPI 0.143.0, Starlette 1.7.0, httpx2 2.13.1; `httpx` warning resolved |
| 2026-10-21 | `13264af` plus uncommitted validation API and frontend changes | `python -m ruff check .` and `python -m ruff format --check .` (Ruff 0.17.1) | Passed: no violations; 23 files already formatted | Run from `backend/` |
| 2026-10-21 | `13264af` plus uncommitted validation API and frontend changes | `python -m pytest -q` (pytest 9.1.1, Python 3.14.6) | 64 passed, 0 failed, 0 warnings | Adds 9 `/validate` API tests and 3 CORS tests |
| 2026-10-21 | `13264af` plus uncommitted validation API and frontend changes | `npm run lint`, `npx tsc --noEmit`, `npm run build` (Next.js 16.3.8, Node 24.21.0) | All passed | Run from `frontend/` |
| 2026-10-21 | `cb38b80` plus uncommitted Task 4.0–4.2 changes | `python -m ruff check .` and `python -m ruff format --check .` (Ruff 0.17.1) | Passed: no violations; 38 files already formatted | After adding the retrieval pipeline |
| 2026-10-21 | `cb38b80` plus uncommitted Task 4.0–4.2 changes | `python -m pytest -q` (pytest 9.1.1, Python 3.14.6) | 125 passed, 0 failed, 1 warning | Adds 61 offline retrieval tests. Warning: ChromaDB 1.5.9 `DeprecationWarning` for `asyncio.iscoroutinefunction` (removal in Python 3.16) |
| 2026-10-21 | `cb38b80` plus uncommitted Task 4.0–4.2 changes | `python -m pip check` in the project `.venv` | No broken requirements | After installing `requirements-dev.txt` |
| 2026-10-21 | `8894695` plus uncommitted Task 4.3 changes | `python -m ruff check .`, `python -m ruff format --check .` (Ruff 0.17.1), `python -m pip check` | Passed: no violations; 48 files already formatted; no broken requirements | No dependency changes |
| 2026-10-21 | `8894695` plus uncommitted Task 4.3 changes | `python -m pytest -q` with `ANTHROPIC_API_KEY` unset (pytest 9.1.1, Python 3.14.6) | 168 passed, 0 failed, 1 warning | Adds 43 offline question-answering tests using fake retrievers and models. No live Claude request was made. Same ChromaDB warning |
| 2026-10-21 | `8894695` plus uncommitted Task 4.3–5.1 changes | `python -m ruff check . ../scripts`, `python -m ruff format --check . ../scripts` (Ruff 0.17.1), `python -m pip check` | Passed: no violations; 58 files already formatted; no broken requirements | No dependency changes |
| 2026-10-21 | `8894695` plus uncommitted Task 4.3–5.1 changes | `python -m pytest -q` with `ANTHROPIC_API_KEY`, `LANGSMITH_TRACING` and `RESQIVO_ALLOW_MODEL_DOWNLOAD` unset (pytest 9.1.1, Python 3.14.6) | 222 passed, 0 failed, 1 warning | Includes 20 download-guard tests and 34 LangGraph workflow tests, all with fake models and the network blocked. No live Claude request was made. Same ChromaDB warning |
| 2026-10-22 | `8894695` plus uncommitted Task 4.3–5.2 changes | `python -m pytest -q tests/test_draft_plan.py tests/test_draft_plan_api.py` with `ANTHROPIC_API_KEY`, `LANGSMITH_TRACING` and `RESQIVO_ALLOW_MODEL_DOWNLOAD` unset (pytest 9.1.1, Python 3.14.6) | 71 passed, 0 failed, 1 warning | 47 workflow and 24 API tests with a fake retriever and scripted fake model, network blocked. No live Claude request was made. Same ChromaDB warning |
| 2026-10-22 | `8894695` plus uncommitted Task 4.3–5.2 changes | `python -m pytest -q` with the same variables unset (pytest 9.1.1, Python 3.14.6) | 293 passed, 0 failed, 1 warning | Adds 71 draft-plan tests; one existing route-list assertion in `test_qa_api.py` extended with `/draft-plan`. Same ChromaDB warning |
| 2026-10-22 | `8894695` plus uncommitted Task 4.3–5.2 changes | `python -m ruff check . ../scripts`, `python -m ruff format --check . ../scripts` (Ruff 0.17.1), `python -m pip check` | Passed: no violations; 61 files already formatted; no broken requirements | No dependency changes |
| 2026-10-22 | `8894695` plus uncommitted Task 4.3–5.3 changes | `python -m pytest -q tests/test_tool_calling.py` with `ANTHROPIC_API_KEY`, `LANGSMITH_TRACING`, `RESQIVO_ALLOW_MODEL_DOWNLOAD`, `RESQIVO_TOOL_CALLING` and `RESQIVO_MAX_TOOL_CALLS` unset (pytest 9.1.1, Python 3.14.6) | 74 passed, 0 failed, 1 warning | Scripted fake model with `bind_tools`; network blocked. `ChatAnthropic.bind_tools` payload built offline with a placeholder key and never sent. No live Claude request was made. Same ChromaDB warning |
| 2026-10-22 | `8894695` plus uncommitted Task 4.3–5.3 changes | `python -m pytest -q` with the same variables unset (pytest 9.1.1, Python 3.14.6) | 367 passed, 0 failed, 1 warning | Adds 74 tool-calling tests; all 293 earlier tests pass unchanged. Same ChromaDB warning |
| 2026-10-22 | `8894695` plus uncommitted Task 4.3–5.3 changes | `python -m ruff check . ../scripts`, `python -m ruff format --check . ../scripts` (Ruff 0.17.1), `python -m pip check` | Passed: no violations; 63 files already formatted; no broken requirements | No dependency changes |
| 2026-10-22 | `8894695` plus uncommitted Task 4.3–6 changes | `python -m pytest -q` before any Task 6 change, with `ANTHROPIC_API_KEY`, `LANGSMITH_TRACING`, `RESQIVO_ALLOW_MODEL_DOWNLOAD`, `RESQIVO_TOOL_CALLING` and `RESQIVO_MAX_TOOL_CALLS` unset (pytest 9.1.1, Python 3.14.6) | 367 passed, 0 failed, 1 warning | Baseline for the evaluation task |
| 2026-10-22 | `8894695` plus uncommitted Task 4.3–6 changes | `python -m pytest -q tests/test_evaluation.py tests/test_evaluation_metrics.py` with the same variables unset | 47 passed, 0 failed, 1 warning | Includes a subprocess run of the CLI with network blocked, a fake API key (removed by the runner), an empty `HOME` (no cached models) and tracing requested; the report showed 0 live calls and `onnx-minilm` skipped as not cached |
| 2026-10-22 | `8894695` plus uncommitted Task 4.3–6 changes | `python -m pytest -q` with the same variables unset | 414 passed, 0 failed, 1 warning | Adds 47 evaluation tests; all 367 earlier tests unchanged and passing. Same ChromaDB warning |
| 2026-10-22 | `8894695` plus uncommitted Task 4.3–6 changes | `python -m ruff check . ../scripts`, `python -m ruff format --check . ../scripts` (Ruff 0.17.1), `python -m pip check` | Passed: no violations; 76 files already formatted; no broken requirements | No dependency changes |
| 2026-10-22 | `8894695` plus uncommitted Task 4.3–6 changes | `python ../scripts/run_evaluation.py --output <scratch>` and `... --include-real-source` (hashing) | Exit 1 (one case failed, as designed). Synthetic retrieval R@1/3/5 12/16/17 of 26, MRR 0.5759; WHO-01 R@1/3/5 10/12/15 of 28, MRR 0.4271 (0.4289 in an earlier run); grounding 12/13; drafting 16/16; tool calling 17/17 | Offline; 0 live model calls. Details in `docs/evaluation.md` section 5 |
| 2026-10-22 | `8894695` plus uncommitted changes | `python -m pytest -q` before grounding hardening, with `ANTHROPIC_API_KEY`, `LANGSMITH_TRACING`, `RESQIVO_ALLOW_MODEL_DOWNLOAD`, `RESQIVO_TOOL_CALLING` and `RESQIVO_MAX_TOOL_CALLS` unset (pytest 9.1.1, Python 3.14.6) | 414 passed, 0 failed, 1 warning | Baseline |
| 2026-10-22 | `8894695` plus uncommitted changes | `python -m pytest -q tests/test_grounding_validation.py tests/test_qa_service.py tests/test_qa_api.py tests/test_evaluation.py` with the same variables unset | 106 passed, 0 failed, 1 warning | Focused grounding, QA and evaluation tests |
| 2026-10-22 | `8894695` plus uncommitted changes | `python -m pytest -q` with the same variables unset | 457 passed, 0 failed, 1 warning | Adds 49 grounding-validation tests. Removes 6 unit tests of the evaluation-only overlap heuristic, which was replaced by the production validator (now covered in `test_grounding_validation.py`). Scripted answers in 7 places in `test_draft_plan.py` (including the `DraftModel` default) and `test_tool_calling.py` were replaced with sentences their passages support, with no assertion weakened; evaluation tests updated to dataset v2. Same ChromaDB warning |
| 2026-10-22 | `8894695` plus uncommitted changes | `python -m ruff check . ../scripts`, `python -m ruff format --check . ../scripts` (Ruff 0.17.1), `python -m pip check` | Passed: no violations; 78 files already formatted; no broken requirements | No dependency changes |
| 2026-10-22 | `8894695` plus uncommitted changes | `python ../scripts/run_evaluation.py --output <scratch>` (hashing, dataset v2) | Exit 1 (synthetic retrieval misses count as failed cases). Grounding 19/19, drafting 16/16, tool calling 17/17; synthetic retrieval unchanged (17/26 within top 5) | Offline; 0 live model calls. Details in `docs/evaluation.md` section 5.3 |
| 2026-10-22 | `8894695` plus uncommitted changes | `python -m pytest -q` before Task 7.3, with `ANTHROPIC_API_KEY`, `LANGSMITH_TRACING`, `RESQIVO_ALLOW_MODEL_DOWNLOAD`, `RESQIVO_TOOL_CALLING` and `RESQIVO_MAX_TOOL_CALLS` unset (pytest 9.1.1, Python 3.14.6) | 457 passed, 0 failed, 1 warning | Baseline |
| 2026-10-22 | `8894695` plus uncommitted changes | `python -m pytest -q tests/test_observability.py` with the same variables unset | 39 passed, 0 failed, 1 warning | Network blocked; tracing never enabled; no live model calls |
| 2026-10-22 | `8894695` plus uncommitted changes | `python -m pytest -q` with the same variables unset | 496 passed, 0 failed, 1 warning | Adds 39 observability tests; all 457 earlier tests pass unchanged (existing log assertions kept their keys). Same ChromaDB warning |
| 2026-10-22 | `8894695` plus uncommitted changes | `python -m ruff check . ../scripts`, `python -m ruff format --check . ../scripts` (Ruff 0.17.1), `python -m pip check` | Passed: no violations; 80 files already formatted; no broken requirements | No dependency changes |
| 2026-10-22 | `8894695` plus uncommitted changes | `python -m pytest -q` before the load-testing task, with `ANTHROPIC_API_KEY`, `LANGSMITH_TRACING`, `RESQIVO_ALLOW_MODEL_DOWNLOAD`, `RESQIVO_TOOL_CALLING` and `RESQIVO_MAX_TOOL_CALLS` unset (pytest 9.1.1, Python 3.14.6) | 496 passed, 0 failed, 1 warning | Baseline |
| 2026-10-22 | `8894695` plus uncommitted changes | `python -m pytest -q tests/test_stress.py` with the same variables unset | 39 passed, 0 failed, 1 warning | Real concurrent ASGI requests (up to 60, concurrency 16), fake models, network blocked; includes a subprocess run of the benchmark |
| 2026-10-22 | `8894695` plus uncommitted changes | `python -m pytest -q` with the same variables unset | 535 passed, 0 failed, 1 warning | Adds 39 tests; all 496 earlier tests unchanged and passing. Same ChromaDB warning |
| 2026-10-22 | `8894695` plus uncommitted changes | `python -m ruff check . ../scripts`, `python -m ruff format --check . ../scripts` (Ruff 0.17.1), `python -m pip check` | Passed: no violations; 84 files already formatted; no broken requirements | No dependency changes |
| 2026-10-22 | `8894695` plus uncommitted changes | `python ../scripts/benchmark.py` (200 requests per endpoint, concurrency 8, 0 ms fake model) and `--concurrency 16 --delay-ms 50` | Exit 0 for both; 0 failed requests | Offline, in-process; results in `docs/stress-testing.md` section 4.1. Not a prediction of live latency |
