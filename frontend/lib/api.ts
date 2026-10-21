// Client for the RESQIVO FastAPI backend.

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/+$/, "");

export type ResourceType =
  | "food"
  | "drinking_water"
  | "medical_supplies"
  | "rescue_personnel"
  | "emergency_vehicles";

export interface Resource {
  resource_id: string;
  name: string;
  resource_type: ResourceType;
  quantity_available: number;
  unit: string;
  location: string;
}

export interface ResourceAllocation {
  allocation_id: string;
  resource_id: string;
  destination_id: string;
  quantity_allocated: number;
}

export interface Shelter {
  shelter_id: string;
  name: string;
  location: string;
  capacity: number;
  current_occupancy: number;
}

export interface PlanValidationRequest {
  resources: Resource[];
  allocations: ResourceAllocation[];
  shelters: Shelter[];
}

export interface ValidationViolation {
  code: string;
  entity_id: string;
  message: string;
  details: Record<string, number>;
}

export interface ValidationResult {
  valid: boolean;
  violations: ValidationViolation[];
}

export class ApiError extends Error {}

function isValidationViolation(value: unknown): value is ValidationViolation {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.code === "string" &&
    typeof v.entity_id === "string" &&
    typeof v.message === "string" &&
    typeof v.details === "object" &&
    v.details !== null &&
    Object.values(v.details).every((detail) => typeof detail === "number")
  );
}

function isValidationResult(value: unknown): value is ValidationResult {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.valid === "boolean" &&
    Array.isArray(v.violations) &&
    v.violations.every(isValidationViolation)
  );
}

export async function validatePlan(
  plan: PlanValidationRequest,
): Promise<ValidationResult> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(plan),
    });
  } catch {
    throw new ApiError(
      `Could not reach the RESQIVO API at ${API_BASE_URL}. Check that the backend is running.`,
    );
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ApiError(
      `The API returned HTTP ${response.status} with a response that is not JSON.`,
    );
  }

  if (!response.ok) {
    throw new ApiError(
      `The API rejected the request (HTTP ${response.status}): ${JSON.stringify(body)}`,
    );
  }

  if (!isValidationResult(body)) {
    throw new ApiError("The API returned a response in an unexpected format.");
  }

  return body;
}
