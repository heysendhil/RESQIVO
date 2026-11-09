// Presentational components for API results. Everything from the API is
// rendered as plain text (React escapes it); nothing is rendered as HTML.

import type {
  AnswerResponse,
  Citation,
  FieldError,
  InsufficientReason,
  PlanReview,
  ResourceAllocation,
  ValidationResult,
} from "@/lib/api";
import { citationPage } from "@/lib/evidence";
import { externalUrl } from "@/lib/safe-url";

export const DRAFT_LABEL = "Draft — requires human review";
export const AUTHORITATIVE_LABEL = "Deterministic validation (authoritative)";
export const AI_LABEL = "AI-generated — not validated guidance";
export const NOT_DISPATCHED =
  "Nothing has been dispatched, booked or requested. A qualified person must " +
  "review any plan before use.";

/** Shown wherever a draft plan is requested or displayed. */
export const SAFETY_DISCLAIMER =
  "This is a draft proposal for human review. No resources have been dispatched, " +
  "booked or requested, and no one has been contacted. A \u2018draft_valid\u2019 status " +
  "means only that the proposal passed RESQIVO\u2019s deterministic validation rules; " +
  "it does not mean the plan is operationally safe, optimal, or appropriate for " +
  "real-world emergency response. RESQIVO answers support simulated planning and " +
  "education only. They do not replace emergency services, public authorities, or " +
  "official instructions.";

/** Compare notices ignoring quotation-mark style, so the backend's copy of the
 * disclaimer is not shown twice. */
