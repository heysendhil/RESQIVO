// Typed client for the RESQIVO FastAPI backend.
//
// Types mirror the backend's Pydantic models (backend/app/models,
// backend/app/qa/schemas.py, backend/app/workflow/schemas.py,
// backend/app/services/validation.py). Every response is shape-checked before
// use, and errors are mapped to fixed messages; raw response bodies are never
// shown to the user.

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/+$/, "");

// Domain models ----------------------------------------------------------------

export const RESOURCE_TYPES = [
  "food",
  "drinking_water",
  "medical_supplies",
  "rescue_personnel",
  "emergency_vehicles",
] as const;
export type ResourceType = (typeof RESOURCE_TYPES)[number];

export const DISASTER_TYPES = ["flood", "earthquake", "cyclone", "wildfire"] as const;
export type DisasterType = (typeof DISASTER_TYPES)[number];

export const SEVERITIES = ["low", "moderate", "high", "critical"] as const;
export type DisasterSeverity = (typeof SEVERITIES)[number];

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

export interface DisasterScenario {
  scenario_id: string;
  name: string;
  disaster_type: DisasterType;
  severity: DisasterSeverity;
  affected_population: number;
  location: string;
  description: string;
}

export interface AllocationNeed {
  destination_id: string;
  resource_type: ResourceType;
  quantity_needed: number;
}

export interface DraftPlanRequest {
  scenario: DisasterScenario;
  resources: Resource[];
  shelters: Shelter[];
  needs: AllocationNeed[];
  constraints: string[];
}

// Backend limits (backend/app/qa/schemas.py, backend/app/workflow/schemas.py).
export const LIMITS = {
  questionChars: 1000,
  descriptionChars: 2000,
  draftResources: 100,
  draftShelters: 100,
  draftNeeds: 200,
  constraints: 10,
  constraintChars: 500,
} as const;

// Responses ---------------------------------------------------------------------

export interface HealthResponse {
  status: string;
  service: string;
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

export interface Citation {
  label: string;
  source_id: string;
  title: string;
  publisher: string;
  url: string;
  chunk_id: string;
  synthetic: boolean;
  distance: number;
}

export type InsufficientReason =
  | "knowledge_base_empty"
  | "no_relevant_passages"
  | "model_reported_insufficient_evidence"
  | "answer_not_grounded";

export interface AnswerResponse {
  status: "answered" | "insufficient_evidence";
  reason: InsufficientReason | null;
  answer: string | null;
  citations: Citation[];
  uses_synthetic_sources: boolean;
  notice: string;
}

export interface PlanReview {
  original_validation: ValidationResult;
  final_plan: PlanValidationRequest;
  final_validation: ValidationResult;
  correction_attempts: number;
  max_correction_attempts: number;
  corrected: boolean;
  uncorrectable_codes: string[];
}

export interface ReviewResponse {
  answer: AnswerResponse;
  plan_review: PlanReview | null;
  notice: string;
}

export type InsufficientInformationReason =
  | "no_affected_population"
  | "no_available_resources"
  | "no_shelters";

export interface DraftPlanResponse {
  request_id: string;
  status: "insufficient_information" | "draft_invalid" | "draft_valid";
  reason: InsufficientInformationReason | null;
  input_validation: ValidationResult;
  guidance: AnswerResponse | null;
  evidence_available: boolean;
  plan_review: PlanReview | null;
  limitations: string[];
  notice: string;
}

// Simulated incident feed (backend/app/incidents/models.py) -------------------------

export const INCIDENT_STATUSES = ["new", "acknowledged", "closed"] as const;
export type IncidentStatus = (typeof INCIDENT_STATUSES)[number];
export type LocationConfidence = "simulated" | "operator_entered" | "unconfirmed";

export interface Coordinates {
  lat: number;
  lon: number;
}

export interface IncidentFields {
  title: string;
  disaster_type: DisasterType;
  severity: DisasterSeverity;
  summary: string;
  location: string;
  coordinates: Coordinates | null;
  affected_people: number | null;
  needs: string[];
  missing_fields: string[];
}

export interface Incident extends IncidentFields {
  incident_id: string;
  status: IncidentStatus;
  source: "simulation" | "call" | "manual";
  location_confidence: LocationConfidence;
  synthetic: true;
  created_at: string;
  updated_at: string;
}

export interface IncidentList {
  incidents: Incident[];
  version: number;
  notice: string;
}

export interface IncidentCreate extends IncidentFields {
  source: "call" | "manual";
}

export interface IncidentDraft {
  title: string | null;
  disaster_type: DisasterType | null;
  severity: DisasterSeverity | null;
  location: string | null;
  affected_people: number | null;
  needs: ResourceType[];
  summary: string;
}

export interface IntakeResponse {
  draft: IncidentDraft;
  missing_fields: string[];
  notice: string;
}

export const INTAKE_LIMITS = { transcriptChars: 4000 } as const;

// Errors ------------------------------------------------------------------------

export type ApiErrorKind =
  | "network"
  | "bad_request"
  | "payload_too_large"
  | "invalid_request"
  | "model_error"
  | "unavailable"
  | "timeout"
  | "server_error"
  | "unexpected_response";

export interface FieldError {
  field: string;
  message: string;
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly fieldErrors: FieldError[];
  /** True only for the backend's "not configured" 503 (no model key or invalid
   * AI settings), as opposed to a temporary outage. */
  readonly notConfigured: boolean;

