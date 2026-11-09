# RESQIVO — Implementation Plan

**Project tagline:** *Every Second. Every Life.*

## 1. Delivery Approach

Build RESQIVO in small, reviewable phases. Complete one task at a time:

**Understand → Plan → Implement → Test → Review → Continue**

Do not begin a later task until the current task's acceptance criteria are checked. Keep the first milestone small and runnable before adding AI orchestration.

## 2. Proposed Repository Structure

```text
resqivo/
├── .github/
│   └── workflows/
├── backend/
│   ├── app/
│   └── tests/
├── frontend/
├── data/
│   └── synthetic/
├── knowledge/
│   └── seed/
├── docs/
│   ├── understanding.md
│   ├── plan.md
│   └── test.md
├── scripts/
├── .env.example
├── .gitignore
└── README.md
```

Create only the folders and files required for the active task. Do not scaffold every planned component before its phase begins. Generated artefacts such as the ChromaDB index are not committed.

## 3. Current Status

| Task | Status | Evidence |
|---|---|---|
| 0.1–0.3 Documentation | Done | `docs/understanding.md`, `docs/plan.md`, `docs/test.md` |
| 0.4 AI architecture decision | Done | This plan and `understanding.md` section 7 |
| 1.1 Initialize repository | Partial | Git repository and `.gitignore`; no root `README.md` yet |
| 1.2 Backend skeleton | Done | FastAPI `GET /health` with a test |
| 1.3 Frontend skeleton | Done | Next.js app in `frontend/` |
| 1.4 Configuration and baseline | Partial | `frontend/.env.example`, `backend/.env.example` (retrieval settings only); run commands in `test.md` sections 3.6 and 3.8 and `docs/rag.md`; no root `README.md` |
| 2.1 Data contracts | Partial | Scenario, resource, shelter, allocation and plan-request models with tests |
| 2.2 Synthetic scenario fixtures | Not started | Sample plans exist only in `frontend/lib/sample-plans.ts` |
| 2.3 Deterministic planning tools | Done | `validate_plan` and its tests |
| 3.1 Scenario API | Not started | `POST /validate` exists, but there are no scenario endpoints |
| 3.3 Draft plan and validation view | Done (offline-tested) | Dashboard in `frontend/` calls all five endpoints (`frontend/README.md`): editable synthetic workspace; deterministic validation labelled authoritative; drafts labelled "Draft — requires human review"; review with corrections; grounded Q&A with citations treated as untrusted; mapped errors for 413, 422, 502, 503 and 504. 64 Vitest tests with `fetch` stubbed; lint and tsc clean. `npm run build` not run (it downloads the Geist font from Google); not yet verified in a browser against a live backend |
| 4.0 Dependency compatibility check | Done | `docs/dependency-compatibility.md` |
| 4.1 Knowledge preparation | Partial | `docs/knowledge-sources.md` and `knowledge/seed/sources.json`; only WHO-01 is cleared for indexing; NDMA permission and three licence checks outstanding |
| 4.2 Retrieval pipeline | Done (synthetic corpus) | `backend/app/rag/`, `docs/rag.md`; offline tests pass with synthetic fixtures. `onnx-minilm` approved for opt-in evaluation only (`docs/embedding-evaluation.md`); `hashing` remains the default. `onnx-minilm` refuses to download its model unless `RESQIVO_ALLOW_MODEL_DOWNLOAD=true` or `--allow-model-download` is given (`docs/rag.md` section 5); full suite 188 passed |
| 4.2a WHO-01 retrieval evaluation | Done (initial) | `docs/who-source-evaluation.md` section 4.1: 28-question set (AI-written, not yet expert-reviewed), offline, in-memory. Top-3: `onnx-minilm` 19/28, `hashing` 12/28. Threshold investigation recommended; cut-off unchanged; WHO-01 not indexed for `/answer` |
| 4.3 Grounded question answering | Done (offline) | `POST /answer` and `backend/app/qa/`; `docs/rag.md` section 7; offline tests pass with fake models. No live Claude request made; answer quality on real sources not validated |
| 5.1 Initial LangGraph workflow | Done (offline) | `backend/app/workflow/`, `POST /review`, `docs/workflow.md`: retrieve → grounded answer → deterministic validation → at most 2 allocation-only corrections. 34 offline tests with a fake model; full suite 222 passed. No live Claude request made |
| 5.2 Orchestrate a draft-plan workflow | Done (offline) | `backend/app/workflow/drafting.py`, `POST /draft-plan`, `docs/workflow.md` section 9: validate request → retrieve guidance → grounded answer → assess evidence → draft allocations → deterministic validation → at most 2 allocation-only corrections, reusing the 5.1 nodes. Distinguishes insufficient information, invalid drafts and valid drafts; supplied stock and shelters cannot be changed. 71 offline tests with a fake model; full suite 293 passed. No live Claude request made; draft quality not evaluated; needs and free-text constraints are not validated |
| 5.3 Tool calling and deterministic checks | Done (offline, opt-in) | `backend/app/workflow/tool_calling.py`, `docs/workflow.md` section 10: model-initiated calls to `search_guidance` and `validate_plan` through `bind_tools`, with a fixed allowlist, per-stage authorization, schema-validated arguments (extra arguments rejected), a 4-call default and an 8-call hard limit, and a recursion backstop. The fixed validation and correction nodes always run. Enabled only by `RESQIVO_TOOL_CALLING=true`; default behaviour unchanged. 74 offline tests with a scripted fake model; full suite 367 passed. No live Claude request made. Scenario lookup and resource-calculation tools not added |
| Evaluation framework (assigned as "Task 6: Agentic AI Evaluation Framework") | Done (offline) | `backend/app/evaluation/`, `scripts/run_evaluation.py`, `data/synthetic/agentic_evaluation.json` v1 (46 cases), `docs/evaluation.md`. Five separate tracks: synthetic retrieval, WHO-01 retrieval (opt-in), grounding, plan drafting, tool calling. JSON report with explicit denominators. Offline results on 2026-10-22: grounding 12/13 cases (GRD-012 is a documented heuristic limitation), drafting 16/16, tool calling 17/17, all safety invariants 100%. 47 tests; full suite 414 passed. No live Claude request made. This delivers the offline part of Task 7.2 below; it is not the plan's Phase 6 stress testing |
| Grounding validation hardening (follow-up to the evaluation) | Done (offline) | `backend/app/qa/grounding.py`, `docs/rag.md` section 7.3.1. Sentence-level checks for every answer path (`/answer`, `/review`, `/draft-plan` guidance, tool calling): each factual sentence must cite a provided label, numbers and units must appear in that sentence's cited passages, at least half its content words must too, and instruction-like passage text is neither evidence nor acceptable output. Malformed or duplicated citations are rejected. Failures return the existing `insufficient_evidence` / `answer_not_grounded`; the API schema is unchanged. Evaluation dataset v2: grounding 19/19, including GRD-008, GRD-009 and GRD-012, which are now rejected. Full suite 457 passed. Lexical checks only, not semantic grounding |
| 5.4 Human review boundary | Not started | |
| 6.1–6.2 Plan stress testing | Not started | STR- test IDs remain defined in `test.md`; no perturbations implemented |
| 7.2 AI evaluation | Partial | Offline framework done (row above). Not done: supervised live-model evaluation, human or LLM-judge review of semantic grounding, RAGAS |
| 7.3 Observability | Done (offline) | `backend/app/observability.py`, `docs/observability.md`: structured single-line events for request start and end, workflow nodes, summaries and failures, retrieval, answers, grounding rejections, tool calls, validation and corrections. Correlation via a validated `X-Request-ID`, propagated through LangGraph nodes and tool executions. An in-process metrics registry (counters and duration histograms, not exposed over HTTP). Injection-safe formatting, logging failures contained, and payloads and secrets never logged. LangSmith stays off by default, and hides inputs and outputs if enabled. 39 tests; full suite 496 passed. Tracing with LangSmith enabled not verified live |
| Load, concurrency and performance testing (assigned as "Task 8") | Done (offline) | `backend/app/limits.py`, `backend/app/evaluation/loadtest.py`, `backend/tests/test_stress.py`, `scripts/benchmark.py`, `docs/stress-testing.md`. Added a request-body limit (413; default 1 MiB, bounds 16 KiB–8 MiB) and a cooperative per-request time budget (504; default 120 s, bounds 1–600 s). Concurrency isolation, failure, timeout and size tests: 39 tests; full suite 535 passed. Offline benchmark measured with fake models; no live Claude performance run. This is not the plan's Phase 6 scenario stress testing (row 6.1–6.2) |
| Model provider migration to Google Gemini | Done (offline, mocked) | `docs/model-provider.md`. `langchain-google-genai` 4.4.0 and `google-genai` 2.29.0 replace `langchain-anthropic`; default model `gemini-3.8-flash` (stable; function calling and structured outputs supported, per Google's documentation on 2026-10-23); backend-only `GOOGLE_API_KEY`. Replies are usable only when `finish_reason` is `STOP`; provider errors are sanitized. API contracts, validation, grounding, correction and tool limits, request limits and the frontend are unchanged. 51 provider tests using the real adapter with the SDK call mocked, including rejection of non-Gemini model names; full suite 575 passed. **No live Gemini request made**; awaiting approval |
| 7.4 Security review | Not started | |

A backend CI workflow (`.github/workflows/ci.yml`) runs Ruff and pytest on pushes and pull requests to `main`.

## 4. Phases and Tasks

### Phase 0 — Requirements and Documentation

**Task 0.1 — Understanding**
- Define purpose, users, scope, exclusions, safety boundaries, and success criteria.
- **Acceptance:** `understanding.md` is reviewed and consistent with the capstone goals.

**Task 0.2 — Plan**
- Define the implementation phases, repository layout, dependencies, and task acceptance criteria.
- **Acceptance:** `plan.md` identifies the order of work and the criteria for moving forward.

**Task 0.3 — Test strategy**
- Define test levels, safety checks, scenario fixtures, and evaluation measures.
- **Acceptance:** `test.md` specifies how the initial workflow will be verified.

**Task 0.4 — AI architecture decision**
- Record the approved AI stack: Anthropic Claude via `langchain-anthropic` (replaced by Google Gemini via `langchain-google-genai` on 2026-10-23; `docs/model-provider.md`), LangChain, LangGraph (replacing CrewAI), ChromaDB, RAGAS (subject to compatibility), and LangSmith (disabled by default).
- Record the knowledge publishers (NDMA India, WHO, UNDRR) and the AI control principles in `understanding.md` section 7.4.
- **Acceptance:** Both documents describe all four capstone requirements (RAG, tool calling, evaluation, observability) without claiming they are implemented.

**Gate:** Review all three documents together before application implementation.

### Phase 1 — Repository and Local Development Foundation

**Task 1.1 — Initialize repository**
- Create the repository structure, `.gitignore`, and a basic `README.md`.
- Configure Git and a repeatable local development workflow.
- **Acceptance:** Structure is correct; no secrets or unnecessary generated files are committed.

**Task 1.2 — Backend skeleton**
- Create a Python virtual environment.
- Add a minimal FastAPI application and `/health` endpoint.
- Add a backend test for the health endpoint.
- **Acceptance:** Application starts locally and the health test passes.

**Task 1.3 — Frontend skeleton**
- Create a Next.js application with TypeScript and the selected styling system.
- Add a simple RESQIVO landing page using the project name and tagline.
- **Acceptance:** Development server starts and production build succeeds.

**Task 1.4 — Configuration and baseline**
- Add `.env.example` with placeholder settings only.
- Confirm secrets are ignored by Git.
- Document the local run commands.
- **Acceptance:** A new developer can configure and start both applications from the documentation.

### Phase 2 — Scenario and Resource Domain

**Task 2.1 — Define data contracts**
- Define Pydantic models for scenarios, resources, constraints, and draft plans.
- Validate required fields, units, non-negative quantities, and valid identifiers.
- **Acceptance:** Valid and invalid model cases have automated tests.

**Task 2.2 — Synthetic scenario fixtures**
- Create a small, clearly labelled synthetic dataset for at least one disaster type.
- Include assumptions, resource inventories, and configured constraints.
- **Acceptance:** Fixture data loads reproducibly and contains no real incident or personal data.

**Task 2.3 — Deterministic planning tools**
- Implement resource totals and constraint-validation functions before connecting an LLM.
- **Acceptance:** Results are reproducible and tests cover insufficient resources, capacity violations, and valid cases.

### Phase 3 — Initial User Experience and API

**Task 3.1 — Scenario API**
- Add endpoints to list and retrieve synthetic scenarios.
- **Acceptance:** API responses match the documented models and have tests.

**Task 3.2 — Scenario interface**
- Build a responsive scenario selection and detail view.
- Display assumptions, resource availability, and warnings.
- **Acceptance:** The interface works at desktop and mobile widths and handles loading/error states.

**Task 3.3 — Draft plan and validation view**
- Show a plan, its resource totals, validation findings, and outstanding assumptions.
- **Acceptance:** The UI distinguishes suggested content from deterministic validation results.

### Phase 4 — Retrieval-Augmented Generation (RAG)

**Task 4.0 — Dependency compatibility check**
- In a disposable environment, install LangGraph, LangChain, `langchain-anthropic`, `langchain-chroma`, ChromaDB, LangSmith, and RAGAS on the project's Python version (3.14).
- Confirm that each package imports, that structured output and tool calling work with the chosen Claude model without forcing a specific tool, and which local embedding model ChromaDB will use.
- Known risk: RAGAS depends on `scikit-network`, which publishes wheels only up to Python 3.13. If RAGAS cannot be installed on 3.14, decide between a separate Python 3.13 evaluation environment and custom metrics only.
- Pin versions that have been released for at least two weeks. Keep runtime and evaluation dependencies in separate requirements files.
- **Acceptance:** Install results and chosen versions are recorded; no application code depends on an unverified package.

**Task 4.1 — Knowledge preparation**
- Add a small, curated set of official public guidance documents from NDMA India, WHO, and UNDRR.
- Record each document's title, publisher, source URL, publication date where available, and retrieval date, and check the publisher's terms of use.
- **Acceptance:** Every indexed document has traceable source metadata; no other publishers are included unless the source list is formally extended.

**Task 4.2 — Retrieval pipeline**
- Implement chunking, embeddings, ChromaDB indexing, and retrieval through `langchain-chroma`.
- Build the index with a script; store it outside version control.
- Make the embedding function injectable so tests use deterministic fake embeddings and need no network access.
- **Acceptance:** A small retrieval test set returns relevant source passages for known questions.

**Task 4.3 — Grounded question answering**
- Answer questions using retrieved evidence and show source references.
- If evidence is insufficient, state that clearly rather than fabricate a citation or instruction.
- **Acceptance:** Tests cover grounded answers, irrelevant retrieval, and insufficient evidence.

### Phase 5 — Agentic Workflow and Tool Calling

**Task 5.1 — Define agent responsibilities**
- Define narrow responsibilities for scenario analysis, evidence retrieval, plan drafting, and review.
- Document tool permissions and the data each step may access.
- **Acceptance:** Each step has an explicit input, output, and bounded responsibility.

**Task 5.2 — Orchestrate a draft-plan workflow**
- Implement a LangGraph workflow after confirming library compatibility (Task 4.0).
- Use structured inputs and outputs, with the model accessed through LangChain (Gemini via `langchain-google-genai` since 2026-10-23; originally Claude via `langchain-anthropic`).
- Include a deterministic validation step that application code always runs on the proposed plan; it is not a tool the model may choose to skip.
- If validation fails, allow a fixed, configurable maximum number of correction attempts, then return the latest plan with its validation failures.
- **Acceptance:** A test scenario completes the workflow; the returned validity always equals `validate_plan` output, including when a fake model claims an invalid plan is valid (`test.md` SAFE-03); correction stops at the configured maximum; failures are recorded clearly (SAFE-08).

**Task 5.3 — Tool calling and deterministic checks**
- Expose approved LangChain tools for guidance search, scenario lookup, resource calculation, and constraint validation (wrapping the existing `validate_plan`).
- Treat tool outputs and retrieved content as data; validate all arguments and results (SAFE-04).
- **Acceptance:** Invalid arguments are rejected and AI output cannot bypass deterministic checks.

**Task 5.4 — Human review boundary**
- Clearly label plans as drafts and show unresolved constraints or missing evidence.
- Do not add automated real-world dispatch or public-warning actions.
- **Acceptance:** No workflow can execute consequential external actions (SAFE-06).

### Phase 6 — Plan Stress Testing

**Task 6.1 — Perturbation definitions**
- Add controlled variations such as a blocked route, reduced shelter capacity, increased demand, or resource shortage.
- **Acceptance:** Each perturbation is deterministic and documented.

**Task 6.2 — Baseline comparison**
- Compare the baseline plan with perturbed scenarios.
- Identify failed constraints, shortages, and changes in resource allocation.
- **Acceptance:** Tests verify that expected failures are detected and reported.

### Phase 7 — Evaluation, Observability, and Hardening

**Task 7.1 — Automated test suite**
- Run unit and API tests; add frontend and end-to-end tests as applicable.
- **Acceptance:** Results are recorded and failures are addressed rather than hidden.

**Task 7.2 — AI evaluation**
- Create a versioned evaluation set of scenario questions, expected source documents, and expected evidence.
- Evaluate retrieval relevance, answer grounding, tool correctness, and agreement with the deterministic validator.
- Use RAGAS (for example faithfulness, answer relevancy, context precision, and context recall) if Task 4.0 confirms compatibility; otherwise use documented custom metrics.
- Run evaluations outside the default CI workflow because they call the LLM.
- **Acceptance:** Evaluation results are repeatable, record the model, package versions, dataset version, and date in `test.md`, and document limitations.

**Task 7.3 — Observability**
- Add structured logs with request identifiers and traceable workflow events, without logging secrets (SAFE-07).
- Add LangSmith tracing for LangGraph runs, disabled by default and enabled only through environment variables.
- **Acceptance:** A failed workflow can be investigated from its recorded events or trace; CI runs with tracing disabled.

**Task 7.4 — Security and privacy review**
- Check secret handling, input validation, dependency configuration, and data boundaries.
- **Acceptance:** No real credentials are committed; synthetic-data and human-review boundaries remain visible.

### Phase 8 — Deployment and Demonstration

**Task 8.1 — Deployment preparation**
- Add deployment configuration and environment-specific settings.
- **Acceptance:** Local tests and production builds pass.

**Task 8.2 — Hosted demonstration**
- Deploy the frontend and API using selected hosting providers.
- Configure HTTPS and safe secret storage.
- **Acceptance:** A reviewer can access the demo and complete the documented synthetic scenario workflow.

**Task 8.3 — Final capstone package**
- Prepare architecture diagrams, setup instructions, test/evaluation results, limitations, and a demonstration script.
- **Acceptance:** The project can be reviewed and reproduced without relying on undocumented steps.

## 5. Configuration, Secrets, and CI

Planned backend environment variables, documented with placeholder values in a backend `.env.example` when the AI phases begin:

| Variable | Purpose | Secret |
|---|---|---|
| `GOOGLE_API_KEY` | Gemini API access (backend only; replaced `ANTHROPIC_API_KEY` on 2026-10-23) | Yes |
| `RESQIVO_LLM_MODEL` | Gemini model ID (default `gemini-3.8-flash`) | No |
| `LANGSMITH_TRACING` | Enables tracing; defaults to `false` | No |
| `LANGSMITH_API_KEY` | LangSmith access | Yes |
| `LANGSMITH_PROJECT` | LangSmith project name | No |
| `RESQIVO_CHROMA_DIR` | Location of the local ChromaDB index | No |

- Secrets are never committed, logged, returned by the API, or exposed to the frontend.
- The default CI workflow must pass without any API keys: AI tests use fake chat models and fake embeddings, and tracing stays disabled.
- Live LLM runs and RAGAS evaluations run manually or in a separate, opt-in workflow.

## 6. Definition of Done for Every Task

Before marking a task complete:

1. Inspect the changes.
2. Run relevant automated tests or validation commands.
3. Record the exact result; do not claim tests passed unless they were run.
4. Document files changed and important design decisions.
5. Record assumptions, known issues, and deferred work.
6. Confirm no unrelated files or secrets were added.
7. Stop and wait for review before beginning the next task.

## 7. Next Priority

Tasks 4.0, 4.2 and 4.3 are complete for offline use, and Task 4.1 is complete apart from the outstanding permissions. Before relying on answers, provide the WHO-01 text and question set, run the WHO-01 retrieval evaluation (`docs/who-source-evaluation.md`), calibrate the `/answer` distance cut-off, and make one supervised live Claude request. Task 5.1 (initial LangGraph workflow, `docs/workflow.md`) is complete offline. Before relying on `/review` or `/answer`, make one supervised live Claude request. Task 5.2 (draft-plan workflow, `POST /draft-plan`, `docs/workflow.md` section 9) is complete offline; before relying on drafts, make one supervised live Claude request and evaluate draft quality. Task 5.3 (model-initiated tool calling, `docs/workflow.md` section 10) is complete offline and is off by default; before enabling it, make one supervised live Claude request with `RESQIVO_TOOL_CALLING=true`. The offline evaluation framework (`docs/evaluation.md`) is complete. Its grounding findings (GRD-008, GRD-009, GRD-012) were addressed by sentence-level grounding validation (`docs/rag.md` section 7.3.1). Still outstanding: semantic grounding needs human review, the vocabulary-based instruction detection has known gaps, and the expected outcomes need independent review. The next AI task is **Task 5.4 — human review boundary**, or a supervised live evaluation (`docs/evaluation.md` section 7). Outstanding foundation work (Tasks 1.1, 1.4, 2.1, 2.2, 3.1, and 3.2) can proceed independently.
