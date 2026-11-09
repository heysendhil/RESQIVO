# RESQIVO — Simulated Live Incidents, Call Intake and Maps

**Status:** implemented on 2026-10-23. Tested offline with fake models and a fake map library (`backend/tests/test_incidents.py`, `frontend/tests/live-incidents.test.tsx`). **No live Gemini call was made for call intake.**

**Every incident is simulated.** RESQIVO does not receive real emergency calls and does not dispatch, book or contact anyone. The API notice, the queue, the detail panel and the call-intake panel all say so.

## 1. Backend (`backend/app/incidents/`)

| Endpoint | Purpose |
|---|---|
| `GET /incidents?status=&limit=` | Incidents, newest first, with a `version` and the simulation notice |
| `POST /incidents` | Create an incident from a manual entry or a reviewed call (`source`: `manual` or `call`). Returns 201 |
| `PATCH /incidents/{incident_id}` | An operator's status change: `new`, `acknowledged` or `closed`. RESQIVO never changes a status itself |
| `POST /incidents/simulate` | Generate synthetic Chennai incidents: `scenario` (`flood` or `cyclone`), `count` (1–20, default 8), `reset_existing`, optional `seed` for repeatable runs |
| `DELETE /incidents` | Delete every incident (all are simulated) |
| `GET /incidents/stream` | Server-sent events. An `incidents` event carries only `{"version": n}` whenever the feed changes; clients then refetch the list. A keepalive comment is sent every 15 s |
| `POST /incidents/intake` | AI extraction from a simulated call transcript (section 3). Stores nothing |

The five original endpoints and their contracts are unchanged. The CORS policy now also allows `PATCH` and `DELETE`, still only from the listed local origins.

**Storage.** A SQLite file (standard library only) at `RESQIVO_INCIDENT_DB`. The default is `data/incidents/incidents.db`, which is ignored by Git. At most 500 incidents are held; beyond that, creation and simulation return 409.

**Errors.**
- 404: unknown incident.
- 409: incident limit reached.
- 422: invalid input. Unknown fields, `"source": "simulation"` on create, out-of-range coordinates and a `dispatched` status are all rejected.
- Intake reuses the existing model errors: 503 not configured, 502 model failure, 504 time budget used up.

**Location confidence**, set by the server:

| Value | Meaning |
|---|---|
| `simulated` | Simulator coordinates: an approximate neighbourhood centre plus a small random offset |
| `operator_entered` | Coordinates typed by an operator |
| `unconfirmed` | No coordinates; text only, so the incident is not shown on the map |

## 2. Simulation

`simulation.py` produces fictional incidents in real Chennai neighbourhoods:
- **Floods:** inland areas such as Velachery, Mudichur and Saidapet.
- **Cyclones:** coastal areas such as Royapuram, Ennore and Besant Nagar.

Every incident is clearly marked:
- titles start with `SIMULATED:`;
- locations end with `Chennai (simulated)`;
- summaries say the figures are synthetic.

Severity, people affected, needs and missing fields are randomised. The neighbourhood centres are approximate and do not identify any real address or event.

## 3. Call intake

1. **Transcript.** An operator types the call, or dictates it with the browser's speech recognition (section 5).
2. **Extraction.** `POST /incidents/intake` asks Gemini for a JSON object: title, disaster type, severity, location, people affected, needs and summary.
   - The transcript is HTML-escaped inside `<call_transcript>` delimiters and treated as untrusted data.
   - The model is never asked for coordinates.
3. **Checks against the transcript.**
   - A **location** must appear in the transcript, and a **people count** must appear in it as digits. Otherwise the value is discarded.
   - Invalid enums and needs are dropped.
   - Missing required facts are listed under `missing_fields`.
4. **Draft only.** The response is a draft labelled "AI-extracted … verify". The operator corrects it and presses **Create incident**; only then is anything stored.

## 4. Frontend

- **Incident queue:**
  - a **Live** tab for the backend feed, with Severity, Type and Status filters and the feed state (Live, Polling, Reconnecting);
  - a **Scenarios** tab for the planning samples.
- **Simulation controls:** Flood simulation, Cyclone simulation, Replace existing incidents, and Clear all incidents, which needs a confirming second click.
- **Live incident detail:**
  - type, location and its source, coordinates, people affected, needs and missing fields;
  - operator actions: Acknowledge, Close and Reopen;
  - **Plan response in workspace**, which copies the incident's facts into the scenario workspace so the existing draft, validation and human-review workflow can run on it.
- **Call Intake section:** transcript, Dictate, Analyse call with AI, Enter manually (no AI), and an editable review form. Coordinates are optional, and the incident can be created only once the title, type, severity and location are present.
- **Map modes:**
  - **Fictional city:** the planning workspace's zones, shelters and supply points; no network use.
  - **Chennai map:** live incidents with coordinates, coloured by severity, on Leaflet 1.9.4. **Streets** uses OpenStreetMap tiles darkened by a CSS filter; **Satellite** uses Esri World Imagery, with Esri's place-name labels on top. **World view** zooms out to the whole globe, and **Zoom to incidents** returns to the incidents, or to Chennai when none have coordinates. Selecting an incident with coordinates switches to this mode. Tooltips are built with `textContent`, so incident text is never rendered as HTML.
