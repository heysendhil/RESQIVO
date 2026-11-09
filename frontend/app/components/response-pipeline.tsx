"use client";

import type { DraftPlanResponse } from "@/lib/api";
import {
  canApprove,
  derivePipeline,
  type PipelineRun,
  type PipelineStatus,
} from "@/lib/pipeline";
import type { RequestState } from "@/lib/use-request";

import { readable } from "./incident-queue";
import { AllocationTable, Badge, DRAFT_LABEL, ErrorAlert, SAFETY_DISCLAIMER } from "./results";

const STATUS: Record<PipelineStatus, { mark: string; tone: string; label: string }> = {
  done: { mark: "✓", tone: "border-emerald-500 bg-emerald-500 text-white", label: "Done" },
  running: { mark: "…", tone: "border-accent bg-accent/15 text-accent motion-safe:animate-pulse", label: "In progress" },
  waiting: { mark: "•", tone: "border-line bg-panel-raised text-muted", label: "Waiting" },
  failed: { mark: "✗", tone: "border-red-500 bg-red-500 text-white", label: "Failed" },
  attention: { mark: "!", tone: "border-amber-500 bg-amber-400 text-slate-950", label: "Needs attention" },
  skipped: { mark: "–", tone: "border-line bg-transparent text-muted", label: "Skipped" },
};

const secondary =
  "rounded-md border border-line px-3 py-1.5 text-xs font-semibold text-ink hover:border-accent/60 hover:bg-accent/10 disabled:cursor-not-allowed disabled:opacity-50";

/** The automatic response pipeline for the most urgent simulated incident.
 * It ends with a human decision, which is only recorded. */
export default function ResponsePipeline({
  run,
  draft,
  approving,
  approveError,
  onApprove,
  onReject,
  onRetry,
  onDismiss,
}: {
  run: PipelineRun;
  draft: RequestState<DraftPlanResponse>;
  approving: boolean;
  approveError: string | null;
  onApprove: () => void;
  onReject: () => void;
  onRetry: () => void;
  onDismiss: () => void;
}) {
  const stages = derivePipeline(run, draft);
  const plan = draft.status === "success" ? draft.data : null;
  const approvable = canApprove(draft);
  const decided = run.decision;

  return (
    <section
      aria-labelledby="pipeline-heading"
      className="flex flex-col gap-4 rounded-lg border border-accent/40 bg-panel p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          <h3 id="pipeline-heading" className="text-sm font-semibold uppercase tracking-wider text-ink">
            Response pipeline
          </h3>
          <p className="text-xs text-muted">
            Started automatically for the most urgent new incident:{" "}
            <span className="font-medium text-ink">{run.incident.title}</span>
          </p>
        </div>
        <button type="button" onClick={onDismiss} className={secondary}>
          Close panel
        </button>
      </div>

      <ol className="grid gap-2 md:grid-cols-5">
        {stages.map((stage, index) => {
          const status = STATUS[stage.status];
          return (
            <li
              key={stage.id}
              data-pipeline-stage={stage.id}
              data-status={stage.status}
              className="flex gap-2.5 rounded-md border border-line bg-canvas/50 p-3 md:flex-col md:gap-1.5"
            >
              <span className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className={`inline-flex size-6 shrink-0 items-center justify-center rounded-full border-2 text-xs font-bold ${status.tone}`}
                >
                  {status.mark}
                </span>
                <span className="text-xs font-medium text-muted">Step {index + 1}</span>
              </span>
              <span className="flex flex-col gap-0.5">
                <span className="text-sm font-semibold text-ink">{stage.label}</span>
                <span className="text-xs font-semibold text-muted">{status.label}</span>
                <span className="break-words text-xs text-muted">{stage.detail}</span>
              </span>
            </li>
          );
        })}
      </ol>

      {draft.status === "error" && (
        <div className="flex flex-col gap-2">
          <ErrorAlert message={draft.message} fieldErrors={draft.fieldErrors} />
          <button type="button" onClick={onRetry} className={`${secondary} w-fit`}>
            Retry the AI draft
          </button>
        </div>
      )}

      {plan?.plan_review && (
        <div className="flex flex-col gap-3 rounded-md border border-amber-500/40 bg-amber-500/5 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="text-sm font-semibold text-ink">Human review</h4>
            <Badge tone="draft">{DRAFT_LABEL}</Badge>
            <Badge tone={plan.status === "draft_valid" ? "ok" : "bad"}>
              {plan.status === "draft_valid" ? "Passed configured rules" : "Rule violations remain"}
            </Badge>
          </div>
          <p className="text-xs text-muted">
            {readable(run.incident.disaster_type)} · {run.incident.severity} · {run.incident.location}
            {run.incident.affected_people !== null &&
              ` · ${run.incident.affected_people.toLocaleString()} people affected`}
          </p>
          <AllocationTable
            allocations={plan.plan_review.final_plan.allocations}
            caption="Proposed allocations (AI draft — not dispatched)"
          />
          <p className="text-xs leading-relaxed text-warn-ink">{SAFETY_DISCLAIMER}</p>

          {decided ? (
            <p
              role="status"
              className={`rounded-md border p-3 text-sm ${
                decided.kind === "approved"
                  ? "border-emerald-500/40 bg-emerald-500/10 text-ok-ink"
                  : "border-line bg-panel-raised text-ink"
              }`}
            >
              {decided.kind === "approved"
                ? `Plan approved by the operator at ${decided.at}. The decision is recorded and the allocations were copied to the workspace; nothing has been dispatched, booked or requested.`
                : `Plan rejected at ${decided.at}. Adjust the resources, shelters or needs and generate a new draft in Draft Plans.`}
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={!approvable || approving}
                  onClick={onApprove}
                  className="rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {approving ? "Recording…" : "Approve plan (record decision)"}
                </button>
                <button type="button" disabled={approving} onClick={onReject} className={secondary}>
                  Reject
                </button>
                <a href="#response-plan" className={secondary}>
                  View full draft
                </a>
              </div>
              {!approvable && (
                <p className="text-xs text-warn-ink">
                  The plan failed the configured rules, so it cannot be approved. Revise it in
                  Draft Plans.
                </p>
              )}
              {approveError && <ErrorAlert message={approveError} />}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
