"use client";

import {
  setIncidentStatus,
  type Incident,
  type IncidentStatus,
  type LocationConfidence,
} from "@/lib/api";
import { useRequest } from "@/lib/use-request";

import { responseTimer } from "@/lib/priority";
import { useNow } from "@/lib/use-now";

import { readable, SEVERITY_TONE, SOURCE_LABEL, STATUS_TONE, timeOf } from "./incident-queue";
import { Badge, ErrorAlert } from "./results";

const CONFIDENCE: Record<LocationConfidence, string> = {
  simulated: "Simulated coordinates (approximate neighbourhood centre)",
  operator_entered: "Coordinates entered by an operator",
  unconfirmed: "Location unconfirmed: text only, not on the map",
};

const ACTIONS: Record<IncidentStatus, { status: IncidentStatus; label: string }[]> = {
  new: [
    { status: "acknowledged", label: "Acknowledge" },
    { status: "closed", label: "Close" },
  ],
  acknowledged: [{ status: "closed", label: "Close" }],
  closed: [{ status: "new", label: "Reopen" }],
};

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3 border-b border-line/60 py-1.5 text-xs last:border-0">
      <dt className="shrink-0 text-muted">{label}</dt>
      <dd className="text-right text-ink">{children}</dd>
    </div>
  );
}

/** A live (simulated) incident. Status changes are the operator's decision and
 * are only recorded; nothing is dispatched. */
export default function LiveIncidentDetails({
  incident,
  onChanged,
  onLoadIntoWorkspace,
  onBack,
}: {
  incident: Incident;
  onChanged: () => void;
  onLoadIntoWorkspace: (incident: Incident) => void;
  onBack: () => void;
}) {
  const update = useRequest<Incident>();
  const now = useNow(incident.status === "new");
  const busy = update.state.status === "loading";

  async function change(status: IncidentStatus) {
    await update.run((signal) => setIncidentStatus(incident.incident_id, status, signal));
    onChanged();
  }

  return (
    <section
      aria-labelledby="live-heading"
      className="flex h-full min-h-0 flex-col rounded-lg border border-line bg-panel"
    >
      <div className="flex flex-col gap-2 border-b border-line p-4">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-mono text-xs text-accent">{incident.incident_id}</span>
          <Badge tone={SEVERITY_TONE[incident.severity] ?? "neutral"}>{incident.severity}</Badge>
          <Badge tone={STATUS_TONE[incident.status]}>{incident.status}</Badge>
          <Badge tone="neutral">{SOURCE_LABEL[incident.source]}</Badge>
        </div>
        <h3 id="live-heading" className="text-lg font-semibold text-ink">
          {incident.title}
        </h3>
        <Badge tone="draft">Simulated incident — not a real emergency</Badge>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
        {incident.summary && <p className="text-sm leading-relaxed text-ink/90">{incident.summary}</p>}
        <dl>
          <Row label="Type">{readable(incident.disaster_type)}</Row>
          <Row label="Location">{incident.location}</Row>
          <Row label="Location source">{CONFIDENCE[incident.location_confidence]}</Row>
          {incident.coordinates && (
            <Row label="Coordinates">
              <span className="font-mono">
                {incident.coordinates.lat.toFixed(4)}, {incident.coordinates.lon.toFixed(4)}
              </span>
            </Row>
          )}
          <Row label="People affected">
            <span className="font-mono">
              {incident.affected_people === null ? "Not stated" : incident.affected_people.toLocaleString()}
            </span>
          </Row>
          <Row label="Needs">
            {incident.needs.length ? incident.needs.map(readable).join(", ") : "None stated"}
          </Row>
          <Row label="Reported">
            <span className="font-mono">{timeOf(incident.created_at)}</span>
          </Row>
          <Row label="Response">
            <span className="font-mono">{responseTimer(incident, now).label}</span>
          </Row>
        </dl>

        {incident.missing_fields.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <p className="text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-muted">
              Missing fields
            </p>
            <ul className="flex flex-col gap-1">
              {incident.missing_fields.map((field) => (
                <li
                  key={field}
                  className="flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 px-2.5 py-1.5 text-xs text-warn-ink"
                >
                  <span aria-hidden="true" className="size-1.5 rounded-full bg-amber-400" />
                  {field}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="flex flex-col gap-2 rounded-md border border-line bg-canvas/50 p-3">
          <p className="text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-muted">
            Operator actions
          </p>
          <div className="flex flex-wrap gap-2">
            {ACTIONS[incident.status].map((action) => (
              <button
                key={action.status}
                type="button"
                disabled={busy}
                onClick={() => void change(action.status)}
                className="rounded-md border border-line px-3 py-1.5 text-xs font-semibold text-ink hover:border-accent/60 hover:bg-accent/10 disabled:opacity-50"
              >
                {action.label}
              </button>
            ))}
            <button
              type="button"
              onClick={() => onLoadIntoWorkspace(incident)}
              className="rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent hover:bg-accent-strong"
            >
              Plan response in workspace
            </button>
          </div>
          <p className="text-[0.7rem] text-muted">
            Status changes only record your decision. Planning copies these facts into the
            scenario workspace for a draft plan; nothing is dispatched or contacted.
          </p>
          {update.state.status === "error" && (
            <ErrorAlert message={update.state.message} fieldErrors={update.state.fieldErrors} />
          )}
        </div>

        <button
          type="button"
          onClick={onBack}
          className="w-fit text-xs text-muted underline underline-offset-2 hover:text-ink"
        >
          Back to the workspace incident
        </button>
      </div>
    </section>
  );
}
