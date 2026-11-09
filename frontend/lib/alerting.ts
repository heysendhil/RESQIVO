// Audible and desktop alerts for new simulated incidents. The rules are pure
// functions so they can be tested without a browser; the browser parts (Web
// Audio, notifications, storage) are in lib/use-incident-alerts.ts.

import type { Incident } from "@/lib/api";

export type AlertLevel = "critical" | "high";

/** Only these severities make a sound or a notification. */
export const ALERTING_SEVERITIES: readonly string[] = ["critical", "high"];

/** At most one sound or notification in this window, however many arrive. */
export const MIN_ALERT_GAP_MS = 5_000;

/** How long a new incident stays highlighted in the queue. */
export const FLASH_MS = 8_000;

/** Incidents in the feed that were not there before and are high or critical.
 * The first load (no previous IDs) never alerts: those incidents are not new. */
export function newAlertingIncidents(
  previousIds: ReadonlySet<string> | null,
  incidents: readonly Incident[],
): Incident[] {
  if (previousIds === null) return [];
  return incidents.filter(
    (incident) =>
      !previousIds.has(incident.incident_id) &&
      incident.status !== "closed" &&
      ALERTING_SEVERITIES.includes(incident.severity),
  );
}

/** The most urgent level among new incidents, or null for none. */
export function alertLevel(incidents: readonly Incident[]): AlertLevel | null {
  if (incidents.some((i) => i.severity === "critical")) return "critical";
  if (incidents.some((i) => i.severity === "high")) return "high";
  return null;
}

/** One line describing a burst of new incidents, for notifications and
 * screen-reader announcements. */
export function alertMessage(incidents: readonly Incident[]): string {
  const level = alertLevel(incidents);
  if (!level) return "";
  const lead = incidents.find((i) => i.severity === level)!;
  const others = incidents.length - 1;
  return (
    `Simulated ${level} incident: ${lead.title} (${lead.location})` +
    (others > 0 ? `, and ${others} more new incident${others === 1 ? "" : "s"}` : "")
  );
}

// Continuous alarm ------------------------------------------------------------------

/** How often the alarm repeats while it is active. */
export const ALARM_INTERVAL_MS = 4_000;

/** Critical incidents that nobody has acknowledged or closed yet. Only these
 * keep the alarm sounding; high incidents beep once on arrival and blink
 * amber on the map, but do not keep the alarm going. */
export function unacknowledgedCritical(incidents: readonly Incident[]): Incident[] {
  return incidents.filter(
    (incident) => incident.status === "new" && incident.severity === "critical",
  );
}

/** Incidents that should blink on the map: unacknowledged critical (red) and
 * high (amber). */
export function blinkLevel(incident: Incident): AlertLevel | null {
  if (incident.status !== "new") return null;
  if (incident.severity === "critical") return "critical";
  if (incident.severity === "high") return "high";
  return null;
}

export class AlertThrottle {
  private last = -Infinity;

  constructor(private readonly gapMs = MIN_ALERT_GAP_MS) {}

  /** True if an alert may fire now; records it if so. */
  allow(now: number): boolean {
    if (now - this.last < this.gapMs) return false;
    this.last = now;
    return true;
  }
}

// Tones (Web Audio) -----------------------------------------------------------------

interface Tone {
  frequency: number;
  start: number;
  duration: number;
}

/** Critical: two urgent high beeps. High: one softer, lower beep. A short
 * chirp confirms that sound has been switched on. */
export const TONES: Record<AlertLevel | "confirm", Tone[]> = {
  critical: [
    { frequency: 880, start: 0, duration: 0.18 },
    { frequency: 880, start: 0.28, duration: 0.18 },
  ],
  high: [{ frequency: 660, start: 0, duration: 0.25 }],
  confirm: [{ frequency: 520, start: 0, duration: 0.08 }],
};

const VOLUME = 0.15;

/** Play a tone with an oscillator: no audio files and no network. */
export function playTone(context: AudioContext, kind: keyof typeof TONES): void {
  const now = context.currentTime;
  for (const tone of TONES[kind]) {
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.type = "sine";
    oscillator.frequency.value = tone.frequency;
    // A short fade in and out avoids clicks.
    gain.gain.setValueAtTime(0, now + tone.start);
    gain.gain.linearRampToValueAtTime(VOLUME, now + tone.start + 0.02);
    gain.gain.linearRampToValueAtTime(0, now + tone.start + tone.duration);
    oscillator.connect(gain).connect(context.destination);
    oscillator.start(now + tone.start);
    oscillator.stop(now + tone.start + tone.duration + 0.02);
  }
}
