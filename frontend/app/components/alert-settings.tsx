"use client";

import type { IncidentAlerts } from "@/lib/use-incident-alerts";

const toggle =
  "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs disabled:cursor-not-allowed disabled:opacity-50";

/** Header switches for sound alerts and desktop notifications. Both are off
 * until switched on, and apply to new high or critical simulated incidents. */
export default function AlertSettings({ alerts }: { alerts: IncidentAlerts }) {
  const denied = alerts.notificationSupport === "denied";
  const unsupported = alerts.notificationSupport === "unsupported";
  return (
    <div role="group" aria-label="Incident alerts" className="flex flex-wrap items-center gap-2">
      <span className="text-xs font-medium uppercase tracking-wider text-muted">Alerts</span>
      {alerts.alarm.active && (
        <button
          type="button"
          onClick={alerts.silence}
          title="Silences the alarm until another critical incident arrives. Acknowledging the critical incidents also stops it."
          className="resqivo-alarm-pill inline-flex items-center gap-1.5 rounded-md border border-red-500/60 bg-red-500/15 px-2 py-0.5 text-xs font-semibold text-bad-ink"
        >
          <span aria-hidden="true" className="size-2 rounded-full bg-current" />
          Alarm · {alerts.alarm.count} critical unacknowledged · Silence
        </button>
      )}
      <button
        type="button"
        role="switch"
        aria-checked={alerts.sound}
        onClick={() => alerts.setSound(!alerts.sound)}
        title="Plays a tone when a new high or critical simulated incident arrives"
        className={`${toggle} ${
          alerts.sound
            ? "border-accent/60 bg-accent/10 text-accent"
            : "border-line text-ink hover:border-accent/60"
        }`}
      >
        <span aria-hidden="true">{alerts.sound ? "🔔" : "🔕"}</span>
        Sound {alerts.sound ? "on" : "off"}
      </button>
      {!unsupported && (
        <button
          type="button"
          role="switch"
          aria-checked={alerts.notifications}
          disabled={denied}
          onClick={() => void alerts.setNotifications(!alerts.notifications)}
          title={
            denied
              ? "Notifications are blocked for this site in your browser settings"
              : "Shows a desktop notification when the RESQIVO tab is in the background"
          }
          className={`${toggle} ${
            alerts.notifications
              ? "border-accent/60 bg-accent/10 text-accent"
              : "border-line text-ink hover:border-accent/60"
          }`}
        >
          Desktop {alerts.notifications ? "on" : denied ? "blocked" : "off"}
        </button>
      )}
    </div>
  );
}
