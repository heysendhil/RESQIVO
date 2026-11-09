import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import Dashboard from "@/app/dashboard";
import { sampleWorkspaces, toPlan } from "@/lib/workspace";

import {
  answered,
  correctedReview,
  draftResponse,
  insufficient,
  jsonResponse,
  overStock,
  reviewResponse,
} from "./fixtures";

type Route = Response | (() => Response | Promise<Response>);

/** Stub fetch by endpoint path; /health is online unless overridden. */
function routeFetch(routes: Record<string, Route>) {
  const all: Record<string, Route> = {
    "/health": jsonResponse({ status: "ok", service: "RESQIVO" }),
    ...routes,
  };
  const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async (url) => {
    const path = new URL(url).pathname;
    const route = all[path];
    if (!route) throw new Error(`Unexpected request to ${path}`);
    const response = typeof route === "function" ? await route() : route;
    return response.clone();
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function bodyOf(fetchMock: ReturnType<typeof routeFetch>, path: string) {
  const call = fetchMock.mock.calls.find(([url]) => new URL(url).pathname === path);
  const init = call?.[1] as RequestInit | undefined;
  return init?.body ? JSON.parse(String(init.body)) : undefined;
}

function panel(name: RegExp) {
  return screen.getByRole("region", { name });
}

async function renderDashboard(routes: Record<string, Route> = {}) {
  const fetchMock = routeFetch(routes);
  const user = userEvent.setup();
  render(<Dashboard />);
  await screen.findByText("Online");
  return { fetchMock, user };
}

describe("health status", () => {
  test("shows the API as online", async () => {
    await renderDashboard();

    expect(screen.getByText("http://api.test")).toBeInTheDocument();
  });

  test("shows an unreachable API with a retry button", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    render(<Dashboard />);

    expect(await screen.findByText("Unavailable")).toBeInTheDocument();
    expect(screen.getByText(/Could not reach the RESQIVO API/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});

describe("safety framing", () => {
  test("states the decision-support and no-dispatch boundaries", async () => {
    await renderDashboard();

    expect(screen.getByText(/Decision support only/)).toBeInTheDocument();
    expect(
      screen.getAllByText(/Nothing has been dispatched, booked or requested/).length,
    ).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /dispatch|send|execute/i })).toBeNull();
  });
});

describe("validate panel", () => {
  test("sends the workspace plan unchanged and shows the authoritative result", async () => {
    let release!: () => void;
    const pending = new Promise<void>((resolve) => (release = resolve));
    const { fetchMock, user } = await renderDashboard({
      "/validate": async () => {
        await pending;
        return jsonResponse(overStock);
      },
    });
    const validate = panel(/Validate allocations/);

    await user.click(within(validate).getByRole("button", { name: "Validate plan" }));

    expect(within(validate).getByRole("status")).toHaveTextContent(
      "Running deterministic validation",
    );
    expect(within(validate).getByRole("button", { name: "Validating…" })).toBeDisabled();
    release();

    expect(
      await within(validate).findByText("Deterministic validation (authoritative)"),
    ).toBeInTheDocument();
    expect(within(validate).getByText("Rule violations found")).toBeInTheDocument();
    expect(within(validate).getByText("DOM-04")).toBeInTheDocument();
    expect(bodyOf(fetchMock, "/validate")).toEqual(
      toPlan(sampleWorkspaces[0].workspace),
    );
  });

  test("never rounds or fills in quantities: invalid text goes to the backend", async () => {
    const { fetchMock, user } = await renderDashboard({
      "/validate": jsonResponse(
        {
          detail: [
            {
              loc: ["body", "resources", 0, "quantity_available"],
              msg: "Input should be a valid integer",
            },
          ],
        },
        422,
      ),
    });
    const quantity = screen.getByLabelText("Resources: Quantity available, row 1");
    await user.clear(quantity);
    await user.type(quantity, "12.5");

    await user.click(screen.getByRole("button", { name: "Validate plan" }));

    const alert = await within(panel(/Validate allocations/)).findByRole("alert");
    expect(alert).toHaveTextContent("HTTP 422");
    expect(alert).toHaveTextContent(
      "resources.0.quantity_available: Input should be a valid integer",
    );
    expect(bodyOf(fetchMock, "/validate").resources[0].quantity_available).toBe("12.5");
  });
});

describe("draft panel", () => {
  test("labels the draft for human review and keeps it separate from the workspace", async () => {
    const { user } = await renderDashboard({ "/draft-plan": jsonResponse(draftResponse) });
    const draft = panel(/Draft a response plan/);
    const before = (screen.getByLabelText("Proposed allocations: Quantity, row 1") as HTMLInputElement).value;

    await user.click(within(draft).getByRole("button", { name: "Generate draft plan" }));

    expect(await within(draft).findByText("Draft — requires human review")).toBeInTheDocument();
    expect(within(draft).getByText("Draft passed rule-based validation")).toBeInTheDocument();
    expect(
      within(draft).getByText("Proposed allocations (AI draft — not dispatched)"),
    ).toBeInTheDocument();
    expect(within(draft).getByText(draftResponse.notice)).toBeInTheDocument();
    expect(within(draft).getByText(draftResponse.limitations[0])).toBeInTheDocument();
    expect(within(draft).getByText(draftResponse.request_id)).toBeInTheDocument();
    expect(
      within(draft).getAllByText(/Deterministic validation \(authoritative\)/).length,
    ).toBeGreaterThan(0);
    // The AI's proposed quantity is shown, but never copied into the workspace.
    expect(within(draft).getByText("600")).toBeInTheDocument();
    expect((screen.getByLabelText("Proposed allocations: Quantity, row 1") as HTMLInputElement).value).toBe(
      before,
    );
  });

  test("explains when there is not enough information to draft", async () => {
    const { user } = await renderDashboard({
      "/draft-plan": jsonResponse({
        ...draftResponse,
        status: "insufficient_information",
        reason: "no_shelters",
        guidance: null,
        evidence_available: false,
        plan_review: null,
        limitations: [],
      }),
    });

    await user.click(screen.getByRole("button", { name: "Generate draft plan" }));

    const draft = panel(/Draft a response plan/);
    expect(await within(draft).findByText("Not enough information to draft")).toBeInTheDocument();
    expect(within(draft).getByText(/No shelters were supplied/)).toBeInTheDocument();
    expect(within(draft).getByText("Draft — requires human review")).toBeInTheDocument();
  });

  test("shows that a draft without evidence is based only on workspace data", async () => {
    const { user } = await renderDashboard({
      "/draft-plan": jsonResponse({
        ...draftResponse,
        guidance: insufficient,
        evidence_available: false,
      }),
    });

    await user.click(screen.getByRole("button", { name: "Generate draft plan" }));

    const draft = panel(/Draft a response plan/);
    expect(await within(draft).findByText("No supporting evidence")).toBeInTheDocument();
    expect(within(draft).getByText(/No sufficiently relevant guidance/)).toBeInTheDocument();
  });
});

describe("review panel", () => {
  test("shows the answer, corrections and the final authoritative validation", async () => {
    const { fetchMock, user } = await renderDashboard({
      "/review": jsonResponse(reviewResponse),
    });
    const review = panel(/Review a plan/);

    await user.click(within(review).getByRole("button", { name: "Review plan" }));

    expect(
      await within(review).findByText("Corrections attempted: 1 of at most 2.", { exact: false }),
    ).toBeInTheDocument();
    expect(within(review).getByText("Validation before correction")).toBeInTheDocument();
    expect(
      within(review).getByText("Deterministic validation (authoritative): final result"),
    ).toBeInTheDocument();
    expect(
      within(review).getByText("Allocations after AI correction (proposal — not dispatched)"),
    ).toBeInTheDocument();
    expect(within(review).getByText("AI-generated — not validated guidance")).toBeInTheDocument();
    expect(within(review).getByText("[P1]")).toBeInTheDocument();
    const sent = bodyOf(fetchMock, "/review");
    expect(sent.plan).toEqual(toPlan(sampleWorkspaces[0].workspace));
    expect(correctedReview.final_plan.allocations[0].quantity_allocated).toBe(900);
  });

  test("can send the question without the plan", async () => {
    const { fetchMock, user } = await renderDashboard({
      "/review": jsonResponse({ ...reviewResponse, plan_review: null }),
    });

    await user.click(screen.getByRole("checkbox", { name: /Include the workspace plan/ }));
    await user.click(screen.getByRole("button", { name: "Review plan" }));

    expect(await screen.findByText(/No plan was included/)).toBeInTheDocument();
    expect(bodyOf(fetchMock, "/review").plan).toBeNull();
  });
});

describe("ask panel", () => {
  test("disables asking until a question is entered", async () => {
    await renderDashboard();

    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
  });

  test("shows citations from retrieval metadata, treating them as untrusted", async () => {
    const withLinks = {
      ...answered,
      answer: "Store water safely [P1]. Check stock daily [P2]. Avoid [P3].",
      citations: [
        answered.citations[0],
        {
          ...answered.citations[0],
          label: "P2",
          source_id: "WHO-01",
          title: "Official guidance",
          url: "https://example.org/guidance.pdf",
          synthetic: false,
        },
        {
          ...answered.citations[0],
          label: "P3",
          title: "Suspicious source",
          url: "javascript:alert(1)",
        },
      ],
    };
    const { fetchMock, user } = await renderDashboard({ "/answer": jsonResponse(withLinks) });

    await user.type(screen.getByLabelText("Your question"), "  How is water stored?  ");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    const ask = panel(/Ask the knowledge base/);
    const citations = await within(ask).findByRole("region", { name: "Evidence citations" });
    expect(within(citations).getByText(/untrusted reference material/)).toBeInTheDocument();
    expect(within(citations).getAllByText("Synthetic source")).toHaveLength(2);
    const link = within(citations).getByRole("link", { name: "Official guidance" });
    expect(link).toHaveAttribute("href", "https://example.org/guidance.pdf");
    expect(link).toHaveAttribute("rel", "noopener noreferrer nofollow");
    expect(within(citations).queryByRole("link", { name: "Suspicious source" })).toBeNull();
    expect(within(citations).getByText("urn:resqivo:synthetic:SYN-001")).toBeInTheDocument();
    expect(bodyOf(fetchMock, "/answer")).toEqual({ question: "How is water stored?" });
  });

  test("states insufficient evidence instead of inventing an answer", async () => {
    const { user } = await renderDashboard({ "/answer": jsonResponse(insufficient) });

    await user.type(screen.getByLabelText("Your question"), "Tsunami lead time?");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    const ask = panel(/Ask the knowledge base/);
    expect(await within(ask).findByText("Insufficient evidence")).toBeInTheDocument();
    expect(within(ask).queryByRole("region", { name: "Evidence citations" })).toBeNull();
  });

  test("renders retrieved and answer text as text, never as HTML", async () => {
    const { user } = await renderDashboard({
      "/answer": jsonResponse({
        ...answered,
        answer: "<img src=x onerror=alert(1)> Store water [P1].",
      }),
    });

    await user.type(screen.getByLabelText("Your question"), "q");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    const ask = panel(/Ask the knowledge base/);
    expect(await within(ask).findByText(/<img src=x onerror=alert\(1\)>/)).toBeInTheDocument();
    expect(ask.querySelector("img")).toBeNull();
  });
});

describe("error states", () => {
  test.each([
    [413, { detail: "Request body too large." }, /too large.*HTTP 413/],
    [502, { detail: "The language model did not return a usable answer." }, /HTTP 502/],
    [503, { detail: "Question answering is not configured." }, /not configured on the server/],
    [503, { detail: "Knowledge retrieval is unavailable." }, /Knowledge retrieval is unavailable/],
    [504, { detail: "The request did not complete in time." }, /did not complete in time/],
  ])("HTTP %i is explained in an alert", async (status, body, message) => {
    const { user } = await renderDashboard({ "/draft-plan": jsonResponse(body, status) });

    await user.click(screen.getByRole("button", { name: "Generate draft plan" }));

    const alert = await within(panel(/Draft a response plan/)).findByRole("alert");
    expect(alert).toHaveTextContent(message);
    expect(screen.queryByText("Draft passed rule-based validation")).toBeNull();
  });

  test("a later success replaces an earlier error", async () => {
    let attempt = 0;
    const { user } = await renderDashboard({
      "/validate": () =>
        ++attempt === 1
          ? jsonResponse({ detail: "The request did not complete in time." }, 504)
          : jsonResponse(overStock),
    });
    const validate = panel(/Validate allocations/);

    await user.click(within(validate).getByRole("button", { name: "Validate plan" }));
    await within(validate).findByRole("alert");
    await user.click(within(validate).getByRole("button", { name: "Validate plan" }));

    await waitFor(() => expect(within(validate).queryByRole("alert")).toBeNull());
    expect(within(validate).getByText("DOM-04")).toBeInTheDocument();
  });
});

describe("workspace", () => {
  test("switching samples replaces the workspace data", async () => {
    const { user } = await renderDashboard();

    await user.click(screen.getByRole("button", { name: sampleWorkspaces[1].label }));

    expect(screen.getByRole("button", { name: sampleWorkspaces[1].label })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByLabelText("Proposed allocations: Destination shelter ID, row 3")).toHaveValue(
      "shelter-009",
    );
  });

  test("rows can be added and removed", async () => {
    const { user } = await renderDashboard();
    const before = screen.getAllByLabelText(/^Shelters: Shelter ID, row/).length;

    await user.click(screen.getByRole("button", { name: "Add row to shelters" }));
    expect(screen.getAllByLabelText(/^Shelters: Shelter ID, row/)).toHaveLength(before + 1);

    await user.click(screen.getByRole("button", { name: `Remove row ${before + 1} from Shelters` }));
    expect(screen.getAllByLabelText(/^Shelters: Shelter ID, row/)).toHaveLength(before);
  });
});
