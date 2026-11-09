import type { DraftPlanResponse, ValidationResult } from "@/lib/api";
import type { WorkspaceSummary } from "@/lib/summary";
import type { RequestState } from "@/lib/use-request";

import { Badge, type Tone } from "./results";

export function number(value: number | null): string {
  return value === null ? "—" : value.toLocaleString();
}

function Card({
  label,
  value,
  detail,
  badge,
  meter,
}: {
  label: string;
  value: React.ReactNode;
  detail?: React.ReactNode;
  badge?: React.ReactNode;
  meter?: { percent: number; tone: "accent" | "warn" | "bad" } | null;
}) {
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-line bg-panel px-3 py-2.5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[0.7rem] font-semibold uppercase tracking-wider text-muted">{label}</p>
        {badge}
      </div>
      <p className="font-mono text-xl font-semibold text-ink">{value}</p>
      {meter && (
        <div aria-hidden="true" className="h-1 overflow-hidden rounded-full bg-panel-raised">
          <div
            className={`h-full rounded-full ${
              meter.tone === "bad" ? "bg-red-400" : meter.tone === "warn" ? "bg-amber-400" : "bg-accent"
            }`}
            style={{ width: `${Math.min(meter.percent, 100)}%` }}
          />
        </div>
      )}
      {detail && <p className="text-xs text-muted">{detail}</p>}
    </div>
  );
}

function validationCard(state: RequestState<ValidationResult>) {
  switch (state.status) {
    case "idle":
      return { value: "Not run", detail: "Run Validate plan to check the allocations." };
    case "loading":
      return { value: "Running…", detail: "Awaiting the deterministic validator." };
    case "error":
      return { value: "Failed", detail: "The request failed; see Review." };
    case "success":
      return state.data.valid
        ? { value: "Passed", detail: "No configured rule violations.", badge: <Badge tone="ok">Valid</Badge> }
        : {
            value: `${state.data.violations.length} violation${state.data.violations.length === 1 ? "" : "s"}`,
            detail: "Configured rules not met.",
            badge: <Badge tone="bad">Invalid</Badge>,
          };
  }
}

const DRAFT_STATUS: Record<DraftPlanResponse["status"], { value: string; tone: Tone }> = {
  draft_valid: { value: "Passed rules", tone: "ok" },
  draft_invalid: { value: "Failed rules", tone: "bad" },
  insufficient_information: { value: "Not drafted", tone: "neutral" },
};

function draftCard(state: RequestState<DraftPlanResponse>) {
  switch (state.status) {
    case "idle":
      return { value: "Not run", detail: "Generate a draft in Draft Plans." };
    case "loading":
      return { value: "Drafting…", detail: "Awaiting the AI and the validator." };
    case "error":
      return { value: "Failed", detail: "The request failed; see Draft Plans." };
    case "success": {
      const status = DRAFT_STATUS[state.data.status];
      return {
        value: status.value,
        detail: "Draft — requires human review",
        badge: <Badge tone={status.tone}>Draft</Badge>,
      };
    }
  }
}

/** Key figures, computed only from the workspace and real API results. */
export default function Overview({
  summary,
  validation,
  draft,
}: {
  summary: WorkspaceSummary;
  validation: RequestState<ValidationResult>;
  draft: RequestState<DraftPlanResponse>;
}) {
  const validate = validationCard(validation);
  const drafted = draftCard(draft);
  const occupancy =
    summary.totalCapacity && summary.totalOccupancy !== null
      ? Math.round((summary.totalOccupancy / summary.totalCapacity) * 100)
      : null;
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      <Card
        label="Affected population"
        value={number(summary.affectedPopulation)}
        detail="As entered for the scenario"
      />
      <Card
        label="Resources"
        value={summary.resourceEntries}
        detail={`${summary.resourceTypes} resource type${summary.resourceTypes === 1 ? "" : "s"} entered`}
      />
      <Card
        label="Shelters"
        value={summary.shelters}
        meter={
          occupancy === null
            ? null
            : {
                percent: occupancy,
                tone: summary.sheltersOverCapacity ? "bad" : occupancy >= 90 ? "warn" : "accent",
              }
        }
        detail={
          <>
            {number(summary.totalOccupancy)} occupied of {number(summary.totalCapacity)} capacity
            {summary.sheltersOverCapacity ? (
              <span className="text-bad-ink"> · {summary.sheltersOverCapacity} over capacity</span>
            ) : null}
          </>
        }
      />
      <Card
        label="Proposed allocations"
        value={summary.allocations}
        detail="Entered for validation and review"
      />
      <Card label="Latest validation" value={validate.value} detail={validate.detail} badge={validate.badge} />
      <Card label="Latest draft" value={drafted.value} detail={drafted.detail} badge={drafted.badge} />
    </div>
  );
}
