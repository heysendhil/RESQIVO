"use client";

import { useId, useState } from "react";

import { DISASTER_TYPES, INCIDENT_STATUSES, SEVERITIES, type Incident } from "@/lib/api";
import { blinkLevel } from "@/lib/alerting";
import { responseTimer, sortByPriority } from "@/lib/priority";
import { useNow } from "@/lib/use-now";
import type { Incident as Scenario } from "@/lib/incidents";
import type { FeedStatus } from "@/lib/use-incidents";

import { Badge, type Tone } from "./results";

export const SEVERITY_TONE: Record<string, Tone> = {
  low: "neutral",
  moderate: "info",
  high: "draft",
  critical: "bad",
};

export const STATUS_TONE: Record<Incident["status"], Tone> = {
  new: "info",
  acknowledged: "draft",
  closed: "neutral",
};

export const SOURCE_LABEL: Record<Incident["source"], string> = {
  simulation: "Simulation",
  call: "Simulated call",
  manual: "Manual entry",
};

const SEVERITY_EDGE: Record<string, string> = {
  low: "border-l-slate-400/60",
  moderate: "border-l-sky-400/70",
  high: "border-l-amber-400/80",
  critical: "border-l-red-400/80",
};

const FEED_LABEL: Record<FeedStatus, { text: string; dot: string }> = {
  connecting: { text: "Connecting", dot: "bg-slate-400" },
  live: { text: "Live", dot: "bg-emerald-400" },
  polling: { text: "Polling", dot: "bg-sky-400" },
  reconnecting: { text: "Reconnecting", dot: "bg-amber-400" },
};

export function readable(value: string): string {
  return value.replace(/_/g, " ");
}

export function timeOf(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function Filter({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: readonly string[];
  onChange: (value: string) => void;
}) {
  const id = useId();
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={id} className="text-[0.65rem] font-semibold uppercase tracking-[0.14em] text-muted">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-md border border-line bg-canvas px-2 py-1.5 text-xs capitalize text-ink focus:border-accent"
      >
        <option value="all">All</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {readable(option)}
          </option>
        ))}
      </select>
    </div>
  );
}

const cardStyle = (severity: string, active: boolean) =>
  `flex w-full flex-col gap-1.5 rounded-md border border-l-4 p-3 text-left ${
    SEVERITY_EDGE[severity] ?? "border-l-line"
  } ${active ? "border-accent/50 bg-accent/5" : "border-line bg-canvas/50 hover:border-accent/40"}`;

function LiveCard({
  incident,
  selected,
  isNew,
  now,
  onSelect,
}: {
  incident: Incident;
  selected: boolean;
  isNew: boolean;
  now: number;
  onSelect: () => void;
}) {
  const timer = responseTimer(incident, now);
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onSelect}
      className={`${cardStyle(incident.severity, selected)} ${timer.overdue ? "border-red-500 bg-red-500/5" : ""} ${
        isNew
          ? `ring-2 motion-safe:animate-pulse ${incident.severity === "critical" ? "ring-red-400/70" : "ring-amber-400/60"}`
          : ""
      }`}
    >
      <span className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5">
          {isNew && (
            <span className="rounded bg-red-500/20 px-1.5 text-[0.6rem] font-bold uppercase tracking-wider text-bad-ink">
              New
            </span>
          )}
          <span className="font-mono text-[0.7rem] text-muted">{incident.incident_id}</span>
        </span>
        <Badge tone={SEVERITY_TONE[incident.severity] ?? "neutral"}>{incident.severity}</Badge>
      </span>
      <span className="text-sm font-semibold text-ink">{incident.title}</span>
      <span className="flex flex-wrap gap-1">
        <Badge tone={STATUS_TONE[incident.status]}>{incident.status}</Badge>
        <Badge tone="neutral">{SOURCE_LABEL[incident.source]}</Badge>
        {blinkLevel(incident) === "critical" && (
          <span
            title="Unacknowledged critical incident: keeps the alarm sounding until acknowledged or closed"
            className="inline-flex items-center gap-1 rounded-full border border-red-500/50 bg-red-500/10 px-2 py-0.5 text-xs font-semibold text-bad-ink"
          >
            <span aria-hidden="true" className="size-1.5 rounded-full bg-current" />
            Alarm
          </span>
        )}
        {incident.missing_fields.length > 0 && (
          <Badge tone="draft">{incident.missing_fields.length} missing</Badge>
        )}
      </span>
      <span className="flex justify-between gap-2 text-[0.7rem] text-muted">
        <span className="truncate">{incident.location}</span>
        <span className="shrink-0 font-mono">{timeOf(incident.created_at)}</span>
      </span>
      <span
        className={`w-fit rounded px-1.5 py-0.5 font-mono text-[0.7rem] font-semibold ${
          timer.overdue
            ? "bg-red-600 text-white"
            : incident.status === "new"
              ? "bg-panel-raised text-ink"
              : "text-muted"
        }`}
      >
        {timer.overdue && <span aria-hidden="true">⚠ </span>}
        {timer.label}
      </span>
    </button>
  );
}

