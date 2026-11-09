import { render, screen, within } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import Dashboard from "@/app/dashboard";
import type { Incident } from "@/lib/api";
import { formatDuration, responseTimer, sortByPriority } from "@/lib/priority";

import { jsonResponse } from "./fixtures";

const NOW = Date.parse("2026-10-24T10:10:00Z");
const ago = (seconds: number) => new Date(NOW - seconds * 1000).toISOString();

function incident(id: string, overrides: Partial<Incident> = {}): Incident {
  return {
    incident_id: id,
    title: `SIMULATED: situation ${id}`,
    disaster_type: "flood",
    severity: "high",
    summary: "",
    location: "Velachery, Chennai (simulated)",
    coordinates: null,
    affected_people: 10,
    needs: [],
    missing_fields: [],
    status: "new",
    source: "simulation",
    location_confidence: "unconfirmed",
    synthetic: true,
    created_at: ago(30),
    updated_at: ago(30),
    ...overrides,
  };
}

describe("priority order", () => {
  test("active before closed, then most severe, then waiting longest", () => {
    const order = sortByPriority([
      incident("low-new", { severity: "low" }),
      incident("critical-closed", { severity: "critical", status: "closed" }),
      incident("high-recent", { created_at: ago(10) }),
      incident("critical-ack", { severity: "critical", status: "acknowledged" }),
      incident("high-old", { created_at: ago(300) }),
      incident("critical-new", { severity: "critical" }),
    ]).map((i) => i.incident_id);

    expect(order).toEqual([
      "critical-new",
      "critical-ack",
      "high-old",
      "high-recent",
      "low-new",
      "critical-closed",
    ]);
  });
});

describe("response timers", () => {
  test("format durations compactly", () => {
    expect([5, 65, 600, 3780].map(formatDuration)).toEqual(["5s", "1m 05s", "10m 00s", "1h 03m"]);
  });

  test("an unacknowledged critical incident is overdue after 60 seconds", () => {
    expect(responseTimer(incident("a", { severity: "critical", created_at: ago(59) }), NOW)).toEqual({
      label: "Waiting 59s",
      overdue: false,
    });
    expect(responseTimer(incident("b", { severity: "critical", created_at: ago(75) }), NOW)).toEqual({
      label: "Overdue 1m 15s",
      overdue: true,
    });
    // High incidents show the timer but do not escalate.
    expect(responseTimer(incident("c", { created_at: ago(600) }), NOW).overdue).toBe(false);
  });

  test("acknowledged incidents show their response time; clock skew never goes negative", () => {
    expect(
      responseTimer(incident("d", { status: "acknowledged", created_at: ago(100), updated_at: ago(58) }), NOW).label,
    ).toBe("Acknowledged in 42s");
    expect(responseTimer(incident("e", { created_at: ago(-5) }), NOW).label).toBe("Waiting 0s");
    expect(responseTimer(incident("f", { status: "closed" }), NOW).label).toBe("Closed");
  });

  test("the queue shows overdue incidents in red and counts them", async () => {
    const created = new Date(Date.now() - 90_000).toISOString();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const path = new URL(url).pathname;
        if (path === "/health") return jsonResponse({ status: "ok", service: "RESQIVO" });
        return jsonResponse({
          incidents: [incident("INC-00000001", { severity: "critical", created_at: created, updated_at: created })],
          version: 1,
          notice: "Simulated.",
        });
      }),
    );
    render(<Dashboard />);
    const queue = await screen.findByRole("region", { name: "Incident queue" });

    const card = await within(queue).findByRole("button", { name: /INC-00000001/ });
    expect(within(card).getByText(/Overdue 1m 3\ds/)).toBeInTheDocument();
    expect(within(queue).getByText("1 overdue")).toBeInTheDocument();
  });
});
