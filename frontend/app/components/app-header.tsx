import HealthStatus from "./health-status";
import ThemeToggle from "./theme-toggle";

/** The RESQIVO mark: a shield (protection) carrying a heartbeat (life), with a
 * red dot for the live moment. Colours follow the light and dark themes. */
export function BrandMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 64 64" className="size-10 shrink-0" fill="none">
      <path d="M32 4 L54 12 V30 C54 45 44 55 32 60 C20 55 10 45 10 30 V12 Z" className="fill-accent" />
      <path
        d="M15 33 H23 L27 23 L33 44 L37.5 29 L40.5 33 H49"
        className="stroke-on-accent"
        strokeWidth="4.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="49" cy="33" r="3.2" className="fill-red-500" />
    </svg>
  );
}

/** Top bar: identity, the simulation label and the real /health check. */
export default function AppHeader({ alerts }: { alerts?: React.ReactNode }) {
  return (
    <header className="sticky top-0 z-20 shrink-0 border-b border-line bg-panel/95 backdrop-blur lg:static">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-2.5 sm:px-6">
        <div className="flex items-center gap-3">
          <BrandMark />
          <div className="flex flex-col leading-tight">
            <p className="text-base font-bold tracking-[0.2em] text-ink">RESQIVO</p>
            <p className="text-xs text-muted">Every Second. Every Life.</p>
          </div>
          <span aria-hidden="true" className="mx-1 h-8 w-px bg-line" />
          <h1 className="text-sm font-semibold text-ink">
            Emergency Operations Center
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <p className="inline-flex items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-xs font-medium text-warn-ink">
            <span className="rounded bg-amber-400/20 px-1.5 py-px font-bold uppercase tracking-wider text-warn-ink">
              Simulation
            </span>
            Simulated scenario: synthetic data for planning and education only
          </p>
          {alerts}
          <HealthStatus />
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
