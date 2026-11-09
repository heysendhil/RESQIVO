// Placement of workspace entities on RESQIVO's fictional city map.
//
// The data model has no coordinates: locations are free text such as
// "Simulated Zone A". Each distinct location is assigned, in order of first
// appearance, to a fixed slot on a fictional map. Positions therefore say
// nothing about real geography and are only a way to show the entered data.
// All positions are percentages of the map's width and height.

import { shelterLoad, type ShelterLoad } from "@/lib/summary";
import type { Row, Workspace } from "@/lib/workspace";

export interface Point {
  x: number;
  y: number;
}

export interface MapZone extends Point {
  name: string;
  /** Radius of the zone outline, in % of the map width. */
  radius: number;
}

export interface MapShelter extends Point {
  index: number;
  id: string;
  name: string;
  zone: string;
  load: ShelterLoad | null;
}

export interface MapSupply extends Point {
  name: string;
  /** Indexes into workspace.resources. */
  resources: number[];
}

export interface MapRoute {
  allocationIndex: number;
  from: Point;
  to: Point;
}

export interface MapLayout {
  zones: MapZone[];
  shelters: MapShelter[];
  supplies: MapSupply[];
  routes: MapRoute[];
  /** Allocation destinations that match no shelter in the workspace. */
  unmatchedDestinations: string[];
}

/** Zone slots on the fictional map, below the title overlay and above the
 * legend bar. */
export const ZONE_SLOTS: Point[] = [
  { x: 30, y: 44 },
  { x: 68, y: 40 },
  { x: 48, y: 72 },
  { x: 82, y: 70 },
  { x: 14, y: 72 },
  { x: 88, y: 34 },
];

/** Supply-point slots near the map edges, clear of the overlays. */
export const SUPPLY_SLOTS: Point[] = [
  { x: 8, y: 30 },
  { x: 50, y: 26 },
  { x: 93, y: 84 },
  { x: 7, y: 54 },
  { x: 28, y: 86 },
  { x: 94, y: 52 },
];

const ZONE_RADIUS = 11;

const NO_LOCATION = "No location entered";

function locationOf(row: Row): string {
  return row.location?.trim() || NO_LOCATION;
}

/** Slot i, nudged for slots reused when there are more names than slots. */
function slot(slots: Point[], index: number): Point {
  const base = slots[index % slots.length];
  const round = Math.floor(index / slots.length);
  return { x: base.x + round * 4, y: base.y + round * 4 };
}

function distinct(values: string[]): string[] {
  return [...new Set(values)];
}

/** Shelters sit on a small ring inside their zone. */
function ringPosition(center: Point, position: number, count: number): Point {
  if (count === 1) return { x: center.x, y: center.y };
  const angle = (2 * Math.PI * position) / count - Math.PI / 2;
  return {
    x: center.x + Math.cos(angle) * 5.5,
    y: center.y + Math.sin(angle) * 8,
  };
}

export function computeMapLayout(ws: Workspace): MapLayout {
  const zoneNames = distinct(ws.shelters.map(locationOf));
  const zones: MapZone[] = zoneNames.map((name, index) => ({
    name,
    ...slot(ZONE_SLOTS, index),
    radius: ZONE_RADIUS,
  }));
  const zoneByName = new Map(zones.map((zone) => [zone.name, zone]));

  const members = new Map<string, number[]>();
  ws.shelters.forEach((row, index) => {
    const zone = locationOf(row);
    members.set(zone, [...(members.get(zone) ?? []), index]);
  });

  const shelters: MapShelter[] = ws.shelters.map((row, index) => {
    const zone = locationOf(row);
    const group = members.get(zone)!;
    return {
      index,
      id: row.shelter_id?.trim() ?? "",
      name: row.name?.trim() || row.shelter_id?.trim() || `Shelter ${index + 1}`,
      zone,
      load: shelterLoad(row),
      ...ringPosition(zoneByName.get(zone)!, group.indexOf(index), group.length),
    };
  });

  const supplyNames = distinct(ws.resources.map(locationOf));
  const supplies: MapSupply[] = supplyNames.map((name, index) => ({
    name,
    ...slot(SUPPLY_SLOTS, index),
    resources: ws.resources.flatMap((row, i) => (locationOf(row) === name ? [i] : [])),
  }));
  const supplyByName = new Map(supplies.map((supply) => [supply.name, supply]));

  // Duplicate IDs are reported by the validator; the first match is drawn.
  const shelterById = new Map<string, MapShelter>();
  for (const shelter of shelters) {
    if (shelter.id && !shelterById.has(shelter.id)) shelterById.set(shelter.id, shelter);
  }
  const resourceLocation = new Map<string, string>();
  for (const row of ws.resources) {
    const id = row.resource_id?.trim();
    if (id && !resourceLocation.has(id)) resourceLocation.set(id, locationOf(row));
  }

  const routes: MapRoute[] = [];
  const unmatched = new Set<string>();
  ws.allocations.forEach((allocation, allocationIndex) => {
    const destination = allocation.destination_id?.trim() ?? "";
    const target = shelterById.get(destination);
    if (!target) {
      if (destination) unmatched.add(destination);
      return;
    }
    const origin = supplyByName.get(resourceLocation.get(allocation.resource_id?.trim() ?? "") ?? "");
    if (!origin) return;
    routes.push({
      allocationIndex,
      from: { x: origin.x, y: origin.y },
      to: { x: target.x, y: target.y },
    });
  });

  return { zones, shelters, supplies, routes, unmatchedDestinations: [...unmatched] };
}
