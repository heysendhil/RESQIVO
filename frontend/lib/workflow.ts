// The agentic workflow as shown in the Command Center. Stage states are derived
// only from the latest real /draft-plan request; nothing is marked complete
// unless the API response confirms it. Human review is never completed by the
// system.

import type { DraftPlanResponse } from "@/lib/api";
import type { RequestState } from "@/lib/use-request";

export type StageStatus =
  | "pending"
  | "running"
  | "complete"
  | "attention"
  | "skipped"
  | "failed"
  | "not_configured"
  | "required";

export interface Stage {
  id: "input" | "retrieval" | "proposal" | "validation" | "review";
  label: string;
  status: StageStatus;
  detail: string;
}

const LABELS: Record<Stage["id"], string> = {
  input: "Scenario input",
  retrieval: "Evidence retrieval",
  proposal: "AI proposal",
  validation: "Deterministic validation",
  review: "Human review",
};

const INSUFFICIENT_REASONS: Record<string, string> = {
  no_affected_population: "no affected population",
  no_available_resources: "no available resources",
  no_shelters: "no shelters",
};

const EVIDENCE_REASONS: Record<string, string> = {
  knowledge_base_empty: "Knowledge base is empty",
  no_relevant_passages: "No relevant passages found",
  model_reported_insufficient_evidence: "Evidence insufficient for guidance",
  answer_not_grounded: "Guidance withheld: not grounded",
};

const HUMAN_REVIEW: Stage = {
  id: "review",
  label: LABELS.review,
  status: "required",
  detail: "A qualified person must review any plan. Nothing is dispatched.",
};

function stage(id: Stage["id"], status: StageStatus, detail: string): Stage {
  return { id, label: LABELS[id], status, detail };
}

export function deriveWorkflow(draft: RequestState<DraftPlanResponse>): Stage[] {
  if (draft.status === "idle") {
    return [
      stage("input", "pending", "Not yet submitted"),
      stage("retrieval", "pending", "Waiting for a draft request"),
      stage("proposal", "pending", "Waiting for a draft request"),
      stage("validation", "pending", "Waiting for a draft request"),
      HUMAN_REVIEW,
    ];
  }
  if (draft.status === "loading") {
    return [
      stage("input", "running", "Submitted; awaiting the API"),
      stage("retrieval", "pending", "In progress or queued"),
      stage("proposal", "pending", "In progress or queued"),
      stage("validation", "pending", "In progress or queued"),
      HUMAN_REVIEW,
    ];
  }
  if (draft.status === "error" && draft.notConfigured) {
    // The backend's own 503: AI features have no model key or valid settings.
    return [
      stage("input", "pending", "Not processed: AI features unavailable"),
      stage("retrieval", "not_configured", "AI features are not configured on the server"),
      stage("proposal", "not_configured", "AI features are not configured on the server"),
      stage("validation", "pending", "Not run for this request; Validate plan still works"),
      HUMAN_REVIEW,
    ];
  }
  if (draft.status === "error") {
    // Only a 422 (field errors) says where the request failed.
    const rejected = draft.fieldErrors.length > 0;
    return [
      stage(
        "input",
        rejected ? "failed" : "pending",
        rejected ? "Inputs rejected by the API" : "Outcome unknown: the request failed",
      ),
      stage("retrieval", "pending", "Not confirmed"),
      stage("proposal", "pending", "Not confirmed"),
      stage("validation", "pending", "Not confirmed"),
      HUMAN_REVIEW,
    ];
  }

  const result = draft.data;
  if (result.status === "insufficient_information") {
    const reason = result.reason ? INSUFFICIENT_REASONS[result.reason] ?? result.reason : "";
    return [
      stage("input", "attention", `Insufficient information${reason ? `: ${reason}` : ""}`),
      stage("retrieval", "skipped", "Not run: no draft possible"),
      stage("proposal", "skipped", "Not run: no draft possible"),
      stage("validation", "skipped", "No draft to validate"),
      HUMAN_REVIEW,
    ];
  }

  const guidance = result.guidance;
  const retrieval =
    guidance && guidance.status === "answered"
      ? stage(
          "retrieval",
          "complete",
          `Evidence found: ${guidance.citations.length} citation${guidance.citations.length === 1 ? "" : "s"}`,
        )
      : stage(
          "retrieval",
          "attention",
          guidance?.reason
            ? EVIDENCE_REASONS[guidance.reason] ?? "No supporting evidence"
            : "No supporting evidence",
        );

  const review = result.plan_review;
  const proposal = review
    ? stage(
        "proposal",
        "complete",
        `Draft produced: ${review.final_plan.allocations.length} allocation${review.final_plan.allocations.length === 1 ? "" : "s"}` +
          (review.correction_attempts
            ? `, ${review.correction_attempts} correction${review.correction_attempts === 1 ? "" : "s"}`
            : ""),
      )
    : stage("proposal", "pending", "Not confirmed");

  const violations = review?.final_validation.violations.length ?? 0;
  const validation = !review
    ? stage("validation", "pending", "Not confirmed")
    : review.final_validation.valid
      ? stage("validation", "complete", "Passed configured rules")
      : stage(
          "validation",
          "attention",
          `${violations} rule violation${violations === 1 ? "" : "s"} remain`,
        );

  return [
    stage("input", "complete", "Accepted by the API"),
    retrieval,
    proposal,
    validation,
    HUMAN_REVIEW,
  ];
}