  constructor(
    kind: ApiErrorKind,
    message: string,
    status: number | null = null,
    fieldErrors: FieldError[] = [],
    notConfigured = false,
  ) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.fieldErrors = fieldErrors;
    this.notConfigured = notConfigured;
  }
}

const MAX_FIELD_ERRORS = 10;

// The backend's fixed 503 messages (backend/app/main.py).
const NOT_CONFIGURED = "Question answering is not configured.";
const RETRIEVAL_UNAVAILABLE = "Knowledge retrieval is unavailable.";

function fieldErrorsFrom(body: unknown): FieldError[] {
  const detail = isObject(body) ? body.detail : undefined;
  if (!Array.isArray(detail)) return [];
  return detail
    .filter(isObject)
    .slice(0, MAX_FIELD_ERRORS)
    .map((item) => {
      const loc = Array.isArray(item.loc) ? item.loc : [];
      const path = loc[0] === "body" ? loc.slice(1) : loc;
      return {
        field: path.map(String).join(".") || "request",
        message: typeof item.msg === "string" ? item.msg : "Invalid value.",
      };
    });
}

function errorForStatus(status: number, body: unknown): ApiError {
  const detail = isObject(body) ? body.detail : undefined;
  switch (status) {
    case 400:
      return new ApiError(
        "bad_request",
        "The API could not read the request (HTTP 400).",
        status,
      );
    case 404:
      return new ApiError(
        "bad_request",
        "The incident no longer exists (HTTP 404). The list will refresh.",
        status,
      );
    case 409:
      return new ApiError(
        "bad_request",
        "The incident limit has been reached (HTTP 409). Clear incidents and try again.",
        status,
      );
    case 413:
      return new ApiError(
        "payload_too_large",
        "The request is too large for the API (HTTP 413). Reduce the number of " +
          "resources, shelters or allocations and try again.",
        status,
      );
    case 422:
      return new ApiError(
        "invalid_request",
        "The API rejected some inputs (HTTP 422). Correct the fields listed below.",
        status,
        fieldErrorsFrom(body),
      );
    case 502:
      return new ApiError(
        "model_error",
        "The language model did not return a usable result (HTTP 502). Nothing " +
          "was produced; try again later.",
        status,
      );
    case 503:
      if (detail === NOT_CONFIGURED) {
        return new ApiError(
          "unavailable",
          "AI features are not configured on the server (HTTP 503). The backend " +
            "needs a model API key set by an administrator. Deterministic " +
            "validation still works.",
          status,
          [],
          true,
        );
      }
      if (detail === RETRIEVAL_UNAVAILABLE) {
        return new ApiError(
          "unavailable",
          "Knowledge retrieval is unavailable (HTTP 503). Try again later.",
          status,
        );
      }
      return new ApiError(
        "unavailable",
        "The service is temporarily unavailable (HTTP 503).",
        status,
      );
    case 504:
      return new ApiError(
        "timeout",
        "The request did not complete in time (HTTP 504). Nothing was produced; " +
          "try again later.",
        status,
      );
    default:
      return new ApiError(
        "server_error",
        `The API returned an unexpected error (HTTP ${status}).`,
        status,
      );
  }
}

// Transport ---------------------------------------------------------------------

