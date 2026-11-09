import type { Alert, AlertSeverity } from "@/lib/alerts";

const STYLE: Record<AlertSeverity, { label: string; dot: string; edge: string }> = {
  critical: { label: "Critical", dot: "bg-red-400", edge: "border-l-red-400/80" },
  warning: { label: "Warning", dot: "bg-amber-400", edge: "border-l-amber-400/80" },
  info: { label: "Info", dot: "bg-sky-400", edge: "border-l-sky-400/70" },
};

/** Alerts derived from the workspace values and the latest API results. */
export default function AlertsPanel({ alerts }: { alerts: Alert[] }) {
  const critical = alerts.filter((a) => a.severity === "critical").length;
  return (
    <section
      aria-labelledby="alerts-heading"
      className="flex flex-col gap-3 rounded-lg border border-line bg-panel p-4"
    >
      <div className="flex items-center justify-between gap-2">
        <h3 id="alerts-heading" className="text-sm font-semibold uppercase tracking-wider text-ink">
          Alerts
        </h3>
        <span className="font-mono text-xs text-muted">
          {alerts.length} total · {critical} critical
        </span>
      </div>
      <p className="text-xs text-muted">
        From the entered workspace values and the latest API results only.
      </p>
      {alerts.length === 0 ? (
        <p className="rounded-md border border-dashed border-line p-4 text-center text-xs text-muted">
          No alerts for the current workspace or latest results.
        </p>
      ) : (
        <ul className="flex max-h-80 flex-col gap-2 overflow-y-auto pr-1">
          {alerts.map((alert) => {
            const style = STYLE[alert.severity];
            return (
              <li
                key={alert.id}
                data-severity={alert.severity}
                className={`flex flex-col gap-0.5 rounded-md border border-line border-l-4 ${style.edge} bg-canvas/50 p-2.5`}
              >
                <p className="flex items-center gap-2 text-xs">
                  <span aria-hidden="true" className={`inline-block size-1.5 rounded-full ${style.dot}`} />
                  <span className="font-semibold uppercase tracking-wider text-muted">{style.label}</span>
                  <span className="text-muted">· {alert.source}</span>
                </p>
                <p className="text-sm font-medium text-ink">{alert.title}</p>
                <p className="text-xs text-muted">{alert.detail}</p>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
