"use client";

import { useState } from "react";

import { clearIncidents, simulateIncidents, type IncidentList } from "@/lib/api";
import { useRequest } from "@/lib/use-request";

const button =
  "rounded-md border border-line px-3 py-1.5 text-xs font-semibold text-ink hover:border-accent/60 hover:bg-accent/10 disabled:cursor-not-allowed disabled:opacity-50";

/** Demo controls for the simulated incident feed. */
export default function SimulationControls({
  onChanged,
  currentIds = [],
  onSimulated,
  autoPlan,
  onAutoPlanChange,
}: {
  onChanged: () => void;
  /** IDs already in the feed, so the incidents a simulation adds can be told apart. */
  currentIds?: string[];
  onSimulated?: (result: IncidentList, idsBefore: ReadonlySet<string>) => void;
  /** Whether a simulation starts the AI response pipeline (uses Gemini calls). */
  autoPlan?: boolean;
  onAutoPlanChange?: (on: boolean) => void;
}) {
  const [replace, setReplace] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const request = useRequest<string>();
  const busy = request.state.status === "loading";

  async function simulate(scenario: "flood" | "cyclone") {
    setConfirmClear(false);
    const idsBefore = new Set(replace ? [] : currentIds);
    await request.run(async (signal) => {
      const result = await simulateIncidents(scenario, { resetExisting: replace }, signal);
      onSimulated?.(result, idsBefore);
      return `${scenario === "flood" ? "Flood" : "Cyclone"} simulation added incidents (${result.incidents.length} in the feed).`;
    });
    onChanged();
  }

  async function clear() {
    setConfirmClear(false);
    await request.run(async (signal) => {
      const result = await clearIncidents(signal);
      return `Cleared ${result.deleted} incident${result.deleted === 1 ? "" : "s"}.`;
    });
    onChanged();
  }

  const status =
    request.state.status === "success"
      ? request.state.data
      : request.state.status === "error"
        ? request.state.message
        : request.state.status === "loading"
          ? "Working…"
          : message;

  return (
    <div
      role="group"
      aria-label="Simulation controls"
      className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-line bg-panel px-3 py-2"
    >
      <span className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-muted">
        Simulation controls
      </span>
      <button type="button" className={button} disabled={busy} onClick={() => void simulate("flood")}>
        Flood simulation
      </button>
      <button type="button" className={button} disabled={busy} onClick={() => void simulate("cyclone")}>
        Cyclone simulation
      </button>
      <label className="flex items-center gap-1.5 text-xs text-muted">
        <input
          type="checkbox"
          checked={replace}
          onChange={(event) => setReplace(event.target.checked)}
          className="size-3.5 accent-accent"
        />
        Replace existing incidents
      </label>
      {onAutoPlanChange && (
        <label
          className="flex items-center gap-1.5 text-xs text-muted"
          title="When on, each simulation drafts an AI plan for the most urgent incident (2 Gemini calls). Switch off to rehearse without using the AI quota."
        >
          <input
            type="checkbox"
            checked={autoPlan ?? false}
            onChange={(event) => onAutoPlanChange(event.target.checked)}
            className="size-3.5 accent-accent"
          />
          Auto-plan with AI
        </label>
      )}
      {confirmClear ? (
        <span className="flex items-center gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => void clear()}
            className="rounded-md border border-red-500/50 bg-red-500/10 px-3 py-1.5 text-xs font-semibold text-bad-ink hover:bg-red-500/20"
          >
            Confirm: delete all incidents
          </button>
          <button type="button" className={button} onClick={() => setConfirmClear(false)}>
            Cancel
          </button>
        </span>
      ) : (
        <button
          type="button"
          className={button}
          disabled={busy}
          onClick={() => {
            setMessage(null);
            setConfirmClear(true);
          }}
        >
          Clear all incidents
        </button>
      )}
      <p
        aria-live="polite"
        className={`text-xs ${request.state.status === "error" ? "text-warn-ink" : "text-muted"}`}
      >
        {status ?? "Synthetic Chennai incidents; nothing is real or dispatched."}
      </p>
    </div>
  );
}
