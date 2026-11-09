// Synthetic sample plans for demonstrating validation. Not real incident data.

import type { PlanValidationRequest } from "@/lib/api";

export interface SamplePlan {
  id: string;
  label: string;
  description: string;
  /** The disaster location for this synthetic scenario, if the sample has one. */
  scenarioLocation?: string;
  plan: PlanValidationRequest;
}

const resources: PlanValidationRequest["resources"] = [
  {
    resource_id: "water-001",
    name: "Bottled drinking water",
    resource_type: "drinking_water",
    quantity_available: 12000,
    unit: "litres",
    location: "Central Warehouse",
  },
  {
    resource_id: "med-001",
    name: "First-aid kits",
    resource_type: "medical_supplies",
    quantity_available: 300,
    unit: "kits",
    location: "District Hospital Store",
  },
];

const shelters: PlanValidationRequest["shelters"] = [
  {
    shelter_id: "shelter-001",
    name: "Government School Hall",
    location: "Simulated Zone A",
    capacity: 800,
    current_occupancy: 620,
  },
  {
    shelter_id: "shelter-002",
    name: "Community Centre",
    location: "Simulated Zone B",
    capacity: 400,
    current_occupancy: 310,
  },
];

export const samplePlans: SamplePlan[] = [
  {
    id: "flood-valid",
    label: "Flood response: within limits",
    description:
      "Water and first-aid kits sent to two shelters, all within stock and capacity.",
    scenarioLocation: "Simulated District A",
    plan: {
      resources,
      shelters,
      allocations: [
        {
          allocation_id: "alloc-001",
          resource_id: "water-001",
          destination_id: "shelter-001",
          quantity_allocated: 7000,
        },
        {
          allocation_id: "alloc-002",
          resource_id: "water-001",
          destination_id: "shelter-002",
          quantity_allocated: 4000,
        },
        {
          allocation_id: "alloc-003",
          resource_id: "med-001",
          destination_id: "shelter-001",
          quantity_allocated: 200,
        },
      ],
    },
  },
  {
    id: "flood-invalid",
    label: "Flood response: with problems",
    description:
      "Water is over-allocated, one allocation targets a shelter that does not exist, and one shelter is over capacity.",
    scenarioLocation: "Simulated District B",
    plan: {
      resources,
      shelters: [
        shelters[0],
        { ...shelters[1], current_occupancy: 460 },
      ],
      allocations: [
        {
          allocation_id: "alloc-001",
          resource_id: "water-001",
          destination_id: "shelter-001",
          quantity_allocated: 9000,
        },
        {
          allocation_id: "alloc-002",
          resource_id: "water-001",
          destination_id: "shelter-002",
          quantity_allocated: 5000,
        },
        {
          allocation_id: "alloc-003",
          resource_id: "med-001",
          destination_id: "shelter-009",
          quantity_allocated: 150,
        },
      ],
    },
  },
];
