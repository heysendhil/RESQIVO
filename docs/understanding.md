# RESQIVO — Project Understanding

**Project tagline:** *Every Second. Every Life.*

## 1. Project Summary

RESQIVO is an Agentic AI-powered disaster-response planning and resource-optimization platform. It is designed to help emergency planners explore simulated disaster scenarios, retrieve relevant guidance, compare response options, allocate limited resources, and identify weaknesses in proposed plans.

RESQIVO is a decision-support prototype. It does not replace emergency services, public authorities, trained responders, or official emergency instructions.

## 2. Problem Statement

During a disaster, planners may need to consider changing conditions, constrained supplies, shelter capacity, evacuation routes, and competing needs. Information can be spread across documents and datasets, making it difficult to compare options consistently.

RESQIVO aims to bring scenario information, reference guidance, resource constraints, and plan evaluation into one interface. It will provide transparent recommendations and explain the evidence and assumptions behind them.

## 3. Goals

- Support multiple simulated natural-disaster scenarios, including floods, earthquakes, cyclones, wildfires, heatwaves, and tsunamis.
- Provide a clear web interface that works on desktop and mobile.
- Use Retrieval-Augmented Generation (RAG) to answer questions from an approved knowledge collection.
- Demonstrate Agentic AI through bounded agents and explicit workflow orchestration.
- Use tool calling for defined operations such as scenario lookup, resource calculations, and plan evaluation.
- Apply deterministic validation to resource quantities, capacity limits, and other hard constraints.
- Stress-test plans against changes such as blocked routes, reduced shelter capacity, or resource shortages.
- Evaluate system quality with repeatable tests and documented evaluation criteria.
- Make AI workflows observable so failures can be investigated.
- Require human review before a recommendation is treated as an operational decision.

## 4. Non-Goals and Safety Boundaries

The initial version will not:

- Dispatch real emergency services or contact emergency responders.
- Automatically issue evacuation orders or public warnings.
- Claim to predict disasters with certainty.
- Treat generated text as authoritative emergency guidance.
- Execute real-world actions or control emergency infrastructure.
- Use live sensitive personal data or real incident data unless separately approved and appropriately protected.

Use synthetic scenarios and clearly labelled demonstration data. Show uncertainty and missing evidence rather than inventing facts. Any consequential plan must be reviewed by a qualified human.

## 5. Intended Users

- Emergency-planning students and researchers.
- Disaster-management planners working with simulated scenarios.
- Reviewers evaluating AI-supported resource planning.
- Capstone evaluators assessing RAG, tool calling, agent orchestration, evaluation, and observability.

## 6. Core User Workflow

1. The user selects or creates a simulated disaster scenario.
2. The platform displays scenario conditions, affected areas, available resources, and assumptions.
3. The user asks a question or requests a draft response plan.
4. The retrieval component finds relevant material from the approved knowledge base.
5. A bounded LangGraph workflow analyses the scenario and proposes options using approved tools.
6. The deterministic validator checks resource totals and configured constraints. Application code always runs this step; the AI cannot skip it.
7. The platform presents recommendations, evidence, assumptions, limitations, and unresolved issues, with deterministic validation results shown separately from AI-generated text.
8. The user can stress-test the plan under changed conditions and compare results.
9. A human reviewer decides whether the plan is suitable for further consideration.

## 7. Technical Direction

The implementation keeps components separate so each can be tested independently.

### 7.1 Current Implementation Status

Implemented and tested in the repository:

- **Backend:** Python 3.14, FastAPI and Pydantic, with `GET /health` and `POST /validate`.
- **Deterministic validator:** `backend/app/services/validation.py` (`validate_plan`), reporting the violation codes listed in `test.md` section 4.1.
- **Frontend:** Next.js, TypeScript and Tailwind CSS, with a page that submits sample plans to `POST /validate` and displays the result.
- **Quality checks:** Ruff, pytest, and a GitHub Actions workflow for the backend.

Not yet implemented: any LLM integration, RAG, tool calling, agent orchestration, AI evaluation, or tracing. The sections below describe the approved direction, not existing functionality.

### 7.2 Approved Architecture

- **Frontend:** Next.js, TypeScript, and Tailwind CSS; responsive web interface with optional Progressive Web App (PWA) support.
- **Backend API:** Python and FastAPI with Pydantic request/response models.
- **LLM:** Google Gemini through `langchain-google-genai` (default `gemini-3.8-flash`), replacing Anthropic Claude on 2026-10-23 (`docs/model-provider.md`). The model is configured by environment variable.
- **LLM and tool integration:** LangChain.
- **Agent orchestration:** LangGraph. This replaces the previously proposed CrewAI/CrewAI Flow.
- **Knowledge retrieval:** RAG with ChromaDB as the vector store.
- **Planning and validation:** The existing deterministic Python validator remains the authority for hard constraints and resource calculations.
- **Evaluation:** RAGAS for RAG quality, subject to compatibility with the project's Python version, plus deterministic custom metrics.
- **Observability:** LangSmith tracing, disabled by default, plus structured application logs.
- **Structured data:** PostgreSQL and SQLAlchemy only if persistent storage is later required; not needed for the four capstone AI requirements.
- **Testing:** Pytest for backend logic and API behaviour; frontend tests and end-to-end tests added as the UI develops.
- **Deployment:** Containerized deployment and a hosted frontend/backend when the local prototype is stable.

