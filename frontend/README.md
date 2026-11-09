# RESQIVO frontend

A Next.js 16 dashboard for the RESQIVO FastAPI backend. It uses React 19, TypeScript and Tailwind CSS 4. **Simulated, synthetic data only. Decision support for human review; nothing is ever dispatched.**

## What it does

| Panel | Endpoint | Shows |
|---|---|---|
| Backend status (header) | `GET /health` | Online or unavailable, with refresh/retry |
| Scenario workspace | — | Editable scenario, resources, shelters, allocations, needs and constraints, starting from two synthetic samples |
| Validate allocations | `POST /validate` | **Deterministic validation (authoritative)**: passed rules or violations |
| Draft a response plan | `POST /draft-plan` | **"Draft — requires human review"**, proposed allocations, validation, guidance with citations, limitations and request ID |
| Review a plan | `POST /review` | Grounded answer with citations, plus validation before and after at most two AI corrections |
| Ask the knowledge base | `POST /answer` | Grounded answer with citations, or an explicit "insufficient evidence" |
| Incident queue, simulation controls, live incident panel | `GET/POST/PATCH/DELETE /incidents`, `POST /incidents/simulate`, `GET /incidents/stream` | The simulated live incident feed, updated through server-sent events (`docs/incidents.md`) |
| Call Intake | `POST /incidents/intake`, `POST /incidents` | AI-suggested incident fields from a simulated call transcript, reviewed by the operator before creation |

Request and response types in `lib/api.ts` mirror the backend's Pydantic models. Every response is shape-checked before it is displayed.

## Layout

An emergency operations centre layout with a **light theme by default** (white panels on a soft grey canvas, slate text, deep cyan accent) and a **dark theme** switch in the header, remembered in the browser. Amber, red and green are reserved for warning, critical and success states. All colours are theme tokens in `app/globals.css`, and status text keeps at least 4.5:1 contrast in both themes. On large screens the header is fixed and the sidebar and content scroll separately; on smaller screens the sidebar becomes a horizontal bar. There is a skip link, and every control has a visible focus outline.

- **Header:** RESQIVO identity, "Emergency Operations Center", a **Simulation** label, and the backend status from `GET /health`, with **Refresh** (or **Retry** after a failure).
- **Sidebar** (each item scrolls to a working section):
  - **Dashboard:**
    - key figures: affected population, resources, shelters with an occupancy bar, allocations, the latest validation and the latest draft;
    - the **incident queue**: the synthetic scenarios plus an edited workspace, with Severity and Type filters;
    - **simulation controls** (Flood, Cyclone, Replace existing, Clear with confirmation) and a **Live / Scenarios** incident queue;
    - the **operational map**, in two modes: **Chennai map** (live incidents via Leaflet on dark OpenStreetMap streets or Esri satellite imagery, with World view; needs internet) or a dark map of a *fictional* city, labelled "Fictional city — not a real place":
      - each distinct location name gets a fixed slot (`lib/map-layout.ts`), since the data has no coordinates;
      - shelters are coloured by occupancy, supply points are shown, and proposed allocations are drawn as routes;
      - the affected area is tinted by severity;
      - collapsible **Layers** toggles, a legend, and a warning for allocations to unknown shelters;
      - no map library, tiles or outside service is used;
    - the **incident detail panel**, with Status, Incident and Map selection tabs. Status keeps deterministic validation, the AI draft, AI-assisted review and human review separate; selecting a marker opens its details.
  - **AI Workflow:** the five-stage pipeline and the **alerts** panel.
  - **Incidents:** the sample selector and scenario fields.
  - **Resources** and **Shelters:** the editable tables.
  - **Knowledge Base:** the sources cited in this session, with PDF pages, plus how documents are indexed.
  - **Ask RESQIVO:** the Ask panel.
  - **Draft Plans:** needs, constraints, the full safety disclaimer and the Draft panel.
  - **Review:** allocations, plus the Validate and Review panels.
  - **Reports** is listed as not available; there is no backend support for it.

