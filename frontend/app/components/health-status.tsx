"use client";

import { useEffect } from "react";

import { API_BASE_URL, getHealth, type HealthResponse } from "@/lib/api";
import { useRequest } from "@/lib/use-request";

import { Badge } from "./results";

/** Backend connection status from the real GET /health endpoint. It reports
 * only whether the API process answers; it does not check AI configuration. */
export default function HealthStatus() {
  const { state, run } = useRequest<HealthResponse>();
  const check = () => void run((signal) => getHealth(signal));

  useEffect(() => {
    void run((signal) => getHealth(signal));
  }, [run]);

  const checking = state.status === "loading" || state.status === "idle";
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm" aria-live="polite">
      <span className="text-xs font-medium uppercase tracking-wider text-muted">Backend</span>
      {checking ? (
        <Badge tone="neutral">Checking…</Badge>
      ) : state.status === "success" && state.data.status === "ok" ? (
        <Badge tone="ok">
          <span aria-hidden="true" className="mr-1.5 inline-block size-1.5 rounded-full bg-emerald-400" />
          Online
        </Badge>
      ) : (
        <Badge tone="bad">
          <span aria-hidden="true" className="mr-1.5 inline-block size-1.5 rounded-full bg-red-400" />
          Unavailable
        </Badge>
      )}
      <span className="font-mono text-xs text-muted">{API_BASE_URL}</span>
      <button
        type="button"
        onClick={check}
        disabled={checking}
        className="rounded-md border border-line px-2 py-0.5 text-xs text-ink hover:border-accent/60 hover:bg-accent/10 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {state.status === "error" ? "Retry" : "Refresh"}
      </button>
      {state.status === "error" && (
        <span className="w-full text-xs text-bad-ink">{state.message}</span>
      )}
    </div>
  );
}
