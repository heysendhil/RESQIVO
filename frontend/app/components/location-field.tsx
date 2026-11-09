"use client";

import { useEffect, useId, useRef, useState } from "react";

import {
  GeolocationError,
  formatCoordinates,
  requestDevicePosition,
  type DevicePosition,
} from "@/lib/geolocation";

// Backend limit for DisasterScenario.location (backend/app/models/scenario.py).
const MAX_LOCATION_CHARS = 200;

type LookupState =
  | { status: "idle" }
  | { status: "locating" }
  | { status: "found"; position: DevicePosition }
  | { status: "inserted" }
  | { status: "error"; message: string };

const inputClass =
  "w-full rounded-md border border-line bg-canvas px-2.5 py-1.5 text-sm text-ink focus:border-accent";
const smallButton =
  "rounded-md border border-line px-3 py-1.5 text-xs font-medium text-ink hover:border-accent/60 hover:bg-accent/10 disabled:cursor-wait disabled:opacity-60";

/** The disaster location: always editable text. The device's position is only
 * looked up when the user clicks the button, and it never replaces the field
 * until the user explicitly chooses to use it. */
export default function LocationField({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const id = useId();
  const [lookup, setLookup] = useState<LookupState>({ status: "idle" });
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  async function locate() {
    setLookup({ status: "locating" });
    try {
      const position = await requestDevicePosition();
      if (mounted.current) setLookup({ status: "found", position });
    } catch (error) {
      if (!mounted.current) return;
      setLookup({
        status: "error",
        message:
          error instanceof GeolocationError
            ? error.message
            : "Your location could not be determined. Enter the disaster location manually.",
      });
    }
  }

  function applyPosition(position: DevicePosition) {
    onChange(formatCoordinates(position));
    setLookup({ status: "inserted" });
  }

  return (
    <div className="flex flex-col gap-1 text-sm sm:col-span-2">
      <label htmlFor={id} className="text-ink">
        Disaster location
      </label>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          id={id}
          type="text"
          value={value}
          maxLength={MAX_LOCATION_CHARS}
          aria-describedby={`${id}-hint`}
          onChange={(event) => onChange(event.target.value)}
          className={inputClass}
        />
        <button
          type="button"
          onClick={() => void locate()}
          disabled={lookup.status === "locating"}
          className={`${smallButton} shrink-0`}
        >
          {lookup.status === "locating" ? "Locating…" : "Use my current location"}
        </button>
      </div>
      <p id={`${id}-hint`} className="text-xs text-muted">
        Where the disaster is, which may differ from where you are. Your browser
        asks for permission only when you press the button.
      </p>

      <div aria-live="polite">
        {lookup.status === "locating" && (
          <p role="status" className="text-xs">
            Requesting your device location…
          </p>
        )}

        {lookup.status === "found" && (
          <div
            role="status"
            className="mt-1 flex flex-col gap-2 rounded-lg border border-sky-500/40 bg-sky-500/10 p-3 text-xs text-info-ink"
          >
            <p>
              Your device reports{" "}
              <span className="font-mono font-semibold">
                {formatCoordinates(lookup.position)}
              </span>{" "}
              (accuracy about {Math.round(lookup.position.accuracy).toLocaleString()} m).
              This is <strong>your</strong> current location, which may not be the
              disaster location. No place name is looked up.
            </p>
            <p>
              If you use it, these coordinates are sent to the RESQIVO backend and
              included in AI draft requests.
            </p>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => applyPosition(lookup.position)}
                className={smallButton}
              >
                Use these coordinates as the disaster location
              </button>
              <button
                type="button"
                onClick={() => setLookup({ status: "idle" })}
                className={smallButton}
              >
                Dismiss
              </button>
            </div>
          </div>
        )}

        {lookup.status === "inserted" && (
          <p role="status" className="text-xs">
            Coordinates inserted. Replace them with, or add, a readable place name if
            you can.
          </p>
        )}

        {lookup.status === "error" && (
          <p
            role="alert"
            className="mt-1 rounded-lg border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-warn-ink"
          >
            {lookup.message}
          </p>
        )}
      </div>
    </div>
  );
}
