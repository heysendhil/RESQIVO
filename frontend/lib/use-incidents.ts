"use client";

// The live incident feed. The backend's server-sent stream only signals that
// the feed changed; the list itself is always fetched from GET /incidents, so
// it is shape-checked like every other response.

import { useCallback, useEffect, useRef, useState } from "react";

import { INCIDENT_STREAM_URL, listIncidents, type Incident } from "@/lib/api";

/** "live": stream connected; "polling": no EventSource, refreshed on a timer;
 * "reconnecting": the stream dropped and the browser is retrying. */
export type FeedStatus = "connecting" | "live" | "polling" | "reconnecting";

export const POLL_INTERVAL_MS = 10_000;

export interface IncidentFeed {
  incidents: Incident[];
  notice: string | null;
  loaded: boolean;
  failed: boolean;
  status: FeedStatus;
  refresh: () => Promise<void>;
}

export function useIncidentFeed(): IncidentFeed {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const [status, setStatus] = useState<FeedStatus>("connecting");
  const latest = useRef(0);

  const refresh = useCallback(async () => {
    // Only the newest request may update the list.
    const call = ++latest.current;
    try {
      const data = await listIncidents();
      if (call !== latest.current) return;
      setIncidents(data.incidents);
      setNotice(data.notice);
      setLoaded(true);
      setFailed(false);
    } catch {
      if (call === latest.current) setFailed(true);
    }
  }, []);

  useEffect(() => {
    // Deferred so that no state is set synchronously while the effect runs.
    const first = setTimeout(() => void refresh(), 0);
    if (typeof EventSource === "undefined") {
      const timer = setInterval(() => void refresh(), POLL_INTERVAL_MS);
      const mode = setTimeout(() => setStatus("polling"), 0);
      return () => {
        clearTimeout(first);
        clearTimeout(mode);
        clearInterval(timer);
      };
    }
    const source = new EventSource(INCIDENT_STREAM_URL);
    source.addEventListener("open", () => setStatus("live"));
    source.addEventListener("incidents", () => void refresh());
    source.addEventListener("error", () => setStatus("reconnecting"));
    return () => {
      clearTimeout(first);
      source.close();
    };
  }, [refresh]);

  return { incidents, notice, loaded, failed, status, refresh };
}
