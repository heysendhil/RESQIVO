"use client";

import { useEffect, useId, useRef, useState } from "react";

import {
  createIncident,
  DISASTER_TYPES,
  intakeCall,
  INTAKE_LIMITS,
  RESOURCE_TYPES,
  SEVERITIES,
  type Incident,
  type IncidentCreate,
  type IncidentDraft,
  type IntakeResponse,
} from "@/lib/api";
import { useRequest } from "@/lib/use-request";

import { readable } from "./incident-queue";
import { primaryButton } from "./panels";
import { AI_LABEL, Badge, ErrorAlert, Loading } from "./results";

// Browser speech recognition (Chrome, Edge, Safari). Not in TypeScript's DOM types.
interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start: () => void;
  stop: () => void;
}

function speechRecognition(): (new () => SpeechRecognitionLike) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as Record<string, unknown>;
  return ((w.SpeechRecognition ?? w.webkitSpeechRecognition) as new () => SpeechRecognitionLike) ?? null;
}

interface FormState {
  title: string;
  disaster_type: string;
  severity: string;
  location: string;
  affected_people: string;
  needs: string[];
  summary: string;
  lat: string;
  lon: string;
}

const EMPTY: FormState = {
  title: "",
  disaster_type: "",
  severity: "",
  location: "",
  affected_people: "",
  needs: [],
  summary: "",
  lat: "",
  lon: "",
};

function fromDraft(draft: IncidentDraft): FormState {
  return {
    title: draft.title ?? "",
    disaster_type: draft.disaster_type ?? "",
    severity: draft.severity ?? "",
    location: draft.location ?? "",
    affected_people: draft.affected_people === null ? "" : String(draft.affected_people),
    needs: draft.needs,
    summary: draft.summary,
    lat: "",
    lon: "",
  };
}

const WHOLE = /^\d+$/;
const DECIMAL = /^-?\d+(\.\d+)?$/;

/** Problems that stop the incident being created, and the fields still missing. */
export function checkForm(form: FormState): { problems: string[]; missing: string[] } {
  const problems = [];
  if (!form.title.trim()) problems.push("Enter a title.");
  if (!form.disaster_type) problems.push("Choose a disaster type.");
  if (!form.severity) problems.push("Choose a severity.");
  if (!form.location.trim()) problems.push("Enter a location.");
  if (form.affected_people.trim() && !WHOLE.test(form.affected_people.trim())) {
    problems.push("People affected must be a whole number, or left empty.");
  }
  const lat = form.lat.trim();
  const lon = form.lon.trim();
  if (lat || lon) {
    if (!DECIMAL.test(lat) || !DECIMAL.test(lon)) {
      problems.push("Enter both latitude and longitude as numbers, or neither.");
    } else if (Math.abs(Number(lat)) > 90 || Math.abs(Number(lon)) > 180) {
      problems.push("Latitude must be within ±90 and longitude within ±180.");
    }
  }
  const missing = form.affected_people.trim() ? [] : ["number of people affected"];
  return { problems, missing };
}

function toRequest(form: FormState, source: IncidentCreate["source"], missing: string[]): IncidentCreate {
  return {
    title: form.title.trim(),
    disaster_type: form.disaster_type as IncidentCreate["disaster_type"],
    severity: form.severity as IncidentCreate["severity"],
    summary: form.summary.trim(),
    location: form.location.trim(),
    coordinates:
      form.lat.trim() && form.lon.trim()
        ? { lat: Number(form.lat), lon: Number(form.lon) }
        : null,
    affected_people: form.affected_people.trim() ? Number(form.affected_people) : null,
    needs: form.needs,
    missing_fields: missing,
    source,
  };
}

function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: (id: string) => React.ReactNode;
  hint?: string;
}) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1 text-sm">
      <label htmlFor={id} className="text-ink">
        {label}
      </label>
      {children(id)}
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </div>
  );
}

const input =
  "rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink placeholder:text-muted/70 focus:border-accent";

/** Simulated call intake: an operator types or dictates what a caller says,
 * the AI suggests incident fields, and the operator corrects and confirms them
 * before an incident is created. */
