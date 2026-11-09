// Browser geolocation for the "Use my current location" button. Only called
// from a user click, so the permission prompt never appears on page load. No
// reverse geocoding or other external service is used: the result is
// coordinates only.

export interface DevicePosition {
  latitude: number;
  longitude: number;
  /** Radius of uncertainty in metres, as reported by the browser. */
  accuracy: number;
}

export type GeolocationFailure =
  | "unsupported"
  | "insecure"
  | "denied"
  | "unavailable"
  | "timeout";

export class GeolocationError extends Error {
  readonly kind: GeolocationFailure;

  constructor(kind: GeolocationFailure) {
    super(GEOLOCATION_MESSAGES[kind]);
    this.name = "GeolocationError";
    this.kind = kind;
  }
}

export const GEOLOCATION_MESSAGES: Record<GeolocationFailure, string> = {
  unsupported:
    "This browser does not support location access. Enter the disaster location manually.",
  insecure:
    "Location access needs a secure page (https or localhost). Enter the disaster location manually.",
  denied:
    "Location permission was denied. You can allow it in your browser's site settings, or enter the disaster location manually.",
  unavailable:
    "Your device could not determine its location. Enter the disaster location manually.",
  timeout:
    "Finding your location took too long. Try again, or enter the disaster location manually.",
};

export const GEOLOCATION_OPTIONS: PositionOptions = {
  enableHighAccuracy: false,
  timeout: 10_000,
  maximumAge: 60_000,
};

// GeolocationPositionError codes (W3C Geolocation API).
const ERROR_KINDS: Record<number, GeolocationFailure> = {
  1: "denied",
  2: "unavailable",
  3: "timeout",
};

export function requestDevicePosition(
  geolocation: Geolocation | undefined = typeof navigator === "undefined"
    ? undefined
    : navigator.geolocation,
  // Only an explicit false blocks the request; browsers enforce this themselves.
  secure: boolean | undefined = typeof window === "undefined"
    ? undefined
    : window.isSecureContext,
): Promise<DevicePosition> {
  if (secure === false) return Promise.reject(new GeolocationError("insecure"));
  if (!geolocation) return Promise.reject(new GeolocationError("unsupported"));
  return new Promise((resolve, reject) => {
    geolocation.getCurrentPosition(
      (position) =>
        resolve({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
        }),
      (error) => reject(new GeolocationError(ERROR_KINDS[error.code] ?? "unavailable")),
      GEOLOCATION_OPTIONS,
    );
  });
}

/** Coordinates at 4 decimal places (about 11 m), e.g. "12.9716, 77.5946". */
export function formatCoordinates({ latitude, longitude }: DevicePosition): string {
  return `${latitude.toFixed(4)}, ${longitude.toFixed(4)}`;
}
