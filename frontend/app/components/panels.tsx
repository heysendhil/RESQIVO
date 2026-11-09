"use client";

import { useId, useState } from "react";

import {
  LIMITS,
  askQuestion,
  draftPlan,
  reviewPlan,
  validatePlan,
  type AnswerResponse,
  type DraftPlanResponse,
  type InsufficientInformationReason,
  type ReviewResponse,
  type ValidationResult,
} from "@/lib/api";
import type { RequestState } from "@/lib/use-request";
import { toDraftRequest, toPlan, type Workspace } from "@/lib/workspace";

import {
  AnswerView,
  Badge,
  DRAFT_LABEL,
  ErrorAlert,
  Loading,
  NOT_DISPATCHED,
  PlanReviewView,
  ResultBlock,
  SAFETY_DISCLAIMER,
  sameNotice,
  ValidationResultView,
} from "./results";

/** The request controls a controlled panel receives from the dashboard. */
export interface RequestControl<T> {
  state: RequestState<T>;
  run: (call: (signal: AbortSignal) => Promise<T>) => Promise<void>;
}

export const primaryButton =
  "inline-flex w-fit items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent shadow-sm hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-50";

export function Panel({
  id,
  title,
  description,
  eyebrow,
  children,
}: {
  id: string;
  title: string;
  description: string;
  eyebrow?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-heading`}
      className="flex scroll-mt-24 flex-col gap-4 rounded-xl border border-line bg-panel p-5"
    >
      <div className="flex flex-col gap-1">
        {eyebrow}
        <h3 id={`${id}-heading`} className="text-base font-semibold text-ink">
          {title}
        </h3>
        <p className="text-sm text-muted">{description}</p>
      </div>
      {children}
    </section>
  );
}

function Outcome<T>({
  state,
  loadingText,
  children,
}: {
  state: RequestState<T>;
  loadingText: string;
  children: (data: T) => React.ReactNode;
}) {
  return (
    <div aria-live="polite" aria-busy={state.status === "loading"} className="flex flex-col gap-3">
      {state.status === "loading" && <Loading>{loadingText}</Loading>}
      {state.status === "error" && (
        <ErrorAlert message={state.message} fieldErrors={state.fieldErrors} />
      )}
      {state.status === "success" && children(state.data)}
    </div>
  );
}

function QuestionField({
  value,
  onChange,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  label: string;
}) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1 text-sm">
      <label htmlFor={id} className="font-medium text-ink">
        {label}
      </label>
      <textarea
        id={id}
        value={value}
        maxLength={LIMITS.questionChars}
        rows={2}
        aria-describedby={`${id}-count`}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink placeholder:text-muted/70 focus:border-accent"
      />
      <span id={`${id}-count`} className="text-xs text-muted">
        {value.length} / {LIMITS.questionChars} characters
      </span>
    </div>
  );
}

// Validate -------------------------------------------------------------------------

export function ValidatePanel({
  workspace,
  request,
}: {
  workspace: Workspace;
  request: RequestControl<ValidationResult>;
}) {
  const { state, run } = request;
  return (
    <Panel
      id="validate"
      title="Validate allocations"
      description="Checks the workspace's resources, shelters and allocations against RESQIVO's deterministic rules. No AI is involved."
      eyebrow={<Badge tone="ok">Deterministic · authoritative</Badge>}
    >
      <button
        type="button"
        className={primaryButton}
        disabled={state.status === "loading"}
        onClick={() => void run((signal) => validatePlan(toPlan(workspace), signal))}
      >
        {state.status === "loading" ? "Validating…" : "Validate plan"}
      </button>
      <Outcome state={state} loadingText="Running deterministic validation…">
        {(result) => (
          <>
            <ValidationResultView result={result} />
            <p className="text-xs text-muted">{NOT_DISPATCHED}</p>
          </>
        )}
      </Outcome>
    </Panel>
  );
}

// Draft --------------------------------------------------------------------------------

const INSUFFICIENT_INFORMATION: Record<InsufficientInformationReason, string> = {
  no_affected_population: "The scenario reports no affected population.",
  no_available_resources: "No resource has any available stock.",
  no_shelters: "No shelters were supplied.",
};

function DraftResult({ draft }: { draft: DraftPlanResponse }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="draft">{DRAFT_LABEL}</Badge>
        {draft.status === "draft_valid" && (
          <Badge tone="ok">Draft passed rule-based validation</Badge>
        )}
        {draft.status === "draft_invalid" && (
          <Badge tone="bad">Draft failed rule-based validation</Badge>
        )}
        {draft.status === "insufficient_information" && (
          <Badge tone="neutral">Not enough information to draft</Badge>
        )}
      </div>
      {!sameNotice(draft.notice, SAFETY_DISCLAIMER) && (
        <p className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-warn-ink">
          {draft.notice}
        </p>
      )}
      {draft.status === "insufficient_information" && draft.reason && (
        <p className="text-sm">
          No draft was produced: {INSUFFICIENT_INFORMATION[draft.reason] ?? draft.reason}
        </p>
      )}
      {draft.plan_review && (
        <ResultBlock title="AI proposal" tone="ai" badge={<Badge tone="draft">Proposal only</Badge>}>
          <PlanReviewView
            review={draft.plan_review}
            planCaption="Proposed allocations (AI draft — not dispatched)"
          />
        </ResultBlock>
      )}
      <ValidationResultView
        result={draft.input_validation}
        title="Validation of the supplied facts (before drafting)"
      />
      {draft.guidance && (
        <AnswerView answer={draft.guidance} title="Guidance from retrieved sources" />
      )}
      {!draft.evidence_available && draft.status !== "insufficient_information" && (
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <Badge tone="neutral">No supporting evidence</Badge> The draft is based only on
          the workspace data.
        </p>
      )}
      {draft.limitations.length > 0 && (
        <div className="rounded-lg border border-line bg-canvas/40 p-3">
          <h4 className="text-sm font-semibold">Limitations</h4>
          <ul className="mt-1 list-disc pl-5 text-sm text-muted">
            {draft.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-xs text-muted">
        Request ID: <span className="font-mono text-ink">{draft.request_id}</span>
      </p>
    </div>
  );
}

export function DraftPanel({
  workspace,
  request,
}: {
  workspace: Workspace;
  request: RequestControl<DraftPlanResponse>;
}) {
  const { state, run } = request;
  return (
    <Panel
      id="draft"
      title="Draft a response plan"
      description="Asks the AI to propose allocations using only the workspace's resources and shelters. The proposal is then checked by the deterministic validator. Your workspace is never changed."
      eyebrow={<Badge tone="draft">AI proposal · requires human review</Badge>}
    >
      <p
        role="note"
        className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm leading-relaxed text-warn-ink"
      >
        <strong className="font-semibold">Safety notice.</strong> {SAFETY_DISCLAIMER}
      </p>
      <button
        type="button"
        className={primaryButton}
        disabled={state.status === "loading"}
        onClick={() => void run((signal) => draftPlan(toDraftRequest(workspace), signal))}
      >
        {state.status === "loading" ? "Drafting…" : "Generate draft plan"}
      </button>
      <Outcome state={state} loadingText="Drafting and validating a proposal… this can take a while.">
        {(draft) => <DraftResult draft={draft} />}
      </Outcome>
    </Panel>
  );
}

// Review ---------------------------------------------------------------------------

export function ReviewPanel({
  workspace,
  request,
}: {
  workspace: Workspace;
  request: RequestControl<ReviewResponse>;
}) {
  const [question, setQuestion] = useState(
    "Does this allocation plan respect stock and shelter constraints?",
  );
  const [includePlan, setIncludePlan] = useState(true);
  const { state, run } = request;
  const trimmed = question.trim();

  return (
    <Panel
      id="review"
      title="Review a plan"
      description="Answers your question from retrieved guidance and, if you include the plan, validates it with at most two allocation-only corrections proposed by the AI."
      eyebrow={<Badge tone="info">AI-assisted · validated</Badge>}
    >
      <QuestionField label="Review question" value={question} onChange={setQuestion} />
      <label className="flex items-center gap-2 text-sm text-ink">
        <input
          type="checkbox"
          checked={includePlan}
          onChange={(event) => setIncludePlan(event.target.checked)}
          className="size-4 accent-accent"
        />
        Include the workspace plan (resources, allocations, shelters)
      </label>
      <button
        type="button"
        className={primaryButton}
        disabled={state.status === "loading" || !trimmed}
        onClick={() =>
          void run((signal) => reviewPlan(trimmed, includePlan ? toPlan(workspace) : null, signal))
        }
      >
        {state.status === "loading" ? "Reviewing…" : "Review plan"}
      </button>
      <Outcome state={state} loadingText="Retrieving guidance and validating… this can take a while.">
        {(review) => (
          <div className="flex flex-col gap-4">
            <AnswerView answer={review.answer} />
            {review.plan_review ? (
              <PlanReviewView
                review={review.plan_review}
                planCaption="Allocations after AI correction (proposal — not dispatched)"
              />
            ) : (
              <p className="text-sm text-muted">No plan was included, so none was validated.</p>
            )}
            <p className="text-xs text-muted">{NOT_DISPATCHED}</p>
          </div>
        )}
      </Outcome>
    </Panel>
  );
}

// Ask -------------------------------------------------------------------------------

export function AskPanel({ request }: { request: RequestControl<AnswerResponse> }) {
  const [question, setQuestion] = useState("");
  const { state, run } = request;
  const trimmed = question.trim();

  return (
    <Panel
      id="ask-panel"
      title="Ask the knowledge base"
      description="Answers come only from retrieved passages and must cite them; otherwise RESQIVO says the evidence is insufficient."
      eyebrow={<Badge tone="info">Retrieval-grounded</Badge>}
    >
      <QuestionField label="Your question" value={question} onChange={setQuestion} />
      <button
        type="button"
        className={primaryButton}
        disabled={state.status === "loading" || !trimmed}
        onClick={() => void run((signal) => askQuestion(trimmed, signal))}
      >
        {state.status === "loading" ? "Searching…" : "Ask"}
      </button>
      <Outcome state={state} loadingText="Searching the knowledge base…">
        {(answer) => <AnswerView answer={answer} />}
      </Outcome>
    </Panel>
  );
}
