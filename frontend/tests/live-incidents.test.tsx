import { act, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import Dashboard from "@/app/dashboard";
import { checkForm } from "@/app/components/call-intake";
import type { Incident, IntakeResponse } from "@/lib/api";
import { useIncidentFeed } from "@/lib/use-incidents";

import { jsonResponse } from "./fixtures";

// A stand-in for Leaflet: records markers instead of drawing tiles.
const leafletLog = vi.hoisted(() => ({
  markers: [] as {
    position: [number, number];
    tooltip: HTMLElement | null;
    click?: () => void;
    className?: string;
  }[],
  tiles: [] as string[],
  shown: new Set<string>(),
  views: [] as unknown[],
}));

vi.mock("leaflet", () => {
  const map = () => ({
    remove: () => {},
    invalidateSize: () => {},
    fitBounds: (bounds: unknown) => leafletLog.views.push(["fit", bounds]),
    setView: (center: unknown, zoom: number) => leafletLog.views.push(["view", center, zoom]),
  });
  const layerGroup = () => ({
    addTo() {
      return this;
    },
    remove() {
      return this;
    },
    clearLayers: () => {
      leafletLog.markers.length = 0;
    },
  });
  const circleMarker = (position: [number, number], options?: { className?: string }) => {
    const entry: (typeof leafletLog.markers)[number] = {
      position,
      tooltip: null,
      className: options?.className,
    };
    const marker = {
      bindTooltip: (content: HTMLElement) => {
        entry.tooltip = content;
        return marker;
      },
      on: (_event: string, handler: () => void) => {
        entry.click = handler;
        return marker;
      },
      addTo: () => {
        leafletLog.markers.push(entry);
        return marker;
      },
      bringToFront: () => marker,
    };
    return marker;
  };
  const api = {
    map,
    layerGroup,
    circleMarker,
    tileLayer: (url: string) => {
      leafletLog.tiles.push(url);
      const tiles = {
        addTo: () => {
          leafletLog.shown.add(url);
          return tiles;
        },
        remove: () => {
          leafletLog.shown.delete(url);
          return tiles;
        },
      };
      return tiles;
    },
    latLngBounds: (points: unknown) => points,
  };
  return { ...api, default: api };
});

const NOTICE = "Simulated incidents for planning and education only.";

function incident(overrides: Partial<Incident> = {}): Incident {
  return {
    incident_id: "INC-0a1b2c3d",
    title: "SIMULATED: Waterlogged street, residents stranded",
    disaster_type: "flood",
    severity: "high",
    summary: "Synthetic training report.",
    location: "Velachery, Chennai (simulated)",
    coordinates: { lat: 12.9815, lon: 80.218 },
    affected_people: 120,
    needs: ["rescue_personnel", "food"],
    missing_fields: ["callback number"],
    status: "new",
    source: "simulation",
    location_confidence: "simulated",
    synthetic: true,
    created_at: "2026-10-23T09:30:00+00:00",
    updated_at: "2026-10-23T09:30:00+00:00",
    ...overrides,
  };
}

const FEED = [
  incident(),
  incident({
    incident_id: "INC-11112222",
    title: "Caller reports roof damage <img src=x onerror=alert(1)>",
    severity: "critical",
    source: "call",
    status: "acknowledged",
    coordinates: null,
    location_confidence: "unconfirmed",
    location: "Near the seafront",
    missing_fields: [],
  }),
];

type Handler = (init?: RequestInit) => Response | Promise<Response>;

function stubApi(routes: Record<string, Handler> = {}) {
  const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(
    async (url, init) => {
      const path = new URL(url).pathname;
      const key = `${init?.method ?? "GET"} ${path}`;
      if (routes[key]) return routes[key](init);
      if (path === "/health") return jsonResponse({ status: "ok", service: "RESQIVO" });
      if (key === "GET /incidents") {
        return jsonResponse({ incidents: FEED, version: 1, notice: NOTICE });
      }
      throw new Error(`Unexpected request to ${key}`);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function calls(fetchMock: ReturnType<typeof stubApi>, key: string) {
  return fetchMock.mock.calls
    .filter(([url, init]) => `${init?.method ?? "GET"} ${new URL(url).pathname}` === key)
    .map(([, init]) => (init?.body ? JSON.parse(String(init.body)) : undefined));
}

async function renderDashboard(routes: Record<string, Handler> = {}) {
  const fetchMock = stubApi(routes);
  const user = userEvent.setup();
  render(<Dashboard />);
  await screen.findByText("Online");
  return { user, fetchMock };
}

const region = (name: string | RegExp) => screen.getByRole("region", { name });

afterEach(() => {
  leafletLog.markers.length = 0;
  leafletLog.tiles.length = 0;
  leafletLog.shown.clear();
  leafletLog.views.length = 0;
});

describe("live incident queue", () => {
  test("shows the simulated feed with status, source and missing fields", async () => {
    await renderDashboard();
    const queue = region("Incident queue");

    const list = await within(queue).findByRole("list", { name: "Live incidents" });
    const cards = within(list).getAllByRole("button");
    expect(cards).toHaveLength(2);
    // Sorted by priority: the critical incident before the high one.
    expect(within(cards[0]).getByText("Simulated call")).toBeInTheDocument();
    expect(within(cards[1]).getByText("INC-0a1b2c3d")).toBeInTheDocument();
    expect(within(cards[1]).getByText("1 missing")).toBeInTheDocument();
    expect(within(queue).getByRole("tab", { name: "Live (2)" })).toHaveAttribute("aria-selected", "true");
    // jsdom has no EventSource, so the feed falls back to polling.
    expect(within(queue).getByText("Polling")).toBeInTheDocument();
  });

  test("a feed failure is explained without hiding the scenarios", async () => {
    const { user } = await renderDashboard({
      "GET /incidents": () => jsonResponse({ detail: "boom" }, 500),
    });
    const queue = region("Incident queue");

    expect(await within(queue).findByText(/Live incident feed unavailable/)).toBeInTheDocument();
    await user.click(within(queue).getByRole("tab", { name: /Scenarios/ }));
    expect(within(queue).getAllByRole("listitem")).toHaveLength(2);
  });

  test("filters live incidents by status", async () => {
    const { user } = await renderDashboard();
    const queue = region("Incident queue");
    await within(queue).findByRole("list", { name: "Live incidents" });

    await user.selectOptions(within(queue).getByLabelText("Status"), "acknowledged");

    expect(within(queue).getAllByRole("listitem")).toHaveLength(1);
    expect(within(queue).getByText(/Caller reports roof damage/)).toBeInTheDocument();
  });
});

describe("selected live incident", () => {
  test("shows its details and switches the map to Chennai", async () => {
    const { user } = await renderDashboard();
    const queue = region("Incident queue");

    await user.click(await within(queue).findByRole("button", { name: /INC-0a1b2c3d/ }));

    const details = region("SIMULATED: Waterlogged street, residents stranded");
    expect(within(details).getByText("Simulated incident — not a real emergency")).toBeInTheDocument();
    expect(within(details).getByText(/Simulated coordinates/)).toBeInTheDocument();
    expect(within(details).getByText("callback number")).toBeInTheDocument();
    expect(within(details).getByText("rescue personnel, food")).toBeInTheDocument();

    const map = region("Operational map");
    expect(within(map).getByRole("button", { name: "Chennai map" })).toHaveAttribute("aria-pressed", "true");
    expect(within(map).getByText(/1 of 2 incidents mapped · 1 without coordinates/)).toBeInTheDocument();
    await waitFor(() => expect(leafletLog.markers).toHaveLength(1));
    expect(leafletLog.markers[0].position).toEqual([12.9815, 80.218]);
    expect(leafletLog.tiles[0]).toBe("https://tile.openstreetmap.org/{z}/{x}/{y}.png");
  });

  test("map tooltips render incident text as text, never HTML", async () => {
    const { user } = await renderDashboard({
      "GET /incidents": () =>
        jsonResponse({
          incidents: [incident({ title: "<img src=x onerror=alert(1)>" })],
          version: 1,
          notice: NOTICE,
        }),
    });

    await user.click(within(region("Operational map")).getByRole("button", { name: "Chennai map" }));

    await waitFor(() => expect(leafletLog.markers).toHaveLength(1));
    const tooltip = leafletLog.markers[0].tooltip!;
    expect(tooltip.querySelector("img")).toBeNull();
    expect(tooltip.textContent).toContain("<img src=x onerror=alert(1)>");
  });

  test("clicking a map marker selects the incident", async () => {
    const { user } = await renderDashboard();
    await user.click(within(region("Operational map")).getByRole("button", { name: "Chennai map" }));
    await waitFor(() => expect(leafletLog.markers).toHaveLength(1));

    act(() => leafletLog.markers[0].click!());

    expect(await screen.findByRole("region", { name: /Waterlogged street/ })).toBeInTheDocument();
  });

  test("status changes are sent only when the operator acts", async () => {
    const { user, fetchMock } = await renderDashboard({
      "PATCH /incidents/INC-0a1b2c3d": () => jsonResponse(incident({ status: "acknowledged" })),
    });
    await user.click(await within(region("Incident queue")).findByRole("button", { name: /INC-0a1b2c3d/ }));
    expect(calls(fetchMock, "PATCH /incidents/INC-0a1b2c3d")).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "Acknowledge" }));

    await waitFor(() =>
      expect(calls(fetchMock, "PATCH /incidents/INC-0a1b2c3d")).toEqual([{ status: "acknowledged" }]),
    );
    expect(screen.queryByRole("button", { name: /dispatch|send|execute/i })).toBeNull();
  });

  test("planning copies the incident facts into the workspace scenario", async () => {
    const { user } = await renderDashboard();
    await user.click(await within(region("Incident queue")).findByRole("button", { name: /INC-0a1b2c3d/ }));

    await user.click(screen.getByRole("button", { name: "Plan response in workspace" }));

    expect(screen.getByLabelText("Scenario ID")).toHaveValue("INC-0a1b2c3d");
    expect(screen.getByLabelText("Scenario name")).toHaveValue(
      "SIMULATED: Waterlogged street, residents stranded",
    );
    expect(screen.getByLabelText("Affected population")).toHaveValue("120");
    expect(region(/SIMULATED: Waterlogged street/)).toHaveTextContent("Edited workspace (synthetic basis)");
  });
});

describe("satellite basemap and world view", () => {
  test("switches between dark streets and worldwide satellite imagery", async () => {
    const { user } = await renderDashboard();
    const map = region("Operational map");
    await user.click(within(map).getByRole("button", { name: "Chennai map" }));
    await waitFor(() => expect(leafletLog.shown.size).toBe(1));
    expect([...leafletLog.shown]).toEqual(["https://tile.openstreetmap.org/{z}/{x}/{y}.png"]);

    await user.click(within(map).getByRole("button", { name: "Satellite" }));

    await waitFor(() => expect(leafletLog.shown.size).toBe(2));
    expect([...leafletLog.shown].every((url) => url.startsWith("https://server.arcgisonline.com/"))).toBe(true);
    expect(within(map).getByRole("button", { name: "Satellite" })).toHaveAttribute("aria-pressed", "true");
    expect(within(map).getByText(/simulated incidents on a real satellite map/)).toBeInTheDocument();
    // Incident markers stay on top of the imagery.
    expect(leafletLog.markers).toHaveLength(1);

    await user.click(within(map).getByRole("button", { name: "Streets" }));
    await waitFor(() => expect([...leafletLog.shown]).toEqual(["https://tile.openstreetmap.org/{z}/{x}/{y}.png"]));
  });

  test("world view zooms out and 'zoom to incidents' returns", async () => {
    const { user } = await renderDashboard();
    const map = region("Operational map");
    await user.click(within(map).getByRole("button", { name: "Chennai map" }));
    await waitFor(() => expect(leafletLog.shown.size).toBe(1));
    leafletLog.views.length = 0;

    await user.click(within(map).getByRole("button", { name: "World view" }));
    await waitFor(() => expect(leafletLog.views).toEqual([["view", [20, 0], 2]]));

    await user.click(within(map).getByRole("button", { name: "Zoom to incidents" }));
    await waitFor(() => expect(leafletLog.views.at(-1)).toEqual(["fit", [[12.9815, 80.218]]]));
  });
});

describe("blinking markers", () => {
  test("unacknowledged high and critical incidents blink; acknowledged ones do not", async () => {
    const { user } = await renderDashboard({
      "GET /incidents": () =>
        jsonResponse({
          incidents: [
            incident({ incident_id: "INC-00000001", severity: "critical" }),
            incident({ incident_id: "INC-00000002", severity: "high", coordinates: { lat: 13.0, lon: 80.25 } }),
            incident({
              incident_id: "INC-00000003",
              severity: "critical",
              status: "acknowledged",
              coordinates: { lat: 13.05, lon: 80.27 },
            }),
          ],
          version: 1,
          notice: NOTICE,
        }),
    });

    await user.click(within(region("Operational map")).getByRole("button", { name: "Chennai map" }));

    await waitFor(() => expect(leafletLog.markers).toHaveLength(3));
    expect(leafletLog.markers.map((m) => m.className)).toEqual([
      "resqivo-blink-critical",
      "resqivo-blink-high",
      undefined,
    ]);

    // The queue shows which incidents keep the alarm sounding.
    const queue = region("Incident queue");
    expect(within(within(queue).getByRole("button", { name: /INC-00000001/ })).getByText("Alarm")).toBeInTheDocument();
    expect(within(within(queue).getByRole("button", { name: /INC-00000003/ })).queryByText("Alarm")).toBeNull();
    // High incidents blink amber but do not keep the alarm sounding.
    expect(within(within(queue).getByRole("button", { name: /INC-00000002/ })).queryByText("Alarm")).toBeNull();

    // Selecting an incident stops it blinking, so it stands out from the alarms.
    await user.click(within(queue).getByRole("button", { name: /INC-00000001/ }));
    await waitFor(() => expect(leafletLog.markers[0].className).toBeUndefined());
    expect(leafletLog.markers[1].className).toBe("resqivo-blink-high");
  });

  test("a moderate incident never blinks or appears in the alarm", async () => {
    const { user } = await renderDashboard({
      "GET /incidents": () =>
        jsonResponse({
          incidents: [incident({ incident_id: "INC-0000000a", severity: "moderate" })],
          version: 1,
          notice: NOTICE,
        }),
    });
    await user.click(within(region("Operational map")).getByRole("button", { name: "Chennai map" }));

    await waitFor(() => expect(leafletLog.markers).toHaveLength(1));
    expect(leafletLog.markers[0].className).toBeUndefined();
    expect(within(screen.getByRole("banner")).queryByRole("button", { name: /Alarm/ })).toBeNull();
    expect(within(region("Incident queue")).queryByText("Alarm")).toBeNull();
  });
});

describe("simulation controls", () => {
  test("start a simulation with the documented request", async () => {
    const { user, fetchMock } = await renderDashboard({
      "POST /incidents/simulate": () => jsonResponse({ incidents: FEED, version: 2, notice: NOTICE }, 201),
    });
    const controls = screen.getByRole("group", { name: "Simulation controls" });

    await user.click(within(controls).getByLabelText("Replace existing incidents"));
    await user.click(within(controls).getByRole("button", { name: "Cyclone simulation" }));

    expect(await within(controls).findByText(/Cyclone simulation added incidents \(2 in the feed\)/)).toBeInTheDocument();
    expect(calls(fetchMock, "POST /incidents/simulate")).toEqual([
      { scenario: "cyclone", count: 8, reset_existing: true },
    ]);
  });

  test("clearing needs confirmation", async () => {
    const { user, fetchMock } = await renderDashboard({
      "DELETE /incidents": () => jsonResponse({ deleted: 2 }),
    });
    const controls = screen.getByRole("group", { name: "Simulation controls" });

    await user.click(within(controls).getByRole("button", { name: "Clear all incidents" }));
    expect(calls(fetchMock, "DELETE /incidents")).toHaveLength(0);
    await user.click(within(controls).getByRole("button", { name: "Confirm: delete all incidents" }));

    expect(await within(controls).findByText("Cleared 2 incidents.")).toBeInTheDocument();
    expect(calls(fetchMock, "DELETE /incidents")).toHaveLength(1);
  });
});

describe("call intake", () => {
  const intake: IntakeResponse = {
    draft: {
      title: "Homes flooding",
      disaster_type: "flood",
      severity: null,
      location: "3rd Main Road, Velachery",
      affected_people: null,
      needs: ["drinking_water"],
      summary: "Water entering homes.",
    },
    missing_fields: ["severity", "number of people affected"],
    notice: "AI-extracted from a simulated call transcript. Verify and correct every field.",
  };

  test("AI suggestions are reviewed before the incident is created", async () => {
    const { user, fetchMock } = await renderDashboard({
      "POST /incidents/intake": () => jsonResponse(intake),
      "POST /incidents": () =>
        jsonResponse(incident({ incident_id: "INC-99998888", source: "call" }), 201),
    });
    const calls_ = region("Call Intake");

    await user.type(within(calls_).getByLabelText("Call transcript"), "Water entering homes in Velachery.");
    await user.click(within(calls_).getByRole("button", { name: "Analyse call with AI" }));

    const review = await screen.findByRole("region", { name: "Review incident" });
    expect(within(review).getByText("AI-generated — not validated guidance")).toBeInTheDocument();
    expect(within(review).getByText(intake.notice)).toBeInTheDocument();
    expect(within(review).getByText("number of people affected")).toBeInTheDocument();
    expect(within(review).getByLabelText("Location")).toHaveValue("3rd Main Road, Velachery");
    expect(within(review).getByLabelText("Latitude")).toHaveValue("");
    expect(within(review).getByRole("button", { name: "Create incident" })).toBeDisabled();
    expect(within(review).getByText("Choose a severity.")).toBeInTheDocument();
    expect(calls(fetchMock, "POST /incidents")).toHaveLength(0);

    await user.selectOptions(within(review).getByLabelText("Severity"), "high");
    await user.click(within(review).getByRole("button", { name: "Create incident" }));

    expect(await within(calls_).findByText(/Incident INC-99998888 created/)).toBeInTheDocument();
    expect(calls(fetchMock, "POST /incidents")).toEqual([
      {
        title: "Homes flooding",
        disaster_type: "flood",
        severity: "high",
        summary: "Water entering homes.",
        location: "3rd Main Road, Velachery",
        coordinates: null,
        affected_people: null,
        needs: ["drinking_water"],
        missing_fields: ["number of people affected"],
        source: "call",
      },
    ]);
  });

  test("manual entry creates an incident without calling the AI", async () => {
    const { user, fetchMock } = await renderDashboard({
      "POST /incidents": () => jsonResponse(incident({ source: "manual" }), 201),
    });
    const calls_ = region("Call Intake");

    await user.click(within(calls_).getByRole("button", { name: "Enter manually (no AI)" }));
    const review = region("Review incident");
    expect(within(review).getByText("Manual entry")).toBeInTheDocument();
    await user.type(within(review).getByLabelText("Title"), "Tree on road");
    await user.selectOptions(within(review).getByLabelText("Disaster type"), "cyclone");
    await user.selectOptions(within(review).getByLabelText("Severity"), "moderate");
    await user.type(within(review).getByLabelText("Location"), "Besant Nagar");
    await user.type(within(review).getByLabelText("People affected"), "12");
    await user.type(within(review).getByLabelText("Latitude"), "12.999");
    await user.type(within(review).getByLabelText("Longitude"), "80.2668");
    await user.click(within(review).getByRole("button", { name: "Create incident" }));

    await waitFor(() => expect(calls(fetchMock, "POST /incidents")).toHaveLength(1));
    expect(calls(fetchMock, "POST /incidents/intake")).toHaveLength(0);
    expect(calls(fetchMock, "POST /incidents")[0]).toMatchObject({
      source: "manual",
      affected_people: 12,
      coordinates: { lat: 12.999, lon: 80.2668 },
      missing_fields: [],
    });
  });

  test("a model failure is shown and nothing is created", async () => {
    const { user, fetchMock } = await renderDashboard({
      "POST /incidents/intake": () =>
        jsonResponse({ detail: "The language model did not return a usable answer." }, 502),
    });
    const calls_ = region("Call Intake");

    await user.type(within(calls_).getByLabelText("Call transcript"), "Help");
    await user.click(within(calls_).getByRole("button", { name: "Analyse call with AI" }));

    expect(await within(calls_).findByText(/did not return a usable result \(HTTP 502\)/)).toBeInTheDocument();
    expect(calls(fetchMock, "POST /incidents")).toHaveLength(0);
  });

  test("checkForm requires the core facts and valid optional numbers", () => {
    const base = {
      title: "T",
      disaster_type: "flood",
      severity: "low",
      location: "L",
      affected_people: "",
      needs: [],
      summary: "",
      lat: "",
      lon: "",
    };
    expect(checkForm(base)).toEqual({ problems: [], missing: ["number of people affected"] });
    expect(checkForm({ ...base, affected_people: "12.5" }).problems).toEqual([
      "People affected must be a whole number, or left empty.",
    ]);
    expect(checkForm({ ...base, lat: "13" }).problems).toEqual([
      "Enter both latitude and longitude as numbers, or neither.",
    ]);
    expect(checkForm({ ...base, lat: "95", lon: "80" }).problems).toEqual([
      "Latitude must be within ±90 and longitude within ±180.",
    ]);
  });
});

describe("incident feed hook", () => {
  test("uses the stream when available and refetches on each change signal", async () => {
    const sources: FakeEventSource[] = [];
    class FakeEventSource {
      listeners: Record<string, (() => void)[]> = {};
      closed = false;
      constructor(public url: string) {
        sources.push(this);
      }
      addEventListener(type: string, listener: () => void) {
        (this.listeners[type] ??= []).push(listener);
      }
      emit(type: string) {
        this.listeners[type]?.forEach((listener) => listener());
      }
      close() {
        this.closed = true;
      }
    }
    vi.stubGlobal("EventSource", FakeEventSource);
    const fetchMock = stubApi();

    const { result, unmount } = renderHook(() => useIncidentFeed());
    await waitFor(() => expect(result.current.loaded).toBe(true));
    expect(sources[0].url).toMatch(/\/incidents\/stream$/);

    act(() => sources[0].emit("open"));
    expect(result.current.status).toBe("live");
    act(() => sources[0].emit("incidents"));
    await waitFor(() => expect(calls(fetchMock, "GET /incidents")).toHaveLength(2));
    act(() => sources[0].emit("error"));
    expect(result.current.status).toBe("reconnecting");

    unmount();
    expect(sources[0].closed).toBe(true);
  });
});
