// Summary figures for the Command Center, computed only from what the user has
// entered in the workspace. A total is shown only when every value it depends
// on is a valid whole number; otherwise it is null and displayed as "—".

import type { Row, Workspace } from "@/lib/workspace";

const WHOLE = /^\d+$/;

function whole(value: string | undefined): number | null {
  const trimmed = (value ?? "").trim();
  return WHOLE.test(trimmed) ? Number(trimmed) : null;
}

function total(rows: Row[], key: string): number | null {
  let sum = 0;
  for (const row of rows) {
    const value = whole(row[key]);
    if (value === null) return null;
    sum += value;
  }
  return sum;
}

export interface ShelterLoad {
  capacity: number;
  occupancy: number;
  /** Occupancy as a share of capacity; null when capacity is 0. */
  ratio: number | null;
  overCapacity: boolean;
}

export function shelterLoad(row: Row): ShelterLoad | null {
  const capacity = whole(row.capacity);
  const occupancy = whole(row.current_occupancy);
  if (capacity === null || occupancy === null) return null;
  return {
    capacity,
    occupancy,
    ratio: capacity > 0 ? occupancy / capacity : null,
    overCapacity: occupancy > capacity,
  };
}

export interface WorkspaceSummary {
  scenarioName: string;
  disasterType: string;
  severity: string;
  location: string;
  affectedPopulation: number | null;
  resourceEntries: number;
  resourceTypes: number;
  shelters: number;
  totalCapacity: number | null;
  totalOccupancy: number | null;
  sheltersOverCapacity: number | null;
  allocations: number;
  needs: number;
}

export function summarizeWorkspace(ws: Workspace): WorkspaceSummary {
  const loads = ws.shelters.map(shelterLoad);
  return {
    scenarioName: ws.scenario.name.trim(),
    disasterType: ws.scenario.disaster_type,
    severity: ws.scenario.severity,
    location: ws.scenario.location.trim(),
    affectedPopulation: whole(ws.scenario.affected_population),
    resourceEntries: ws.resources.length,
    resourceTypes: new Set(ws.resources.map((r) => r.resource_type)).size,
    shelters: ws.shelters.length,
    totalCapacity: total(ws.shelters, "capacity"),
    totalOccupancy: total(ws.shelters, "current_occupancy"),
    sheltersOverCapacity: loads.some((load) => load === null)
      ? null
      : loads.filter((load) => load!.overCapacity).length,
    allocations: ws.allocations.length,
    needs: ws.needs.length,
  };
}