async function request<T>(
  path: string,
  init: {
    method: "GET" | "POST" | "PATCH" | "DELETE";
    body?: unknown;
    signal?: AbortSignal;
  },
  isExpected: (value: unknown) => value is T,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: init.method,
      headers:
        init.body === undefined ? undefined : { "Content-Type": "application/json" },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      signal: init.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(
      "network",
      `Could not reach the RESQIVO API at ${API_BASE_URL}. Check that the ` +
        "backend is running.",
    );
  }

  let body: unknown = null;
  let isJson = true;
  try {
    body = await response.json();
  } catch {
    isJson = false;
  }

  if (!response.ok) throw errorForStatus(response.status, body);
  if (!isJson || !isExpected(body)) {
    throw new ApiError(
      "unexpected_response",
      "The API returned a response in an unexpected format.",
      response.status,
    );
  }
  return body;
}

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request("/health", { method: "GET", signal }, isHealthResponse);
}

export function validatePlan(
  plan: PlanValidationRequest,
  signal?: AbortSignal,
): Promise<ValidationResult> {
  return request("/validate", { method: "POST", body: plan, signal }, isValidationResult);
}

export function askQuestion(
  question: string,
  signal?: AbortSignal,
): Promise<AnswerResponse> {
  return request(
    "/answer",
    { method: "POST", body: { question }, signal },
    isAnswerResponse,
  );
}

export function reviewPlan(
  question: string,
  plan: PlanValidationRequest | null,
  signal?: AbortSignal,
): Promise<ReviewResponse> {
  return request(
    "/review",
    { method: "POST", body: { question, plan }, signal },
    isReviewResponse,
  );
}

export function draftPlan(
  draft: DraftPlanRequest,
  signal?: AbortSignal,
): Promise<DraftPlanResponse> {
  return request(
    "/draft-plan",
    { method: "POST", body: draft, signal },
    isDraftPlanResponse,
  );
}

export function listIncidents(signal?: AbortSignal): Promise<IncidentList> {
  return request("/incidents", { method: "GET", signal }, isIncidentList);
}

export function createIncident(
  incident: IncidentCreate,
  signal?: AbortSignal,
): Promise<Incident> {
  return request("/incidents", { method: "POST", body: incident, signal }, isIncident);
}

export function setIncidentStatus(
  incidentId: string,
  status: IncidentStatus,
  signal?: AbortSignal,
): Promise<Incident> {
  return request(
    `/incidents/${encodeURIComponent(incidentId)}`,
    { method: "PATCH", body: { status }, signal },
    isIncident,
  );
}

export function simulateIncidents(
  scenario: "flood" | "cyclone",
  options: { count?: number; resetExisting?: boolean } = {},
  signal?: AbortSignal,
): Promise<IncidentList> {
  return request(
    "/incidents/simulate",
    {
      method: "POST",
      body: {
        scenario,
        count: options.count ?? 8,
        reset_existing: options.resetExisting ?? false,
      },
      signal,
    },
    isIncidentList,
  );
}

export function clearIncidents(signal?: AbortSignal): Promise<{ deleted: number }> {
  return request(
    "/incidents",
    { method: "DELETE", signal },
    (value): value is { deleted: number } => isObject(value) && isNumber(value.deleted),
  );
}

export function intakeCall(transcript: string, signal?: AbortSignal): Promise<IntakeResponse> {
  return request(
    "/incidents/intake",
    { method: "POST", body: { transcript }, signal },
    isIntakeResponse,
  );
}

/** URL of the server-sent change signal for the incident feed. */
export const INCIDENT_STREAM_URL = `${API_BASE_URL}/incidents/stream`;

// Response shape checks -------------------------------------------------------------

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isArrayOf<T>(value: unknown, item: (v: unknown) => v is T): value is T[] {
  return Array.isArray(value) && value.every(item);
}

function isHealthResponse(value: unknown): value is HealthResponse {
  return isObject(value) && isString(value.status) && isString(value.service);
}

function isValidationViolation(value: unknown): value is ValidationViolation {
  return (
    isObject(value) &&
    isString(value.code) &&
    isString(value.entity_id) &&
    isString(value.message) &&
    isObject(value.details) &&
    Object.values(value.details).every(isNumber)
  );
}

export function isValidationResult(value: unknown): value is ValidationResult {
  return (
    isObject(value) &&
    typeof value.valid === "boolean" &&
    isArrayOf(value.violations, isValidationViolation)
  );
}

function isCitation(value: unknown): value is Citation {
  return (
    isObject(value) &&
    isString(value.label) &&
    isString(value.source_id) &&
    isString(value.title) &&
    isString(value.publisher) &&
    isString(value.url) &&
    isString(value.chunk_id) &&
    typeof value.synthetic === "boolean" &&
    isNumber(value.distance)
  );
}

