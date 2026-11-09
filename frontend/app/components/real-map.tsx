"use client";

import "leaflet/dist/leaflet.css";

import type { CircleMarker, Layer, LayerGroup, Map as LeafletMap } from "leaflet";
import { useEffect, useRef, useState } from "react";

import { blinkLevel } from "@/lib/alerting";
import type { Incident } from "@/lib/api";

/** Approximate centre of Chennai, where the simulated incidents are placed. */
export const CHENNAI_CENTER: [number, number] = [13.04, 80.21];
// OpenStreetMap's standard tiles: free and keyless, for light use under the
// OSM tile usage policy. They are darkened with a CSS filter (globals.css).
export const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
export const TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

// Esri World Imagery: worldwide satellite and aerial imagery, keyless for light
// use under Esri's terms, with Esri's place-name labels drawn on top.
export const SATELLITE_URL =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
export const SATELLITE_LABELS_URL =
  "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}";
export const SATELLITE_ATTRIBUTION =
  "Imagery &copy; Esri, Maxar, Earthstar Geographics, and the GIS User Community";

export type Basemap = "streets" | "satellite";
export type MapView = "incidents" | "world";

export const SEVERITY_COLOUR: Record<string, string> = {
  low: "#94a3b8",
  moderate: "#38bdf8",
  high: "#fb923c",
  critical: "#f87171",
};

const SEVERITY_RADIUS: Record<string, number> = { low: 6, moderate: 7, high: 8, critical: 10 };

function tooltipContent(incident: Incident): HTMLElement {
  // Built with textContent: incident text is data and never parsed as HTML.
  const element = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = incident.title;
  const detail = document.createElement("div");
  detail.textContent = `${incident.incident_id} · ${incident.severity} · ${incident.status}`;
  element.append(title, detail);
  return element;
}

/** A real map of Chennai (Leaflet with OpenStreetMap tiles, loaded from
 * OpenStreetMap's servers by the browser) showing simulated incidents that
 * have coordinates. */
