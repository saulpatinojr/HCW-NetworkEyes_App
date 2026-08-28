"use client";

import { useState, useMemo } from "react";
import { EmptyState } from "@/components/ui/empty-state";

// ─── Resource label helpers ────────────────────────────────────────────────────

/**
 * Strip quoted resource names from a finding title to produce a grouping pattern.
 * "No Azure Firewall deployed in 'sub-conn-tst'" → "no azure firewall deployed in '…'"
 * "VNet 'my-vnet' has no DDoS Protection Plan"  → "vnet '…' has no ddos protection plan"
 */
function normalizeTitle(title: string): string {
  return title.replace(/'[^']+'/g, "'…'").toLowerCase().trim();
}

/**
 * Extract a human-readable resource identifier from a finding's title + description.
 * Priority: RG/ResourceName > ResourceName > first quoted string.
 *
 * Examples:
 *   title: "VNet 'my-vnet' has no DDoS Protection Plan"
 *   desc:  "VNet 'my-vnet' (eastus, RG: my-rg) has no..."
 *   → "my-rg / my-vnet"
 *
 *   title: "No Azure Firewall deployed in 'sub-conn-tst'"
 *   → "sub-conn-tst"
 *
 *   title: "Subnet 'snet-app' in 'vnet-hub' has no NSG"
 *   → "snet-app · vnet-hub"
 */
