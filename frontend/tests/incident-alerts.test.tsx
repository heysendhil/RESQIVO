import { act, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import Dashboard from "@/app/dashboard";
import type { Incident } from "@/lib/api";
import {
  AlertThrottle,
  TONES,
  alertLevel,
  alertMessage,
  blinkLevel,
  newAlertingIncidents,
  playTone,
  unacknowledgedCritical,
} from "@/lib/alerting";
import { useIncidentAlerts } from "@/lib/use-incident-alerts";

import { jsonResponse } from "./fixtures";

vi.mock("leaflet", () => ({ default: {} }));

const NOTICE = "Simulated incidents for planning and education only.";

function incident(id: string, severity: Incident["severity"], overrides: Partial<Incident> = {}): Incident {
  return {
    incident_id: id,
    title: `SIMULATED: ${severity} situation ${id}`,
    disaster_type: "flood",
    severity,
    summary: "Synthetic.",
    location: "Velachery, Chennai (simulated)",
    coordinates: null,
    affected_people: 10,
    needs: [],
    missing_fields: [],
    status: "new",
    source: "simulation",
    location_confidence: "unconfirmed",
    synthetic: true,
    created_at: "2026-10-23T09:30:00+00:00",
    updated_at: "2026-10-23T09:30:00+00:00",
    ...overrides,
  };
}

// A fake Web Audio context that records the tones played.
const played: number[][] = [];

class FakeAudioContext {
  currentTime = 0;
  state = "running";
  destination = {};
  private tone: number[] | null = null;
  resume() {
    return Promise.resolve();
  }
  createOscillator() {
    const tone: number[] = [];
    if (!this.tone) {
      this.tone = tone;
      played.push(tone);
    }
    const current = this.tone;
    queueMicrotask(() => {
      this.tone = null;
    });
    return {
      type: "sine",
      frequency: {
        set value(hz: number) {
          current.push(hz);
        },
      },
      connect: (node: unknown) => node,
      start: () => {},
      stop: () => {},
    };
  }
  createGain() {
    return {
      gain: { setValueAtTime: () => {}, linearRampToValueAtTime: () => {} },
      connect: (node: unknown) => node,
    };
  }
}

let feed: Incident[] = [];

function stubApi() {
  const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(
    async (url, init) => {
      const path = new URL(url).pathname;
      const method = init?.method ?? "GET";
      if (path === "/health") return jsonResponse({ status: "ok", service: "RESQIVO" });
      if (method === "GET" && path === "/incidents") {
        return jsonResponse({ incidents: feed, version: feed.length, notice: NOTICE });
      }
      if (method === "POST" && path === "/incidents/simulate") {
        return jsonResponse({ incidents: feed, version: feed.length, notice: NOTICE }, 201);
      }
      throw new Error(`Unexpected request to ${method} ${path}`);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
}

async function renderDashboard() {
  stubApi();
  const user = userEvent.setup();
  render(<Dashboard />);
  await screen.findByText("Online");
  await within(screen.getByRole("region", { name: "Incident queue" })).findByRole("tab", {
    name: `Live (${feed.length})`,
  });
  return user;
}

/** Make new incidents arrive, through the Flood simulation button. */
async function arrive(user: ReturnType<typeof userEvent.setup>, incidents: Incident[]) {
  feed = [...incidents, ...feed];
  await user.click(screen.getByRole("button", { name: "Flood simulation" }));
  await within(screen.getByRole("region", { name: "Incident queue" })).findByRole("tab", {
    name: `Live (${feed.length})`,
  });
}

const header = () => screen.getByRole("banner");

beforeEach(() => {
  played.length = 0;
  feed = [incident("INC-00000001", "critical")];
  window.localStorage.clear();
  vi.stubGlobal("AudioContext", FakeAudioContext);
});

afterEach(() => {
  Object.defineProperty(document, "hidden", { configurable: true, value: false });
});

describe("alert rules", () => {
  test("the first load never alerts; later high or critical arrivals do", () => {
    const first = [incident("INC-1", "critical")];
    expect(newAlertingIncidents(null, first)).toEqual([]);

    const later = [
      incident("INC-2", "critical"),
      incident("INC-3", "high"),
      incident("INC-4", "moderate"),
      incident("INC-5", "low"),
      incident("INC-6", "critical", { status: "closed" }),
      ...first,
    ];
    expect(newAlertingIncidents(new Set(["INC-1"]), later).map((i) => i.incident_id)).toEqual([
      "INC-2",
      "INC-3",
    ]);
  });

  test("the most urgent level decides the tone and the message", () => {
    const burst = [incident("INC-3", "high"), incident("INC-2", "critical")];

    expect(alertLevel(burst)).toBe("critical");
    expect(alertLevel([incident("INC-3", "high")])).toBe("high");
    expect(alertLevel([])).toBeNull();
    expect(alertMessage(burst)).toBe(
      "Simulated critical incident: SIMULATED: critical situation INC-2 " +
        "(Velachery, Chennai (simulated)), and 1 more new incident",
    );
  });

  test("the throttle allows one alert per window", () => {
    const throttle = new AlertThrottle(5000);

    expect(throttle.allow(0)).toBe(true);
    expect(throttle.allow(4999)).toBe(false);
    expect(throttle.allow(5000)).toBe(true);
  });

  test("tones are generated, not loaded: two 880 Hz beeps for critical", () => {
    const context = new FakeAudioContext();

    playTone(context as unknown as AudioContext, "critical");

    expect(played).toEqual([[880, 880]]);
    expect(TONES.high).toEqual([{ frequency: 660, start: 0, duration: 0.25 }]);
  });
});

describe("sound alerts", () => {
  test("are off by default, so nothing plays", async () => {
    const user = await renderDashboard();

    expect(within(header()).getByRole("switch", { name: /Sound off/ })).toHaveAttribute("aria-checked", "false");
    await arrive(user, [incident("INC-00000002", "critical")]);

    expect(played).toEqual([]);
  });

  test("when on, a new critical incident plays the urgent tone, once per burst", async () => {
    const user = await renderDashboard();

    await user.click(within(header()).getByRole("switch", { name: /Sound off/ }));
    expect(played).toEqual([[520]]); // confirmation chirp
    expect(window.localStorage.getItem("resqivo.alerts.sound")).toBe("on");

    await arrive(user, [
      incident("INC-00000002", "critical"),
      incident("INC-00000003", "high"),
      incident("INC-00000004", "critical"),
    ]);

    await waitFor(() => expect(played).toEqual([[520], [880, 880]]));
  });

  test("a new high incident plays the softer tone; low and moderate stay silent", async () => {
    const user = await renderDashboard();
    await user.click(within(header()).getByRole("switch", { name: /Sound off/ }));

    await arrive(user, [incident("INC-00000005", "moderate"), incident("INC-00000006", "low")]);
    expect(played).toEqual([[520]]);

    await arrive(user, [incident("INC-00000007", "high")]);
    await waitFor(() => expect(played).toEqual([[520], [660]]));
  });

  test("after a reload, audio is unlocked by the first click on the page", async () => {
    window.localStorage.setItem("resqivo.alerts.sound", "on");
    const created = vi.fn();
    class CountingAudioContext extends FakeAudioContext {
      constructor() {
        super();
        created();
      }
    }
    vi.stubGlobal("AudioContext", CountingAudioContext);
    const user = await renderDashboard();
    await within(header()).findByRole("switch", { name: /Sound on/ });
    expect(created).not.toHaveBeenCalled();

    await user.click(screen.getByRole("heading", { name: "Dashboard" }));

    expect(created).toHaveBeenCalledTimes(1);
  });

  test("the setting is remembered in this browser", async () => {
    window.localStorage.setItem("resqivo.alerts.sound", "on");

    await renderDashboard();

    await waitFor(() =>
      expect(within(header()).getByRole("switch", { name: /Sound on/ })).toHaveAttribute("aria-checked", "true"),
    );
  });

  test("new incidents are highlighted and announced even without sound", async () => {
    const user = await renderDashboard();

    await arrive(user, [incident("INC-00000002", "critical")]);

    const queue = screen.getByRole("region", { name: "Incident queue" });
    const card = within(queue).getByRole("button", { name: /INC-00000002/ });
    expect(await within(card).findByText("New")).toBeInTheDocument();
    expect(within(queue).getByRole("button", { name: /INC-00000001/ })).not.toHaveTextContent("New");
    expect(
      await screen.findByText(/^Simulated critical incident: SIMULATED: critical situation INC-00000002/),
    ).toHaveClass("sr-only");
  });
});

describe("with the live stream", () => {
  test("a second refresh right after an arrival keeps the highlight and plays once", async () => {
    const sources: { emit: (type: string) => void }[] = [];
    class FakeEventSource {
      listeners: Record<string, (() => void)[]> = {};
      constructor() {
        sources.push(this);
      }
      addEventListener(type: string, listener: () => void) {
        (this.listeners[type] ??= []).push(listener);
      }
      emit(type: string) {
        this.listeners[type]?.forEach((listener) => listener());
      }
      close() {}
    }
    vi.stubGlobal("EventSource", FakeEventSource);
    const user = await renderDashboard();
    await user.click(within(header()).getByRole("switch", { name: /Sound off/ }));

    feed = [incident("INC-00000009", "critical"), ...feed];
    // The button and the stream both refetch the feed, back to back.
    await user.click(screen.getByRole("button", { name: "Flood simulation" }));
    sources[0].emit("incidents");

    const queue = screen.getByRole("region", { name: "Incident queue" });
    const card = await within(queue).findByRole("button", { name: /INC-00000009/ });
    expect(await within(card).findByText("New")).toBeInTheDocument();
    await waitFor(() => expect(played).toEqual([[520], [880, 880]]));
  });
});

describe("continuous alarm", () => {
  test("only unacknowledged critical incidents keep the alarm; high ones only blink", () => {
    const incidents = [
      incident("INC-1", "critical"),
      incident("INC-2", "high"),
      incident("INC-3", "critical", { status: "acknowledged" }),
      incident("INC-4", "high", { status: "closed" }),
      incident("INC-5", "moderate"),
    ];

    expect(unacknowledgedCritical(incidents).map((i) => i.incident_id)).toEqual(["INC-1"]);
    expect(incidents.map(blinkLevel)).toEqual(["critical", "high", null, null, null]);
  });

  test("repeats until silenced; a new high beeps once, a new critical restarts it", () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
    window.localStorage.setItem("resqivo.alerts.sound", "on");
    const first = [incident("INC-1", "critical")];
    const { result, rerender } = renderHook(({ list }) => useIncidentAlerts(list, true), {
      initialProps: { list: first },
    });
    act(() => vi.advanceTimersByTime(0)); // saved settings are read

    expect(result.current.alarm).toEqual({ count: 1, active: true });
    act(() => vi.advanceTimersByTime(8_000));
    // Two repeats of the critical double beep.
    expect(played.flat()).toEqual([880, 880, 880, 880]);

    act(() => result.current.silence());
    expect(result.current.alarm).toEqual({ count: 0, active: false });
    let before = played.flat().length;
    act(() => vi.advanceTimersByTime(12_000));
    expect(played.flat().slice(before)).toEqual([]);

    // A new high incident beeps once on arrival but does not keep the alarm going.
    before = played.flat().length;
    const withHigh = [incident("INC-2", "high"), ...first];
    rerender({ list: withHigh });
    expect(result.current.alarm).toEqual({ count: 0, active: false });
    act(() => vi.advanceTimersByTime(20_000));
    expect(played.flat().slice(before)).toEqual([660]);

    // A new critical incident restarts the continuous alarm.
    rerender({ list: [incident("INC-3", "critical"), ...withHigh] });
    expect(result.current.alarm).toEqual({ count: 1, active: true });
    before = played.flat().length;
    act(() => vi.advanceTimersByTime(8_000));
    expect(played.flat().slice(before)).toEqual([880, 880, 880, 880]);
    vi.useRealTimers();
  });

  test("stops once the incidents are acknowledged, and never sounds with sound off", () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
    window.localStorage.setItem("resqivo.alerts.sound", "on");
    const { result, rerender } = renderHook(({ list }) => useIncidentAlerts(list, true), {
      initialProps: { list: [incident("INC-1", "critical")] },
    });
    act(() => vi.advanceTimersByTime(0));

    rerender({ list: [incident("INC-1", "critical", { status: "acknowledged" })] });
    act(() => vi.advanceTimersByTime(20_000));
    expect(result.current.alarm.active).toBe(false);
    expect(played).toEqual([]);

    act(() => result.current.setSound(false));
    const before = played.flat().length;
    rerender({ list: [incident("INC-2", "critical")] });
    act(() => vi.advanceTimersByTime(20_000));
    expect(played.flat().slice(before)).toEqual([]);
    expect(result.current.alarm.active).toBe(true);
    vi.useRealTimers();
  });

  test("the header shows the alarm and Silence stops it", async () => {
    const user = await renderDashboard();

    const alarm = within(header()).getByRole("button", { name: /Alarm · 1 critical unacknowledged · Silence/ });
    await user.click(alarm);

    expect(within(header()).queryByRole("button", { name: /Alarm/ })).toBeNull();
  });
});

describe("desktop notifications", () => {
  function stubNotifications(permission: NotificationPermission, grant: NotificationPermission = permission) {
    const shown: { title: string; body?: string }[] = [];
    class FakeNotification {
      static permission = permission;
      static requestPermission = vi.fn(async () => {
        FakeNotification.permission = grant;
        return grant;
      });
      constructor(title: string, options?: NotificationOptions) {
        shown.push({ title, body: options?.body });
      }
    }
    vi.stubGlobal("Notification", FakeNotification);
    return { shown, FakeNotification };
  }

  test("ask permission only when switched on, and notify only while the tab is hidden", async () => {
    const { shown, FakeNotification } = stubNotifications("default", "granted");
    const user = await renderDashboard();
    expect(FakeNotification.requestPermission).not.toHaveBeenCalled();

    await user.click(within(header()).getByRole("switch", { name: /Desktop off/ }));
    expect(FakeNotification.requestPermission).toHaveBeenCalledTimes(1);
    expect(within(header()).getByRole("switch", { name: /Desktop on/ })).toBeInTheDocument();

    await arrive(user, [incident("INC-00000002", "critical")]);
    expect(shown).toEqual([]); // the tab is visible

    Object.defineProperty(document, "hidden", { configurable: true, value: true });
    vi.useFakeTimers({ toFake: ["Date"], now: Date.now() + 10_000 });
    await arrive(user, [incident("INC-00000003", "critical")]);
    vi.useRealTimers();

    await waitFor(() => expect(shown).toHaveLength(1));
    expect(shown[0].title).toBe("RESQIVO simulation");
    expect(shown[0].body).toMatch(/^Simulated critical incident: SIMULATED: critical situation INC-00000003/);
  });

  test("blocked notifications are explained and cannot be switched on", async () => {
    stubNotifications("denied");
    await renderDashboard();

    const button = await within(header()).findByRole("switch", { name: /Desktop blocked/ });
    expect(button).toBeDisabled();
  });

  test("browsers without notifications show no switch", async () => {
    await renderDashboard();

    expect(within(header()).queryByRole("switch", { name: /Desktop/ })).toBeNull();
  });
});
