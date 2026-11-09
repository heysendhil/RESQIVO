import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import Dashboard from "@/app/dashboard";
import { SAFETY_DISCLAIMER } from "@/app/components/results";
import type { AnswerResponse, DraftPlanResponse, ValidationResult } from "@/lib/api";
import { deriveAlerts } from "@/lib/alerts";
import { citationPage, citedSources } from "@/lib/evidence";
import { computeMapLayout } from "@/lib/map-layout";
import { assessmentStatus, incidentQueue } from "@/lib/incidents";
import type { RequestState } from "@/lib/use-request";
import { deriveWorkflow } from "@/lib/workflow";
import { sampleWorkspaces } from "@/lib/workspace";

import { answered, draftResponse, jsonResponse, overStock } from "./fixtures";

type Route = (init?: RequestInit) => Response;

const FEED_NOTICE = "Simulated incidents for planning and education only.";
const emptyFeed = () => jsonResponse({ incidents: [], version: 0, notice: FEED_NOTICE });

function stubApi(routes: Record<string, Route> = {}) {
  const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(
    async (url, init) => {
      const path = new URL(url).pathname;
      if (routes[path]) return routes[path](init);
      if (path === "/health") return jsonResponse({ status: "ok", service: "RESQIVO" });
      if (path === "/incidents") return emptyFeed();
      throw new Error(`Unexpected request to ${path}`);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function renderDashboard(routes: Record<string, Route> = {}) {
  const fetchMock = stubApi(routes);
  const user = userEvent.setup();
  render(<Dashboard />);
  await screen.findByText("Online");
  return { user, fetchMock };
}

const region = (name: string | RegExp) => screen.getByRole("region", { name });

async function showScenarios(user: ReturnType<typeof userEvent.setup>) {
  await user.click(within(region("Incident queue")).getByRole("tab", { name: /Scenarios/ }));
  return region("Incident queue");
}
const idle = { status: "idle" } as const;

const PDF_URL = "https://iris.who.int/server/api/core/bitstreams/abc/content";
const pdfAnswer: AnswerResponse = {
  ...answered,
  uses_synthetic_sources: false,
  citations: [
    {
      ...answered.citations[0],
      source_id: "WHO-01",
      title: "Health Emergency and Disaster Risk Management Framework",
      publisher: "World Health Organization",
      url: `${PDF_URL}#page=12`,
      synthetic: false,
    },
  ],
};

describe("header", () => {
  test("shows the dashboard title, the simulation label and a working refresh", async () => {
    const { user, fetchMock } = await renderDashboard();
    const header = screen.getByRole("banner");

    expect(within(header).getByRole("heading", { name: "Emergency Operations Center" })).toBeInTheDocument();
    expect(within(header).getByText("Simulation")).toBeInTheDocument();

    await user.click(within(header).getByRole("button", { name: "Refresh" }));
    await within(header).findByText("Online");
    const healthCalls = fetchMock.mock.calls.filter(([url]) => new URL(url).pathname === "/health");
    expect(healthCalls).toHaveLength(2);
  });
});

describe("theme", () => {
  test("is light by default, and the dark theme is a remembered switch", async () => {
    window.localStorage.clear();
    delete document.documentElement.dataset.theme;
    const { user } = await renderDashboard();
    const toggle = within(screen.getByRole("banner")).getByRole("switch", { name: "Dark theme" });

    expect(toggle).toHaveAttribute("aria-checked", "false");
    expect(document.documentElement.dataset.theme).toBeUndefined();

    await user.click(toggle);
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem("resqivo.theme")).toBe("dark");
    expect(toggle).toHaveAttribute("aria-checked", "true");

    await user.click(toggle);
    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(window.localStorage.getItem("resqivo.theme")).toBe("light");
  });
});

describe("incident queue", () => {
  test("lists the synthetic scenarios and marks the one in the workspace", async () => {
    const { user } = await renderDashboard();
    const queue = await showScenarios(user);

    const items = within(queue).getAllByRole("listitem");
    expect(items).toHaveLength(sampleWorkspaces.length);
    expect(within(queue).getByText(/Synthetic planning scenarios/)).toBeInTheDocument();
    expect(within(items[0]).getByText("In workspace")).toBeInTheDocument();
    expect(within(items[0]).getByText("Not assessed")).toBeInTheDocument();
  });

  test("selecting an incident loads it and clears the previous results", async () => {
    const { user } = await renderDashboard({ "/validate": () => jsonResponse(overStock) });
    await user.click(screen.getByRole("button", { name: "Validate plan" }));
    await showScenarios(user);
    await within(region("Incident queue")).findByText("Rule violations found");

    await user.click(
      within(region("Incident queue")).getByRole("button", { name: new RegExp(sampleWorkspaces[1].label) }),
    );

    const details = region(/Synthetic river flood/);
    expect(within(details).getByText(`Synthetic sample: ${sampleWorkspaces[1].label}`)).toBeInTheDocument();
    expect(within(details).getByText(/Simulated District B/)).toBeInTheDocument();
    expect(within(details).getByText("Not run for this workspace.")).toBeInTheDocument();
  });

  test("an edited workspace appears as its own selected incident", async () => {
    const { user } = await renderDashboard();

    const name = screen.getByLabelText(/Scenario name/);
    await user.clear(name);
    await user.type(name, "Edited flood");

    const queue = await showScenarios(user);
    expect(within(queue).getAllByRole("listitem")).toHaveLength(sampleWorkspaces.length + 1);
    expect(within(queue).getByText("Edited workspace")).toBeInTheDocument();
  });

  test("filters by severity and explains an empty result", async () => {
    const { user } = await renderDashboard();
    const queue = await showScenarios(user);

    await user.selectOptions(within(queue).getByLabelText("Severity"), "critical");
    expect(within(queue).getByText("No incidents match these filters.")).toBeInTheDocument();

    await user.selectOptions(within(queue).getByLabelText("Severity"), "high");
    await user.selectOptions(within(queue).getByLabelText("Type"), "earthquake");
    expect(within(queue).getByText("No incidents match these filters.")).toBeInTheDocument();

    await user.selectOptions(within(queue).getByLabelText("Type"), "flood");
    expect(within(queue).getAllByRole("listitem")).toHaveLength(sampleWorkspaces.length);
  });
});

describe("operational map", () => {
  test("is labelled as a fictional map and shows the entered zones, shelters and supplies", async () => {
    await renderDashboard();
    const map = region("Operational map");

    expect(within(map).getByText(/Fictional city — not a real place/)).toBeInTheDocument();
    expect(within(map).getByText("Simulated Zone A")).toBeInTheDocument();
    expect(within(map).getByText("Simulated Zone B")).toBeInTheDocument();
    expect(within(map).getByText("Central Warehouse")).toBeInTheDocument();
    expect(
      within(map).getByRole("button", {
        name: "Shelter Government School Hall: 620 of 800 places, within capacity",
      }),
    ).toBeInTheDocument();
    expect(within(map).getByText("2 shelters · 2 supply points · 3 routes")).toBeInTheDocument();
  });

  test("selecting a marker shows its details in the Map selection tab", async () => {
    const { user } = await renderDashboard();
    const map = region("Operational map");

    await user.click(within(map).getByRole("button", { name: /Shelter Community Centre/ }));

    expect(within(map).getByRole("button", { name: /Shelter Community Centre/ })).toHaveAttribute("aria-pressed", "true");
    const details = region(/Synthetic river flood/);
    expect(within(details).getByRole("tab", { name: "Map selection" })).toHaveAttribute("aria-selected", "true");
    const panel = within(details).getByRole("tabpanel");
    expect(within(panel).getByText("shelter-002")).toBeInTheDocument();
    expect(within(panel).getByText("alloc-002: 4000 × water-001")).toBeInTheDocument();

    await user.click(within(map).getByRole("button", { name: /Supply point Central Warehouse/ }));
    expect(within(within(details).getByRole("tabpanel")).getByText("12000 litres", { exact: false })).toBeInTheDocument();
  });

  test("layers can be switched off and on", async () => {
    const { user } = await renderDashboard();
    const map = region("Operational map");
    await user.click(within(map).getByRole("button", { name: /Layers/ }));
    const layer = within(map).getByRole("switch", { name: /Shelters/ });

    await user.click(layer);
    expect(layer).toHaveAttribute("aria-checked", "false");
    expect(within(map).queryByRole("button", { name: /^Shelter / })).toBeNull();

    await user.click(layer);
    expect(within(map).getAllByRole("button", { name: /^Shelter / })).toHaveLength(2);
  });

  test("flags allocations to shelters that are not in the workspace", async () => {
    const { user } = await renderDashboard();

    await user.click(screen.getByRole("button", { name: sampleWorkspaces[1].label }));

    expect(within(region("Operational map")).getByText("shelter-009")).toBeInTheDocument();
  });

  test("computeMapLayout places entities by location name only", () => {
    const layout = computeMapLayout(sampleWorkspaces[1].workspace);

    expect(layout.zones.map((z) => z.name)).toEqual(["Simulated Zone A", "Simulated Zone B"]);
    expect(layout.supplies.map((s) => [s.name, s.resources])).toEqual([
      ["Central Warehouse", [0]],
      ["District Hospital Store", [1]],
    ]);
    expect(layout.routes.map((r) => r.allocationIndex)).toEqual([0, 1]);
    expect(layout.unmatchedDestinations).toEqual(["shelter-009"]);
    expect(computeMapLayout(sampleWorkspaces[1].workspace)).toEqual(layout);
  });
});

describe("alerts", () => {
  test("come only from workspace values and validator results", async () => {
    const { user } = await renderDashboard({ "/validate": () => jsonResponse(overStock) });
    const alerts = region("Alerts");
    expect(within(alerts).getByText("No alerts for the current workspace or latest results.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Validate plan" }));

    expect(await within(alerts).findByText("DOM-04 on water-001")).toBeInTheDocument();
    expect(within(alerts).getByText(/Deterministic validator/)).toBeInTheDocument();
  });

  test("deriveAlerts flags over-capacity and near-capacity shelters", () => {
    const workspace = {
      ...sampleWorkspaces[0].workspace,
      shelters: [
        { shelter_id: "s1", name: "Hall", location: "Z", capacity: "100", current_occupancy: "120" },
        { shelter_id: "s2", name: "School", location: "Z", capacity: "100", current_occupancy: "95" },
        { shelter_id: "s3", name: "Gym", location: "Z", capacity: "100", current_occupancy: "10" },
        { shelter_id: "s4", name: "Bad", location: "Z", capacity: "lots", current_occupancy: "10" },
      ],
    };

    const alerts = deriveAlerts(workspace, idle, idle);

    expect(alerts.map((a) => [a.severity, a.title])).toEqual([
      ["critical", "Hall: over capacity"],
      ["warning", "School: near capacity"],
    ]);
  });

  test("a failed draft is a warning, never a success", () => {
    const draft: RequestState<DraftPlanResponse> = {
      status: "error",
      message: "The request did not complete in time (HTTP 504).",
      fieldErrors: [],
    };

    const alerts = deriveAlerts(sampleWorkspaces[0].workspace, idle, draft);

    expect(alerts).toContainEqual(
      expect.objectContaining({ severity: "warning", title: "Draft request failed" }),
    );
  });
});

describe("incident status", () => {
  const valid: RequestState<ValidationResult> = { status: "success", data: { valid: true, violations: [] } };

  test("is derived from real results and never claims completion of human review", () => {
    expect(assessmentStatus(idle, idle).label).toBe("Not assessed");
    expect(assessmentStatus(valid, idle).label).toBe("Passed configured rules");
    expect(assessmentStatus(idle, { status: "success", data: draftResponse }).label).toBe(
      "Draft ready · awaiting human review",
    );
    expect(assessmentStatus(idle, { status: "loading" }).label).toBe("Assessment in progress");
  });

  test("only the active incident carries the status", () => {
    const queue = incidentQueue(sampleWorkspaces[0].id, sampleWorkspaces[0].workspace.scenario, {
      label: "Passed configured rules",
      tone: "ok",
    });

    expect(queue.map((i) => i.status.label)).toEqual(["Passed configured rules", "Not assessed"]);
  });
});

describe("workflow states", () => {
  test("a 'not configured' 503 marks the AI stages as not configured", async () => {
    const { user } = await renderDashboard({
      "/draft-plan": () => jsonResponse({ detail: "Question answering is not configured." }, 503),
    });

    await user.click(screen.getByRole("button", { name: "Generate draft plan" }));
    await screen.findByText(/Last draft request failed/);

    const stage = (id: string) => document.querySelector(`li[data-stage="${id}"]`);
    expect(stage("retrieval")).toHaveAttribute("data-status", "not_configured");
    expect(stage("proposal")).toHaveAttribute("data-status", "not_configured");
    expect(stage("review")).toHaveAttribute("data-status", "required");
    expect(within(stage("review") as HTMLElement).getByText("Waiting for review")).toBeInTheDocument();
  });

  test("other errors are not reported as 'not configured'", () => {
    const stages = deriveWorkflow({
      status: "error",
      message: "The service is temporarily unavailable (HTTP 503).",
      fieldErrors: [],
      httpStatus: 503,
      notConfigured: false,
    });

    expect(stages.map((s) => s.status)).not.toContain("not_configured");
  });
});

describe("draft plans", () => {
  test("the full safety disclaimer is visible before any draft is requested", async () => {
    await renderDashboard();

    const draft = region("Draft a response plan");
    expect(within(draft).getByRole("note")).toHaveTextContent(SAFETY_DISCLAIMER);
    expect(SAFETY_DISCLAIMER).toMatch(/No resources have been dispatched, booked or requested/);
    expect(SAFETY_DISCLAIMER).toMatch(/does not mean the plan is operationally safe/);
  });

  test("the backend's copy of the same disclaimer is not repeated", async () => {
    const backendNotice = SAFETY_DISCLAIMER.replace(/[‘’]/g, '"').replace('"s', "'s");
    const { user } = await renderDashboard({
      "/draft-plan": () => jsonResponse({ ...draftResponse, notice: backendNotice }),
    });

    await user.click(screen.getByRole("button", { name: "Generate draft plan" }));
    await screen.findByText("Proposed allocations (AI draft — not dispatched)");

    expect(within(region("Draft a response plan")).getAllByText(/No resources have been dispatched/)).toHaveLength(1);
  });
});

describe("knowledge base", () => {
  test("shows an honest empty state before any evidence is returned", async () => {
    await renderDashboard();
    const kb = region("Knowledge Base");

    expect(within(kb).getByText("Index contents not reported by the API")).toBeInTheDocument();
    expect(within(kb).getByText(/No evidence has been returned yet/)).toBeInTheDocument();
    expect(within(kb).getByText(/build --corpus approved/)).toBeInTheDocument();
  });

  test("an empty knowledge base reported by the API is explained", async () => {
    const { user } = await renderDashboard({
      "/answer": () =>
        jsonResponse({
          ...answered,
          status: "insufficient_evidence",
          reason: "knowledge_base_empty",
          answer: null,
          citations: [],
        }),
    });

    await user.type(screen.getByLabelText("Your question"), "Water?");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(await within(region("Knowledge Base")).findByText(/reported that the knowledge base is empty/)).toBeInTheDocument();
    expect(screen.getByText("The knowledge base is empty, so no guidance is available.")).toBeInTheDocument();
  });

  test("cited sources show the PDF page supplied by the backend", async () => {
    const { user } = await renderDashboard({ "/answer": () => jsonResponse(pdfAnswer) });

    await user.type(screen.getByLabelText("Your question"), "Water?");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    const kb = region("Knowledge Base");
    const row = (await within(kb).findByText("WHO-01")).closest("tr") as HTMLElement;
    expect(within(row).getByText("12")).toBeInTheDocument();
    expect(within(region("Ask the knowledge base")).getByText("12")).toBeInTheDocument();
  });

  test("citationPage reads only the backend's #page fragment", () => {
    expect(citationPage({ url: `${PDF_URL}#page=7` })).toBe(7);
    expect(citationPage({ url: PDF_URL })).toBeNull();
    expect(citationPage({ url: "urn:resqivo:synthetic:SYN-001" })).toBeNull();
    expect(citationPage({ url: `${PDF_URL}#page=7&zoom=2` })).toBeNull();
  });

  test("citedSources groups citations by source and ignores unanswered responses", () => {
    const second = { ...pdfAnswer.citations[0], label: "P2", url: `${PDF_URL}#page=3` };
    const sources = citedSources([
      { ...pdfAnswer, citations: [pdfAnswer.citations[0], second] },
      null,
      { ...pdfAnswer, status: "insufficient_evidence", reason: "no_relevant_passages" },
    ]);

    expect(sources).toEqual([
      expect.objectContaining({ sourceId: "WHO-01", pages: [3, 12], citations: 2 }),
    ]);
  });
});
