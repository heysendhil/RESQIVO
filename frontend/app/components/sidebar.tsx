"use client";

import { useEffect, useState } from "react";

/** Every item links to a section that exists on the page and works. Reports
 * has no backend support, so it is listed as unavailable text, not a link. */
type IconName = "grid" | "flow" | "alert" | "phone" | "boxes" | "home" | "book" | "chat" | "spark" | "shield";

export interface NavItem {
  id: string;
  label: string;
  icon: IconName;
}

export const NAV_GROUPS: readonly { label: string; items: readonly NavItem[] }[] = [
  {
    label: "Operations",
    items: [
      { id: "command-center", label: "Dashboard", icon: "grid" },
      { id: "workflow", label: "AI Workflow", icon: "flow" },
      { id: "scenario", label: "Incidents", icon: "alert" },
      { id: "calls", label: "Call Intake", icon: "phone" },
    ],
  },
  {
    label: "Logistics",
    items: [
      { id: "resources", label: "Resources", icon: "boxes" },
      { id: "shelters", label: "Shelters", icon: "home" },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { id: "knowledge", label: "Knowledge Base", icon: "book" },
      { id: "ask", label: "Ask RESQIVO", icon: "chat" },
    ],
  },
  {
    label: "Planning",
    items: [
      { id: "response-plan", label: "Draft Plans", icon: "spark" },
      { id: "validation", label: "Review", icon: "shield" },
    ],
  },
];

export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((group) => [...group.items]);

const ICONS: Record<IconName, string> = {
  grid: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
  flow: "M5 6h4v4H5zM15 14h4v4h-4zM9 8h3a2 2 0 0 1 2 2v4a2 2 0 0 0 2 2",
  alert: "M12 4 3 20h18L12 4zM12 10v4M12 17v.5",
  phone: "M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a1 1 0 0 1-1 1A16 16 0 0 1 4 5a1 1 0 0 1 1-1z",
  boxes: "M3 7l9-4 9 4-9 4-9-4zM3 7v10l9 4 9-4V7M12 11v10",
  home: "M4 11 12 4l8 7M6 10v10h12V10M10 20v-5h4v5",
  book: "M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2V5zM4 19a2 2 0 0 1 2-2h13",
  chat: "M4 5h16v11H9l-5 4V5zM8 9h8M8 12h5",
  spark: "M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6",
  shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3zM8.5 12l2.5 2.5 4.5-5",
};

function Icon({ name }: { name: IconName }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="size-4 shrink-0" fill="none">
      <path d={ICONS[name]} stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Highlight the section currently in view, where the browser supports it. */
function useActiveSection(): string {
  const [active, setActive] = useState<string>(NAV_ITEMS[0].id);
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: "-20% 0px -70% 0px" },
    );
    for (const item of NAV_ITEMS) {
      const element = document.getElementById(item.id);
      if (element) observer.observe(element);
    }
    return () => observer.disconnect();
  }, []);
  return active;
}

export default function Sidebar() {
  const active = useActiveSection();
  return (
    <nav
      aria-label="Dashboard sections"
      className="border-b border-line bg-panel lg:sticky lg:top-0 lg:flex lg:h-screen lg:w-56 lg:shrink-0 lg:flex-col lg:overflow-y-auto lg:border-r lg:border-b-0"
    >
      <div className="flex gap-4 overflow-x-auto px-3 py-2 lg:shrink-0 lg:flex-col lg:gap-5 lg:overflow-visible lg:px-3 lg:py-5">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="flex shrink-0 items-center gap-1 lg:flex-col lg:items-stretch">
            <p className="hidden px-3 pb-1 text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-muted/80 lg:block">
              {group.label}
            </p>
            <ul className="flex gap-1 lg:flex-col">
              {group.items.map((item) => {
                const current = item.id === active;
                return (
                  <li key={item.id} className="shrink-0">
                    <a
                      href={`#${item.id}`}
                      aria-current={current ? "location" : undefined}
                      className={`flex items-center gap-2.5 whitespace-nowrap rounded-md border-l-2 px-3 py-1.5 text-sm transition-colors ${
                        current
                          ? "border-accent bg-accent/10 font-medium text-accent"
                          : "border-transparent text-muted hover:bg-panel-raised hover:text-ink"
                      }`}
                    >
                      <Icon name={item.icon} />
                      {item.label}
                    </a>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
      <div className="hidden flex-col gap-2 px-6 pb-5 text-xs leading-relaxed text-muted lg:mt-auto lg:flex">
        <p>
          <span className="font-medium text-ink">Reports</span> — not available yet: the
          backend has no reporting endpoint.
        </p>
        <p>Decision support for human review. Nothing is dispatched.</p>
      </div>
    </nav>
  );
}
