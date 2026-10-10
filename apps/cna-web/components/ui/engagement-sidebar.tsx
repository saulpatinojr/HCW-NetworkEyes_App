"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";

// WAI-01 / W3C-02: aria-hidden on decorative icons; labels conveyed by adjacent text or Link aria-label
const icon = (d: string) => (
  <svg aria-hidden="true" focusable="false" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d={d} />
  </svg>
);

interface NavItem {
  path: string;
  label: string;
  icon: React.ReactNode;
}

interface NavGroup {
  num: number;
  label: string;
  items: NavItem[];
}

// ── Sequential assessment journey (Phase F) ──────────────────────────────────
const NAV_GROUPS: NavGroup[] = [
  {
    num: 1,
    label: "Discovery & Ingestion",
    items: [
      { path: "/discovery",   label: "Ingestion Hub", icon: icon("M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z") },
      { path: "/connections", label: "Connections",   icon: icon("M13 10V3L4 14h7v7l9-11h-7z") },
      { path: "/documents",   label: "Documents",     icon: icon("M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z") },
      { path: "/inventory",   label: "Inventory",     icon: icon("M4 6h16M4 10h16M4 14h16M4 18h16") },
    ],
  },
  {
    num: 2,
    label: "Executive Dashboard",
    items: [
      { path: "",              label: "Overview",     icon: icon("M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6") },
      { path: "/presentation", label: "Presentation", icon: icon("M8 13v-1m4 1v-3m4 3V8M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z") },
    ],
  },
  {
    num: 3,
    label: "Traffic Matrix",
    items: [
      { path: "/traffic",  label: "Traffic Matrix", icon: icon("M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4") },
      { path: "/findings", label: "Findings",       icon: icon("M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z") },
    ],
  },
  {
    num: 4,
    label: "FinOps",
    items: [
      { path: "/finops", label: "Cost Analysis", icon: icon("M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z") },
    ],
  },
  {
    num: 5,
    label: "Observability & Resilience",
    items: [
      { path: "/resilience", label: "Resilience", icon: icon("M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z") },
    ],
  },
  {
    num: 6,
    label: "Future State",
    items: [
      { path: "/diagram", label: "Diagram", icon: icon("M7 8h10M7 12h7m-7 4h10M5 4h14a2 2 0 012 2v12a2 2 0 01-2 2H5a2 2 0 01-2-2V6a2 2 0 012-2z") },
    ],
  },
  {
    num: 7,
    label: "Copilot",
    items: [
      { path: "/copilot", label: "Copilot Chat", icon: icon("M8 10h.01M12 10h.01M16 10h.01M21 12c0 4.418-4.03 8-9 8a9.86 9.86 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z") },
      { path: "/analysis", label: "AI Analysis", icon: icon("M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z") },
    ],
  },
  {
    num: 8,
    label: "Report",
    items: [
      { path: "/report",              label: "Book Mode",    icon: icon("M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253") },
      { path: "/deliverables",        label: "Assessments",  icon: icon("M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4") },
      { path: "/client-deliverables", label: "Deliverables", icon: icon("M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4") },
    ],
  },
];

const STORAGE_KEY = "cna-sidebar-collapsed";

// The collapsed flag lives in localStorage and is read through
// useSyncExternalStore: the server snapshot is always "expanded", so the
// first client render matches the HTML and the stored preference applies on
// hydration without a setState-in-effect (react-hooks/set-state-in-effect).
const collapsedListeners = new Set<() => void>();

function subscribeCollapsed(callback: () => void) {
  collapsedListeners.add(callback);
  window.addEventListener("storage", callback);
  return () => {
    collapsedListeners.delete(callback);
    window.removeEventListener("storage", callback);
  };
}

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "true";
  } catch {
    return false; // localStorage not available
  }
}

function writeCollapsed(next: boolean) {
  try {
    localStorage.setItem(STORAGE_KEY, String(next));
  } catch {
    /* ignore */
  }
  collapsedListeners.forEach((listener) => listener());
}

