import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { notFound } from "next/navigation";
import Link from "next/link";
import { deriveStatMasters } from "@/lib/derive-stat-masters";
import { getStatMasters } from "@/lib/metrics-api";
import { StackedBar, type StackedBarDatum } from "@/components/charts/stacked-bar";
import { SEVERITY_HEX } from "@/components/charts/chart-theme";
import { PivotGrid } from "@/components/pivot/pivot-grid";
import { StatusBadge } from "@/components/ui/status-badge";
import { SEV_ORDER } from "../presentation/_lib/metrics";

interface PageProps {
  params: Promise<{ id: string }>;
}

const COST_CATEGORY_RE = /cost|finops|optimi[sz]ation|spend/i;

export default async function FinOpsPage({ params }: PageProps) {
  const { id } = await params;
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
  const records = (await getStatMasters(id)) ?? deriveStatMasters(engagement.findings);

  // Cost-relevant findings: AZ-COST rule ids (Phase B) or cost-flavored categories
  const costFindings = engagement.findings.filter(
    (f) => /\bAZ-COST-\d+/i.test(f.title) || COST_CATEGORY_RE.test(f.category),
  );
  const hasCostData = records.some((r) => r.est_monthly_cost_impact > 0);

  // Stacked bar: est cost impact by category, stacked by severity
  const categories = [...new Set(records.filter((r) => r.est_monthly_cost_impact > 0).map((r) => r.category))];
  const chartData: StackedBarDatum[] = categories.map((cat) => {
    const row: StackedBarDatum = { category: cat };
    for (const sev of SEV_ORDER) {
      const sum = records
        .filter((r) => r.category === cat && r.severity === sev)
        .reduce((s, r) => s + r.est_monthly_cost_impact, 0);
      if (sum > 0) row[sev] = Math.round(sum);
    }
    return row;
  });

  return (
    <div className="space-y-5">
      {/* ── Header ── */}
      <div>
        <h2 className="label-caps text-navy-500">FinOps</h2>
        <h1 className="mt-0.5 text-xl font-black text-navy-800 dark:text-navy-100">
          Network Cost Optimization
        </h1>
        <p className="mt-1 text-xs text-navy-400">
          Estimated monthly cost impact derived from FinOps findings (orphaned public IPs, idle
          gateways, oversized SKUs). Estimates are static-price approximations — verify before
          presenting to clients.
        </p>
      </div>

      {/* ── Cost chart or fallback ── */}
      <div className="glass rounded-xl p-5">
        <h2 className="label-caps mb-4 text-navy-500">Est. Monthly Cost Impact by Category</h2>
        {hasCostData ? (
          <StackedBar
            data={chartData}
            series={[...SEV_ORDER]}
            colors={SEVERITY_HEX}
            valueFormatter={(v) => `$${v.toLocaleString()}`}
          />
        ) : (
          <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-navy-700 px-6 py-10 text-center">
            <p className="text-sm font-semibold text-navy-300">No cost data yet</p>
            <p className="max-w-md text-xs text-navy-500">
              Cost-impact figures are produced by the FinOps analysis rules (AZ-COST findings with
              estimated monthly impact). Re-run discovery and analysis after the FinOps engine is
              enabled to populate this chart.
            </p>
          </div>
        )}
      </div>

      {/* ── Pivot explorer ── */}
      {records.length > 0 && (
        <PivotGrid
          records={records}
          defaultRow="category"
          defaultColumn="severity"
          defaultMeasure={hasCostData ? "est_monthly_cost_impact" : "finding_count"}
          title="Cost Pivot Explorer"
        />
      )}

      {/* ── AZ-COST findings table ── */}
      <div className="glass rounded-xl p-5">
        <h2 className="label-caps mb-4 text-navy-500">
          Cost Findings ({costFindings.length})
        </h2>
        {costFindings.length === 0 ? (
          <p className="py-6 text-center text-xs text-navy-500">
            No AZ-COST findings recorded for this engagement.{" "}
            <Link href={`/engagements/${id}/findings`} className="font-semibold text-teal-500 hover:underline">
              View all findings →
            </Link>
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-xs">
              <thead>
                <tr className="border-b border-navy-700/40">
                  <th className="pb-2 text-left font-medium text-navy-500">Severity</th>
                  <th className="pb-2 text-left font-medium text-navy-500">Finding</th>
                  <th className="pb-2 text-left font-medium text-navy-500">Category</th>
                  <th className="pb-2 text-left font-medium text-navy-500">Recommendation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-navy-700/30">
                {costFindings.map((f) => (
                  <tr key={f.id}>
                    <td className="py-2.5 pr-3 align-top">
                      <StatusBadge value={f.severity} variant="severity" />
                    </td>
                    <td className="py-2.5 pr-4 align-top">
                      <p className="font-semibold text-navy-800 dark:text-navy-100">{f.title}</p>
                      <p className="mt-0.5 line-clamp-2 text-navy-400">{f.description}</p>
                    </td>
                    <td className="py-2.5 pr-4 align-top text-navy-400">{f.category}</td>
                    <td className="py-2.5 align-top text-navy-400">
                      {f.recommendation ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