function extractResourceLabel(title: string, description: string): string {
  const quoted = [...title.matchAll(/'([^']+)'/g)].map((m) => m[1]);
  // Look for "RG: my-rg" or "(RG: my-rg," inside the description
  const rgMatch = description.match(/[,()\s]RG:\s*([^\s,.()']+)/i);
  const rg = rgMatch?.[1] ?? null;

  if (quoted.length === 0) return title.slice(0, 72);
  if (quoted.length === 1) {
    return rg && rg !== quoted[0] ? `${rg} / ${quoted[0]}` : quoted[0];
  }
  // Multiple resource names in the title (e.g. subnet + vnet)
  if (rg && rg !== quoted[0]) return `${rg} / ${quoted[0]}`;
  return quoted.slice(0, 2).join(" · ");
}

const styleKey = "style";
const makeStyle = (props: React.CSSProperties) => ({ [styleKey]: props }) as any;

/**
 * Within a group, deduplicate findings that share the same resource label
 * (true duplicates from repeated sync runs). Returns deduplicated entries with count.
 */
function deduplicateInstances(
  items: FindingItem[],
): { label: string; finding: FindingItem; count: number }[] {
  const seen = new Map<string, { finding: FindingItem; count: number }>();
  for (const f of items) {
    const label = extractResourceLabel(f.title, f.description);
    if (seen.has(label)) {
      seen.get(label)!.count++;
    } else {
      seen.set(label, { finding: f, count: 1 });
    }
  }
  return Array.from(seen.entries()).map(([label, { finding, count }]) => ({
    label,
    finding,
    count,
  }));
}

// ─── InstanceRow ─────────────────────────────────────────────────────────────

function InstanceRow({
  label,
  finding,
  count,
}: {
  label: string;
  finding: FindingItem;
  count: number;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="px-5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        {...{ "aria-expanded": open }}
        aria-controls={`finding-instance-${finding.id}`}
        className="flex w-full items-center gap-2 py-2.5 text-left hover:text-navy-800 dark:hover:text-navy-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-1"
      >
        <svg
          aria-hidden="true"
          focusable="false"
          className={`h-3.5 w-3.5 shrink-0 text-navy-500 transition-transform ${open ? "rotate-90" : ""}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
        <span className="min-w-0 flex-1 truncate font-mono text-xs font-semibold text-navy-400 dark:text-navy-300">
          {label}
        </span>
        {count > 1 && (
          <span className="shrink-0 rounded border border-navy-600/40 bg-navy-100/60 dark:bg-navy-700/40 px-1.5 py-0.5 text-[10px] font-semibold text-navy-400">
            ×{count} syncs
          </span>
        )}
      </button>
      {open && (
        <div id={`finding-instance-${finding.id}`} className="pb-4 pl-5">
          <p className="mb-2.5 text-sm leading-relaxed text-navy-400 dark:text-navy-300">{finding.description}</p>
          {finding.recommendation && (
            <div className="rounded-lg border border-teal-900/30 bg-teal-50 dark:bg-teal-900/10 px-3 py-2.5">
              <p className="text-xs leading-relaxed text-teal-700 dark:text-teal-300">
                <span className="font-semibold text-teal-800 dark:text-teal-200">Recommendation: </span>
                {finding.recommendation}
              </p>
              <a
                href={finding.msLearnUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-teal-700 dark:text-teal-400 hover:text-teal-700 dark:hover:text-teal-300 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500"
              >
                <svg aria-hidden="true" focusable="false" className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                </svg>
                MS Learn docs
                <span className="sr-only"> (opens in new tab)</span>
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

type Sev = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFORMATIONAL";

export interface FindingItem {
  id: string;
  title: string;
  category: string;
  severity: string;
  description: string;
  recommendation: string | null;
  aiGenerated: boolean;
  msLearnUrl: string;
}

const SEV_ORDER: Sev[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"];

const SEV_META: Record<Sev, { label: string; dot: string; border: string; badge: string; bar: string }> = {
  CRITICAL:      { label: "Critical", dot: "bg-red-500",    border: "border-l-red-500",    badge: "bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 border border-red-800/40",         bar: "bg-red-500" },
  HIGH:          { label: "High",     dot: "bg-orange-500", border: "border-l-orange-500", badge: "bg-orange-50 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 border border-orange-800/40", bar: "bg-orange-500" },
  MEDIUM:        { label: "Medium",   dot: "bg-yellow-400", border: "border-l-yellow-400", badge: "bg-yellow-50 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 border border-yellow-800/40", bar: "bg-yellow-400" },
  LOW:           { label: "Low",      dot: "bg-blue-400",   border: "border-l-blue-400",   badge: "bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border border-blue-800/40",       bar: "bg-blue-400" },
  INFORMATIONAL: { label: "Info",     dot: "bg-navy-400",   border: "border-l-navy-500",   badge: "bg-navy-100/60 dark:bg-navy-800/50 text-navy-400 dark:text-navy-300 border border-navy-700/40",       bar: "bg-navy-500" },
};

// Risk matrix constants
const CATEGORY_ORDER = [
  "Access Control", "Network Security", "Network Segmentation", "Network Protection",
  "Application Security", "Routing & Transit", "Encryption", "Compliance", "Configuration",
];

const MATRIX_SEV_DOT: Record<Sev, string> = {
  CRITICAL: "bg-red-500", HIGH: "bg-orange-500", MEDIUM: "bg-yellow-400",
  LOW: "bg-blue-400", INFORMATIONAL: "bg-navy-400",
};

interface Props {
  findings: FindingItem[];
}

export function FindingsClient({ findings }: Props) {
  const [sevFilter, setSevFilter] = useState<Sev | "ALL">("ALL");
  const [categoryFilter, setCategoryFilter] = useState("ALL");
  const [sourceFilter, setSourceFilter] = useState<"ALL" | "LIVE" | "AI">("ALL");
  const [expandedGroupKey, setExpandedGroupKey] = useState<string | null>(null);

  const liveCount = useMemo(() => findings.filter((f) => !f.aiGenerated).length, [findings]);
  const aiCount = useMemo(() => findings.filter((f) => f.aiGenerated).length, [findings]);

  // Unique issue group count across ALL findings (unfiltered) — shown in the header
  const totalGroups = useMemo(() => {
    const keys = new Set<string>();
    for (const f of findings) keys.add(`${f.severity}::${f.category}::${normalizeTitle(f.title)}`);
    return keys.size;
  }, [findings]);

  const sevCounts = useMemo(() => {
    const c = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0, INFORMATIONAL: 0 } as Record<Sev, number>;
    for (const f of findings) c[f.severity as Sev]++;
    return c;
  }, [findings]);

  const categories = useMemo(
    () => [...new Set(findings.map((f) => f.category))].sort((a, b) => {
      const ai = CATEGORY_ORDER.indexOf(a), bi = CATEGORY_ORDER.indexOf(b);
      if (ai === -1 && bi === -1) return a.localeCompare(b);
      if (ai === -1) return 1; if (bi === -1) return -1;
      return ai - bi;
    }),
    [findings],
  );

  const filtered = useMemo(() => findings.filter((f) => {
    if (sevFilter !== "ALL" && f.severity !== sevFilter) return false;
    if (categoryFilter !== "ALL" && f.category !== categoryFilter) return false;
    if (sourceFilter === "LIVE" && f.aiGenerated) return false;
    if (sourceFilter === "AI" && !f.aiGenerated) return false;
    return true;
  }), [findings, sevFilter, categoryFilter, sourceFilter]);

  // Group by normalized title — strips quoted resource names so the same finding type
  // on different resources/subscriptions collapses into one group.
  // e.g. "No Firewall in 'sub-A'" + "No Firewall in 'sub-B'" → one group, two instances.
  const grouped = useMemo(() => {
    const map = new Map<string, FindingItem[]>();
    for (const f of filtered) {
      const key = `${f.severity}::${f.category}::${normalizeTitle(f.title)}`;
      const arr = map.get(key) ?? [];
      arr.push(f);
      map.set(key, arr);
    }
    return Array.from(map.entries()).sort(([ka], [kb]) => {
      const sa = ka.split("::")[0] as Sev;
      const sb = kb.split("::")[0] as Sev;
      return SEV_ORDER.indexOf(sa) - SEV_ORDER.indexOf(sb);
    });
  }, [filtered]);

  if (findings.length === 0) {
    return (
      <EmptyState title="No findings yet">
        Run discovery on the Connections tab, or upload documents and run AI analysis on the Documents tab.
      </EmptyState>
    );
  }

  const total = findings.length;

  return (
    <div className="space-y-4">
      {/* ── Summary header ── */}
      <div className="glass p-5">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-navy-800 dark:text-navy-100">
              Findings
              <span className="ml-2 text-base font-normal text-navy-400">
                {totalGroups} unique issues
              </span>
            </h2>
            <p className="mt-0.5 text-xs text-navy-500">
              {total} total findings · {liveCount} live discovery · {aiCount} AI analysis
            </p>
          </div>

          {/* Severity pills */}
          <div className="flex flex-wrap gap-2">
            {SEV_ORDER.filter((s) => sevCounts[s] > 0).map((sev) => (
              <div key={sev} className="flex items-center gap-1.5 rounded-full border border-navy-700/40 bg-navy-100/60 dark:bg-navy-800/40 px-3 py-1">
                <span className={`h-2 w-2 rounded-full ${SEV_META[sev].dot}`} />
                <span className="text-xs font-semibold text-navy-500 dark:text-navy-200">{SEV_META[sev].label}</span>
                <span className="text-xs text-navy-400">{sevCounts[sev]}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Proportional severity bar */}
        <div
          className="flex h-1.5 w-full gap-0.5 overflow-hidden rounded-full"
          role="img"
          aria-label={`Severity breakdown: ${SEV_ORDER.filter((s) => sevCounts[s] > 0)
            .map((s) => `${SEV_META[s].label}: ${sevCounts[s]}`)
            .join(", ")}`}
        >
          {SEV_ORDER.filter((s) => sevCounts[s] > 0).map((sev) => (
            <div
              key={sev}
              title={`${SEV_META[sev].label}: ${sevCounts[sev]}`}
              className={`${SEV_META[sev].bar} rounded-full transition-all`}
              {...makeStyle({ width: `${(sevCounts[sev] / total) * 100}%` })}
            />
          ))}
        </div>
      </div>

      {/* ── Risk matrix ── */}
      {categories.length > 0 && (
        <div className="glass p-5">
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-navy-500">
            Risk Matrix — Severity × Category
          </h3>
          <p className="mb-4 text-[10px] text-navy-600">Raw finding counts across all subscriptions and resources</p>
          <div className="overflow-x-auto">
            <table className="min-w-full text-xs">
              <caption className="sr-only">Risk Matrix — Severity counts by Category</caption>
              <thead>
                <tr className="border-b border-navy-700/40">
                  <th scope="col" className="w-40 pb-2 text-left text-xs font-semibold text-navy-400">Category</th>
                  {SEV_ORDER.map((sev) => (
                    <th key={sev} scope="col" className="pb-2 text-center font-semibold text-navy-400">
                      {SEV_META[sev].label}
                    </th>
                  ))}
                  <th scope="col" className="pb-2 text-center font-semibold text-navy-400">Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-navy-700/30">
                {categories.map((cat) => {
                  const rowTotal = SEV_ORDER.reduce(
                    (s, sev) => s + findings.filter((f) => f.category === cat && f.severity === sev).length, 0,
                  );
                  return (
                    <tr key={cat} className="hover:bg-navy-50 dark:hover:bg-navy-800/20">
                      <th scope="row" className="py-2 pr-4 text-left text-xs font-medium text-navy-500 dark:text-navy-200 font-normal">{cat}</th>
                      {SEV_ORDER.map((sev) => {
                        const count = findings.filter((f) => f.category === cat && f.severity === sev).length;
                        return (
                          <td key={sev} className="py-2 text-center">
                            {count > 0 ? (
                              <span className={`inline-flex h-6 w-6 items-center justify-center rounded font-bold text-xs text-white ${MATRIX_SEV_DOT[sev]}`}>
                                {count}
                              </span>
                            ) : (
                              <span className="text-navy-700">—</span>
                            )}
                          </td>
                        );
                      })}
                      <td className="py-2 text-center text-xs font-semibold text-navy-400 dark:text-navy-300">{rowTotal}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Filter toolbar ── */}
      <div className="glass p-4">
        <div className="flex flex-wrap items-center gap-2">
          {/* Severity toggles */}
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter findings by severity">
            <button
              type="button"
              onClick={() => setSevFilter("ALL")}
              {...{ "aria-pressed": sevFilter === "ALL" }}
              className={`rounded-full px-3 py-1 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 ${
                sevFilter === "ALL"
                  ? "bg-navy-100 text-navy-800 ring-2 ring-teal-500/50 dark:bg-navy-600 dark:text-navy-100"
                  : "bg-navy-100/60 dark:bg-navy-800/40 text-navy-400 hover:text-navy-400 dark:hover:text-navy-300 hover:bg-navy-100/60 dark:hover:bg-navy-700/40"
              }`}
            >
              All
            </button>
            {SEV_ORDER.filter((s) => sevCounts[s] > 0).map((sev) => (
              <button
                key={sev}
                type="button"
                onClick={() => setSevFilter(sevFilter === sev ? "ALL" : sev)}
                {...{ "aria-pressed": sevFilter === sev }}
                className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 ${
                  sevFilter === sev
                    ? `${SEV_META[sev].badge} ring-2 ring-teal-500/50`
                    : "bg-navy-100/60 dark:bg-navy-800/40 text-navy-400 hover:text-navy-400 dark:hover:text-navy-300 hover:bg-navy-100/60 dark:hover:bg-navy-700/40"
                }`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${SEV_META[sev].dot}`} />
                {SEV_META[sev].label}
                <span className="opacity-60">{sevCounts[sev]}</span>
              </button>
            ))}
          </div>

          {/* Category + source selects */}
          <div className="ml-auto flex gap-2">
            <select
              aria-label="Filter by category"
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="rounded-lg border border-navy-700/40 bg-navy-100/60 dark:bg-navy-800/40 px-3 py-1 text-xs text-navy-400 dark:text-navy-300 focus:outline-none focus:ring-2 focus:ring-teal-500"
            >
              <option value="ALL">All Categories</option>
              {categories.map((cat) => (
                <option key={cat} value={cat}>{cat}</option>
              ))}
            </select>
            <select
              aria-label="Filter by source"
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value as "ALL" | "LIVE" | "AI")}
              className="rounded-lg border border-navy-700/40 bg-navy-100/60 dark:bg-navy-800/40 px-3 py-1 text-xs text-navy-400 dark:text-navy-300 focus:outline-none focus:ring-2 focus:ring-teal-500"
            >
              <option value="ALL">All Sources</option>
              <option value="LIVE">Live Discovery</option>
              <option value="AI">AI Analysis</option>
            </select>
          </div>
        </div>

        {filtered.length !== findings.length && (
          <p className="mt-2 text-xs text-navy-600">
            Showing {grouped.length} of {totalGroups} issues ({filtered.length} of {total} findings)
          </p>
        )}
      </div>

      {/* ── Finding list (grouped) ── */}
      {grouped.length === 0 ? (
        <EmptyState variant="inline" title="No findings match the current filters" />
      ) : (
        <div className="glass overflow-hidden divide-y divide-navy-700/30">
          {grouped.map(([groupKey, items]) => {
            const rep = items[0];
            const sev = rep.severity as Sev;
            const meta = SEV_META[sev];
            // Deduplicate within the group: same resource label = same finding from multiple syncs
            const dedupedInstances = deduplicateInstances(items);
            const isGroup = dedupedInstances.length > 1;
            const isExpanded = expandedGroupKey === groupKey;
            // Display title uses the normalized pattern (e.g. "No Azure Firewall deployed in '…'")
            const displayTitle = normalizeTitle(rep.title)
              // Capitalise first letter for display
              .replace(/^'/, "'")
              .replace(/^\w/, (c) => c.toUpperCase());

            return (
              <div key={groupKey} className={`border-l-4 ${meta.border}`}>
                {/* Group / single header row */}
                <button
                  type="button"
                  onClick={() => setExpandedGroupKey(isExpanded ? null : groupKey)}
                  {...{ "aria-expanded": isExpanded }}
                  aria-controls={`finding-group-${groupKey}`}
                  className={`w-full px-5 py-3.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-1 ${
                    isExpanded ? "bg-navy-50 dark:bg-navy-800/20" : "hover:bg-navy-50 dark:hover:bg-navy-800/10"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <span className={`mt-0.5 inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-xs font-semibold ${meta.badge}`}>
                      {meta.label}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold leading-snug text-navy-800 dark:text-navy-100">
                        {displayTitle}
                      </p>
                      <div className="mt-1.5 flex flex-wrap items-center gap-2">
                        <span className="inline-flex items-center rounded border border-navy-700/40 bg-navy-100/60 dark:bg-navy-800/40 px-2 py-0.5 text-xs text-navy-400">
                          {rep.category}
                        </span>
                        <span className={`inline-flex items-center rounded border px-2 py-0.5 text-xs ${
                          rep.aiGenerated
                            ? "border-teal-800/40 bg-teal-50 dark:bg-teal-900/20 text-teal-700 dark:text-teal-400"
                            : "border-violet-800/40 bg-violet-50 dark:bg-violet-900/20 text-violet-600 dark:text-violet-400"
                        }`}>
                          {rep.aiGenerated ? "AI Analysis" : "Live Discovery"}
                        </span>
                        {isGroup && (
                          <span className="inline-flex items-center rounded-full border border-navy-600/40 bg-navy-100/60 dark:bg-navy-700/40 px-2 py-0.5 text-xs font-semibold text-navy-400 dark:text-navy-300">
                            {dedupedInstances.length} affected resources
                          </span>
                        )}
                      </div>
                    </div>
                    <svg
                      aria-hidden="true"
                      focusable="false"
                      className={`mt-0.5 h-4 w-4 shrink-0 text-navy-600 transition-transform ${isExpanded ? "rotate-180" : ""}`}
                      fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                    </svg>
                  </div>
                </button>

                {/* Expanded content */}
                {isExpanded && (
                  <div id={`finding-group-${groupKey}`} className="divide-y divide-navy-700/20 bg-navy-50 dark:bg-navy-800/10">
                    {isGroup ? (
                      /* Multiple affected resources — one row per resource */
                      dedupedInstances.map(({ label, finding, count }) => (
                        <InstanceRow key={finding.id} label={label} finding={finding} count={count} />
                      ))
                    ) : (
                      /* Single resource — show detail inline */
                      <div className="px-5 pb-5 pt-2">
                        {/* Resource identifier */}
                        <p className="mb-2 font-mono text-xs font-semibold text-navy-400">
                          {dedupedInstances[0].label}
                          {dedupedInstances[0].count > 1 && (
                            <span className="ml-2 rounded border border-navy-600/40 bg-navy-100/60 dark:bg-navy-700/40 px-1.5 py-0.5 text-[10px] font-semibold text-navy-400">
                              ×{dedupedInstances[0].count} syncs
                            </span>
                          )}
                        </p>
                        <p className="mb-3 text-sm leading-relaxed text-navy-400 dark:text-navy-300">{rep.description}</p>
                        {rep.recommendation && (
                          <div className="rounded-lg border border-teal-900/30 bg-teal-50 dark:bg-teal-900/10 px-3 py-2.5">
                            <p className="text-xs leading-relaxed text-teal-700 dark:text-teal-300">
                              <span className="font-semibold text-teal-800 dark:text-teal-200">Recommendation: </span>
                              {rep.recommendation}
                            </p>
                            <a href={rep.msLearnUrl} target="_blank" rel="noopener noreferrer"
                              className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-teal-700 dark:text-teal-400 hover:text-teal-700 dark:hover:text-teal-300 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500">
                              <svg aria-hidden="true" focusable="false" className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                              </svg>
                              MS Learn docs
                              <span className="sr-only"> (opens in new tab)</span>
                            </a>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
