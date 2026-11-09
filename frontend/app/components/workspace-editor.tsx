"use client";

import { LIMITS } from "@/lib/api";
import {
  SCENARIO_OPTIONS,
  TABLES,
  emptyRow,
  sampleWorkspaces,
  type Row,
  type ScenarioFields,
  type TableName,
} from "@/lib/workspace";

import LocationField from "./location-field";

export const inputClass =
  "w-full rounded-md border border-line bg-canvas px-2.5 py-1.5 text-sm text-ink placeholder:text-muted/70 focus:border-accent";
const ghostButton =
  "rounded-md border border-line px-3 py-1.5 text-xs font-medium text-ink hover:border-accent/60 hover:bg-accent/10";

function readable(value: string): string {
  return value.replace(/_/g, " ");
}

// Samples ----------------------------------------------------------------------------

export function SampleSelector({
  sampleId,
  onSelectSample,
}: {
  sampleId: string | null;
  onSelectSample: (id: string) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-col gap-2 sm:flex-row" role="group" aria-label="Sample scenarios">
        {sampleWorkspaces.map((sample) => {
          const active = sample.id === sampleId;
          return (
            <button
              key={sample.id}
              type="button"
              aria-pressed={active}
              onClick={() => onSelectSample(sample.id)}
              title={sample.description}
              className={`rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                active
                  ? "border-accent bg-accent/10 text-ink"
                  : "border-line text-ink hover:border-accent/50 hover:bg-panel-raised"
              }`}
            >
              {sample.label}
            </button>
          );
        })}
      </div>
      <p className="text-xs text-muted">
        Samples are <strong className="text-warn-ink">synthetic</strong> training
        data. Every quantity and capacity comes from what is entered here; RESQIVO
        never fills them in.
      </p>
    </div>
  );
}

// Scenario form ------------------------------------------------------------------------

function Group({ legend, children }: { legend: string; children: React.ReactNode }) {
  return (
    <fieldset className="grid gap-3 rounded-lg border border-line bg-canvas/30 p-4 sm:grid-cols-2">
      <legend className="px-1 text-xs font-semibold uppercase tracking-wider text-muted">
        {legend}
      </legend>
      {children}
    </fieldset>
  );
}

export function ScenarioForm({
  scenario,
  onChange,
}: {
  scenario: ScenarioFields;
  onChange: (key: keyof ScenarioFields, value: string) => void;
}) {
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Group legend="Identification">
        <TextField label="Scenario ID" value={scenario.scenario_id} onChange={(v) => onChange("scenario_id", v)} />
        <TextField label="Scenario name" value={scenario.name} onChange={(v) => onChange("name", v)} />
      </Group>
      <Group legend="Impact">
        <SelectField
          label="Disaster type"
          value={scenario.disaster_type}
          options={SCENARIO_OPTIONS.disaster_type}
          onChange={(v) => onChange("disaster_type", v)}
        />
        <SelectField
          label="Severity"
          value={scenario.severity}
          options={SCENARIO_OPTIONS.severity}
          onChange={(v) => onChange("severity", v)}
        />
        <TextField
          label="Affected population"
          inputMode="numeric"
          value={scenario.affected_population}
          onChange={(v) => onChange("affected_population", v)}
        />
      </Group>
      <Group legend="Location">
        <LocationField value={scenario.location} onChange={(v) => onChange("location", v)} />
      </Group>
      <Group legend="Description">
        <label className="flex flex-col gap-1 text-sm sm:col-span-2">
          <span className="text-ink">Description (optional)</span>
          <textarea
            value={scenario.description}
            maxLength={LIMITS.descriptionChars}
            rows={4}
            onChange={(event) => onChange("description", event.target.value)}
            className={inputClass}
          />
        </label>
      </Group>
    </div>
  );
}

