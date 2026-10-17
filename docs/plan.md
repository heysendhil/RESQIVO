# RESQIVO — Implementation Plan

**Project tagline:** *Every Second. Every Life.*

## 1. Delivery Approach

Build RESQIVO in small, reviewable phases. Complete one task at a time:

**Understand → Plan → Implement → Test → Review → Continue**

Do not begin a later task until the current task's acceptance criteria are checked. Keep the first milestone small and runnable before adding AI orchestration.

## 2. Proposed Repository Structure

```text
resqivo/
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

Create only the folders and files required for the active task. Do not scaffold every planned component before its phase begins.

## 3. Phases and Tasks

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

**Task 4.1 — Knowledge preparation**
- Add a small, curated set of appropriate public guidance documents or clearly labelled educational material.
- Record document titles, sources, dates where available, and metadata.
- **Acceptance:** Every indexed document has traceable source metadata.

**Task 4.2 — Retrieval pipeline**
- Implement chunking, embeddings, indexing, and retrieval.
- **Acceptance:** A small retrieval test set returns relevant source passages for known questions.

**Task 4.3 — Grounded question answering**
- Answer questions using retrieved evidence and show source references.
- If evidence is insufficient, state that clearly rather than fabricate a citation or instruction.
- **Acceptance:** Tests cover grounded answers, irrelevant retrieval, and insufficient evidence.

### Phase 5 — Agentic Workflow and Tool Calling

**Task 5.1 — Define agent responsibilities**
- Define narrow responsibilities for scenario analysis, evidence retrieval, plan drafting, and review.
- Document tool permissions and the data each agent may access.
- **Acceptance:** Each agent has an explicit input, output, and bounded responsibility.

**Task 5.2 — Orchestrate a draft-plan workflow**
- Implement a controlled CrewAI/CrewAI Flow workflow after confirming library compatibility.
- Use structured inputs and outputs.
- **Acceptance:** A test scenario completes the workflow and records failures clearly.

**Task 5.3 — Tool calling and deterministic checks**
- Expose approved tools for scenario lookup, resource calculation, and constraint validation.
- Treat tool outputs as data; validate all arguments and results.
- **Acceptance:** Invalid arguments are rejected and AI output cannot bypass deterministic checks.

**Task 5.4 — Human review boundary**
- Clearly label plans as drafts and show unresolved constraints or missing evidence.
- Do not add automated real-world dispatch or public-warning actions.
- **Acceptance:** No workflow can execute consequential external actions.

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
- Create a fixed set of scenario questions and expected evidence.
- Evaluate retrieval relevance, answer grounding, tool correctness, and plan-constraint validity.
- **Acceptance:** Evaluation results are repeatable and limitations are documented.

**Task 7.3 — Observability**
- Add structured logs and traceable workflow events without logging secrets.
- Add tracing/evaluation tools only when the baseline workflow is stable.
- **Acceptance:** A failed workflow can be investigated from its recorded events.

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

## 4. Definition of Done for Every Task

Before marking a task complete:

1. Inspect the changes.
2. Run relevant automated tests or validation commands.
3. Record the exact result; do not claim tests passed unless they were run.
4. Document files changed and important design decisions.
5. Record assumptions, known issues, and deferred work.
6. Confirm no unrelated files or secrets were added.
7. Stop and wait for review before beginning the next task.

## 5. Initial Priority

Start with **Phase 0** and complete the three documentation files. Then implement **Phase 1** only. Do not start RAG, agent orchestration, database integration, or deployment until the earlier foundations and acceptance criteria are complete.
