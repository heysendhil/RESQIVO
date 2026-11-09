import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import Dashboard from "@/app/dashboard";
import { NAV_ITEMS } from "@/app/components/sidebar";
import type { DraftPlanResponse } from "@/lib/api";
import { summarizeWorkspace } from "@/lib/summary";
import type { RequestState } from "@/lib/use-request";
import { deriveWorkflow, type StageStatus } from "@/lib/workflow";
import { sampleWorkspaces } from "@/lib/workspace";

import { draftResponse, insufficient, jsonResponse, overStock } from "./fixtures";

function stubApi(routes: Record<string, () => Response> = {}) {
  const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(
    async (url) => {
      const path = new URL(url).pathname;
      if (routes[path]) return routes[path]();
      if (path === "/health") return jsonResponse({ status: "ok", service: "RESQIVO" });
      throw new Error(`Unexpected request to ${path}`);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function renderDashboard(routes: Record<string, () => Response> = {}) {
  stubApi(routes);
  const user = userEvent.setup();
  render(<Dashboard />);
  await screen.findByText("Online");
  return user;
}

function card(label: string) {
  const heading = screen.getByText(label, { selector: "p" });
  return heading.closest("div.rounded-xl") as HTMLElement;
}

function stageStatuses(): Record<string, string | null> {
  const items = document.querySelectorAll("li[data-stage]");
  return Object.fromEntries(
    Array.from(items).map((item) => [item.getAttribute("data-stage"), item.getAttribute("data-status")]),
  );
}

describe("navigation and header", () => {
  test("the sidebar lists only implemented sections, each with a real target", async () => {
    await renderDashboard();

    const nav = screen.getByRole("navigation", { name: "Dashboard sections" });
    const links = within(nav).getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual([
      "Dashboard",
      "AI Workflow",
      "Incidents",
      "Call Intake",
      "Resources",
      "Shelters",
      "Knowledge Base",
      "Ask RESQIVO",
      "Draft Plans",
      "Review",
    ]);
    for (const item of NAV_ITEMS) {
      expect(document.getElementById(item.id)).not.toBeNull();
    }
    expect(within(nav).queryByText(/Evaluation|Monitoring/)).toBeNull();
    // Reports has no backend support: it is explained, never offered as a link.
    expect(within(nav).queryByRole("link", { name: /Reports/ })).toBeNull();
    expect(within(nav).getByText(/not available yet/)).toBeInTheDocument();
  });

  test("the header shows the identity, synthetic-data label and real API health", async () => {
    await renderDashboard();

    const header = screen.getByRole("banner");
    expect(within(header).getByText(/RESQIVO/)).toBeInTheDocument();
    expect(within(header).getByText("Every Second. Every Life.")).toBeInTheDocument();
    expect(within(header).getByText(/synthetic data for planning and education only/)).toBeInTheDocument();
    expect(within(header).getByText("Online")).toBeInTheDocument();
  });

  test("health is shown as unavailable when the API cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    render(<Dashboard />);

    expect(await within(screen.getByRole("banner")).findByText("Unavailable")).toBeInTheDocument();
  });

  test("a skip link leads to the main content", async () => {
    await renderDashboard();

    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveAttribute("href", "#main");
    expect(document.getElementById("main")?.tagName).toBe("MAIN");
  });
});

describe("command center overview", () => {
  test("cards are computed from the workspace and say 'Not run' before any request", async () => {
    await renderDashboard();

    expect(screen.getByRole("heading", { name: "Synthetic river flood" })).toBeInTheDocument();
    expect(screen.getByText(`Synthetic sample: ${sampleWorkspaces[0].label}`)).toBeInTheDocument();
    expect(card("Resources")).toHaveTextContent("2");
    expect(card("Shelters")).toHaveTextContent("930 occupied of 1,200 capacity");
    expect(card("Proposed allocations")).toHaveTextContent("3");
    expect(card("Latest validation")).toHaveTextContent("Not run");
    expect(card("Latest draft")).toHaveTextContent("Not run");
  });

  test("invalid entered values show '—' instead of an invented total", async () => {
    const user = await renderDashboard();

    const capacity = screen.getByLabelText("Shelters: Capacity, row 1");
    await user.clear(capacity);
    await user.type(capacity, "lots");

    expect(card("Shelters")).toHaveTextContent("930 occupied of — capacity");
    expect(screen.getByText("Edited workspace (synthetic basis)")).toBeInTheDocument();
  });

  test("over-capacity shelters are flagged from the entered values", async () => {
    const user = await renderDashboard();

    await user.click(screen.getByRole("button", { name: sampleWorkspaces[1].label }));

    expect(card("Shelters")).toHaveTextContent("1 over capacity");
    const inventory = screen.getByRole("region", { name: "Shelters" });
    expect(within(inventory).getByText("Over capacity")).toBeInTheDocument();
  });

  test("the validation card reflects the real validator result", async () => {
    const user = await renderDashboard({ "/validate": () => jsonResponse(overStock) });

    await user.click(screen.getByRole("button", { name: "Validate plan" }));

    await within(card("Latest validation")).findByText("1 violation");
    expect(within(card("Latest validation")).getByText("Invalid")).toBeInTheDocument();
  });
});

describe("agentic workflow", () => {
  test("starts pending, with human review required", async () => {
    await renderDashboard();

    expect(stageStatuses()).toEqual({
      input: "pending",
      retrieval: "pending",
      proposal: "pending",
      validation: "pending",
      review: "required",
    });
  });

  test("completes stages only from a real draft result", async () => {
    const user = await renderDashboard({ "/draft-plan": () => jsonResponse(draftResponse) });

    await user.click(screen.getByRole("button", { name: "Generate draft plan" }));
    await screen.findByText("Proposed allocations (AI draft — not dispatched)");

    expect(stageStatuses()).toEqual({
      input: "complete",
      retrieval: "complete",
      proposal: "complete",
      validation: "complete",
      review: "required",
    });
    expect(screen.getByText("Evidence found: 1 citation")).toBeInTheDocument();
    expect(card("Latest draft")).toHaveTextContent("Passed rules");
    expect(card("Latest draft")).toHaveTextContent("Draft — requires human review");
  });

  test("a failed draft request marks nothing complete", async () => {
    const user = await renderDashboard({
      "/draft-plan": () => jsonResponse({ detail: "The request did not complete in time." }, 504),
    });

    await user.click(screen.getByRole("button", { name: "Generate draft plan" }));
    await screen.findByText(/Last draft request failed/);

    expect(Object.values(stageStatuses())).not.toContain("complete");
    expect(card("Latest draft")).toHaveTextContent("Failed");
  });
});

describe("deriveWorkflow", () => {
  const success = (data: DraftPlanResponse): RequestState<DraftPlanResponse> => ({
    status: "success",
    data,
  });
  const statuses = (state: RequestState<DraftPlanResponse>) =>
    Object.fromEntries(deriveWorkflow(state).map((s) => [s.id, s.status])) as Record<
      string,
      StageStatus
    >;

  test.each([
    [{ status: "idle" } as const],
    [{ status: "loading" } as const],
    [{ status: "error", message: "x", fieldErrors: [] } as const],
    [{ status: "success", data: draftResponse } as const],
  ])("human review is never completed (%j)", (state) => {
    expect(statuses(state as RequestState<DraftPlanResponse>).review).toBe("required");
  });

  test("a 422 marks the input as rejected; other failures leave stages unconfirmed", () => {
    expect(
      statuses({ status: "error", message: "x", fieldErrors: [{ field: "a", message: "b" }] }).input,
    ).toBe("failed");
    expect(statuses({ status: "error", message: "x", fieldErrors: [] })).toEqual({
      input: "pending",
      retrieval: "pending",
      proposal: "pending",
      validation: "pending",
      review: "required",
    });
  });

  test("insufficient information skips the AI stages", () => {
    expect(
      statuses(
        success({
          ...draftResponse,
          status: "insufficient_information",
          reason: "no_shelters",
          guidance: null,
          plan_review: null,
        }),
      ),
    ).toEqual({
      input: "attention",
      retrieval: "skipped",
      proposal: "skipped",
      validation: "skipped",
      review: "required",
    });
  });

  test("missing evidence and failed validation need attention", () => {
    const failed = {
      ...draftResponse,
      status: "draft_invalid" as const,
      guidance: insufficient,
      evidence_available: false,
      plan_review: { ...draftResponse.plan_review!, final_validation: overStock },
    };

    const stages = deriveWorkflow(success(failed));

    expect(stages.find((s) => s.id === "retrieval")).toMatchObject({
      status: "attention",
      detail: "No relevant passages found",
    });
    expect(stages.find((s) => s.id === "validation")).toMatchObject({
      status: "attention",
      detail: "1 rule violation remain",
    });
  });
});

describe("summarizeWorkspace", () => {
  test("counts and totals come only from entered values", () => {
    const summary = summarizeWorkspace(sampleWorkspaces[0].workspace);

    expect(summary).toMatchObject({
      resourceEntries: 2,
      resourceTypes: 2,
      shelters: 2,
      totalCapacity: 1200,
      totalOccupancy: 930,
      sheltersOverCapacity: 0,
      allocations: 3,
      affectedPopulation: 930,
    });
  });

  test("any invalid value makes the dependent total unknown", () => {
    const workspace = sampleWorkspaces[0].workspace;
    const summary = summarizeWorkspace({
      ...workspace,
      scenario: { ...workspace.scenario, affected_population: "about 900" },
      shelters: [{ ...workspace.shelters[0], current_occupancy: "-5" }, workspace.shelters[1]],
    });

    expect(summary.affectedPopulation).toBeNull();
    expect(summary.totalOccupancy).toBeNull();
    expect(summary.sheltersOverCapacity).toBeNull();
    expect(summary.totalCapacity).toBe(1200);
  });
});
