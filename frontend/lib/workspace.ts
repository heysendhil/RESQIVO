// The editable scenario workspace and its conversion into backend requests.
//
// Table cells hold exactly what the user typed. When a request is built, cells
// in numeric columns become numbers only if they are whole numbers; anything
// else is sent unchanged so the backend's own validation rejects it (HTTP 422).
// The UI never fills in, rounds or invents a quantity or capacity.

import {
  DISASTER_TYPES,
  RESOURCE_TYPES,
  SEVERITIES,
  type DisasterScenario,
  type DraftPlanRequest,
  type PlanValidationRequest,
} from "@/lib/api";
import { samplePlans, type SamplePlan } from "@/lib/sample-plans";

export type Row = Record<string, string>;

export interface Column {
  key: string;
  label: string;
  kind: "text" | "number" | "select";
  options?: readonly string[];
}

export type TableName = "resources" | "shelters" | "allocations" | "needs";

export const TABLES: Record<TableName, { title: string; columns: Column[] }> = {
  resources: {
    title: "Resources (available inventory)",
    columns: [
      { key: "resource_id", label: "Resource ID", kind: "text" },
      { key: "name", label: "Name", kind: "text" },
      { key: "resource_type", label: "Type", kind: "select", options: RESOURCE_TYPES },
      { key: "quantity_available", label: "Quantity available", kind: "number" },
      { key: "unit", label: "Unit", kind: "text" },
      { key: "location", label: "Location", kind: "text" },
    ],
  },
  shelters: {
    title: "Shelters",
    columns: [
      { key: "shelter_id", label: "Shelter ID", kind: "text" },
      { key: "name", label: "Name", kind: "text" },
      { key: "location", label: "Location", kind: "text" },
      { key: "capacity", label: "Capacity", kind: "number" },
      { key: "current_occupancy", label: "Current occupancy", kind: "number" },
    ],
  },
  allocations: {
    title: "Proposed allocations (for validation and review)",
    columns: [
      { key: "allocation_id", label: "Allocation ID", kind: "text" },
      { key: "resource_id", label: "Resource ID", kind: "text" },
      { key: "destination_id", label: "Destination shelter ID", kind: "text" },
      { key: "quantity_allocated", label: "Quantity", kind: "number" },
    ],
  },
  needs: {
    title: "Known needs (optional, used for drafting)",
    columns: [
      { key: "destination_id", label: "Shelter ID", kind: "text" },
      { key: "resource_type", label: "Resource type", kind: "select", options: RESOURCE_TYPES },
      { key: "quantity_needed", label: "Quantity needed", kind: "number" },
    ],
  },
};

export interface ScenarioFields {
  scenario_id: string;
  name: string;
  disaster_type: string;
  severity: string;
  affected_population: string;
  location: string;
  description: string;
}

export const SCENARIO_OPTIONS = {
  disaster_type: DISASTER_TYPES,
  severity: SEVERITIES,
} as const;

export interface Workspace {
  scenario: ScenarioFields;
  resources: Row[];
  shelters: Row[];
  allocations: Row[];
  needs: Row[];
  constraints: string;
}

export function emptyRow(table: TableName): Row {
  return Object.fromEntries(
    TABLES[table].columns.map((c) => [c.key, c.kind === "select" ? c.options![0] : ""]),
  );
}

const WHOLE_NUMBER = /^-?\d+$/;

/** A whole number if the text is one; otherwise the text itself, for the
 * backend to reject. */
export function toNumberOrText(value: string): number | string {
  const trimmed = value.trim();
  return WHOLE_NUMBER.test(trimmed) ? Number(trimmed) : value;
}

function convert(table: TableName, rows: Row[]) {
  const numeric = new Set(
    TABLES[table].columns.filter((c) => c.kind === "number").map((c) => c.key),
  );
  return rows.map((row) =>
    Object.fromEntries(
      Object.entries(row).map(([key, value]) => [
        key,
        numeric.has(key) ? toNumberOrText(value) : value,
      ]),
    ),
  );
}

export function constraintList(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

// The converted objects may contain unparsed text in numeric fields; the
// backend validates them, so they are typed as the request shape here.
export function toPlan(ws: Workspace): PlanValidationRequest {
  return {
    resources: convert("resources", ws.resources),
    allocations: convert("allocations", ws.allocations),
    shelters: convert("shelters", ws.shelters),
  } as unknown as PlanValidationRequest;
}

export function toDraftRequest(ws: Workspace): DraftPlanRequest {
  const scenario = {
    ...ws.scenario,
    affected_population: toNumberOrText(ws.scenario.affected_population),
  } as unknown as DisasterScenario;
  return {
    scenario,
    resources: convert("resources", ws.resources),
    shelters: convert("shelters", ws.shelters),
    needs: convert("needs", ws.needs),
    constraints: constraintList(ws.constraints),
  } as unknown as DraftPlanRequest;
}

// Synthetic sample workspaces ----------------------------------------------------

function rows<T extends object>(items: T[]): Row[] {
  return items.map((item) =>
    Object.fromEntries(Object.entries(item).map(([k, v]) => [k, String(v)])),
  );
}

export interface SampleWorkspace {
  id: string;
  label: string;
  description: string;
  workspace: Workspace;
}

/** Build a workspace from a sample. The disaster location comes from the
 * sample's own data; a sample without one starts with an empty location for the
 * user to fill in, never a made-up or device location. */
export function workspaceFromSample(sample: SamplePlan): SampleWorkspace {
  return {
    id: sample.id,
    label: sample.label,
    description: sample.description,
    workspace: {
      scenario: {
        scenario_id: `SCN-${sample.id}`,
        name: "Synthetic river flood",
        disaster_type: "flood",
        severity: "high",
        affected_population: "930",
        location: sample.scenarioLocation ?? "",
        description:
          "Synthetic training scenario: river flooding has displaced families into two shelters.",
      },
      resources: rows(sample.plan.resources),
      shelters: rows(sample.plan.shelters),
      allocations: rows(sample.plan.allocations),
      needs: [
        {
          destination_id: "shelter-001",
          resource_type: "drinking_water",
          quantity_needed: "6000",
        },
      ],
      constraints: "Road to Zone B is passable by light vehicles only.",
    },
  };
}

export const sampleWorkspaces: SampleWorkspace[] = samplePlans.map(workspaceFromSample);