export function ConstraintsField({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-semibold text-ink">
        Operational constraints (optional, one per line, up to {LIMITS.constraints})
      </span>
      <textarea
        value={value}
        rows={3}
        onChange={(event) => onChange(event.target.value)}
        className={inputClass}
      />
      <span className="text-xs text-muted">
        Constraints guide the draft only; the validator does not check them.
      </span>
    </label>
  );
}

function TextField({
  label,
  value,
  onChange,
  inputMode,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  inputMode?: "numeric";
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-ink">{label}</span>
      <input
        type="text"
        inputMode={inputMode}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={inputClass}
      />
    </label>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: readonly string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-ink">{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} className={inputClass}>
        {options.map((option) => (
          <option key={option} value={option}>
            {readable(option)}
          </option>
        ))}
      </select>
    </label>
  );
}

// Tables -------------------------------------------------------------------------------

export function TableEditor({
  table,
  rows,
  onChange,
  rowStatus,
  statusLabel = "Status",
}: {
  table: TableName;
  rows: Row[];
  onChange: (rows: Row[]) => void;
  /** Optional read-only column computed from each row's entered values. */
  rowStatus?: (row: Row) => React.ReactNode;
  statusLabel?: string;
}) {
  const { title, columns } = TABLES[table];
  const shortTitle = title.split(" (")[0];

  function update(index: number, key: string, value: string) {
    onChange(rows.map((row, i) => (i === index ? { ...row, [key]: value } : row)));
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full min-w-[44rem] text-left text-sm">
          <caption className="border-b border-line bg-panel-raised px-3 py-2 text-left">
            <span className="font-semibold text-ink">{title}</span>{" "}
            <span className="text-xs text-muted">
              · {rows.length} {rows.length === 1 ? "row" : "rows"}
            </span>
          </caption>
          <thead>
            <tr className="border-b border-line text-xs text-muted">
              {columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className={`px-2 py-2 font-medium ${column.kind === "number" ? "text-right" : ""}`}
                >
                  {column.label}
                </th>
              ))}
              {rowStatus && (
                <th scope="col" className="px-2 py-2 font-medium">
                  {statusLabel}
                </th>
              )}
              <th scope="col" className="px-2 py-2">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={columns.length + (rowStatus ? 2 : 1)} className="px-3 py-3 text-xs text-muted">
                  No rows. Add one below.
                </td>
              </tr>
            )}
            {rows.map((row, index) => (
              <tr key={index} className="border-b border-line/60 last:border-0 hover:bg-panel-raised/50">
                {columns.map((column) => {
                  const label = `${shortTitle}: ${column.label}, row ${index + 1}`;
                  return (
                    <td key={column.key} className="px-1.5 py-1">
                      {column.kind === "select" ? (
                        <select
                          aria-label={label}
                          value={row[column.key]}
                          onChange={(event) => update(index, column.key, event.target.value)}
                          className={inputClass}
                        >
                          {column.options!.map((option) => (
                            <option key={option} value={option}>
                              {readable(option)}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          aria-label={label}
                          type="text"
                          inputMode={column.kind === "number" ? "numeric" : undefined}
                          value={row[column.key]}
                          onChange={(event) => update(index, column.key, event.target.value)}
                          className={`${inputClass} ${column.kind === "number" ? "text-right font-mono" : ""}`}
                        />
                      )}
                    </td>
                  );
                })}
                {rowStatus && <td className="px-2 py-1">{rowStatus(row)}</td>}
                <td className="px-1.5 py-1">
                  <button
                    type="button"
                    onClick={() => onChange(rows.filter((_, i) => i !== index))}
                    aria-label={`Remove row ${index + 1} from ${shortTitle}`}
                    className="rounded-md px-2 py-1 text-xs text-bad-ink hover:bg-red-500/10"
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button type="button" onClick={() => onChange([...rows, emptyRow(table)])} className={`${ghostButton} w-fit`}>
        Add row to {shortTitle.toLowerCase()}
      </button>
    </div>
  );
}
