// The automatic response pipeline that runs after a simulation: the most
// urgent new incident is taken through intake, an AI draft and deterministic
// validation, and then waits for a human decision. The decision is only
// recorded; nothing is dispatched. Stage states come from real API results.

import type { DraftPlanResponse, Incident } from "@/lib/api";
import type { RequestState } from "@/lib/use-request";
import type { Workspace } from "@/lib/workspace";

const SEVERITY_RANK: Record<string, number> = { critical: 3, high: 2, moderate: 1, low: 0 };

/** The most urgent of the given incidents: highest severity, then most people
 * affected (unknown counts last), then the first listed. */
export function mostUrgent(incidents: readonly Incident[]): Incident | null {
  let best: Incident | null = null;
  for (const incident of incidents) {
    if (incident.status === "closed") continue;
    if (
      !best ||
      SEVERITY_RANK[incident.severity] > SEVERITY_RANK[best.severity] ||
      (SEVERITY_RANK[incident.severity] === SEVERITY_RANK[best.severity] &&
        (incident.affected_people ?? -1) > (best.affected_people ?? -1))
    ) {
      best = incident;
    }
  }
  return best;
}

/** The workspace with the incident's facts as its scenario. Resources,
 * shelters, needs and constraints are kept: quantities are never invented. */
export function workspaceForIncident(workspace: Workspace, incident: Incident): Workspace {
  return {
    ...workspace,
    scenario: {
      scenario_id: incident.incident_id,
      name: incident.title,
      disaster_type: incident.disaster_type,
      severity: incident.severity,
      affected_population:
        incident.affected_people === null ? "" : String(incident.affected_people),
      location: incident.location,
      description: incident.summary,
    },
  };
}

export type Decision = { kind: "approved" | "rejected"; at: string } | null;

export interface PipelineRun {
  incident: Incident;
  decision: Decision;
}

export type PipelineStatus = "done" | "running" | "waiting" | "failed" | "attention" | "skipped";

export interface PipelineStage {
  id: "incident" | "intake" | "allocation" | "validation" | "review";
  label: string;
  status: PipelineStatus;
  detail: string;
}

/** Whether the operator may approve: only a draft that exists and passed the
 * configured rules. Anything else must be revised first. */
export function canApprove(draft: RequestState<DraftPlanResponse>): boolean {
  return draft.status === "success" && draft.data.status === "draft_valid";
}

export function derivePipeline(
  run: PipelineRun,
  draft: RequestState<DraftPlanResponse>,
): PipelineStage[] {
  const { incident, decision } = run;
  const missing = incident.missing_fields.length;
  const stages: PipelineStage[] = [
    {
      id: "incident",
      label: "Incident received",
      status: "done",
      detail: `${incident.incident_id} · ${incident.severity} · ${incident.location}`,
    },
    {
      id: "intake",
      label: "Intake recorded",
      // Intake is complete either way; missing facts are follow-up items for
      // the operator, not a failure of the step.
      status: "done",
      detail: missing
        ? `Recorded · follow up: ${incident.missing_fields.join(", ")}`
        : "All required facts present",
    },
  ];

  if (draft.status === "idle" || draft.status === "loading") {
    stages.push(
      {
        id: "allocation",
        label: "AI resource allocation",
        status: draft.status === "loading" ? "running" : "waiting",
        detail: "Drafting from the workspace's available resources and shelters",
      },
      { id: "validation", label: "Deterministic validation", status: "waiting", detail: "Runs on the draft" },
      { id: "review", label: "Human review", status: "waiting", detail: "Waiting for a plan" },
    );
    return stages;
  }

  if (draft.status === "error") {
    stages.push(
      { id: "allocation", label: "AI resource allocation", status: "failed", detail: draft.message },
      { id: "validation", label: "Deterministic validation", status: "skipped", detail: "No draft to check" },
      { id: "review", label: "Human review", status: "skipped", detail: "No plan to review" },
    );
    return stages;
  }

  const result = draft.data;
  if (result.status === "insufficient_information" || !result.plan_review) {
    stages.push(
      {
        id: "allocation",
        label: "AI resource allocation",
        status: "attention",
        detail: "Not enough information to draft; check resources and shelters",
      },
      { id: "validation", label: "Deterministic validation", status: "skipped", detail: "No draft to check" },
      { id: "review", label: "Human review", status: "skipped", detail: "No plan to review" },
    );
    return stages;
  }

  const allocations = result.plan_review.final_plan.allocations.length;
  const violations = result.plan_review.final_validation.violations.length;
  stages.push(
    {
      id: "allocation",
      label: "AI resource allocation",
      status: "done",
      detail: `${allocations} proposed allocation${allocations === 1 ? "" : "s"}${
        result.evidence_available ? ", grounded in WHO guidance" : ", no supporting evidence"
      }`,
    },
    {
      id: "validation",
      label: "Deterministic validation",
      status: result.status === "draft_valid" ? "done" : "attention",
      detail:
        result.status === "draft_valid"
          ? "Passed the configured rules"
          : `${violations} rule violation${violations === 1 ? "" : "s"} remain`,
    },
    {
      id: "review",
      label: "Human review",
      status: decision ? "done" : result.status === "draft_valid" ? "waiting" : "attention",
      detail: decision
        ? `${decision.kind === "approved" ? "Approved" : "Rejected"} by the operator (recorded only)`
        : result.status === "draft_valid"
          ? "Awaiting your decision"
          : "Revise the plan before it can be approved",
    },
  );
  return stages;
}