Verify package compatibility and pin versions before implementation (see `plan.md`, Task 4.0).

### 7.3 Capstone AI Requirements

| Requirement | Approach | Evidence of completion |
|---|---|---|
| **RAG** | Curated official guidance indexed in ChromaDB; answers cite retrieved passages and state when evidence is insufficient. | Retrieval tests on a fixed question set; every cited passage traces to a source document. |
| **Tool calling** | The LangGraph workflow calls approved LangChain tools, including guidance search and the existing `validate_plan`. Tool arguments and results are validated. | Tests show invalid tool arguments are rejected and tool results match the underlying functions. |
| **Evaluation** | A versioned evaluation dataset; RAGAS metrics where compatible; deterministic metrics for retrieval, tool correctness, and agreement with the validator. | Repeatable evaluation reports recorded in `test.md` with model, versions, and date. |
| **Observability** | LangSmith traces of LangGraph runs when explicitly enabled; structured logs with request identifiers. | A failed workflow can be investigated from its trace or logs, which contain no secrets. |

### 7.4 AI Control Principles

- **The validator is authoritative.** Application code always runs `validate_plan` on any AI-proposed plan before a result is returned. The response's validity comes only from the validator, never from model output (`test.md` SAFE-03).
- **Bounded correction.** If validation fails, the workflow may ask the model to revise the plan a limited number of times (a fixed, configurable maximum). It then returns the latest plan with its validation failures rather than looping or reporting false success.
- **Untrusted content.** Retrieved documents and model output are treated as data. Instructions inside retrieved content cannot override application rules (SAFE-04).
- **Failures are explicit.** LLM, retrieval, or tracing failures are reported clearly, never as a successful plan (SAFE-08).
- **No external actions.** No tool can dispatch responders, issue warnings, or act outside the application (SAFE-06).
- **Secrets.** API keys come from environment variables. They are never committed, logged, or sent to the frontend (SAFE-07).
- **Key-free CI.** The default CI workflow must pass without API keys, using fake models and embeddings. Live LLM runs and evaluations run separately.

### 7.5 Knowledge Sources

The knowledge base will contain official public disaster-management guidance from:

- **NDMA India** (National Disaster Management Authority, Government of India)
- **WHO** (World Health Organization)
- **UNDRR** (United Nations Office for Disaster Risk Reduction)

Specific documents have not yet been selected. Each document added must record its title, publisher, source URL, publication date where available, and retrieval date, and must be checked against the publisher's terms of use. Only material from these publishers is in scope unless the source list is formally extended.

## 8. Key Functional Requirements

- **FR-01:** Users can view and select synthetic disaster scenarios.
- **FR-02:** Users can view scenario assumptions and available resources.
- **FR-03:** Users can ask questions grounded in the approved knowledge base.
- **FR-04:** The system can generate a draft response plan with cited or traceable supporting material where available.
- **FR-05:** The system can calculate resource allocations using deterministic tools.
- **FR-06:** The system validates plans against explicit constraints.
- **FR-07:** Users can run stress tests by changing scenario parameters.
- **FR-08:** Users can compare a baseline plan with stressed scenarios.
- **FR-09:** The system records assumptions, validation outcomes, and limitations.
- **FR-10:** The interface clearly labels simulated data and requires human review for consequential decisions.

## 9. Quality Requirements

- Keep API contracts explicit and validated.
- Make calculations reproducible for the same inputs.
- Separate LLM-generated suggestions from deterministic validation results.
- Provide useful error messages and handle missing evidence safely.
- Protect secrets using environment variables; never commit real credentials.
- Keep the interface accessible and usable on mobile screens.
- Log technical failures without exposing secrets or unnecessary personal data.
- Keep LangSmith tracing disabled unless explicitly enabled, because traces send prompts and plan data to an external service.
- Document known limitations and avoid unsupported claims about real-world effectiveness.

## 10. Success Criteria for the Initial Prototype

The initial prototype is successful when a user can:

1. Open the RESQIVO interface and choose a synthetic scenario.
2. Inspect its assumptions and resource inventory.
3. Request a draft plan and see the relevant evidence or an explicit evidence gap.
4. Run deterministic constraint checks.
5. Change one or more conditions and compare the revised outcome.
6. See clear warnings, limitations, and a human-review boundary.
7. Reproduce the main workflow using documented steps and automated tests.

## 11. Assumptions and Open Decisions

- Initial demonstrations use synthetic data only.
- The first release is a responsive web application; native mobile applications are out of scope.
- AI recommendations are advisory and are not directly executed.
- The first supported scenarios and exact resource types will be selected during planning.
- **Decided:** Anthropic Claude as the LLM provider (changed to Google Gemini on 2026-10-23); LangGraph, LangChain, ChromaDB, RAGAS, and LangSmith as the AI stack; NDMA India, WHO, and UNDRR as knowledge publishers.
- **Open:** the specific guidance documents, the embedding model, the maximum number of correction attempts, whether RAGAS runs on Python 3.14 or in a separate evaluation environment, and the hosting, authentication, and final deployment architecture.