/** The queue: live simulated incidents from the backend feed, and the
 * synthetic planning scenarios. */
export default function IncidentQueue({
  scenarios,
  onSelectScenario,
  live,
  liveLoaded,
  liveFailed,
  feedStatus,
  selectedIncidentId,
  onSelectIncident,
  flashing = new Set<string>(),
}: {
  scenarios: Scenario[];
  onSelectScenario: (sampleId: string) => void;
  live: Incident[];
  liveLoaded: boolean;
  liveFailed: boolean;
  feedStatus: FeedStatus;
  selectedIncidentId: string | null;
  onSelectIncident: (incidentId: string | null) => void;
  /** New high or critical incidents to highlight. */
  flashing?: ReadonlySet<string>;
}) {
  const [tab, setTab] = useState<"live" | "scenarios">("live");
  const [severity, setSeverity] = useState("all");
  const [type, setType] = useState("all");
  const [status, setStatus] = useState("all");
  const matches = (s: string, t: string) =>
    (severity === "all" || s === severity) && (type === "all" || t === type);
  // Most urgent first, as in a dispatch queue.
  const shownLive = sortByPriority(live).filter(
    (i) => matches(i.severity, i.disaster_type) && (status === "all" || i.status === status),
  );
  const now = useNow(live.some((i) => i.status === "new"));
  const overdue = live.filter((i) => responseTimer(i, now).overdue).length;
  const shownScenarios = scenarios.filter((i) =>
    matches(i.scenario.severity, i.scenario.disaster_type),
  );
  const shown = tab === "live" ? shownLive.length : shownScenarios.length;
  const feed = FEED_LABEL[feedStatus];

  return (
    <section
      aria-labelledby="queue-heading"
      className="flex h-full min-h-0 flex-col rounded-lg border border-line bg-panel"
    >
      <div className="flex flex-col gap-3 border-b border-line p-4">
        <div className="flex items-baseline justify-between gap-2">
          <h3 id="queue-heading" className="text-xs font-semibold uppercase tracking-[0.18em] text-ink">
            Incident queue
          </h3>
          <span className="text-sm font-semibold text-ink">
            {shown} <span className="text-xs font-normal text-muted">shown</span>
          </span>
        </div>
        <div role="tablist" aria-label="Queue" className="grid grid-cols-2 rounded-md border border-line p-0.5">
          {(
            [
              ["live", `Live (${live.length})`],
              ["scenarios", `Scenarios (${scenarios.length})`],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={tab === id}
              onClick={() => setTab(id)}
              className={`rounded px-2 py-1 text-xs font-semibold ${
                tab === id ? "bg-accent/15 text-accent" : "text-muted hover:text-ink"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className={`grid gap-2 ${tab === "live" ? "grid-cols-3" : "grid-cols-2"}`}>
          <Filter label="Severity" value={severity} options={SEVERITIES} onChange={setSeverity} />
          <Filter label="Type" value={type} options={DISASTER_TYPES} onChange={setType} />
          {tab === "live" && (
            <Filter label="Status" value={status} options={INCIDENT_STATUSES} onChange={setStatus} />
          )}
        </div>
        {tab === "live" ? (
          <p className="flex items-center gap-1.5 text-[0.7rem] text-muted">
            <span aria-hidden="true" className={`inline-block size-1.5 rounded-full ${feed.dot}`} />
            <span className="font-semibold text-ink">{feed.text}</span> · simulated incident feed ·
            sorted by priority
            {overdue > 0 && (
              <span className="ml-auto shrink-0 whitespace-nowrap rounded bg-red-600 px-1.5 font-semibold text-white">
                {overdue} overdue
              </span>
            )}
          </p>
        ) : (
          <p className="text-[0.7rem] text-muted">Synthetic planning scenarios with resources and shelters.</p>
        )}
      </div>

      {tab === "live" ? (
        liveFailed && !liveLoaded ? (
          <p role="status" className="m-4 rounded-md border border-amber-500/40 bg-amber-500/10 p-4 text-center text-xs text-warn-ink">
            Live incident feed unavailable. Check that the backend is running.
          </p>
        ) : !liveLoaded ? (
          <p className="m-4 text-center text-xs text-muted">Loading incidents…</p>
        ) : live.length === 0 ? (
          <p className="m-4 rounded-md border border-dashed border-line p-4 text-center text-xs text-muted">
            No incidents yet. Start a flood or cyclone simulation, or create one in Call
            Intake.
          </p>
        ) : shownLive.length === 0 ? (
          <p className="m-4 rounded-md border border-dashed border-line p-4 text-center text-xs text-muted">
            No incidents match these filters.
          </p>
        ) : (
          <ul aria-label="Live incidents" className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-3">
            {shownLive.map((incident) => (
              <li key={incident.incident_id}>
                <LiveCard
                  incident={incident}
                  selected={incident.incident_id === selectedIncidentId}
                  isNew={flashing.has(incident.incident_id)}
                  now={now}
                  onSelect={() =>
                    onSelectIncident(
                      incident.incident_id === selectedIncidentId ? null : incident.incident_id,
                    )
                  }
                />
              </li>
            ))}
          </ul>
        )
      ) : shownScenarios.length === 0 ? (
        <p className="m-4 rounded-md border border-dashed border-line p-4 text-center text-xs text-muted">
          No incidents match these filters.
        </p>
      ) : (
        <ul aria-label="Scenarios" className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-3">
          {shownScenarios.map((incident) => {
            const active = incident.active && selectedIncidentId === null;
            const body = (
              <>
                <span className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[0.7rem] text-muted">
                    {incident.scenario.scenario_id || "No scenario ID"}
                  </span>
                  <Badge tone={SEVERITY_TONE[incident.scenario.severity] ?? "neutral"}>
                    {incident.scenario.severity}
                  </Badge>
                </span>
                <span className="text-sm font-semibold capitalize text-ink">
                  {readable(incident.scenario.disaster_type)}
                </span>
                <span className="text-xs text-ink/90">{incident.label}</span>
                <span className="flex flex-wrap gap-1">
                  <Badge tone={incident.status.tone}>{incident.status.label}</Badge>
                </span>
                <span className="text-[0.7rem] text-muted">
                  {incident.scenario.location.trim() || "No location entered"}
                </span>
              </>
            );
            return (
              <li key={incident.key}>
                {incident.active ? (
                  <button
                    type="button"
                    aria-current={active ? "true" : undefined}
                    className={cardStyle(incident.scenario.severity, active)}
                    onClick={() => onSelectIncident(null)}
                  >
                    {body}
                    <span className="text-[0.65rem] font-semibold uppercase tracking-[0.14em] text-accent">
                      In workspace
                    </span>
                  </button>
                ) : (
                  <button
                    type="button"
                    className={cardStyle(incident.scenario.severity, false)}
                    onClick={() => onSelectScenario(incident.sampleId!)}
                  >
                    {body}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
