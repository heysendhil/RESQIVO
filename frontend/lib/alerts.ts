// Alerts shown in the Command Center. Each one is derived from the entered
// workspace values or from a real API result; none is generated or simulated.

import type { DraftPlanResponse, ValidationResult } from "@/lib/api";
import { shelterLoad } from "@/lib/summary";
import type { RequestState } from "@/lib/use-request";
import type { Workspace } from "@/lib/workspace";

export type AlertSeverity = "critical" | "warning" | "info";

export interface Alert {
  id: string;
  severity: AlertSeverity;
  title: string;
  detail: string;
  /** Where the alert comes from, shown to the user. */
  source: "Workspace data" | "Deterministic validator" | "AI draft" | "API request";
}

/** Occupancy at or above this share of capacity is a warning. */
export const NEAR_CAPACITY = 0.9;

const ORDER: Record<AlertSeverity, number> = { critical: 0, warning: 1, info: 2 };

export function deriveAlerts(
  workspace: Workspace,
  validation: RequestState<ValidationResult>,
  draft: RequestState<DraftPlanResponse>,
): Alert[] {
  const alerts: Alert[] = [];

  workspace.shelters.forEach((row, index) => {
    const load = shelterLoad(row);
    if (!load) return;
    const name = row.name?.trim() || row.shelter_id?.trim() || `Shelter ${index + 1}`;
    const figures = `${load.occupancy.toLocaleString()} of ${load.capacity.toLocaleString()} places occupied`;
    if (load.overCapacity) {
      alerts.push({
        id: `shelter-over-${index}`,
        severity: "critical",
        title: `${name}: over capacity`,
        detail: figures,
        source: "Workspace data",
      });
    } else if (load.ratio !== null && load.ratio >= NEAR_CAPACITY) {
      alerts.push({
        id: `shelter-near-${index}`,
        severity: "warning",
        title: `${name}: near capacity`,
        detail: `${figures} (${Math.round(load.ratio * 100)}%)`,
        source: "Workspace data",
      });
    }
  });

  if (validation.status === "success") {
    validation.data.violations.forEach((violation, index) => {
      alerts.push({
        id: `violation-${index}`,
        severity: "critical",
        title: `${violation.code} on ${violation.entity_id}`,
        detail: violation.message,
        source: "Deterministic validator",
      });
    });
  } else if (validation.status === "error") {
    alerts.push({
      id: "validation-error",
      severity: "warning",
      title: "Validation request failed",
      detail: validation.message,
      source: "API request",
    });
  }

  if (draft.status === "success") {
    if (draft.data.status === "draft_invalid") {
      alerts.push({
        id: "draft-invalid",
        severity: "warning",
        title: "Latest draft failed rule-based validation",
        detail: "Review the remaining violations in Draft Plans before any use.",
        source: "AI draft",
      });
    }
    if (!draft.data.evidence_available && draft.data.status !== "insufficient_information") {
      alerts.push({
        id: "draft-no-evidence",
        severity: "info",
        title: "Latest draft has no supporting evidence",
        detail: "The draft is based only on the workspace data.",
        source: "AI draft",
      });
    }
  } else if (draft.status === "error") {
    alerts.push({
      id: "draft-error",
      severity: "warning",
      title: "Draft request failed",
      detail: draft.message,
      source: "API request",
    });
  }

  return alerts.sort((a, b) => ORDER[a.severity] - ORDER[b.severity]);
}
