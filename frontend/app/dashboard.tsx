"use client";

import { useEffect, useState } from "react";

import {
  ApiError,
  draftPlan,
  setIncidentStatus,
  type AnswerResponse,
  type DraftPlanResponse,
  type Incident,
  type IncidentList,
  type ReviewResponse,
  type ValidationResult,
} from "@/lib/api";
import { deriveAlerts } from "@/lib/alerts";
import { assessmentStatus, incidentQueue } from "@/lib/incidents";
import { mostUrgent, workspaceForIncident, type PipelineRun } from "@/lib/pipeline";
import { shelterLoad, summarizeWorkspace } from "@/lib/summary";
import { useIncidentAlerts } from "@/lib/use-incident-alerts";
import { useIncidentFeed } from "@/lib/use-incidents";
import { useRequest } from "@/lib/use-request";
import { deriveWorkflow } from "@/lib/workflow";
import {
  sampleWorkspaces,
  type Row,
  type ScenarioFields,
  toDraftRequest,
  type TableName,
  type Workspace,
} from "@/lib/workspace";

import AlertSettings from "./components/alert-settings";
import AlertsPanel from "./components/alerts";
import AppHeader from "./components/app-header";
import CallIntake from "./components/call-intake";
import IncidentDetails, { type DetailTab } from "./components/incident-details";
import IncidentQueue from "./components/incident-queue";
import KnowledgeBase from "./components/knowledge-base";
import LiveIncidentDetails from "./components/live-incident";
import OperationalPicture, { type MapMode, type MapSelection } from "./components/operational-picture";
import ResponsePipeline from "./components/response-pipeline";
import Overview from "./components/overview";
import { AskPanel, DraftPanel, ReviewPanel, ValidatePanel } from "./components/panels";
import { Badge, NOT_DISPATCHED } from "./components/results";
import Sidebar from "./components/sidebar";
import SimulationControls from "./components/simulation-controls";
import WorkflowTracker from "./components/workflow";
import {
  ConstraintsField,
  SampleSelector,
  ScenarioForm,
  TableEditor,
} from "./components/workspace-editor";

const AUTO_PLAN_KEY = "resqivo.autoPlan";

function Section({
  id,
  title,
  subtitle,
  children,
}: {
  id: string;
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="flex scroll-mt-36 flex-col gap-4 lg:scroll-mt-6">
      <div className="flex flex-col gap-1 border-b border-line pb-3">
        <h2 id={`${id}-title`} className="text-base font-semibold uppercase tracking-wider text-ink">
          {title}
        </h2>
        <p className="text-sm text-muted">{subtitle}</p>
      </div>
      {children}
    </section>
  );
}

/** Occupancy computed from the entered values only; "—" when they are invalid. */
function ShelterOccupancy({ row }: { row: Row }) {
  const load = shelterLoad(row);
  if (!load) return <span className="text-xs text-muted">—</span>;
  if (load.overCapacity) return <Badge tone="bad">Over capacity</Badge>;
  if (load.ratio === null) return <span className="text-xs text-muted">No capacity</span>;
  const percent = Math.round(load.ratio * 100);
  return (
    <div className="flex min-w-[7rem] items-center gap-2" title={`${load.occupancy} of ${load.capacity}`}>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-panel-raised">
        <div
          className={`h-full rounded-full ${percent >= 90 ? "bg-amber-400" : "bg-accent"}`}
          style={{ width: `${percent}%` }}
        />
      </div>
      <span className="font-mono text-xs text-ink">{percent}%</span>
    </div>
  );
}

