// Priority ordering and response timers for the live incident queue, as in
// computer-aided dispatch systems: the most urgent active incident is first,
// and an unacknowledged critical incident escalates after a set time.

import type { Incident } from "@/lib/api";

const SEVERITY_RANK: Record<string, number> = { critical: 0, high: 1, moderate: 2, low: 3 };
const STATUS_RANK: Record<Incident["status"], number> = { new: 0, acknowledged: 1, closed: 2 };

/** An unacknowledged critical incident is overdue after this many seconds. */
export const OVERDUE_AFTER_SECONDS = 60;

/** Active before closed; then most severe; then waiting longest. */
export function byPriority(a: Incident, b: Incident): number {
  const closed = Number(a.status === "closed") - Number(b.status === "closed");
  if (closed) return closed;
  const severity = SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity];
  if (severity) return severity;
  const status = STATUS_RANK[a.status] - STATUS_RANK[b.status];
  if (status) return status;
  return Date.parse(a.created_at) - Date.parse(b.created_at);
}

export function sortByPriority(incidents: readonly Incident[]): Incident[] {
  return [...incidents].sort(byPriority);
}

function secondsBetween(fromIso: string, to: number): number {
  const from = Date.parse(fromIso);
  // Never negative, even if the browser clock is slightly behind the server's.
  return Number.isNaN(from) ? 0 : Math.max(0, Math.floor((to - from) / 1000));
}

/** "45s", "2m 05s", "1h 03m". */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${String(seconds % 60).padStart(2, "0")}s`;
  return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, "0")}m`;
}

export interface ResponseTimer {
  label: string;
  overdue: boolean;
}

/** The timer shown for an incident at time now (milliseconds). */
export function responseTimer(incident: Incident, now: number): ResponseTimer {
  if (incident.status === "new") {
    const waiting = secondsBetween(incident.created_at, now);
    const overdue = incident.severity === "critical" && waiting >= OVERDUE_AFTER_SECONDS;
    return { label: `${overdue ? "Overdue" : "Waiting"} ${formatDuration(waiting)}`, overdue };
  }
  if (incident.status === "acknowledged") {
    // updated_at is the latest status change, which for an acknowledged
    // incident is its acknowledgement: the time from report to acknowledgement.
    const acknowledged = Date.parse(incident.updated_at);
    const response = Number.isNaN(acknowledged) ? 0 : secondsBetween(incident.created_at, acknowledged);
    return { label: `Acknowledged in ${formatDuration(response)}`, overdue: false };
  }
  return { label: "Closed", overdue: false };
}
