"use client";

import { useState } from "react";

import {
  ApiError,
  validatePlan,
  type PlanValidationRequest,
  type ValidationResult,
} from "@/lib/api";
import { samplePlans } from "@/lib/sample-plans";

type RequestState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; result: ValidationResult }
  | { status: "error"; message: string };

export default function ValidatePlan() {
  const [selectedId, setSelectedId] = useState(samplePlans[0].id);
  const [state, setState] = useState<RequestState>({ status: "idle" });

  const selected =
    samplePlans.find((sample) => sample.id === selectedId) ?? samplePlans[0];

  function selectPlan(id: string) {
    setSelectedId(id);
    setState({ status: "idle" });
  }

  async function submit() {
    setState({ status: "loading" });
    try {
      const result = await validatePlan(selected.plan);
      setState({ status: "success", result });
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.message
          : "Unexpected error while validating the plan.";
      setState({ status: "error", message });
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">1. Choose a sample plan</h2>
        <div className="flex flex-col gap-2 sm:flex-row">
          {samplePlans.map((sample) => (
            <button
              key={sample.id}
              type="button"
              onClick={() => selectPlan(sample.id)}
              aria-pressed={sample.id === selectedId}
              className={`rounded-lg border px-4 py-2 text-left text-sm transition-colors ${
                sample.id === selectedId
                  ? "border-foreground bg-foreground text-background"
                  : "border-black/15 hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
              }`}
            >
              {sample.label}
            </button>
          ))}
        </div>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          {selected.description}
        </p>
        <PlanSummary plan={selected.plan} />
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">2. Validate</h2>
        <div>
          <button
            type="button"
            onClick={submit}
            disabled={state.status === "loading"}
            className="rounded-lg bg-red-700 px-5 py-2.5 text-sm font-medium text-white hover:bg-red-800 disabled:cursor-wait disabled:opacity-60"
          >
            {state.status === "loading" ? "Validating…" : "Validate plan"}
          </button>
        </div>
        <div aria-live="polite">
          <ResultPanel state={state} />
        </div>
      </section>
    </div>
  );
}

function PlanSummary({ plan }: { plan: PlanValidationRequest }) {
  return (
    <div className="grid gap-4 text-sm md:grid-cols-3">
      <SummaryList
        title="Resources"
        items={plan.resources.map(
          (r) =>
            `${r.resource_id}: ${r.name}, ${r.quantity_available.toLocaleString()} ${r.unit}`,
        )}
      />
      <SummaryList
        title="Allocations"
        items={plan.allocations.map(
          (a) =>
            `${a.allocation_id}: ${a.quantity_allocated.toLocaleString()} of ${a.resource_id} to ${a.destination_id}`,
        )}
      />
      <SummaryList
        title="Shelters"
        items={plan.shelters.map(
          (s) =>
            `${s.shelter_id}: ${s.name}, ${s.current_occupancy}/${s.capacity} occupied`,
        )}
      />
    </div>
  );
}

function SummaryList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-lg border border-black/10 p-3 dark:border-white/15">
      <h3 className="mb-2 font-medium">{title}</h3>
      <ul className="flex flex-col gap-1 font-mono text-xs break-words">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function ResultPanel({ state }: { state: RequestState }) {
  if (state.status === "idle") {
    return null;
  }

  if (state.status === "loading") {
    return (
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        Sending plan to the validation API…
      </p>
    );
  }

  if (state.status === "error") {
    return (
      <div
        role="alert"
        className="rounded-lg border border-amber-600/40 bg-amber-50 p-4 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200"
      >
        <p className="font-semibold">Validation could not be completed</p>
        <p className="mt-1 break-words">{state.message}</p>
      </div>
    );
  }

  const { result } = state;

  return (
    <div className="flex flex-col gap-3">
      <p
        className={`w-fit rounded-full px-3 py-1 text-sm font-semibold ${
          result.valid
            ? "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300"
            : "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300"
        }`}
      >
        {result.valid ? "Valid" : "Invalid"}
      </p>

      {result.violations.length === 0 ? (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          No configured constraint violations were found.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {result.violations.map((violation, index) => (
            <li
              key={`${violation.code}-${violation.entity_id}-${index}`}
              className="rounded-lg border border-black/10 p-3 text-sm dark:border-white/15"
            >
              <p>
                <span className="font-mono font-semibold">{violation.code}</span>{" "}
                <span className="text-zinc-600 dark:text-zinc-400">
                  on <span className="font-mono">{violation.entity_id}</span>
                </span>
              </p>
              <p className="mt-1">{violation.message}</p>
              {Object.keys(violation.details).length > 0 && (
                <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 font-mono text-xs">
                  {Object.entries(violation.details).map(([key, value]) => (
                    <div key={key} className="contents">
                      <dt className="text-zinc-600 dark:text-zinc-400">{key}</dt>
                      <dd>{value.toLocaleString()}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </li>
          ))}
        </ul>
      )}

      <p className="text-xs text-zinc-600 dark:text-zinc-400">
        Draft validation of configured rules only. A human reviewer must approve
        any plan; RESQIVO does not dispatch resources.
      </p>
    </div>
  );
}
