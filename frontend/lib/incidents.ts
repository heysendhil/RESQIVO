// The incident queue. RESQIVO's backend has no incident list: each request
// carries one scenario. The queue therefore lists the synthetic sample
// scenarios, plus the user's edited workspace, and derives the active
// incident's status only from real API results for that workspace.

import type { DraftPlanResponse, ValidationResult } from "@/lib/api";
import type { RequestState } from "@/lib/use-request";
import { sampleWorkspaces, type ScenarioFields } from "@/lib/workspace";

export type IncidentTone = "ok" | "bad" | "draft" | "info" | "neutral";

export interface IncidentStatus {
  label: string;
  tone: IncidentTone;
}

export interface Incident {
  /** The sample ID, or "edited" for the user's edited workspace. */
  key: string;
  sampleId: string | null;
  label: string;
  scenario: ScenarioFields;
  active: boolean;
  status: IncidentStatus;
}

export const NOT_ASSESSED: IncidentStatus = { label: "Not assessed", tone: "neutral" };

/** Status of the active workspace from the latest validation and draft. */
export function assessmentStatus(
  validation: RequestState<ValidationResult>,
  draft: RequestState<DraftPlanResponse>,
): IncidentStatus {
  if (validation.status === "loading" || draft.status === "loading") {
    return { label: "Assessment in progress", tone: "info" };
  }
  if (draft.status === "success") {
    switch (draft.data.status) {
      case "draft_valid":
        return { label: "Draft ready · awaiting human review", tone: "draft" };
      case "draft_invalid":
        return { label: "Draft failed rules", tone: "bad" };
      case "insufficient_information":
        return { label: "Insufficient information", tone: "neutral" };
    }
  }
  if (draft.status === "error") return { label: "Draft request failed", tone: "bad" };
  if (validation.status === "success") {
    return validation.data.valid
      ? { label: "Passed configured rules", tone: "ok" }
      : { label: "Rule violations found", tone: "bad" };
  }
  if (validation.status === "error") return { label: "Validation request failed", tone: "bad" };
  return NOT_ASSESSED;
}

export function incidentQueue(
  activeSampleId: string | null,
  activeScenario: ScenarioFields,
  activeStatus: IncidentStatus,
): Incident[] {
  const samples: Incident[] = sampleWorkspaces.map((sample) => {
    const active = sample.id === activeSampleId;
    return {
      key: sample.id,
      sampleId: sample.id,
      label: sample.label,
      scenario: active ? activeScenario : sample.workspace.scenario,
      active,
      status: active ? activeStatus : NOT_ASSESSED,
    };
  });
  if (activeSampleId !== null) return samples;
  return [
    {
      key: "edited",
      sampleId: null,
      label: "Edited workspace",
      scenario: activeScenario,
      active: true,
      status: activeStatus,
    },
    ...samples,
  ];
}
