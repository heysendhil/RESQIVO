"use client";

import { useState } from "react";

import type { Incident } from "@/lib/api";
import { NEAR_CAPACITY } from "@/lib/alerts";
import { computeMapLayout, type MapShelter } from "@/lib/map-layout";
import type { Workspace } from "@/lib/workspace";

import { readable } from "./incident-queue";
import RealMap, { SEVERITY_COLOUR, type Basemap, type MapView } from "./real-map";

export type MapMode = "fictional" | "chennai";

export type MapSelection =
  | { kind: "shelter"; index: number }
  | { kind: "supply"; name: string }
  | null;

type LayerId = "zone" | "shelters" | "supplies" | "routes" | "labels";

const LAYERS: { id: LayerId; label: string }[] = [
  { id: "zone", label: "Affected area" },
  { id: "shelters", label: "Shelters" },
  { id: "supplies", label: "Supply points" },
  { id: "routes", label: "Allocation routes" },
  { id: "labels", label: "Labels" },
];

const SEVERITY_FILL: Record<string, string> = {
  low: "#38bdf8",
  moderate: "#facc15",
  high: "#fb923c",
  critical: "#f87171",
};

function shelterState(shelter: MapShelter) {
  const load = shelter.load;
  if (!load) return { ring: "border-slate-400 bg-slate-500/30", text: "no valid figures" };
  if (load.overCapacity) return { ring: "border-red-400 bg-red-500/40", text: "over capacity" };
  if (load.ratio !== null && load.ratio >= NEAR_CAPACITY) {
    return { ring: "border-amber-300 bg-amber-400/40", text: "near capacity" };
  }
  return { ring: "border-emerald-300 bg-emerald-400/35", text: "within capacity" };
}

/** The fictional city base map: river, parks and roads. Purely decorative. */
function BaseMap() {
  const line = { vectorEffect: "non-scaling-stroke" as const, fill: "none" };
  const stroke = (colour: string, width: number) => ({ stroke: `var(${colour})`, strokeWidth: width });
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      className="absolute inset-0 size-full"
    >
      <rect width="100" height="100" style={{ fill: "var(--map-bg)" }} />
      {Array.from({ length: 19 }, (_, i) => (
        <g key={i} style={stroke("--map-grid", 1)} {...line}>
          <path d={`M${(i + 1) * 5} 0V100`} />
          <path d={`M0 ${(i + 1) * 5}H100`} />
        </g>
      ))}
      <g style={{ fill: "var(--map-park)" }}>
        <rect x="54" y="40" width="9" height="7" rx="1" />
        <rect x="6" y="28" width="8" height="10" rx="1" />
        <rect x="70" y="80" width="12" height="8" rx="1" />
      </g>
      <path d="M0 58 C18 52 30 62 46 54 S74 42 100 46" style={stroke("--map-water", 18)} {...line} />
      <path d="M0 58 C18 52 30 62 46 54 S74 42 100 46" style={stroke("--map-water-line", 2)} {...line} />
      <g style={stroke("--map-road", 3)} {...line}>
        <path d="M0 20 C30 18 60 23 100 19" />
        <path d="M0 84 C35 80 65 87 100 82" />
        <path d="M22 0 C20 40 25 70 21 100" />
        <path d="M70 0 C72 30 67 70 71 100" />
        <path d="M0 96 L100 4" />
      </g>
      <g style={stroke("--map-road-minor", 1.5)} {...line}>
        <path d="M40 0 C41 30 38 70 41 100" />
        <path d="M0 38 C40 36 60 40 100 35" />
        <path d="M0 70 C40 72 60 68 100 72" />
        <path d="M88 0 C86 50 90 70 87 100" />
      </g>
    </svg>
  );
}

/** A map of a fictional city. Zones, shelters and supply points are placed
 * in fixed slots by location name (lib/map-layout.ts); nothing is real
 * geography, and no map service or coordinates are used. */