**Honest figures:**
- **Cards:** computed only from the entered workspace and real API results. A total is "—" when any value it depends on is not a valid whole number. The validation and draft cards say "Not run" until a request returns.
- **Incidents:** the backend has no incident list, so the queue holds the synthetic samples. Only the selected incident has a status, derived from its latest validation and draft. Selecting another incident clears the previous results.
- **Alerts** (`lib/alerts.ts`): only shelters at or above 90% or over capacity, validator violations, failed requests, and drafts that failed the rules or have no evidence. Nothing else is generated.
- **Workflow** (`lib/workflow.ts`): stages are derived only from the latest `/draft-plan` response, and the API reports no durations or scores, so none are shown.
  - **Completed:** shown only when the response confirms it.
  - **Not configured:** shown when the backend says AI features are not configured (HTTP 503).
  - **Human review:** always "Waiting for review"; it is never completed.
- **Knowledge base** (`lib/evidence.ts`): the API has no endpoint that lists indexed documents, so the view shows only sources cited in this session. Page numbers come from the `#page=N` that the backend adds to citation URLs for PDF passages. File names are not returned by the API.

## Safety behaviour in the UI

- **The validator decides validity.** Validator results are labelled "Deterministic validation (authoritative)". AI text is labelled "AI-generated — not validated guidance". A draft that passes the validator is described only as passing the configured rules, never as safe.
- **No invented numbers.** Quantities and capacities come only from the workspace inputs. Cells are sent as typed: whole numbers become numbers, and anything else is sent unchanged for the backend to reject (HTTP 422). Values are never rounded or filled in.
- **AI proposals stay separate.** Drafts and corrections are shown as proposals and are never copied into the workspace.
- **Nothing is dispatched.** There is no dispatch, booking or messaging control, and no request is made automatically except the health check.
- **Citations are untrusted reference material.**
  - Each citation shows its source, publisher and synthetic flag.
  - Only `http(s)` URLs become links, opened with `rel="noopener noreferrer nofollow"`; anything else, such as the synthetic `urn:` IDs, is shown as text.
  - All API text is rendered as text, never as HTML.
- **Backend notices are always shown,** including the draft notice and limitations.

### Disaster location

- **From samples.** Selecting a sample fills the location from that sample's own `scenarioLocation` (`lib/sample-plans.ts`). A sample without one leaves the field empty, so a location is never invented.
- **"Use my current location"** uses the browser Geolocation API (`lib/geolocation.ts`):
  - **Permission:** requested only when the button is pressed, never on page load.
  - **Never automatic:** your position is only *shown*, as coordinates with their accuracy, alongside a reminder that it may not be the disaster location. The field changes only when you press **"Use these coordinates as the disaster location"**; **Dismiss** leaves it unchanged.
  - **No external service.** No reverse geocoding is done, so a place name is not looked up. The inserted text is the coordinates (4 decimal places, about 11 m), which you can edit into a readable place name.
  - **Errors:** permission denied, position unavailable, timeout (10 s), an unsupported browser and an insecure page each show a clear message and leave the field unchanged.
  - **Privacy:** once inserted, the coordinates are part of the scenario sent to the backend and to the AI model in draft requests.
- **Always editable:** the field is free text, up to the backend's 200-character limit.

## Setup

Requirements: Node.js 24 and npm 11, the versions this was tested with. The backend must be running (see `docs/test.md` section 3.6).

```bash
cd frontend
npm install
cp .env.example .env.local      # optional: only to change the API URL
npm run dev                     # http://resqivo.localhost:3000 (or http://localhost:3000)
```

`resqivo.localhost` is a loopback alias: Chrome, Edge and Firefox send any `*.localhost` name to this machine, so no `/etc/hosts` entry is needed, and the page stays a secure context (device location keeps working). Safari may not resolve it; use `http://localhost:3000` there, with `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8002`. `next.config.ts` lists it in `allowedDevOrigins`.

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `http://127.0.0.1:8000` | Backend base URL. Inlined into the browser bundle at build time, so **never put a secret here**. |

