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
| `requirements.txt` | Runtime only: `fastapi`, `pydantic`, `uvicorn[standard]`, `starlette` | Running the API |
| `requirements-dev.txt` | Includes `requirements.txt`, plus `pytest`, `httpx2` (HTTP client for FastAPI's `TestClient`) and `ruff` | Development and testing |

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