export function EngagementSidebar({ engagementId }: { engagementId: string }) {
  const pathname = usePathname();
  const base = `/engagements/${engagementId}`;

  const isCollapsed = useSyncExternalStore(subscribeCollapsed, readCollapsed, () => false);

  function toggle() {
    writeCollapsed(!isCollapsed);
  }

  return (
    // WAI-17: aria-label distinguishes this landmark from the header nav
    <aside
      aria-label="Engagement navigation"
      className={[
        "relative flex-shrink-0 transition-all duration-200",
        isCollapsed ? "w-[3.25rem]" : "w-52",
      ].join(" ")}
    >
      <div
        className={[
          /* glass panel */
          "glass sticky top-20 flex flex-col overflow-hidden",
          isCollapsed ? "w-[3.25rem]" : "w-52",
        ].join(" ")}
      >
        {/* ── Toggle row ── */}
        <div className="flex items-center justify-between border-b border-navy-100/40 px-2 py-2.5 dark:border-navy-700/40">
          {!isCollapsed && (
            <span className="label-caps pl-1 text-navy-400 dark:text-navy-300" aria-hidden="true">
              Navigation
            </span>
          )}
          {/* WAI-02: aria-label replaces title; aria-expanded + aria-controls communicate state */}
          <button
            type="button"
            onClick={toggle}
            aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            {...{ "aria-expanded": !isCollapsed }}
            aria-controls="engagement-nav"
            className={[
              "flex h-7 w-7 items-center justify-center rounded-lg text-navy-300 transition-colors hover:bg-teal-50 hover:text-teal-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-1 dark:text-navy-500 dark:hover:bg-teal-900/30 dark:hover:text-teal-400",
              isCollapsed ? "mx-auto" : "ml-auto",
            ].join(" ")}
          >
            {/* W3C-02: decorative chevron SVG hidden from AT */}
            {isCollapsed ? (
              <svg aria-hidden="true" focusable="false" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
            ) : (
              <svg aria-hidden="true" focusable="false" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
              </svg>
            )}
          </button>
        </div>

        {/* WAI-17: id matches aria-controls on toggle button; aria-label names this nav region */}
        <nav id="engagement-nav" aria-label="Engagement sections" className="flex flex-col gap-0.5 overflow-y-auto p-1.5">
          {NAV_GROUPS.map((group, gi) => (
            <div key={group.num} className="flex flex-col gap-0.5">
              {/* ── Numbered journey group header ── */}
              {isCollapsed ? (
                gi > 0 && <div className="mx-2 my-1 border-t border-navy-100/40 dark:border-navy-700/40" aria-hidden="true" />
              ) : (
                <p
                  className={[
                    "label-caps truncate px-2 text-navy-400 dark:text-navy-300",
                    gi === 0 ? "pt-1.5" : "pt-3",
                  ].join(" ")}
                  title={`${group.num}. ${group.label}`}
                >
                  {group.num}&nbsp;·&nbsp;{group.label}
                </p>
              )}
              {group.items.map((item) => {
                const href = `${base}${item.path}`;
                const isActive =
                  item.path === ""
                    ? pathname === base
                    : pathname === href || pathname.startsWith(href + "/");

                return (
                  // WAI-01: When collapsed, icon is the only visible content — aria-label provides the name.
                  // When expanded, the visible text label makes aria-label redundant (omit to avoid duplication).
                  <Link
                    key={item.path}
                    href={href}
                    aria-label={isCollapsed ? item.label : undefined}
                    aria-current={isActive ? "page" : undefined}
                    className={[
                      "flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-1",
                      isActive
                        ? "nav-active font-semibold"
                        : "text-navy-500 hover:bg-navy-50/60 hover:text-navy-800 dark:text-navy-300 dark:hover:bg-navy-800/40 dark:hover:text-navy-100",
                    ].join(" ")}
                  >
                    <span className="flex-shrink-0" aria-hidden="true">{item.icon}</span>
                    {!isCollapsed && (
                      <span className="truncate">{item.label}</span>
                    )}
                    {isActive && !isCollapsed && (
                      <span className="ml-auto h-1.5 w-1.5 flex-shrink-0 rounded-full bg-teal-500" aria-hidden="true" />
                    )}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
      </div>
    </aside>
  );
}
