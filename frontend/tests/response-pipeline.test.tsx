import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";

import Dashboard from "@/app/dashboard";
import type { DraftPlanResponse, Incident } from "@/lib/api";
import { canApprove, derivePipeline, mostUrgent, workspaceForIncident } from "@/lib/pipeline";
import type { RequestState } from "@/lib/use-request";
import { sampleWorkspaces } from "@/lib/workspace";

import { draftResponse, jsonResponse, overStock } from "./fixtures";

const NOTICE = "Simulated incidents for planning and education only.";

// The auto-plan setting is remembered; start every test from the default (on).
beforeEach(() => window.localStorage.clear());

function incident(id: string, severity: Incident["severity"], overrides: Partial<Incident> = {}): Incident {
  return {
    incident_id: id,
    title: `SIMULATED: ${severity} situation ${id}`,
    disaster_type: "flood",
    severity,
    summary: "Synthetic training report.",
    location: "Velachery, Chennai (simulated)",
    coordinates: null,
    affected_people: 100,
    needs: ["drinking_water"],
    missing_fields: ["callback number"],
    status: "new",
    source: "simulation",
    location_confidence: "unconfirmed",
    synthetic: true,
    created_at: "2026-10-24T10:00:00+00:00",
    updated_at: "2026-10-24T10:00:00+00:00",
    ...overrides,
  };
}

const OLD_CRITICAL = incident("INC-0000000a", "critical", { affected_people: 999 });
const NEW_INCIDENTS = [
  incident("INC-00000001", "high", { affected_people: 500 }),
  incident("INC-00000002", "critical", { affected_people: 120 }),
  incident("INC-00000003", "critical", { affected_people: 300 }),
  incident("INC-00000004", "low"),
];

type Handler = (init?: RequestInit) => Response | Promise<Response>;