export default function OperationalPicture({
  workspace,
  severity,
  disasterType,
  selection,
  onSelect,
  mode,
  onMode,
  incidents,
  selectedIncidentId,
  onSelectIncident,
}: {
  workspace: Workspace;
  severity: string;
  disasterType: string;
  selection: MapSelection;
  onSelect: (selection: MapSelection) => void;
  mode: MapMode;
  onMode: (mode: MapMode) => void;
  incidents: Incident[];
  selectedIncidentId: string | null;
  onSelectIncident: (incidentId: string | null) => void;
}) {
  const [layersOpen, setLayersOpen] = useState(false);
  const [basemap, setBasemap] = useState<Basemap>("streets");
  const [view, setView] = useState<{ target: MapView; request: number }>({
    target: "incidents",
    request: 0,
  });
  const goTo = (target: MapView) => setView((current) => ({ target, request: current.request + 1 }));
  const [layers, setLayers] = useState<Record<LayerId, boolean>>({
    zone: true,
    shelters: true,
    supplies: true,
    routes: true,
    labels: true,
  });
  const layout = computeMapLayout(workspace);
  const fill = SEVERITY_FILL[severity] ?? "#38bdf8";
  const empty = layout.shelters.length === 0 && layout.supplies.length === 0;
  const toggle = (id: LayerId) => setLayers((current) => ({ ...current, [id]: !current[id] }));
  const mapped = incidents.filter((i) => i.coordinates).length;

  return (
    <section
      aria-labelledby="picture-heading"
      className="relative flex h-full min-h-[30rem] flex-col overflow-hidden rounded-lg border border-line bg-map-bg"
    >
      {mode === "chennai" ? (
        <RealMap
          incidents={incidents}
          selectedIncidentId={selectedIncidentId}
          onSelectIncident={onSelectIncident}
          basemap={basemap}
          view={view}
        />
      ) : (
      <>
      <BaseMap />

      {layers.zone &&
        layout.zones.map((zone) => (
          <span
            key={`zone-${zone.name}`}
            aria-hidden="true"
            className="absolute aspect-square -translate-x-1/2 -translate-y-1/2 rounded-full border-[1.5px] border-dashed"
            style={{
              left: `${zone.x}%`,
              top: `${zone.y}%`,
              width: `${zone.radius * 2}%`,
              borderColor: `${fill}99`,
              backgroundColor: `${fill}1f`,
            }}
          />
        ))}

      {layers.routes && (
        <svg aria-hidden="true" viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 size-full">
          {layout.routes.map((route) => (
            <line
              key={route.allocationIndex}
              x1={route.from.x}
              y1={route.from.y}
              x2={route.to.x}
              y2={route.to.y}
              style={{ stroke: "var(--accent)" }}
              strokeOpacity="0.7"
              strokeWidth="1.5"
              strokeDasharray="5 4"
              vectorEffect="non-scaling-stroke"
            />
          ))}
        </svg>
      )}

      {layers.labels &&
        layout.zones.map((zone) => (
          <span
            key={`label-${zone.name}`}
            className="pointer-events-none absolute -translate-x-1/2 translate-y-6 whitespace-nowrap rounded bg-canvas/75 px-1.5 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wider text-ink/90"
            style={{ left: `${zone.x}%`, top: `${zone.y}%` }}
          >
            {zone.name}
          </span>
        ))}

      {layers.shelters &&
        layout.shelters.map((shelter) => {
          const state = shelterState(shelter);
          const selected = selection?.kind === "shelter" && selection.index === shelter.index;
          const load = shelter.load;
          return (
            <button
              key={`shelter-${shelter.index}`}
              type="button"
              aria-pressed={selected}
              aria-label={`Shelter ${shelter.name}: ${
                load
                  ? `${load.occupancy.toLocaleString()} of ${load.capacity.toLocaleString()} places`
                  : "capacity not a whole number"
              }, ${state.text}`}
              onClick={() => onSelect(selected ? null : { kind: "shelter", index: shelter.index })}
              className={`absolute flex size-7 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 text-[0.65rem] font-bold text-ink shadow-[0_0_0_3px_var(--map-bg)] ${state.ring} ${
                selected ? "outline outline-2 outline-offset-2 outline-accent" : ""
              }`}
              style={{ left: `${shelter.x}%`, top: `${shelter.y}%` }}
            >
              S
            </button>
          );
        })}

      {layers.supplies &&
        layout.supplies.map((supply) => {
          const selected = selection?.kind === "supply" && selection.name === supply.name;
          return (
            <div key={`supply-${supply.name}`}>
              <button
                type="button"
                aria-pressed={selected}
                aria-label={`Supply point ${supply.name}: ${supply.resources.length} resource${supply.resources.length === 1 ? "" : "s"}`}
                onClick={() => onSelect(selected ? null : { kind: "supply", name: supply.name })}
                className={`absolute flex size-6 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-sm border-2 border-accent bg-accent/25 text-[0.6rem] font-bold text-ink shadow-[0_0_0_3px_var(--map-bg)] ${
                  selected ? "outline outline-2 outline-offset-2 outline-accent" : ""
                }`}
                style={{ left: `${supply.x}%`, top: `${supply.y}%` }}
              >
                R
              </button>
              {layers.labels && (
                <span
                  className={`pointer-events-none absolute translate-y-4 whitespace-nowrap rounded bg-canvas/75 px-1 text-[0.6rem] text-muted ${
                    // Labels near an edge extend inwards so they are not cut off.
                    supply.x < 20 ? "-translate-x-3" : supply.x > 80 ? "-translate-x-[calc(100%-0.75rem)]" : "-translate-x-1/2"
                  }`}
                  style={{ left: `${supply.x}%`, top: `${supply.y}%` }}
                >
                  {supply.name}
                </span>
              )}
            </div>
          );
        })}

      {empty && (
        <p className="absolute inset-x-6 top-1/2 -translate-y-1/2 rounded-md border border-dashed border-line bg-canvas/80 p-4 text-center text-sm text-muted">
          No shelters or resources entered. Add them under Shelters and Resources to see
          them on the map.
        </p>
      )}
      </>
      )}

      {/* Overlays */}
      <div className="pointer-events-none relative z-10 flex items-start justify-between gap-3 p-3">
        <div className="pointer-events-auto flex min-w-0 flex-col gap-0.5 rounded-md border border-line bg-canvas/85 px-3 py-1.5 backdrop-blur">
          <h3 id="picture-heading" className="text-xs font-semibold uppercase tracking-[0.16em] text-ink">
            Operational map
          </h3>
          <p className="flex flex-wrap items-center gap-1.5 text-[0.68rem] text-muted">
            <span className="rounded bg-amber-400/20 px-1.5 font-bold uppercase tracking-wider text-warn-ink">
              Simulation
            </span>
            {mode === "chennai"
              ? `Chennai · simulated incidents on a real ${basemap === "satellite" ? "satellite " : ""}map`
              : `Fictional city — not a real place · ${readable(disasterType)}, ${severity}`}
          </p>
          <div role="group" aria-label="Map mode" className="mt-1 flex w-fit rounded border border-line p-0.5">
            {(
              [
                ["fictional", "Fictional city"],
                ["chennai", "Chennai map"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                aria-pressed={mode === id}
                onClick={() => onMode(id)}
                className={`rounded px-2 py-0.5 text-[0.68rem] font-semibold ${
                  mode === id ? "bg-accent/15 text-accent" : "text-muted hover:text-ink"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        {mode === "chennai" && (
          <div className="pointer-events-auto flex shrink-0 flex-col items-end gap-1.5">
            <div role="group" aria-label="Basemap" className="flex rounded-md border border-line bg-canvas/85 p-0.5 backdrop-blur">
              {(
                [
                  ["streets", "Streets"],
                  ["satellite", "Satellite"],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  aria-pressed={basemap === id}
                  onClick={() => setBasemap(id)}
                  className={`rounded px-2 py-0.5 text-[0.68rem] font-semibold ${
                    basemap === id ? "bg-accent/15 text-accent" : "text-muted hover:text-ink"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <div role="group" aria-label="Map view" className="flex gap-1">
              <button
                type="button"
                onClick={() => goTo("world")}
                className="rounded-md border border-line bg-canvas/85 px-2 py-0.5 text-[0.68rem] font-semibold text-ink backdrop-blur hover:border-accent/60"
              >
                World view
              </button>
              <button
                type="button"
                onClick={() => goTo("incidents")}
                className="rounded-md border border-line bg-canvas/85 px-2 py-0.5 text-[0.68rem] font-semibold text-ink backdrop-blur hover:border-accent/60"
              >
                Zoom to incidents
              </button>
            </div>
          </div>
        )}
        {mode === "fictional" && (
        <div className="pointer-events-auto flex shrink-0 flex-col items-end gap-1">
          <button
            type="button"
            aria-expanded={layersOpen}
            aria-controls="map-layers"
            onClick={() => setLayersOpen((open) => !open)}
            className="rounded-md border border-line bg-canvas/85 px-2.5 py-1.5 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-ink backdrop-blur hover:border-accent/60"
          >
            Layers {layersOpen ? "▴" : "▾"}
          </button>
          <fieldset
            id="map-layers"
            hidden={!layersOpen}
            className="flex flex-col gap-1 rounded-md border border-line bg-canvas/90 p-2 backdrop-blur"
          >
            <legend className="sr-only">Map layers</legend>
            {LAYERS.map((layer) => (
              <button
                key={layer.id}
                type="button"
                role="switch"
                aria-checked={layers[layer.id]}
                onClick={() => toggle(layer.id)}
                className="flex items-center justify-between gap-3 rounded px-1 py-0.5 text-left text-xs text-ink hover:bg-panel-raised"
              >
                {layer.label}
                <span
                  aria-hidden="true"
                  className={`rounded-full px-1.5 text-[0.6rem] font-bold ${
                    layers[layer.id] ? "bg-emerald-400/20 text-ok-ink" : "bg-panel-raised text-muted"
                  }`}
                >
                  {layers[layer.id] ? "ON" : "OFF"}
                </span>
              </button>
            ))}
          </fieldset>
        </div>
        )}
      </div>

      {mode === "chennai" ? (
      <div className="pointer-events-none relative z-10 mt-auto flex flex-wrap items-end justify-between gap-3 p-3 pb-6">
        <ul
          aria-label="Legend"
          className="pointer-events-auto flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-line bg-canvas/85 px-3 py-1.5 text-[0.68rem] text-muted backdrop-blur"
        >
          {Object.entries(SEVERITY_COLOUR).map(([level, colour]) => (
            <li key={level} className="flex items-center gap-1.5 capitalize">
              <span className="size-2.5 rounded-full" style={{ backgroundColor: colour }} /> {level}
            </li>
          ))}
          <li className="flex items-center gap-1.5"><span className="size-2.5 rounded-full border-2 border-accent" /> Selected</li>
          <li className="flex items-center gap-1.5"><span className="resqivo-alarm-pill size-2.5 rounded-full bg-red-500" /> Blinking: unacknowledged (red critical = alarm, amber high)</li>
        </ul>
        <p className="pointer-events-auto rounded-md border border-line bg-canvas/85 px-2 py-1 font-mono text-[0.7rem] text-muted">
          {mapped} of {incidents.length} incidents mapped
          {incidents.length > mapped && ` · ${incidents.length - mapped} without coordinates`}
        </p>
      </div>
      ) : (
      <div className="pointer-events-none relative z-10 mt-auto flex flex-wrap items-end justify-between gap-3 p-3">
        <ul
          aria-label="Legend"
          className="pointer-events-auto flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-line bg-canvas/85 px-3 py-1.5 text-[0.68rem] text-muted backdrop-blur"
        >
          <li className="flex items-center gap-1.5"><span className="size-2.5 rounded-full border-2 border-emerald-300" /> Within capacity</li>
          <li className="flex items-center gap-1.5"><span className="size-2.5 rounded-full border-2 border-amber-300" /> ≥ 90% full</li>
          <li className="flex items-center gap-1.5"><span className="size-2.5 rounded-full border-2 border-red-400" /> Over capacity</li>
          <li className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm border-2 border-accent" /> Supply point</li>
          <li className="flex items-center gap-1.5"><span className="h-0 w-3 border-t-2 border-dashed border-accent" /> Proposed allocation</li>
          <li className="flex items-center gap-1.5"><span className="size-2.5 rounded-full border border-dashed" style={{ borderColor: fill }} /> Affected area</li>
        </ul>
        <div className="pointer-events-auto flex flex-col items-end gap-1.5">
          {layout.unmatchedDestinations.length > 0 && (
            <p className="rounded-md border border-red-500/40 bg-panel/95 px-2 py-1 text-[0.7rem] text-bad-ink">
              Allocations to unknown shelters:{" "}
              <span className="font-mono">{layout.unmatchedDestinations.join(", ")}</span>
            </p>
          )}
          <p className="rounded-md border border-line bg-canvas/85 px-2 py-1 font-mono text-[0.7rem] text-muted">
            {layout.shelters.length} shelters · {layout.supplies.length} supply points ·{" "}
            {layout.routes.length} routes
          </p>
          <p className="rounded-md border border-line bg-canvas/85 px-2 py-1 text-[0.7rem] text-muted">
            Live incidents are shown on the Chennai map.
          </p>
        </div>
      </div>
      )}
    </section>
  );
}