export default function RealMap({
  incidents,
  selectedIncidentId,
  onSelectIncident,
  basemap = "streets",
  view = { target: "incidents", request: 0 },
}: {
  incidents: Incident[];
  selectedIncidentId: string | null;
  onSelectIncident: (incidentId: string | null) => void;
  basemap?: Basemap;
  /** A view change; a new request number applies it again. */
  view?: { target: MapView; request: number };
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<LeafletMap | null>(null);
  const layer = useRef<LayerGroup | null>(null);
  const leaflet = useRef<typeof import("leaflet") | null>(null);
  const fitted = useRef(false);
  const basemaps = useRef<Record<Basemap, Layer[]> | null>(null);
  const [ready, setReady] = useState(false);
  const onSelect = useRef(onSelectIncident);

  const incidentsRef = useRef(incidents);
  useEffect(() => {
    onSelect.current = onSelectIncident;
    incidentsRef.current = incidents;
  }, [onSelectIncident, incidents]);

  // Create the map once; Leaflet needs the browser, so it is loaded here.
  useEffect(() => {
    let cancelled = false;
    void import("leaflet").then((L) => {
      if (cancelled || !container.current || map.current) return;
      leaflet.current = L;
      map.current = L.map(container.current, {
        center: CHENNAI_CENTER,
        zoom: 11,
        minZoom: 2,
        worldCopyJump: true,
        zoomControl: true,
        attributionControl: true,
      });
      basemaps.current = {
        streets: [
          L.tileLayer(TILE_URL, {
            attribution: TILE_ATTRIBUTION,
            maxZoom: 19,
            className: "resqivo-map-tiles",
          }),
        ],
        satellite: [
          L.tileLayer(SATELLITE_URL, { attribution: SATELLITE_ATTRIBUTION, maxZoom: 19 }),
          L.tileLayer(SATELLITE_LABELS_URL, { maxZoom: 19 }),
        ],
      };
      layer.current = L.layerGroup().addTo(map.current);
      setReady(true);
      setTimeout(() => map.current?.invalidateSize(), 0);
      container.current.dispatchEvent(new Event("resqivo:map-ready"));
    });
    return () => {
      cancelled = true;
      map.current?.remove();
      map.current = null;
      layer.current = null;
      basemaps.current = null;
    };
  }, []);

  // Show only the chosen basemap's tile layers, beneath the incident markers.
  useEffect(() => {
    if (!ready || !map.current || !basemaps.current) return;
    for (const [name, layers] of Object.entries(basemaps.current)) {
      for (const tiles of layers) {
        if (name === basemap) tiles.addTo(map.current);
        else tiles.remove();
      }
    }
    layer.current?.remove();
    layer.current?.addTo(map.current);
  }, [basemap, ready]);

  // Move to the whole world, or back to the incidents (Chennai if none).
  // Only an explicit request moves the map, not every incident update.
  useEffect(() => {
    if (!ready || !map.current || view.request === 0) return;
    if (view.target === "world") {
      map.current.setView([20, 0], 2);
      return;
    }
    const points = incidentsRef.current
      .filter((i) => i.coordinates)
      .map((i) => [i.coordinates!.lat, i.coordinates!.lon] as [number, number]);
    if (points.length && leaflet.current) {
      map.current.fitBounds(leaflet.current.latLngBounds(points), {
        padding: [40, 40],
        maxZoom: 13,
      });
    } else {
      map.current.setView(CHENNAI_CENTER, 11);
    }
  }, [view.request, view.target, ready]);

  // Redraw markers whenever the incidents or the selection change.
  useEffect(() => {
    const draw = () => {
      const L = leaflet.current;
      if (!L || !layer.current || !map.current) return;
      layer.current.clearLayers();
      const points: [number, number][] = [];
      let selectedMarker: CircleMarker | null = null;
      for (const incident of incidents) {
        if (!incident.coordinates) continue;
        const position: [number, number] = [incident.coordinates.lat, incident.coordinates.lon];
        points.push(position);
        const selected = incident.incident_id === selectedIncidentId;
        const colour = SEVERITY_COLOUR[incident.severity] ?? "#94a3b8";
        // Unacknowledged high and critical incidents blink until acknowledged.
        // The selected incident never blinks, so it is distinct from any
        // alarming incidents nearby.
        const blink = selected ? null : blinkLevel(incident);
        const marker: CircleMarker = L.circleMarker(position, {
          className: blink ? `resqivo-blink-${blink}` : undefined,
          radius: (SEVERITY_RADIUS[incident.severity] ?? 7) + (selected ? 4 : 0),
          color: selected ? "#0891b2" : colour,
          weight: selected ? 4 : 2,
          fillColor: colour,
          fillOpacity: incident.status === "closed" ? 0.25 : 0.7,
        });
        marker.bindTooltip(tooltipContent(incident), { direction: "top", offset: [0, -6] });
        marker.on("click", () => onSelect.current(incident.incident_id));
        marker.addTo(layer.current);
        if (selected) selectedMarker = marker;
      }
      // Drawn last, so overlapping markers never hide the selection.
      selectedMarker?.bringToFront();
      if (!fitted.current && points.length > 0) {
        map.current.fitBounds(L.latLngBounds(points), { padding: [40, 40], maxZoom: 13 });
        fitted.current = true;
      }
    };
    draw();
    const element = container.current;
    element?.addEventListener("resqivo:map-ready", draw);
    return () => element?.removeEventListener("resqivo:map-ready", draw);
  }, [incidents, selectedIncidentId]);

  return (
    <div
      ref={container}
      role="application"
      aria-label="Map of Chennai with simulated incidents. Use the incident queue to select incidents with the keyboard."
      className="absolute inset-0 z-0 bg-map-bg"
    />
  );
}
