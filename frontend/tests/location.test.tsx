import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import Dashboard from "@/app/dashboard";
import {
  GEOLOCATION_MESSAGES,
  GEOLOCATION_OPTIONS,
  formatCoordinates,
  requestDevicePosition,
} from "@/lib/geolocation";
import { samplePlans } from "@/lib/sample-plans";
import { sampleWorkspaces, toDraftRequest, workspaceFromSample } from "@/lib/workspace";

import { draftResponse, jsonResponse } from "./fixtures";

type Success = (position: GeolocationPosition) => void;
type Failure = (error: GeolocationPositionError) => void;

const LONDON = { latitude: 51.507351, longitude: -0.127758, accuracy: 24.6 };

function position(coords = LONDON) {
  return { coords, timestamp: 0 } as unknown as GeolocationPosition;
}

function positionError(code: 1 | 2 | 3) {
  return { code, message: "browser detail" } as GeolocationPositionError;
}

/** Install a fake navigator.geolocation whose behaviour each test controls. */
function installGeolocation(
  behaviour: (success: Success, failure: Failure, options?: PositionOptions) => void,
) {
  const getCurrentPosition = vi.fn(behaviour);
  Object.defineProperty(navigator, "geolocation", {
    value: { getCurrentPosition },
    configurable: true,
  });
  return getCurrentPosition;
}

function removeGeolocation() {
  Object.defineProperty(navigator, "geolocation", { value: undefined, configurable: true });
}

afterEach(() => {
  removeGeolocation();
});

