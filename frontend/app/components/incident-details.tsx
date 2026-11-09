"use client";

import type { DraftPlanResponse, ReviewResponse, ValidationResult } from "@/lib/api";
import { shelterLoad, type WorkspaceSummary } from "@/lib/summary";
import type { RequestState } from "@/lib/use-request";
import { constraintList, type Workspace } from "@/lib/workspace";

import { readable, SEVERITY_TONE } from "./incident-queue";
import type { MapSelection } from "./operational-picture";
import { number } from "./overview";
import { Badge, DRAFT_LABEL } from "./results";

export type DetailTab = "status" | "incident" | "selection";

const TABS: { id: DetailTab; label: string }[] = [
  { id: "status", label: "Status" },
  { id: "incident", label: "Incident" },
  { id: "selection", label: "Map selection" },
];

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3 border-b border-line/60 py-1.5 text-xs last:border-0">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right text-ink">{children}</dd>
    </div>
  );
}

function Block({ title, edge, children }: { title: string; edge: string; children: React.ReactNode }) {
  return (
    <div className={`flex flex-col gap-1 rounded-md border border-line border-l-4 ${edge} bg-canvas/50 p-2.5`}>
      <p className="text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-muted">{title}</p>
      <div className="text-xs leading-relaxed text-ink">{children}</div>
    </div>
  );
}

function validationText(state: RequestState<ValidationResult>) {
  switch (state.status) {
    case "idle":
      return "Not run for this workspace.";
    case "loading":
      return "Running…";
    case "error":
      return "The validation request failed.";
    case "success":
      return state.data.valid ? (
        "Passed the configured rules."
      ) : (
        <>
          {state.data.violations.length} violation(s):{" "}
          <span className="font-mono text-bad-ink">
            {[...new Set(state.data.violations.map((v) => v.code))].join(", ")}
          </span>
        </>
      );
  }
}

function draftText(state: RequestState<DraftPlanResponse>) {
  switch (state.status) {
    case "idle":
      return "No draft generated.";
    case "loading":
      return "Drafting…";
    case "error":
      return "The draft request failed.";
    case "success": {
      const draft = state.data;
      if (draft.status === "insufficient_information") return "Not enough information to draft.";
      const allocations = draft.plan_review?.final_plan.allocations.length ?? 0;
      const citations = draft.guidance?.status === "answered" ? draft.guidance.citations.length : 0;
      return (
        <>
          {allocations} proposed allocation(s), {draft.status === "draft_valid" ? "passed" : "failed"}{" "}
          rule-based validation; {citations} citation(s). {DRAFT_LABEL}.
        </>
      );
    }
  }
}

function reviewText(state: RequestState<ReviewResponse>) {
  if (state.status === "loading") return "AI-assisted review running…";
  if (state.status === "error") return "The AI-assisted review request failed.";
  if (state.status === "success" && state.data.plan_review) {
    return state.data.plan_review.final_validation.valid
      ? "Final plan passed the configured rules."
      : "Violations remain in the final plan.";
  }
  return "No AI-assisted review run.";
}

