// Synthetic fixtures shaped exactly like the backend's responses. No real data.

import { vi } from "vitest";

import type {
  AnswerResponse,
  DraftPlanRequest,
  DraftPlanResponse,
  PlanReview,
  PlanValidationRequest,
  ReviewResponse,
  ValidationResult,
} from "@/lib/api";

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Stub fetch with one response per call, in order (the last one repeats). */
export function stubFetch(...responses: Response[]) {
  const queue = [...responses];
  const fetchMock = vi.fn(async () => {
    const next = queue.length > 1 ? queue.shift()! : queue[0];
    return next.clone();
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock as unknown as ReturnType<typeof vi.fn> & {
    mock: { calls: [string, RequestInit & { body: string; headers: unknown }][] };
  };
}

export const plan: PlanValidationRequest = {
  resources: [
    {
      resource_id: "water-001",
      name: "Bottled drinking water",
      resource_type: "drinking_water",
      quantity_available: 1000,
      unit: "litres",
      location: "Depot",
    },
  ],
  allocations: [
    {
      allocation_id: "alloc-001",
      resource_id: "water-001",
      destination_id: "shelter-001",
      quantity_allocated: 1100,
    },
  ],
  shelters: [
    {
      shelter_id: "shelter-001",
      name: "Community Hall",
      location: "Zone A",
      capacity: 500,
      current_occupancy: 200,
    },
  ],
};

export const validResult: ValidationResult = { valid: true, violations: [] };

export const overStock: ValidationResult = {
  valid: false,
  violations: [
    {
      code: "DOM-04",
      entity_id: "water-001",
      message: "Resource allocation exceeds available stock.",
      details: { quantity_available: 1000, quantity_allocated: 1100, excess_quantity: 100 },
    },
  ],
};

const NOTICE =
  "RESQIVO answers support simulated planning and education only. They do not " +
  "replace emergency services, public authorities, or official instructions.";

export const answered: AnswerResponse = {
  status: "answered",
  reason: null,
  answer: "Store drinking water in clean covered containers [P1].",
  citations: [
    {
      label: "P1",
      source_id: "SYN-001",
      title: "SYNTHETIC: Drinking water storage at temporary shelters",
      publisher: "RESQIVO synthetic test fixture (not an official source)",
      url: "urn:resqivo:synthetic:SYN-001",
      chunk_id: "SYN-001:0000",
      synthetic: true,
      distance: 0.42,
    },
  ],
  uses_synthetic_sources: true,
  notice: NOTICE,
};

export const insufficient: AnswerResponse = {
  status: "insufficient_evidence",
  reason: "no_relevant_passages",
  answer: null,
  citations: [],
  uses_synthetic_sources: false,
  notice: NOTICE,
};

export const correctedReview: PlanReview = {
  original_validation: overStock,
  final_plan: {
    ...plan,
    allocations: [{ ...plan.allocations[0], quantity_allocated: 900 }],
  },
  final_validation: validResult,
  correction_attempts: 1,
  max_correction_attempts: 2,
  corrected: true,
  uncorrectable_codes: [],
};

export const reviewResponse: ReviewResponse = {
  answer: answered,
  plan_review: correctedReview,
  notice: NOTICE,
};

export const draftRequest: DraftPlanRequest = {
  scenario: {
    scenario_id: "SCN-001",
    name: "Synthetic river flood",
    disaster_type: "flood",
    severity: "high",
    affected_population: 800,
    location: "Simulated District A",
    description: "Synthetic scenario.",
  },
  resources: plan.resources,
  shelters: plan.shelters,
  needs: [],
  constraints: [],
};

const DRAFT_NOTICE =
  "This is a draft proposal for human review. No resources have been dispatched, " +
  "booked or requested, and no one has been contacted.";

export const draftResponse: DraftPlanResponse = {
  request_id: "3f2a9c0b1d2e4f5a8b7c6d5e4f3a2b1c",
  status: "draft_valid",
  reason: null,
  input_validation: validResult,
  guidance: answered,
  evidence_available: true,
  plan_review: {
    original_validation: validResult,
    final_plan: {
      ...plan,
      allocations: [{ ...plan.allocations[0], quantity_allocated: 600 }],
    },
    final_validation: validResult,
    correction_attempts: 0,
    max_correction_attempts: 2,
    corrected: false,
    uncorrectable_codes: [],
  },
  limitations: [
    "The validator checks stock, identifiers, destinations and shelter occupancy. " +
      "It does not check whether needs or constraints are met.",
  ],
  notice: DRAFT_NOTICE,
};