export default function Dashboard() {
  const [sampleId, setSampleId] = useState<string | null>(sampleWorkspaces[0].id);
  const [workspace, setWorkspace] = useState<Workspace>(sampleWorkspaces[0].workspace);
  const validation = useRequest<ValidationResult>();
  const draft = useRequest<DraftPlanResponse>();
  const review = useRequest<ReviewResponse>();
  const ask = useRequest<AnswerResponse>();
  const [selection, setSelection] = useState<MapSelection>(null);
  const [detailTab, setDetailTab] = useState<DetailTab>("status");
  const feed = useIncidentFeed();
  const incidentAlerts = useIncidentAlerts(feed.incidents, feed.loaded);
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null);
  const [mapMode, setMapMode] = useState<MapMode>("fictional");
  const selectedIncident = feed.incidents.find((i) => i.incident_id === selectedIncidentId) ?? null;
  const [pipeline, setPipeline] = useState<PipelineRun | null>(null);
  const [autoPlan, setAutoPlanState] = useState(true);

  // The auto-plan choice is remembered in this browser; read after mounting.
  useEffect(() => {
    const id = setTimeout(() => {
      try {
        if (window.localStorage.getItem(AUTO_PLAN_KEY) === "off") setAutoPlanState(false);
      } catch {
        // Storage unavailable: keep the default.
      }
    }, 0);
    return () => clearTimeout(id);
  }, []);

  function setAutoPlan(on: boolean) {
    setAutoPlanState(on);
    try {
      window.localStorage.setItem(AUTO_PLAN_KEY, on ? "on" : "off");
    } catch {
      // Storage unavailable: the choice lasts for this page only.
    }
  }
  const [approving, setApproving] = useState(false);
  const [approveError, setApproveError] = useState<string | null>(null);

  /** After a simulation, take the most urgent new incident through intake,
   * an AI draft from the workspace's available resources, and deterministic
   * validation, then wait for the operator's decision. */
  function startPipeline(result: IncidentList, idsBefore: ReadonlySet<string>) {
    if (!autoPlan) return;
    const added = result.incidents.filter((i) => !idsBefore.has(i.incident_id));
    const incident = mostUrgent(added);
    if (!incident) return;
    const next = workspaceForIncident(workspace, incident);
    edit(next);
    clearResults();
    setApproveError(null);
    setPipeline({ incident, decision: null });
    setSelectedIncidentId(incident.incident_id);
    if (incident.coordinates) setMapMode("chennai");
    void draft.run((signal) => draftPlan(toDraftRequest(next), signal));
  }

  function retryPipeline() {
    if (!pipeline) return;
    const next = workspaceForIncident(workspace, pipeline.incident);
    edit(next);
    void draft.run((signal) => draftPlan(toDraftRequest(next), signal));
  }

  /** Record the operator's approval: the incident is acknowledged and the
   * approved allocations are copied to the workspace. Nothing is dispatched. */
  async function approvePlan() {
    if (!pipeline || draft.state.status !== "success" || !draft.state.data.plan_review) return;
    const allocations = draft.state.data.plan_review.final_plan.allocations;
    const current =
      feed.incidents.find((i) => i.incident_id === pipeline.incident.incident_id) ??
      pipeline.incident;
    setApproving(true);
    setApproveError(null);
    try {
      if (current.status === "new") {
        await setIncidentStatus(current.incident_id, "acknowledged");
      }
    } catch (error) {
      setApproveError(
        error instanceof ApiError ? error.message : "The decision could not be recorded.",
      );
      setApproving(false);
      return;
    }
    edit({
      ...workspace,
      allocations: allocations.map((a) => ({
        allocation_id: a.allocation_id,
        resource_id: a.resource_id,
        destination_id: a.destination_id,
        quantity_allocated: String(a.quantity_allocated),
      })),
    });
    setPipeline({ ...pipeline, decision: { kind: "approved", at: new Date().toLocaleTimeString() } });
    setApproving(false);
    void feed.refresh();
  }

  function selectIncident(id: string | null) {
    setSelectedIncidentId(id);
    const incident = feed.incidents.find((i) => i.incident_id === id);
    // Live incidents with coordinates are shown on the real map.
    if (incident?.coordinates) setMapMode("chennai");
  }

  function clearResults() {
    validation.reset();
    draft.reset();
    review.reset();
    setSelection(null);
    setDetailTab("status");
  }

  /** Copy a live incident's facts into the scenario workspace for planning.
   * Resources, shelters and allocations stay as they are. */
  function planIncident(incident: Incident) {
    edit({
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
    });
    clearResults();
    setSelectedIncidentId(null);
    setPipeline(null);
  }

  function selectOnMap(next: MapSelection) {
    setSelection(next);
    if (next) setDetailTab("selection");
  }

  function selectSample(id: string) {
    const sample = sampleWorkspaces.find((s) => s.id === id);
    if (sample) {
      setSampleId(id);
      setWorkspace(sample.workspace);
      // Results belong to the previous incident; never show them for this one.
      clearResults();
      setSelectedIncidentId(null);
      setPipeline(null);
    }
  }

  function edit(next: Workspace) {
    setSampleId(null);
    setWorkspace(next);
  }

  const setScenario = (key: keyof ScenarioFields, value: string) =>
    edit({ ...workspace, scenario: { ...workspace.scenario, [key]: value } });
  const setRows = (table: TableName) => (rows: Row[]) => edit({ ...workspace, [table]: rows });

  const sampleLabel = sampleWorkspaces.find((s) => s.id === sampleId)?.label ?? null;
  const summary = summarizeWorkspace(workspace);
  const incidents = incidentQueue(
    sampleId,
    workspace.scenario,
    assessmentStatus(validation.state, draft.state),
  );
  const answers = [
    ask.state.status === "success" ? ask.state.data : null,
    draft.state.status === "success" ? draft.state.data.guidance : null,
    review.state.status === "success" ? review.state.data.answer : null,
  ];

  return (
    <div className="flex min-h-screen flex-col bg-canvas text-ink">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-accent focus:px-3 focus:py-2 focus:text-on-accent"
      >
        Skip to main content
      </a>
      <AppHeader alerts={<AlertSettings alerts={incidentAlerts} />} />
      <p aria-live="assertive" className="sr-only">
        {incidentAlerts.announcement}
      </p>
      <div className="flex flex-1 flex-col lg:flex-row lg:items-start">
        <Sidebar />
        <main
          id="main"
          tabIndex={-1}
          className="flex min-w-0 flex-1 flex-col gap-10 px-4 py-5 focus:outline-none sm:px-6 lg:px-6"
        >
          <Section
            id="command-center"
            title="Dashboard"
            subtitle="Operational overview of the selected incident, computed from the workspace and real API results."
          >
            <p className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs text-warn-ink">
              <strong>Decision support only.</strong> AI output is labelled and always
              checked by the deterministic validator, whose result is authoritative.{" "}
              {NOT_DISPATCHED}
            </p>
            <Overview summary={summary} validation={validation.state} draft={draft.state} />
            <SimulationControls
              onChanged={() => void feed.refresh()}
              currentIds={feed.incidents.map((i) => i.incident_id)}
              onSimulated={startPipeline}
              autoPlan={autoPlan}
              onAutoPlanChange={setAutoPlan}
            />
            {pipeline && (
              <ResponsePipeline
                run={pipeline}
                draft={draft.state}
                approving={approving}
                approveError={approveError}
                onApprove={() => void approvePlan()}
                onReject={() =>
                  setPipeline({
                    ...pipeline,
                    decision: { kind: "rejected", at: new Date().toLocaleTimeString() },
                  })
                }
                onRetry={retryPipeline}
                onDismiss={() => setPipeline(null)}
              />
            )}
            <div className="grid gap-3 md:grid-cols-[16rem_minmax(0,1fr)] xl:h-[max(36rem,calc(100vh-6rem))] xl:grid-cols-[17rem_minmax(0,1fr)_21rem] 2xl:grid-cols-[19rem_minmax(0,1fr)_23rem]">
              <div className="min-h-0 md:max-xl:h-[34rem]">
                <IncidentQueue
                  scenarios={incidents}
                  onSelectScenario={selectSample}
                  live={feed.incidents}
                  liveLoaded={feed.loaded}
                  liveFailed={feed.failed}
                  feedStatus={feed.status}
                  selectedIncidentId={selectedIncident?.incident_id ?? null}
                  onSelectIncident={selectIncident}
                  flashing={incidentAlerts.flashing}
                />
              </div>
              <div className="min-h-0 md:max-xl:h-[34rem]">
                <OperationalPicture
                  workspace={workspace}
                  severity={workspace.scenario.severity}
                  disasterType={workspace.scenario.disaster_type}
                  selection={selection}
                  onSelect={selectOnMap}
                  mode={mapMode}
                  onMode={setMapMode}
                  incidents={feed.incidents}
                  selectedIncidentId={selectedIncident?.incident_id ?? null}
                  onSelectIncident={selectIncident}
                />
              </div>
              <div className="min-h-0 md:col-span-2 xl:col-span-1">
                {selectedIncident ? (
                  <LiveIncidentDetails
                    incident={selectedIncident}
                    onChanged={() => void feed.refresh()}
                    onLoadIntoWorkspace={planIncident}
                    onBack={() => setSelectedIncidentId(null)}
                  />
                ) : (
                <IncidentDetails
                  workspace={workspace}
                  summary={summary}
                  sampleLabel={sampleLabel}
                  validation={validation.state}
                  draft={draft.state}
                  review={review.state}
                  selection={selection}
                  tab={detailTab}
                  onTab={setDetailTab}
                />
                )}
              </div>
            </div>
          </Section>

          <Section
            id="workflow"
            title="AI Workflow"
            subtitle="The stages RESQIVO actually runs for a draft plan, and alerts from the latest results."
          >
            <div className="grid gap-4 2xl:grid-cols-3">
              <div className="2xl:col-span-2">
                <WorkflowTracker
                  stages={deriveWorkflow(draft.state)}
                  error={draft.state.status === "error" ? draft.state.message : undefined}
                />
              </div>
              <AlertsPanel alerts={deriveAlerts(workspace, validation.state, draft.state)} />
            </div>
          </Section>

          <Section
            id="scenario"
            title="Incidents"
            subtitle="Start from a synthetic sample or describe the incident scenario directly."
          >
            <SampleSelector sampleId={sampleId} onSelectSample={selectSample} />
            <ScenarioForm scenario={workspace.scenario} onChange={setScenario} />
          </Section>

          <Section
            id="calls"
            title="Call Intake"
            subtitle="Simulated calls: the AI suggests incident fields, and you review them before an incident is created."
          >
            <CallIntake
              onCreated={(incident) => {
                void feed.refresh();
                setSelectedIncidentId(incident.incident_id);
              }}
            />
          </Section>

          <Section
            id="resources"
            title="Resources"
            subtitle="Available stock exactly as entered. Nothing is invented or rounded."
          >
            <TableEditor table="resources" rows={workspace.resources} onChange={setRows("resources")} />
          </Section>

          <Section
            id="shelters"
            title="Shelters"
            subtitle="Capacity and occupancy as entered. Occupancy is computed from these values."
          >
            <TableEditor
              table="shelters"
              rows={workspace.shelters}
              onChange={setRows("shelters")}
              rowStatus={(row) => <ShelterOccupancy row={row} />}
              statusLabel="Occupancy"
            />
          </Section>

          <Section
            id="knowledge"
            title="Knowledge Base"
            subtitle="Sources cited by grounded answers in this session, and how documents are indexed."
          >
            <KnowledgeBase answers={answers} />
          </Section>

          <Section
            id="ask"
            title="Ask RESQIVO"
            subtitle="Grounded answers from retrieved guidance, with citations."
          >
            <AskPanel request={ask} />
          </Section>

          <Section
            id="response-plan"
            title="Draft Plans"
            subtitle="Needs and constraints guide the AI proposal; the deterministic validator then checks it."
          >
            <TableEditor table="needs" rows={workspace.needs} onChange={setRows("needs")} />
            <ConstraintsField
              value={workspace.constraints}
              onChange={(constraints) => edit({ ...workspace, constraints })}
            />
            <DraftPanel workspace={workspace} request={draft} />
          </Section>

          <Section
            id="validation"
            title="Review"
            subtitle="Deterministic checks of the proposed allocations, and AI-assisted review with bounded corrections. Human review is always required."
          >
            <TableEditor table="allocations" rows={workspace.allocations} onChange={setRows("allocations")} />
            <div className="grid gap-6 xl:grid-cols-2">
              <ValidatePanel workspace={workspace} request={validation} />
              <ReviewPanel workspace={workspace} request={review} />
            </div>
          </Section>

          <footer className="border-t border-line pt-4 text-xs text-muted">
            RESQIVO · Agentic AI disaster-response planning with deterministic resource
            validation. Simulated data; decision support only.
          </footer>
        </main>
      </div>
    </div>
  );
}