function SelectionDetails({ workspace, selection }: { workspace: Workspace; selection: MapSelection }) {
  if (!selection) {
    return (
      <p className="rounded-md border border-dashed border-line p-4 text-center text-xs text-muted">
        Select a shelter (S) or supply point (R) on the map to see its details.
      </p>
    );
  }

  if (selection.kind === "shelter") {
    const row = workspace.shelters[selection.index];
    if (!row) return <p className="text-xs text-muted">This shelter is no longer in the workspace.</p>;
    const load = shelterLoad(row);
    const id = row.shelter_id?.trim() ?? "";
    const inbound = workspace.allocations.filter((a) => a.destination_id?.trim() === id);
    const needs = workspace.needs.filter((n) => n.destination_id?.trim() === id);
    return (
      <div className="flex flex-col gap-3">
        <div>
          <p className="text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-muted">Shelter</p>
          <p className="text-sm font-semibold text-ink">{row.name || "Unnamed shelter"}</p>
        </div>
        <dl>
          <Row label="Shelter ID"><span className="font-mono">{id || "—"}</span></Row>
          <Row label="Location">{row.location || "No location entered"}</Row>
          <Row label="Capacity"><span className="font-mono">{load ? load.capacity.toLocaleString() : row.capacity || "—"}</span></Row>
          <Row label="Current occupancy"><span className="font-mono">{load ? load.occupancy.toLocaleString() : row.current_occupancy || "—"}</span></Row>
          <Row label="Load">
            {!load ? "—" : load.overCapacity ? <Badge tone="bad">Over capacity</Badge> : load.ratio === null ? "No capacity" : `${Math.round(load.ratio * 100)}%`}
          </Row>
        </dl>
        <Block title="Proposed allocations inbound" edge="border-l-accent/70">
          {inbound.length === 0 ? (
            "None entered."
          ) : (
            <ul className="font-mono">
              {inbound.map((a, i) => (
                <li key={`${a.allocation_id}-${i}`}>
                  {a.allocation_id}: {a.quantity_allocated} × {a.resource_id}
                </li>
              ))}
            </ul>
          )}
        </Block>
        <Block title="Known needs" edge="border-l-line">
          {needs.length === 0 ? (
            "None entered."
          ) : (
            <ul>
              {needs.map((n, i) => (
                <li key={i}>
                  {readable(n.resource_type)}: <span className="font-mono">{n.quantity_needed}</span>
                </li>
              ))}
            </ul>
          )}
        </Block>
      </div>
    );
  }

  const name = selection.name;
  const resources = workspace.resources.filter((r) => (r.location?.trim() || "No location entered") === name);
  const ids = new Set(resources.map((r) => r.resource_id?.trim()));
  const outbound = workspace.allocations.filter((a) => ids.has(a.resource_id?.trim()));
  return (
    <div className="flex flex-col gap-3">
      <div>
        <p className="text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-muted">Supply point</p>
        <p className="text-sm font-semibold text-ink">{name}</p>
      </div>
      <Block title="Resources held" edge="border-l-accent/70">
        {resources.length === 0 ? (
          "None."
        ) : (
          <ul>
            {resources.map((r, i) => (
              <li key={`${r.resource_id}-${i}`}>
                {r.name || r.resource_id}:{" "}
                <span className="font-mono">
                  {r.quantity_available} {r.unit}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Block>
      <Block title="Proposed allocations outbound" edge="border-l-line">
        {outbound.length === 0 ? (
          "None entered."
        ) : (
          <ul className="font-mono">
            {outbound.map((a, i) => (
              <li key={`${a.allocation_id}-${i}`}>
                {a.allocation_id}: {a.quantity_allocated} → {a.destination_id}
              </li>
            ))}
          </ul>
        )}
      </Block>
    </div>
  );
}

/** The selected incident: its latest results, scenario facts and the map
 * selection. The validator's result, AI output and human review stay
 * visibly separate. */
export default function IncidentDetails({
  workspace,
  summary,
  sampleLabel,
  validation,
  draft,
  review,
  selection,
  tab,
  onTab,
}: {
  workspace: Workspace;
  summary: WorkspaceSummary;
  sampleLabel: string | null;
  validation: RequestState<ValidationResult>;
  draft: RequestState<DraftPlanResponse>;
  review: RequestState<ReviewResponse>;
  selection: MapSelection;
  tab: DetailTab;
  onTab: (tab: DetailTab) => void;
}) {
  const scenario = workspace.scenario;
  const constraints = constraintList(workspace.constraints);
  return (
    <section
      aria-labelledby="details-heading"
      className="flex h-full min-h-0 flex-col rounded-lg border border-line bg-panel"
    >
      <div className="flex flex-col gap-2 border-b border-line p-4">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-mono text-xs text-accent">{scenario.scenario_id || "No scenario ID"}</span>
          <Badge tone={SEVERITY_TONE[summary.severity] ?? "neutral"}>{summary.severity} severity</Badge>
          <Badge tone="accent">{readable(summary.disasterType)}</Badge>
        </div>
        <h3 id="details-heading" className="text-lg font-semibold text-ink">
          {summary.scenarioName || "Untitled scenario"}
        </h3>
        <p className="text-xs text-muted">
          {summary.location || "No location entered"} · affected population{" "}
          <span className="font-mono text-ink">{number(summary.affectedPopulation)}</span>
        </p>
        <Badge tone="draft">
          {sampleLabel ? `Synthetic sample: ${sampleLabel}` : "Edited workspace (synthetic basis)"}
        </Badge>
      </div>

      <div role="tablist" aria-label="Incident details" className="flex border-b border-line px-2">
        {TABS.map((item) => (
          <button
            key={item.id}
            id={`detail-tab-${item.id}`}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            aria-controls="detail-panel"
            onClick={() => onTab(item.id)}
            className={`-mb-px border-b-2 px-3 py-2 text-xs font-semibold uppercase tracking-wider ${
              tab === item.id ? "border-accent text-accent" : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div
        id="detail-panel"
        role="tabpanel"
        aria-labelledby={`detail-tab-${tab}`}
        className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-4"
      >
        {tab === "status" && (
          <>
            <Block title="Deterministic validation" edge="border-l-emerald-400/70">
              {validationText(validation)}
            </Block>
            <Block title="AI draft" edge="border-l-sky-400/70">
              {draftText(draft)}
            </Block>
            <Block title="AI-assisted review" edge="border-l-sky-400/70">
              {reviewText(review)}
            </Block>
            <Block title="Human review" edge="border-l-amber-400/70">
              Required for any plan. RESQIVO never marks human review complete, and
              nothing is dispatched.
            </Block>
          </>
        )}
        {tab === "incident" && (
          <>
            <dl>
              <Row label="Scenario ID"><span className="font-mono">{scenario.scenario_id || "—"}</span></Row>
              <Row label="Disaster type">{readable(summary.disasterType)}</Row>
              <Row label="Location">{summary.location || "No location entered"}</Row>
              <Row label="Affected population"><span className="font-mono">{number(summary.affectedPopulation)}</span></Row>
              <Row label="Resources · shelters"><span className="font-mono">{summary.resourceEntries} · {summary.shelters}</span></Row>
              <Row label="Allocations · needs"><span className="font-mono">{summary.allocations} · {summary.needs}</span></Row>
            </dl>
            {scenario.description.trim() && (
              <Block title="Description" edge="border-l-line">{scenario.description}</Block>
            )}
            <Block title="Constraints" edge="border-l-line">
              {constraints.length === 0 ? "None entered." : (
                <ul className="list-disc pl-4">
                  {constraints.map((c) => <li key={c}>{c}</li>)}
                </ul>
              )}
            </Block>
          </>
        )}
        {tab === "selection" && <SelectionDetails workspace={workspace} selection={selection} />}
      </div>
    </section>
  );
}
