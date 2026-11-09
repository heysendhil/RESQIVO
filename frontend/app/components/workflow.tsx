import type { Stage, StageStatus } from "@/lib/workflow";

export const STAGE_STATUS: Record<
  StageStatus,
  { label: string; dot: string; text: string; bar: string }
> = {
  pending: { label: "Waiting", dot: "border-line bg-panel-raised", text: "text-muted", bar: "bg-line" },
  running: { label: "In progress", dot: "border-accent bg-accent/30", text: "text-accent", bar: "bg-accent/60" },
  complete: { label: "Completed", dot: "border-emerald-400 bg-emerald-400", text: "text-ok-ink", bar: "bg-emerald-400/70" },
  attention: { label: "Needs attention", dot: "border-amber-400 bg-amber-400", text: "text-warn-ink", bar: "bg-amber-400/70" },
  skipped: { label: "Skipped", dot: "border-line bg-transparent", text: "text-muted", bar: "bg-line" },
  failed: { label: "Failed", dot: "border-red-400 bg-red-400", text: "text-bad-ink", bar: "bg-red-400/70" },
  not_configured: { label: "Not configured", dot: "border-slate-400 bg-transparent", text: "text-muted", bar: "bg-slate-500/50" },
  required: { label: "Waiting for review", dot: "border-amber-400 bg-transparent", text: "text-warn-ink", bar: "bg-amber-400/40" },
};

/** The agentic workflow pipeline. Each stage's state is taken from the latest
 * /draft-plan request; durations and scores are not shown because the API
 * does not report them. */
export default function WorkflowTracker({
  stages,
  error,
}: {
  stages: Stage[];
  error?: string;
}) {
  return (
    <section
      aria-labelledby="workflow-heading"
      className="flex flex-col gap-4 rounded-lg border border-line bg-panel p-4"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id="workflow-heading" className="text-sm font-semibold uppercase tracking-wider text-ink">
          Agentic workflow pipeline
        </h3>
        <p className="text-xs text-muted">
          Stages reflect the latest draft run; none is marked complete without an API result.
        </p>
      </div>
      <ol className="grid gap-2 md:grid-cols-5 md:gap-0">
        {stages.map((stage, index) => {
          const status = STAGE_STATUS[stage.status];
          return (
            <li
              key={stage.id}
              data-stage={stage.id}
              data-status={stage.status}
              className="relative flex gap-3 rounded-md border border-line bg-canvas/50 p-3 md:flex-col md:gap-2 md:rounded-none md:border-y md:border-r-0 md:border-l-0 md:first:rounded-l-md md:first:border-l md:last:rounded-r-md md:last:border-r"
            >
              <div className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className={`inline-flex size-6 shrink-0 items-center justify-center rounded-full border-2 font-mono text-[0.65rem] font-bold ${status.dot} ${
                    stage.status === "complete" ? "text-slate-950" : "text-ink"
                  }`}
                >
                  {index + 1}
                </span>
                <span aria-hidden="true" className={`hidden h-0.5 flex-1 rounded md:block ${status.bar}`} />
              </div>
              <div className="flex flex-col gap-0.5">
                <p className="text-sm font-semibold text-ink">{stage.label}</p>
                <p className={`text-xs font-semibold ${status.text}`}>{status.label}</p>
                <p className="text-xs text-muted">{stage.detail}</p>
              </div>
            </li>
          );
        })}
      </ol>
      {error && (
        <p role="note" className="text-xs text-warn-ink">
          Last draft request failed: {error}
        </p>
      )}
    </section>
  );
}