The frontend holds no API keys. `/answer`, `/review` and `/draft-plan` need `GOOGLE_API_KEY` (Gemini) set **on the backend**, never in the frontend or a `NEXT_PUBLIC_` variable. Without it they return HTTP 503, and the UI says AI features are not configured; validation still works.

The backend accepts browser requests only from `http://localhost:3000`, `http://127.0.0.1:3000` and `http://resqivo.localhost:3000` (CORS in `backend/app/main.py`).

### Error messages

| HTTP status | Shown to the user |
|---|---|
| network failure | The API at the configured URL cannot be reached |
| 413 | The request is too large; reduce resources, shelters or allocations |
| 422 | The inputs were rejected, with each field and the backend's message |
| 502 | The language model returned no usable result; nothing was produced |
| 503 | AI features not configured, knowledge retrieval unavailable, or the service is unavailable |
| 504 | The request did not complete in time; nothing was produced |
| other | An unexpected error, with the status code only |

Raw error bodies and stack traces are never displayed.

## Checks

```bash
npm test            # Vitest + React Testing Library (jsdom); fetch is stubbed, no backend needed
npm run test:watch  # watch mode
npm run lint        # ESLint
npx tsc --noEmit    # type check
```

The tests never call a real backend or model.

`npm run build` and `npm run dev` load the Geist font through `next/font/google`, which downloads it from Google at build or dev time. Visitors' browsers do not contact Google.

## Manual verification

1. Start the backend:

   ```bash
   cd backend
   ../.venv/bin/python -m uvicorn app.main:app --port 8000
   ```

2. Start the frontend with `npm run dev`, then open http://resqivo.localhost:3000.
3. **API status** shows **Online**. Stop the backend and press **Retry**: it shows **Unavailable** with the API URL.
4. **Validate plan** with the *within limits* sample: **Passed configured rules**. With the *with problems* sample: violations `DOM-04`, `DOM-05` and `DOM-06-UNKNOWN-DESTINATION`.
5. Change a resource quantity to `12.5` and validate: an HTTP 422 alert names `resources.0.quantity_available`.
6. **Without `GOOGLE_API_KEY` on the backend**, **Generate draft plan**, **Review plan** and **Ask** show the HTTP 503 "not configured" message. Validation still works.
7. **Disaster location:**
   - Switch samples: the location changes to *Simulated District A* or *B*.
   - Press **Use my current location**: the browser asks for permission at that moment. Allow it and the coordinates appear, but the field changes only after **Use these coordinates as the disaster location**.
   - Block the permission: a "permission was denied" message appears and the field is unchanged.
8. With a key, and only if you intend to spend API credit:
   - drafts show **Draft — requires human review**;
   - answers show citations, or **Insufficient evidence**;
   - the workspace is unchanged after a draft.

## Layout

```text
app/page.tsx                    page shell (server component)
app/dashboard.tsx               app shell, workspace state and sections (client)
app/components/app-header.tsx   identity, synthetic-data label, API health
app/components/sidebar.tsx      section navigation (implemented sections only)
app/components/overview.tsx     scenario summary and cards
app/components/workflow.tsx     agentic workflow tracker
app/components/health-status.tsx
app/components/workspace-editor.tsx
app/components/location-field.tsx  disaster location with opt-in device location
app/components/panels.tsx       Validate, Draft, Review and Ask panels
app/components/results.tsx      validation, answer, citation and plan-review views
lib/api.ts                      typed API client and error mapping
lib/workspace.ts                workspace model and request builders
lib/sample-plans.ts             synthetic samples
lib/safe-url.ts                 http(s)-only citation links
lib/geolocation.ts              browser Geolocation API wrapper and error messages
lib/use-request.ts              loading, error and abort handling
lib/summary.ts                  overview figures from entered values only
lib/workflow.ts                 workflow stages from real draft results only
tests/                          Vitest tests
```