function isAnswerResponse(value: unknown): value is AnswerResponse {
  return (
    isObject(value) &&
    (value.status === "answered" || value.status === "insufficient_evidence") &&
    (value.reason === null || isString(value.reason)) &&
    (value.answer === null || isString(value.answer)) &&
    isArrayOf(value.citations, isCitation) &&
    typeof value.uses_synthetic_sources === "boolean" &&
    isString(value.notice)
  );
}

function isPlan(value: unknown): value is PlanValidationRequest {
  return (
    isObject(value) &&
    Array.isArray(value.resources) &&
    Array.isArray(value.allocations) &&
    Array.isArray(value.shelters)
  );
}

function isPlanReview(value: unknown): value is PlanReview {
  return (
    isObject(value) &&
    isValidationResult(value.original_validation) &&
    isPlan(value.final_plan) &&
    isValidationResult(value.final_validation) &&
    isNumber(value.correction_attempts) &&
    isNumber(value.max_correction_attempts) &&
    typeof value.corrected === "boolean" &&
    isArrayOf(value.uncorrectable_codes, isString)
  );
}

function isReviewResponse(value: unknown): value is ReviewResponse {
  return (
    isObject(value) &&
    isAnswerResponse(value.answer) &&
    (value.plan_review === null || isPlanReview(value.plan_review)) &&
    isString(value.notice)
  );
}

function isDraftPlanResponse(value: unknown): value is DraftPlanResponse {
  return (
    isObject(value) &&
    isString(value.request_id) &&
    (value.status === "insufficient_information" ||
      value.status === "draft_invalid" ||
      value.status === "draft_valid") &&
    (value.reason === null || isString(value.reason)) &&
    isValidationResult(value.input_validation) &&
    (value.guidance === null || isAnswerResponse(value.guidance)) &&
    typeof value.evidence_available === "boolean" &&
    (value.plan_review === null || isPlanReview(value.plan_review)) &&
    isArrayOf(value.limitations, isString) &&
    isString(value.notice)
  );
}

function isNullableNumber(value: unknown): boolean {
  return value === null || isNumber(value);
}

function isCoordinates(value: unknown): value is Coordinates {
  return isObject(value) && isNumber(value.lat) && isNumber(value.lon);
}

export function isIncident(value: unknown): value is Incident {
  return (
    isObject(value) &&
    isString(value.incident_id) &&
    isString(value.title) &&
    isString(value.summary) &&
    isString(value.location) &&
    isString(value.created_at) &&
    isString(value.updated_at) &&
    (DISASTER_TYPES as readonly unknown[]).includes(value.disaster_type) &&
    (SEVERITIES as readonly unknown[]).includes(value.severity) &&
    (INCIDENT_STATUSES as readonly unknown[]).includes(value.status) &&
    ["simulation", "call", "manual"].includes(value.source as string) &&
    ["simulated", "operator_entered", "unconfirmed"].includes(
      value.location_confidence as string,
    ) &&
    value.synthetic === true &&
    (value.coordinates === null || isCoordinates(value.coordinates)) &&
    isNullableNumber(value.affected_people) &&
    isArrayOf(value.needs, isString) &&
    isArrayOf(value.missing_fields, isString)
  );
}

function isIncidentList(value: unknown): value is IncidentList {
  return (
    isObject(value) &&
    isArrayOf(value.incidents, isIncident) &&
    isNumber(value.version) &&
    isString(value.notice)
  );
}

function isNullableString(value: unknown): boolean {
  return value === null || isString(value);
}

function isIntakeResponse(value: unknown): value is IntakeResponse {
  if (!isObject(value) || !isObject(value.draft)) return false;
  const draft = value.draft;
  return (
    isNullableString(draft.title) &&
    isNullableString(draft.location) &&
    (draft.disaster_type === null ||
      (DISASTER_TYPES as readonly unknown[]).includes(draft.disaster_type)) &&
    (draft.severity === null || (SEVERITIES as readonly unknown[]).includes(draft.severity)) &&
    isNullableNumber(draft.affected_people) &&
    isArrayOf(draft.needs, (n): n is ResourceType =>
      (RESOURCE_TYPES as readonly unknown[]).includes(n),
    ) &&
    isString(draft.summary) &&
    isArrayOf(value.missing_fields, isString) &&
    isString(value.notice)
  );
}