function stubApi() {
  const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(
    async (url) => {
    const path = new URL(url).pathname;
    if (path === "/health") return jsonResponse({ status: "ok", service: "RESQIVO" });
    if (path === "/draft-plan") return jsonResponse(draftResponse);
    throw new Error(`Unexpected request to ${path}`);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function renderDashboard() {
  const fetchMock = stubApi();
  const user = userEvent.setup();
  render(<Dashboard />);
  await screen.findByText("Online");
  return { user, fetchMock, field: screen.getByLabelText("Disaster location") };
}

describe("scenario population", () => {
  test("each sample fills the location from its own data", async () => {
    const { user, field } = await renderDashboard();

    expect(field).toHaveValue("Simulated District A");
    await user.clear(field);
    await user.type(field, "My edit");
    await user.click(screen.getByRole("button", { name: sampleWorkspaces[1].label }));
    expect(field).toHaveValue("Simulated District B");
    await user.click(screen.getByRole("button", { name: sampleWorkspaces[0].label }));
    expect(field).toHaveValue("Simulated District A");
  });

  test("a sample without a location starts empty instead of inventing one", () => {
    const withoutLocation = { ...samplePlans[0], scenarioLocation: undefined };

    expect(workspaceFromSample(withoutLocation).workspace.scenario.location).toBe("");
    expect(sampleWorkspaces.map((s) => s.workspace.scenario.location)).toEqual(
      samplePlans.map((p) => p.scenarioLocation),
    );
  });

  test("the location stays freely editable", async () => {
    const { user, field } = await renderDashboard();

    await user.clear(field);
    await user.type(field, "Riverside ward, Simulated District A");

    expect(field).toHaveValue("Riverside ward, Simulated District A");
  });
});

describe("use my current location", () => {
  test("permission is not requested until the button is pressed", async () => {
    const getCurrentPosition = installGeolocation(() => {});

    await renderDashboard();

    expect(getCurrentPosition).not.toHaveBeenCalled();
  });

  test("shows the coordinates but changes nothing until the user confirms", async () => {
    const getCurrentPosition = installGeolocation((success) => success(position()));
    const { user, field, fetchMock } = await renderDashboard();

    await user.click(screen.getByRole("button", { name: "Use my current location" }));

    expect(getCurrentPosition).toHaveBeenCalledTimes(1);
    expect(getCurrentPosition.mock.calls[0][2]).toEqual(GEOLOCATION_OPTIONS);
    const status = await screen.findByText(/Your device reports/);
    expect(status).toHaveTextContent("51.5074, -0.1278");
    expect(status).toHaveTextContent("accuracy about 25 m");
    expect(status).toHaveTextContent(/may not be the disaster location/);
    expect(field).toHaveValue("Simulated District A"); // not silently replaced

    await user.click(
      screen.getByRole("button", { name: "Use these coordinates as the disaster location" }),
    );

    expect(field).toHaveValue("51.5074, -0.1278");
    expect(screen.getByText(/Coordinates inserted/)).toBeInTheDocument();
    // The confirmed, still-editable value is what the draft request sends.
    await user.type(field, " (Riverside ward)");
    await user.click(screen.getByRole("button", { name: "Generate draft plan" }));
    const draftCall = fetchMock.mock.calls.find(
      ([url]) => new URL(url).pathname === "/draft-plan",
    );
    const sent = JSON.parse(String(draftCall?.[1]?.body));
    expect(sent.scenario.location).toBe("51.5074, -0.1278 (Riverside ward)");
  });

  test("dismissing leaves the disaster location untouched", async () => {
    installGeolocation((success) => success(position()));
    const { user, field } = await renderDashboard();

    await user.click(screen.getByRole("button", { name: "Use my current location" }));
    await user.click(await screen.findByRole("button", { name: "Dismiss" }));

    expect(field).toHaveValue("Simulated District A");
    expect(screen.queryByText(/Your device reports/)).toBeNull();
  });

  test("shows a busy state while the browser is locating", async () => {
    installGeolocation(() => {}); // never answers
    const { user } = await renderDashboard();

    await user.click(screen.getByRole("button", { name: "Use my current location" }));

    expect(screen.getByRole("button", { name: "Locating…" })).toBeDisabled();
    expect(screen.getByText("Requesting your device location…")).toBeInTheDocument();
  });

  test.each([
    [1, "denied", /permission was denied/],
    [2, "unavailable", /could not determine its location/],
    [3, "timeout", /took too long/],
  ] as const)("error code %i (%s) is explained and changes nothing", async (code, _kind, message) => {
    installGeolocation((_success, failure) => failure(positionError(code)));
    const { user, field } = await renderDashboard();

    await user.click(screen.getByRole("button", { name: "Use my current location" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(message);
    expect(alert).toHaveTextContent(/enter the disaster location manually|Try again/i);
    expect(alert).not.toHaveTextContent("browser detail");
    expect(field).toHaveValue("Simulated District A");
    // The user can try again after an error.
    expect(screen.getByRole("button", { name: "Use my current location" })).toBeEnabled();
  });

  test("a browser without geolocation is explained", async () => {
    removeGeolocation();
    const { user, field } = await renderDashboard();

    await user.click(screen.getByRole("button", { name: "Use my current location" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      GEOLOCATION_MESSAGES.unsupported,
    );
    expect(field).toHaveValue("Simulated District A");
  });
});

describe("geolocation helper", () => {
  test("rejects on an insecure page without asking the browser", async () => {
    const getCurrentPosition = vi.fn();

    await expect(
      requestDevicePosition({ getCurrentPosition } as unknown as Geolocation, false),
    ).rejects.toMatchObject({ kind: "insecure" });
    expect(getCurrentPosition).not.toHaveBeenCalled();
  });

  test("unknown error codes are treated as unavailable", async () => {
    const geolocation = {
      getCurrentPosition: (_s: Success, failure: Failure) =>
        failure({ code: 99 } as unknown as GeolocationPositionError),
    } as unknown as Geolocation;

    await expect(requestDevicePosition(geolocation, true)).rejects.toMatchObject({
      kind: "unavailable",
    });
  });

  test("coordinates are formatted to four decimal places", () => {
    expect(formatCoordinates(LONDON)).toBe("51.5074, -0.1278");
    expect(formatCoordinates({ latitude: -33.86882, longitude: 151.20929, accuracy: 5 })).toBe(
      "-33.8688, 151.2093",
    );
  });

  test("the draft request carries whatever location the user set", () => {
    const workspace = {
      ...sampleWorkspaces[0].workspace,
      scenario: { ...sampleWorkspaces[0].workspace.scenario, location: "Ward 7" },
    };

    expect(toDraftRequest(workspace).scenario.location).toBe("Ward 7");
  });
});