function setup(routes: Record<string, Handler> = {}) {
  let feed: Incident[] = [OLD_CRITICAL];
  const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(
    async (url, init) => {
      const path = new URL(url).pathname;
      const key = `${init?.method ?? "GET"} ${path}`;
      if (routes[key]) return routes[key](init);
      if (path === "/health") return jsonResponse({ status: "ok", service: "RESQIVO" });
      if (key === "GET /incidents") return jsonResponse({ incidents: feed, version: 1, notice: NOTICE });
      if (key === "POST /incidents/simulate") {
        feed = [...NEW_INCIDENTS, ...feed];
        return jsonResponse({ incidents: feed, version: 2, notice: NOTICE }, 201);
      }
      throw new Error(`Unexpected request to ${key}`);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  const calls = (key: string) =>
    fetchMock.mock.calls
      .filter(([url, init]) => `${init?.method ?? "GET"} ${new URL(url).pathname}` === key)
      .map(([, init]) => (init?.body ? JSON.parse(String(init.body)) : undefined));
  return { fetchMock, calls };
}

async function start(routes: Record<string, Handler> = {}) {
  const api = setup(routes);
  const user = userEvent.setup();
  render(<Dashboard />);
  await screen.findByText("Online");
  await within(screen.getByRole("region", { name: "Incident queue" })).findByRole("tab", { name: "Live (1)" });
  await user.click(screen.getByRole("button", { name: "Flood simulation" }));
  return { user, ...api };
}

const pipeline = () => screen.getByRole("region", { name: "Response pipeline" });

function stageStatuses(): Record<string, string | null> {
  return Object.fromEntries(
    [...document.querySelectorAll("li[data-pipeline-stage]")].map((li) => [
      li.getAttribute("data-pipeline-stage"),
      li.getAttribute("data-status"),
    ]),
  );
}

describe("pipeline rules", () => {
  test("the most urgent incident is the highest severity, then the most people", () => {
    expect(mostUrgent(NEW_INCIDENTS)?.incident_id).toBe("INC-00000003");
    expect(mostUrgent([incident("A", "high", { affected_people: null }), incident("B", "high")])?.incident_id).toBe("B");
    expect(mostUrgent([incident("C", "critical", { status: "closed" })])).toBeNull();
    expect(mostUrgent([])).toBeNull();
  });

  test("planning keeps the workspace's resources, shelters and needs", () => {
    const base = sampleWorkspaces[0].workspace;
    const next = workspaceForIncident(base, NEW_INCIDENTS[2]);

    expect(next.scenario).toMatchObject({
      scenario_id: "INC-00000003",
      severity: "critical",
      affected_population: "300",
      location: "Velachery, Chennai (simulated)",
    });
    expect(next.resources).toBe(base.resources);
    expect(next.shelters).toBe(base.shelters);
    expect(next.needs).toBe(base.needs);
    expect(workspaceForIncident(base, incident("X", "high", { affected_people: null })).scenario.affected_population).toBe("");
  });

  test("stages follow the real draft result; only a valid draft can be approved", () => {
    const run = { incident: NEW_INCIDENTS[2], decision: null };
    const statuses = (draft: RequestState<DraftPlanResponse>) =>
      derivePipeline(run, draft).map((s) => s.status);

    expect(statuses({ status: "loading" })).toEqual(["done", "done", "running", "waiting", "waiting"]);
    expect(statuses({ status: "error", message: "x", fieldErrors: [] })).toEqual([
      "done", "done", "failed", "skipped", "skipped",
    ]);
    const valid = { status: "success", data: draftResponse } as const;
    expect(statuses(valid)).toEqual(["done", "done", "done", "done", "waiting"]);
    expect(canApprove(valid)).toBe(true);

    const invalid = {
      status: "success",
      data: {
        ...draftResponse,
        status: "draft_invalid",
        plan_review: { ...draftResponse.plan_review!, final_validation: overStock },
      },
    } as const;
    expect(statuses(invalid)).toEqual(["done", "done", "done", "attention", "attention"]);
    expect(canApprove(invalid)).toBe(false);

    // Missing facts are listed as follow-up items on a completed intake step.
    expect(derivePipeline(run, valid)[1]).toMatchObject({
      status: "done",
      detail: "Recorded · follow up: callback number",
    });

    const decided = { ...run, decision: { kind: "approved" as const, at: "10:00" } };
    expect(derivePipeline(decided, valid).at(-1)).toMatchObject({ status: "done" });
  });
});

describe("automatic response after a simulation", () => {
  test("drafts a plan for the most urgent new incident from the workspace resources", async () => {
    const { calls } = await start({ "POST /draft-plan": () => jsonResponse(draftResponse) });

    await within(pipeline()).findByText("Awaiting your decision");
    const [request] = calls("POST /draft-plan");
    // The new critical incident with the most people, not the older one.
    expect(request.scenario).toMatchObject({ scenario_id: "INC-00000003", severity: "critical" });
    expect(request.resources).toHaveLength(sampleWorkspaces[0].workspace.resources.length);
    expect(stageStatuses()).toEqual({
      incident: "done",
      intake: "done",
      allocation: "done",
      validation: "done",
      review: "waiting",
    });
    expect(within(pipeline()).getByText("Proposed allocations (AI draft — not dispatched)")).toBeInTheDocument();
    expect(within(pipeline()).getByText(/No resources have been dispatched/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /dispatch|send|execute/i })).toBeNull();
  });

  test("approval is recorded only: the incident is acknowledged and the allocations copied", async () => {
    const { user, calls } = await start({
      "POST /draft-plan": () => jsonResponse(draftResponse),
      "PATCH /incidents/INC-00000003": () =>
        jsonResponse(incident("INC-00000003", "critical", { status: "acknowledged" })),
    });
    await within(pipeline()).findByText("Awaiting your decision");
    expect(calls("PATCH /incidents/INC-00000003")).toHaveLength(0);

    await user.click(within(pipeline()).getByRole("button", { name: "Approve plan (record decision)" }));

    expect(await within(pipeline()).findByText(/Plan approved by the operator at/)).toBeInTheDocument();
    expect(calls("PATCH /incidents/INC-00000003")).toEqual([{ status: "acknowledged" }]);
    expect(stageStatuses().review).toBe("done");
    const allocations = draftResponse.plan_review!.final_plan.allocations;
    expect(screen.getByLabelText("Proposed allocations: Allocation ID, row 1")).toHaveValue(
      allocations[0].allocation_id,
    );
  });

  test("rejection is recorded and nothing is changed", async () => {
    const { user, calls } = await start({ "POST /draft-plan": () => jsonResponse(draftResponse) });
    await within(pipeline()).findByText("Awaiting your decision");

    await user.click(within(pipeline()).getByRole("button", { name: "Reject" }));

    expect(within(pipeline()).getByText(/Plan rejected at/)).toBeInTheDocument();
    expect(calls("PATCH /incidents/INC-00000003")).toHaveLength(0);
  });

  test("a failed draft can be retried", async () => {
    let attempt = 0;
    const { user } = await start({
      "POST /draft-plan": () =>
        ++attempt === 1
          ? jsonResponse({ detail: "The language model did not return a usable answer." }, 502)
          : jsonResponse(draftResponse),
    });

    await within(pipeline()).findByText(/did not return a usable result/, { selector: "p" });
    expect(stageStatuses().allocation).toBe("failed");
    await user.click(within(pipeline()).getByRole("button", { name: "Retry the AI draft" }));

    await within(pipeline()).findByText("Awaiting your decision");
  });

  test("with auto-plan switched off, a simulation makes no AI calls", async () => {
    const api = setup({ "POST /draft-plan": () => jsonResponse(draftResponse) });
    const user = userEvent.setup();
    render(<Dashboard />);
    await screen.findByText("Online");
    const toggle = screen.getByRole("checkbox", { name: "Auto-plan with AI" });
    expect(toggle).toBeChecked();

    await user.click(toggle);
    await user.click(screen.getByRole("button", { name: "Flood simulation" }));

    await within(screen.getByRole("region", { name: "Incident queue" })).findByRole("tab", { name: "Live (5)" });
    expect(api.calls("POST /draft-plan")).toHaveLength(0);
    expect(screen.queryByRole("region", { name: "Response pipeline" })).toBeNull();
    expect(window.localStorage.getItem("resqivo.autoPlan")).toBe("off");
  });

  test("a plan that fails the rules cannot be approved", async () => {
    await start({
      "POST /draft-plan": () =>
        jsonResponse({
          ...draftResponse,
          status: "draft_invalid",
          plan_review: { ...draftResponse.plan_review!, final_validation: overStock },
        }),
    });

    await within(pipeline()).findByText("Revise the plan before it can be approved");
    expect(within(pipeline()).getByRole("button", { name: "Approve plan (record decision)" })).toBeDisabled();
  });
});