export function sameNotice(a: string, b: string): boolean {
  const plain = (text: string) => text.replace(/[\u2018\u2019\u201c\u201d"']/g, "'").trim();
  return plain(a) === plain(b);
}

const INSUFFICIENT_MESSAGES: Record<InsufficientReason, string> = {
  knowledge_base_empty: "The knowledge base is empty, so no guidance is available.",
  no_relevant_passages: "No sufficiently relevant guidance was found.",
  model_reported_insufficient_evidence:
    "The retrieved guidance does not contain enough information to answer.",
  answer_not_grounded:
    "The generated answer could not be grounded in the retrieved guidance, so it " +
    "was withheld.",
};

export type Tone = "ok" | "bad" | "draft" | "info" | "neutral" | "accent";

const TONES: Record<Tone, string> = {
  ok: "border-emerald-500/40 bg-emerald-500/10 text-ok-ink",
  bad: "border-red-500/40 bg-red-500/10 text-bad-ink",
  draft: "border-amber-500/40 bg-amber-500/10 text-warn-ink",
  info: "border-sky-500/40 bg-sky-500/10 text-info-ink",
  neutral: "border-line bg-panel-raised text-muted",
  accent: "border-accent/40 bg-accent/10 text-accent",
};

export function Badge({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return (
    <span
      className={`inline-flex w-fit items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${TONES[tone]}`}
    >
      {children}
    </span>
  );
}

/** A labelled block that separates one kind of result from another. */
export function ResultBlock({
  title,
  badge,
  tone = "neutral",
  children,
}: {
  title: string;
  badge?: React.ReactNode;
  tone?: "neutral" | "authoritative" | "ai";
  children: React.ReactNode;
}) {
  const edge = {
    neutral: "border-l-line",
    authoritative: "border-l-emerald-400/70",
    ai: "border-l-sky-400/70",
  }[tone];
  return (
    <div className={`flex flex-col gap-2 rounded-lg border border-line border-l-4 ${edge} bg-canvas/40 p-3`}>
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-sm font-semibold text-ink">{title}</h4>
        {badge}
      </div>
      {children}
    </div>
  );
}

export function ErrorAlert({
  message,
  fieldErrors = [],
}: {
  message: string;
  fieldErrors?: FieldError[];
}) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm text-warn-ink"
    >
      <p className="font-semibold">The request could not be completed</p>
      <p className="mt-1 break-words">{message}</p>
      {fieldErrors.length > 0 && (
        <ul className="mt-2 list-disc pl-5 font-mono text-xs">
          {fieldErrors.map((error, index) => (
            <li key={`${error.field}-${index}`}>
              <span className="font-semibold">{error.field}</span>: {error.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function Loading({ children }: { children: React.ReactNode }) {
  return (
    <p role="status" className="flex items-center gap-2 text-sm text-muted">
      <span
        aria-hidden="true"
        className="inline-block size-3 animate-spin rounded-full border-2 border-accent/30 border-t-accent motion-reduce:animate-none"
      />
      {children}
    </p>
  );
}

export function ValidationResultView({
  result,
  title = AUTHORITATIVE_LABEL,
}: {
  result: ValidationResult;
  title?: string;
}) {
  return (
    <ResultBlock
      title={title}
      tone="authoritative"
      badge={
        <Badge tone={result.valid ? "ok" : "bad"}>
          {result.valid ? "Passed configured rules" : "Rule violations found"}
        </Badge>
      }
    >
      {result.violations.length === 0 ? (
        <p className="text-sm text-muted">No configured constraint violations were found.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {result.violations.map((violation, index) => (
            <li
              key={`${violation.code}-${violation.entity_id}-${index}`}
              className="rounded-md border border-red-500/25 bg-red-500/5 p-3 text-sm"
            >
              <p>
                <span className="font-mono font-semibold text-bad-ink">{violation.code}</span>{" "}
                <span className="text-muted">
                  on <span className="font-mono text-ink">{violation.entity_id}</span>
                </span>
              </p>
              <p className="mt-1">{violation.message}</p>
              {Object.keys(violation.details).length > 0 && (
                <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 font-mono text-xs">
                  {Object.entries(violation.details).map(([key, value]) => (
                    <div key={key} className="contents">
                      <dt className="text-muted">{key}</dt>
                      <dd>{value.toLocaleString()}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted">
        Passing means only that RESQIVO&apos;s configured rules pass. It is not
        evidence that a plan is operationally safe.
      </p>
    </ResultBlock>
  );
}

function CitationItem({ citation }: { citation: Citation }) {
  const href = externalUrl(citation.url);
  const page = citationPage(citation);
  return (
    <li className="rounded-md border border-line bg-panel-raised/60 p-3 text-xs">
      <p className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-accent/15 px-1.5 py-0.5 font-mono font-semibold text-accent">
          [{citation.label}]
        </span>
        {href ? (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="font-medium text-ink underline decoration-accent/60 underline-offset-2 hover:decoration-accent"
          >
            {citation.title}
          </a>
        ) : (
          <span className="font-medium text-ink">{citation.title}</span>
        )}
        {citation.synthetic && <Badge tone="draft">Synthetic source</Badge>}
      </p>
      <p className="mt-1 text-muted">
        {citation.publisher} · source <span className="font-mono">{citation.source_id}</span>
        {page !== null && (
          <>
            {" "}
            · page <span className="font-mono">{page}</span>
          </>
        )}
        {!href && (
          <>
            {" "}
            · <span className="font-mono break-all">{citation.url}</span>
          </>
        )}
      </p>
    </li>
  );
}

export function AnswerView({
  answer,
  title = "Grounded answer",
}: {
  answer: AnswerResponse;
  title?: string;
}) {
  return (
    <ResultBlock title={title} tone="ai" badge={<Badge tone="info">{AI_LABEL}</Badge>}>
      {answer.status === "answered" && answer.answer ? (
        <>
          <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">
            {answer.answer}
          </p>
          <section aria-label="Evidence citations" className="flex flex-col gap-2">
            <h5 className="text-xs font-semibold uppercase tracking-wider text-muted">
              Evidence citations
            </h5>
            <p className="text-xs text-muted">
              Retrieved passages are untrusted reference material. Verify against
              official sources before relying on them.
            </p>
            <ul className="flex flex-col gap-2">
              {answer.citations.map((citation) => (
                <CitationItem key={citation.label} citation={citation} />
              ))}
            </ul>
          </section>
        </>
      ) : (
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <Badge tone="neutral">Insufficient evidence</Badge>
          <span>
            {answer.reason
              ? INSUFFICIENT_MESSAGES[answer.reason] ?? "No grounded answer is available."
              : "No grounded answer is available."}
          </span>
        </p>
      )}
      <p className="text-xs text-muted">{answer.notice}</p>
    </ResultBlock>
  );
}

export function AllocationTable({
  allocations,
  caption,
}: {
  allocations: ResourceAllocation[];
  caption: string;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="w-full min-w-[28rem] text-left text-xs">
        <caption className="border-b border-line bg-panel-raised px-3 py-2 text-left text-sm font-semibold text-ink">
          {caption}
        </caption>
        <thead className="text-muted">
          <tr className="border-b border-line">
            <th scope="col" className="px-3 py-2 font-medium">Allocation</th>
            <th scope="col" className="px-3 py-2 font-medium">Resource</th>
            <th scope="col" className="px-3 py-2 font-medium">Destination</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">Quantity</th>
          </tr>
        </thead>
        <tbody className="font-mono">
          {allocations.map((a, index) => (
            <tr key={`${a.allocation_id}-${index}`} className="border-b border-line/60 last:border-0">
              <td className="px-3 py-1.5">{a.allocation_id}</td>
              <td className="px-3 py-1.5">{a.resource_id}</td>
              <td className="px-3 py-1.5">{a.destination_id}</td>
              <td className="px-3 py-1.5 text-right">{a.quantity_allocated.toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PlanReviewView({
  review,
  planCaption,
}: {
  review: PlanReview;
  planCaption: string;
}) {
  return (
    <div className="flex flex-col gap-3">
      <AllocationTable allocations={review.final_plan.allocations} caption={planCaption} />
      <p className="text-sm">
        Corrections attempted: {review.correction_attempts} of at most{" "}
        {review.max_correction_attempts}.{" "}
        {review.corrected
          ? "The model's corrected allocations passed validation."
          : review.correction_attempts > 0
            ? "Corrections did not resolve every violation."
            : "No correction was needed or possible."}
      </p>
      {review.uncorrectable_codes.length > 0 && (
        <p className="text-sm">
          Problems in the supplied facts that allocation changes cannot fix:{" "}
          <span className="font-mono">{review.uncorrectable_codes.join(", ")}</span>
        </p>
      )}
      <ValidationResultView result={review.original_validation} title="Validation before correction" />
      <ValidationResultView
        result={review.final_validation}
        title={`${AUTHORITATIVE_LABEL}: final result`}
      />
    </div>
  );
}