export default function CallIntake({ onCreated }: { onCreated: (incident: Incident) => void }) {
  const [transcript, setTranscript] = useState("");
  const [form, setForm] = useState<FormState | null>(null);
  const [source, setSource] = useState<IncidentCreate["source"]>("call");
  const [listening, setListening] = useState(false);
  const [speechError, setSpeechError] = useState<string | null>(null);
  const recognizer = useRef<SpeechRecognitionLike | null>(null);
  const analysis = useRequest<IntakeResponse>();
  const creation = useRequest<Incident>();
  const transcriptId = useId();
  const [canDictate, setCanDictate] = useState(false);

  useEffect(() => {
    const id = setTimeout(() => setCanDictate(speechRecognition() !== null), 0);
    return () => {
      clearTimeout(id);
      recognizer.current?.stop();
    };
  }, []);

  function toggleDictation() {
    if (listening) {
      recognizer.current?.stop();
      return;
    }
    const Recognition = speechRecognition();
    if (!Recognition) return;
    const recognition = new Recognition();
    recognition.lang = "en-IN";
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      let text = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) text += event.results[i][0].transcript;
      }
      if (text) {
        setTranscript((current) =>
          `${current}${current && !current.endsWith(" ") ? " " : ""}${text.trim()}`.slice(
            0,
            INTAKE_LIMITS.transcriptChars,
          ),
        );
      }
    };
    recognition.onerror = () => setSpeechError("Dictation stopped: the browser could not recognise speech.");
    recognition.onend = () => setListening(false);
    recognizer.current = recognition;
    setSpeechError(null);
    setListening(true);
    recognition.start();
  }

  async function analyse() {
    creation.reset();
    await analysis.run(async (signal) => {
      const result = await intakeCall(transcript.trim(), signal);
      setForm(fromDraft(result.draft));
      setSource("call");
      return result;
    });
  }

  function manual() {
    analysis.reset();
    creation.reset();
    setForm({ ...EMPTY });
    setSource("manual");
  }

  const check = form ? checkForm(form) : null;
  const set = (key: keyof FormState, value: string | string[]) =>
    setForm((current) => (current ? { ...current, [key]: value } : current));

  async function create() {
    if (!form || !check || check.problems.length) return;
    const request = toRequest(form, source, check.missing);
    await creation.run(async (signal) => {
      const incident = await createIncident(request, signal);
      onCreated(incident);
      setForm(null);
      setTranscript("");
      analysis.reset();
      return incident;
    });
  }

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <section aria-labelledby="call-heading" className="flex flex-col gap-3 rounded-lg border border-line bg-panel p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 id="call-heading" className="text-sm font-semibold uppercase tracking-wider text-ink">
            Simulated call
          </h3>
          <Badge tone="draft">Training simulation · not an emergency line</Badge>
        </div>
        <p className="text-xs text-muted">
          Type or dictate what the caller says. RESQIVO does not receive real calls. In a
          real emergency, contact local emergency services.
        </p>
        <div className="flex flex-col gap-1 text-sm">
          <label htmlFor={transcriptId} className="font-medium text-ink">
            Call transcript
          </label>
          <textarea
            id={transcriptId}
            value={transcript}
            maxLength={INTAKE_LIMITS.transcriptChars}
            rows={7}
            onChange={(event) => setTranscript(event.target.value)}
            placeholder="Caller: water is entering our homes on 3rd Main Road, Velachery. There are 45 people here…"
            className={input}
          />
          <span className="text-xs text-muted">
            {transcript.length} / {INTAKE_LIMITS.transcriptChars} characters
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className={primaryButton}
            disabled={!transcript.trim() || analysis.state.status === "loading"}
            onClick={() => void analyse()}
          >
            {analysis.state.status === "loading" ? "Analysing…" : "Analyse call with AI"}
          </button>
          {canDictate && (
            <button
              type="button"
              aria-pressed={listening}
              onClick={toggleDictation}
              className="rounded-lg border border-line px-3 py-2 text-sm text-ink hover:border-accent/60 hover:bg-accent/10"
            >
              {listening ? "Stop dictation" : "Dictate"}
            </button>
          )}
          <button
            type="button"
            onClick={manual}
            className="rounded-lg border border-line px-3 py-2 text-sm text-ink hover:border-accent/60 hover:bg-accent/10"
          >
            Enter manually (no AI)
          </button>
        </div>
        {canDictate && (
          <p className="text-xs text-muted">
            Dictation uses your browser&apos;s speech recognition. In Chrome, audio is sent to
            Google for transcription. It starts only when you press Dictate.
          </p>
        )}
        {speechError && <p className="text-xs text-warn-ink">{speechError}</p>}
        <div aria-live="polite">
          {analysis.state.status === "loading" && (
            <Loading>Extracting incident details… this can take a while.</Loading>
          )}
          {analysis.state.status === "error" && (
            <ErrorAlert message={analysis.state.message} fieldErrors={analysis.state.fieldErrors} />
          )}
          {creation.state.status === "success" && (
            <p role="status" className="rounded-md border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm text-ok-ink">
              Incident {creation.state.data.incident_id} created and added to the live queue.
            </p>
          )}
        </div>
      </section>

      <section aria-labelledby="intake-form-heading" className="flex flex-col gap-3 rounded-lg border border-line bg-panel p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 id="intake-form-heading" className="text-sm font-semibold uppercase tracking-wider text-ink">
            Review incident
          </h3>
          {form && source === "call" && <Badge tone="info">{AI_LABEL}</Badge>}
          {form && source === "manual" && <Badge tone="neutral">Manual entry</Badge>}
        </div>
        {!form ? (
          <p className="rounded-md border border-dashed border-line p-6 text-center text-sm text-muted">
            Analyse a call, or enter an incident manually, to review it here before it is
            created.
          </p>
        ) : (
          <>
            {analysis.state.status === "success" && (
              <>
                <p className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-warn-ink">
                  {analysis.state.data.notice}
                </p>
                {analysis.state.data.missing_fields.length > 0 && (
                  <div className="text-xs">
                    <p className="font-semibold text-ink">Not stated in the call — ask the caller:</p>
                    <ul className="mt-1 flex flex-wrap gap-1.5">
                      {analysis.state.data.missing_fields.map((field) => (
                        <li key={field}>
                          <Badge tone="draft">{field}</Badge>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <Field label="Title">
                  {(id) => <input id={id} value={form.title} maxLength={120} onChange={(e) => set("title", e.target.value)} className={input} />}
                </Field>
              </div>
              <Field label="Disaster type">
                {(id) => (
                  <select id={id} value={form.disaster_type} onChange={(e) => set("disaster_type", e.target.value)} className={input}>
                    <option value="">Choose…</option>
                    {DISASTER_TYPES.map((t) => <option key={t} value={t}>{readable(t)}</option>)}
                  </select>
                )}
              </Field>
              <Field label="Severity" hint={source === "call" ? "AI-suggested from the description; confirm it." : undefined}>
                {(id) => (
                  <select id={id} value={form.severity} onChange={(e) => set("severity", e.target.value)} className={input}>
                    <option value="">Choose…</option>
                    {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                )}
              </Field>
              <div className="sm:col-span-2">
                <Field label="Location">
                  {(id) => <input id={id} value={form.location} maxLength={200} onChange={(e) => set("location", e.target.value)} className={input} />}
                </Field>
              </div>
              <Field label="People affected" hint="Leave empty if the caller did not say.">
                {(id) => <input id={id} inputMode="numeric" value={form.affected_people} onChange={(e) => set("affected_people", e.target.value)} className={input} />}
              </Field>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Latitude">
                  {(id) => <input id={id} inputMode="decimal" value={form.lat} onChange={(e) => set("lat", e.target.value)} className={input} />}
                </Field>
                <Field label="Longitude">
                  {(id) => <input id={id} inputMode="decimal" value={form.lon} onChange={(e) => set("lon", e.target.value)} className={input} />}
                </Field>
              </div>
              <p className="text-xs text-muted sm:col-span-2">
                Coordinates are optional; enter them only if confirmed. Without them the
                incident is listed but not shown on the map. The AI never supplies coordinates.
              </p>
              <fieldset className="flex flex-col gap-1.5 sm:col-span-2">
                <legend className="text-sm text-ink">Needs</legend>
                <div className="flex flex-wrap gap-x-4 gap-y-1">
                  {RESOURCE_TYPES.map((need) => (
                    <label key={need} className="flex items-center gap-1.5 text-xs text-ink">
                      <input
                        type="checkbox"
                        checked={form.needs.includes(need)}
                        onChange={(e) =>
                          set("needs", e.target.checked ? [...form.needs, need] : form.needs.filter((n) => n !== need))
                        }
                        className="size-3.5 accent-accent"
                      />
                      {readable(need)}
                    </label>
                  ))}
                </div>
              </fieldset>
              <div className="sm:col-span-2">
                <Field label="Summary">
                  {(id) => <textarea id={id} rows={3} maxLength={2000} value={form.summary} onChange={(e) => set("summary", e.target.value)} className={input} />}
                </Field>
              </div>
            </div>
            {check && check.problems.length > 0 && (
              <ul className="list-disc pl-5 text-xs text-warn-ink">
                {check.problems.map((problem) => <li key={problem}>{problem}</li>)}
              </ul>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                className={primaryButton}
                disabled={!check || check.problems.length > 0 || creation.state.status === "loading"}
                onClick={() => void create()}
              >
                {creation.state.status === "loading" ? "Creating…" : "Create incident"}
              </button>
              <button
                type="button"
                onClick={() => setForm(null)}
                className="rounded-lg border border-line px-3 py-2 text-sm text-ink hover:border-accent/60"
              >
                Discard
              </button>
            </div>
            {creation.state.status === "error" && (
              <ErrorAlert message={creation.state.message} fieldErrors={creation.state.fieldErrors} />
            )}
            <p className="text-xs text-muted">
              Creating an incident adds it to the simulated feed only. Nothing is dispatched
              and no one is contacted.
            </p>
          </>
        )}
      </section>
    </div>
  );
}
