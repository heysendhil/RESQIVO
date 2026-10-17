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
5. Bounded AI agents analyse the scenario and propose options using approved tools.
6. A deterministic engine checks resource totals and configured constraints.
7. The platform presents recommendations, evidence, assumptions, limitations, and unresolved issues.
8. The user can stress-test the plan under changed conditions and compare results.
9. A human reviewer decides whether the plan is suitable for further consideration.

## 7. Proposed Technical Direction

The implementation should keep components separate so each can be tested independently.

- **Frontend:** Next.js, TypeScript, and Tailwind CSS; responsive web interface with optional Progressive Web App (PWA) support.
- **Backend API:** Python and FastAPI with Pydantic request/response models.
- **Agent orchestration:** CrewAI/CrewAI Flow, subject to validation against the installed versions.
- **Knowledge retrieval:** RAG pipeline with embeddings and a vector store such as ChromaDB.
- **Structured data:** PostgreSQL and SQLAlchemy when persistent storage is introduced.
- **Planning and validation:** Deterministic Python functions for hard constraints and resource calculations.
- **Testing:** Pytest for backend logic and API behaviour; frontend tests and end-to-end tests added as the UI develops.
- **Evaluation and observability:** Repeatable scenario benchmarks, retrieval/answer-quality evaluation, structured logs, and tracing as later milestones.
- **Deployment:** Containerized deployment and a hosted frontend/backend when the local prototype is stable.

These are intended choices, not evidence that any component has already been implemented. Verify package compatibility and pin versions during setup.

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
- Document known limitations and avoid unsupported claims about real-world effectiveness.

## 10. Success Criteria for the Initial Prototype

The initial prototype is successful when a user can:

1. Open the RESQIVO interface and choose a synthetic scenario.
2. inspect its assumptions and resource inventory.
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
- Hosting provider, LLM provider, vector-store configuration, authentication, and final deployment architecture must be decided before production deployment.
