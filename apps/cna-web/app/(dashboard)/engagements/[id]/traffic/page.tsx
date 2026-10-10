import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { notFound } from "next/navigation";
import Link from "next/link";
import { EmptyState } from "@/components/ui/empty-state";
import { deriveStatMasters } from "@/lib/derive-stat-masters";
import { getStatMasters } from "@/lib/metrics-api";
import { TRAFFIC_DIRECTION_LABELS } from "@/components/charts/chart-theme";
import { TrafficBreakdown } from "@/components/charts/traffic-breakdown";
import { PivotGrid } from "@/components/pivot/pivot-grid";
import { StatusBadge } from "@/components/ui/status-badge";
import { SEV_ORDER } from "../presentation/_lib/metrics";

interface PageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ dir?: string }>;
}

const TABS = [
  { key: "all", label: "All Traffic" },
  { key: "east_west", label: "East-West" },
  { key: "north_south", label: "North-South" },
  { key: "management", label: "Management" },
  { key: "unclassified", label: "Unclassified" },
] as const;

export default async function TrafficMatrixPage({ params, searchParams }: PageProps) {
  const { id } = await params;
  const { dir } = await searchParams;
  const session = await auth();

  const engagement = await prisma.engagement.findUnique({
    where: { id },
    include: {
      members: true,
      findings: { orderBy: [{ severity: "asc" }, { category: "asc" }] },
    },
  });
  if (!engagement) notFound();
  const isMember = engagement.members.some((m) => m.userId === session?.user?.id);
  if (!isMember) notFound();

  // Prefer pre-aggregated records from the metrics API (Phase C); fall back
  // to client-side derivation when the endpoint is unavailable or empty.
  const derived = deriveStatMasters(engagement.findings);
  const records = (await getStatMasters(id)) ?? derived;
  const findingsWithDir = engagement.findings.map((f, i) => ({
    ...f,
    direction: derived[i].traffic_direction,
  }));

  const activeTab = TABS.some((t) => t.key === dir) ? (dir as string) : "all";
  const tabRecords = activeTab === "all" ? records : records.filter((r) => r.traffic_direction === activeTab);
  const tabFindings =
    activeTab === "all" ? findingsWithDir : findingsWithDir.filter((f) => f.direction === activeTab);

  // Direction × severity breakdown for the chart (always full dataset).
  // Sum finding_count — API records are aggregated (one row per dimension
  // tuple) while derived records are one-per-finding; summing works for both.
  const countFindings = (rs: typeof records) => rs.reduce((s, r) => s + r.finding_count, 0);
  const breakdown = (["east_west", "north_south", "management", "unclassified"] as const)
    .map((direction) => ({
      direction,
      counts: Object.fromEntries(
        SEV_ORDER.map((sev) => [
          sev,
          countFindings(
            records.filter((r) => r.traffic_direction === direction && r.severity === sev),
          ),
        ]),
      ),
    }))
    .filter((d) => Object.values(d.counts).some((c) => c > 0));

  return (
    <div className="space-y-5">
      {/* ── Header ── */}
      <div>
        <h2 className="label-caps text-navy-500">Traffic Matrix</h2>
        <h1 className="mt-0.5 text-xl font-black text-navy-800 dark:text-navy-100">
          East-West &amp; North-South Analysis
        </h1>
        <p className="mt-1 text-xs text-navy-400">
          Findings classified by traffic direction. Legacy findings without an explicit
          classification are bucketed heuristically; unmatched items appear as Unclassified.
        </p>
      </div>

      {/* ── Tabs (searchParams-driven) ── */}
      <nav aria-label="Traffic direction tabs" className="flex flex-wrap gap-1.5">
        {TABS.map((tab) => {
          const active = tab.key === activeTab;
          const count =
            tab.key === "all"
              ? countFindings(records)
              : countFindings(records.filter((r) => r.traffic_direction === tab.key));
          return (
            <Link
              key={tab.key}
              href={tab.key === "all" ? `/engagements/${id}/traffic` : `/engagements/${id}/traffic?dir=${tab.key}`}
              aria-current={active ? "page" : undefined}
              className={[
                "rounded-full border px-3.5 py-1.5 text-xs font-semibold transition-colors",
                active
                  ? "border-teal-500 bg-teal-50 text-teal-700 dark:bg-teal-900/40 dark:text-teal-300"
                  : "border-navy-200 text-navy-500 hover:border-teal-500/40 hover:text-teal-600 dark:border-navy-700 dark:text-navy-300 dark:hover:text-teal-400",
              ].join(" ")}
            >
              {tab.label} <span className="opacity-60">({count})</span>
            </Link>
          );
        })}
      </nav>

      {engagement.findings.length === 0 ? (
        <EmptyState title="No findings yet">
          Run discovery and AI analysis to populate the traffic matrix.{" "}
          <Link href={`/engagements/${id}/connections`} className="font-semibold text-teal-600 dark:text-teal-400 hover:underline">
            Go to Connections →
          </Link>
        </EmptyState>
      ) : (
        <>
          {/* ── Breakdown chart ── */}
          <div className="glass rounded-xl p-5">
            <h2 className="label-caps mb-4 text-navy-500">Findings by Direction &amp; Severity</h2>
            <TrafficBreakdown data={breakdown} />
          </div>

          {/* ── Pivot explorer ── */}
          <PivotGrid
            records={tabRecords}
            defaultRow="category"
            defaultColumn="severity"
            title={`Pivot Explorer — ${TABS.find((t) => t.key === activeTab)?.label}`}
          />

          {/* ── Filtered findings list ── */}
          <div className="glass rounded-xl p-5">
            <h2 className="label-caps mb-4 text-navy-500">
              {TABS.find((t) => t.key === activeTab)?.label} Findings ({tabFindings.length})
            </h2>
            {tabFindings.length === 0 ? (
              <p className="py-6 text-center text-xs text-navy-500">
                No findings in this traffic direction.
              </p>
            ) : (
              <ul className="divide-y divide-navy-700/30">
                {tabFindings.map((f) => (
                  <li key={f.id} className="flex items-start gap-3 py-3">
                    <StatusBadge value={f.severity} variant="severity" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-navy-800 dark:text-navy-100">{f.title}</p>
                      <p className="mt-0.5 line-clamp-2 text-xs text-navy-400">{f.description}</p>
                    </div>
                    <span className="flex-shrink-0 rounded-full border border-navy-200 px-2 py-0.5 text-xs text-navy-400 dark:border-navy-700">
                      {TRAFFIC_DIRECTION_LABELS[f.direction]}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}