- **Live updates:** the feed uses the server-sent stream, and falls back to polling every 10 s where `EventSource` is unavailable. Only the newest list request may update the screen.

### 4.0 Automatic response pipeline (`lib/pipeline.ts`, `response-pipeline.tsx`)

After every Flood or Cyclone simulation, the **most urgent new incident** is taken through the workflow automatically. "Most urgent" means highest severity, then most people affected; incidents that were already in the feed are ignored.

1. **Incident received:** the simulated incident.
2. **Intake recorded:** the simulation's own facts. Missing fields are flagged; the AI is not used for this stage.
3. **AI resource allocation:** the incident's facts become the workspace scenario, and `POST /draft-plan` drafts allocations using only the workspace's **available resources, shelters, known needs and constraints**. No quantity is invented.
4. **Deterministic validation:** the draft's validator result, after at most two corrections.
5. **Human review:** **Approve plan (record decision)** or **Reject**.
   - Approval is possible only for a draft that passed the configured rules.
   - Approving acknowledges the incident and copies the approved allocations into the workspace.
   - **Nothing is dispatched, booked or requested**, and the decision is only recorded in the dashboard.
   - A failed draft can be retried.

The panel shows each stage's real state, and the existing Draft Plans and AI Workflow views show the same draft. Starting a manual plan or choosing another scenario closes the panel.

### 4.0.1 Priority queue and response timers (`lib/priority.ts`)

The **Live** queue is ordered like a dispatch queue: active incidents before closed ones, then critical → high → moderate → low, then the incident waiting longest. Each card shows a live timer: "Waiting 1m 05s" while new, "Acknowledged in 42s" once acknowledged, or "Closed". An **unacknowledged critical incident escalates after 60 s**: the card turns red with "⚠ Overdue", and the queue header counts overdue incidents. Timers use the server's `created_at` and `updated_at`, and are never negative even if the clocks differ slightly.

### 4.1 Incident alerts (`lib/alerting.ts`, `lib/use-incident-alerts.ts`)

- **What triggers an alert:** an incident that arrives in the live feed after the page has loaded and is **high** or **critical** and not closed. Incidents present on first load never alert. Low and moderate are silent.
- **Sound** (header switch, **off by default**):
  - critical plays two 880 Hz beeps; high plays one softer 660 Hz beep;
  - switching sound on plays a short chirp, which also lets the browser start audio;
  - tones are generated with the Web Audio API, so there are no audio files and no network use.
- **Desktop notifications** (header switch, off by default): browser permission is requested only when the switch is turned on. A notification appears only while the RESQIVO tab is hidden, and its text is plain text. If notifications are blocked the switch says so and is disabled; it is not shown where the browser has no notification support.
- **Continuous alarm until acknowledged (critical only):** while any critical incident is still `new` (not acknowledged or closed), a double beep repeats every 4 s, only with sound switched on. High incidents beep once on arrival and blink amber, but do not keep the alarm going. A red **"Alarm · N critical unacknowledged · Silence"** button appears in the header, and those incidents carry an **Alarm** tag in the queue. **Silence** stops it until another critical incident arrives; acknowledging or closing the critical incidents stops it permanently.
- **Blinking map markers:** on the Chennai map, unacknowledged critical incidents blink red and high ones blink amber (the selected incident never blinks and is drawn on top), at most about once per second (under the 3-per-second limit of WCAG 2.3.1). With reduced motion requested, they show a thick steady outline instead.
- **No alarm storms:** at most one arrival sound or notification every 5 seconds. A burst of new incidents plays once, at the most urgent level.
- **Not sound alone:** new high or critical incidents are marked **New** and highlighted in the queue for 8 seconds (the pulse is skipped when reduced motion is requested), and a message is announced to screen readers.
- **Saved in this browser only:** both settings are kept in `localStorage`. Everything is local and simulated; nobody is called or contacted.

## 5. Privacy and outside services

- **Map tiles** are loaded by the browser from `tile.openstreetmap.org`, which therefore sees the viewer's IP address and the map area viewed. OpenStreetMap's tile usage policy allows only light use: this suits development and demonstrations. A deployment should use its own or a commercial tile service.
- **Satellite imagery** is loaded from Esri's `server.arcgisonline.com` (World Imagery and World Boundaries and Places), which sees the same information. It worked without a key on 2026-10-23 and is attributed as Esri requires. Esri's terms of use apply: production use needs an ArcGIS account or another licensed imagery provider.
- **CARTO tiles are not used.** CARTO's free basemap returned "API KEY REQUIRED" when this was tested on 2026-10-23.
- **Dictation** uses the browser's speech recognition and starts only when **Dictate** is pressed. In Chrome, audio is sent to Google for transcription, and the panel says so.
- **Call intake** sends the transcript to Gemini, like other AI features. It is not logged; events carry only counts.

## 6. Limitations

- **Single process:** incidents live in one SQLite file, and stream change detection is per process. Several API workers would each signal only their own changes.
- **No authentication:** anyone who can reach the API can create, change or clear incidents. This is acceptable only for local simulation.
- **Grounding checks are literal:** a location or count the caller says in other words, such as "fifty" or a reordered address, is dropped and must be typed by the operator.
- **Map accessibility:** markers on the Chennai map are not keyboard-focusable. The incident queue is the keyboard route to every incident.
- **Not tested live:** call intake with real Gemini output has not been tried.
