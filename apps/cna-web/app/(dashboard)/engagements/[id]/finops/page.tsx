import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { notFound } from "next/navigation";
import Link from "next/link";
import { StatusBadge } from "@/components/ui/status-badge";
import { getMergedTopology } from "../presentation/_lib/get-merged-topology";
import { EmptyState } from "@/components/ui/empty-state";
import {
  buildChargeableInventory,
  buildEgressSpend,
  formatUsd,
  type FinOpsSubscription,
} from "@/lib/finops/inventory";

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

  const { topology, jobDate } = await getMergedTopology(id);
  const subs = (topology?.subscriptions ?? []) as unknown as FinOpsSubscription[];

  // 1. Measured spend — Azure Cost Management actuals collected at discovery time
  const egressRows = buildEgressSpend(subs);
  const measuredRows = egressRows.filter((r) => r.egressUsdMtd != null);
  const egressTotal = measuredRows.reduce((s, r) => s + (r.egressUsdMtd ?? 0), 0);

  // 2. Chargeable inventory — every network resource that bills monthly
  const groups = buildChargeableInventory(subs);
  const inventoryTotal = groups.reduce((s, g) => s + g.estMonthlyUsd, 0);
  const flaggedTotal = groups.reduce((s, g) => s + g.flaggedCount, 0);

  // 3. Waste findings — AZ-COST rule ids or cost-flavored categories
  const costFindings = engagement.findings.filter(
    (f) => /\bAZ-COST-\d+/i.test(f.title) || COST_CATEGORY_RE.test(f.category),
  );

  return (
    <div className="space-y-5">
      {/* ── Header ── */}
      <div>
        <h2 className="label-caps text-navy-500">FinOps</h2>
        <h1 className="mt-0.5 text-xl font-black text-navy-800 dark:text-navy-100">
          Network Cost Visibility
        </h1>
        <p className="mt-1 text-xs text-navy-400">
          Measured egress spend from Azure Cost Management actuals, the full chargeable network
          inventory with static list-price estimates, and waste findings. Estimated figures are
          marked with a dagger (†) — see the footnote below.
          {jobDate && (
            <> Data collected {jobDate.toLocaleDateString("en-US", { dateStyle: "medium" })}.</>
          )}
        </p>
      </div>

      {/* ── 1. Measured egress spend (MTD actuals) ── */}
      <div className="glass rounded-xl p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="label-caps text-navy-500">Measured Egress Spend — Month to Date</h2>
          {measuredRows.length > 0 && (
            <span className="text-sm font-black text-navy-800 dark:text-navy-100">
              {formatUsd(egressTotal)} <span className="font-medium text-navy-400">total MTD</span>
            </span>
          )}
        </div>
        {measuredRows.length === 0 ? (
          <EmptyState variant="inline" title="No measured spend yet">
            Month-to-date egress actuals are pulled from the Azure Cost Management API (Bandwidth
            and Virtual Network meters) during discovery. Re-run discovery with a credential that
            has Cost Management Reader to populate this section.
          </EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-xs">
              <thead>
                <tr className="border-b border-navy-700/40">
                  <th className="pb-2 text-left font-medium text-navy-500">Subscription</th>
                  <th className="pb-2 text-right font-medium text-navy-500">Egress $ MTD (actual)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-navy-700/30">
                {egressRows.map((r) => (
                  <tr key={r.subscriptionId}>
                    <td className="py-2 pr-4">
                      <span className="font-semibold text-navy-800 dark:text-navy-100">
                        {r.subscriptionName ?? r.subscriptionId}
                      </span>
                      {r.subscriptionName && (
                        <span className="ml-2 font-mono text-[10px] text-navy-500">
                          {r.subscriptionId.slice(0, 8)}
                        </span>
                      )}
                    </td>
                    <td className="py-2 text-right font-mono">
                      {r.egressUsdMtd != null ? (
                        <span className="font-semibold text-navy-800 dark:text-navy-100">
                          {formatUsd(r.egressUsdMtd)}
                        </span>
                      ) : (
                        <span className="text-navy-500">not collected</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-3 text-[10px] text-navy-500">
              Source: Azure Cost Management Query API, ActualCost, meter categories Bandwidth +
              Virtual Network, subscription scope, month to date at collection time.
            </p>
          </div>
        )}
      </div>

      {/* ── 2. Chargeable network inventory ── */}
      <div className="glass rounded-xl p-5">
        <div className="mb-1 flex items-center justify-between">
          <h2 className="label-caps text-navy-500">Chargeable Network Inventory</h2>
          {groups.length > 0 && (
            <span className="text-sm font-black text-navy-800 dark:text-navy-100">
              {formatUsd(inventoryTotal)}{" "}
              <span className="font-medium text-navy-400">est./mo&nbsp;†</span>
            </span>
          )}
        </div>
        <p className="mb-4 text-xs text-navy-400">
          Every discovered network resource that bills monthly, priced from static East-US
          pay-as-you-go list rates&nbsp;†. Data-processing and per-GB charges are excluded.
          {flaggedTotal > 0 && (
            <span className="ml-1 font-semibold text-amber-500">
              {flaggedTotal} resource{flaggedTotal === 1 ? "" : "s"} flagged as likely waste.
            </span>
          )}
        </p>
        {groups.length === 0 ? (
          <EmptyState variant="inline" title="No inventory yet">
            Run discovery to populate the chargeable-resource inventory (public IPs, gateways,
            firewalls, Bastion, NAT gateways, App Gateway, private endpoints, DNS zones).
          </EmptyState>
        ) : (
          <div className="space-y-5">
            {groups.map((group) => (
              <div key={group.kind}>
                <div className="mb-2 flex items-center gap-2">
                  <h3 className="text-xs font-bold text-navy-800 dark:text-navy-100">
                    {group.kind}
                  </h3>
                  <span className="pill-teal text-[10px]">{group.rows.length}</span>
                  <span className="text-[10px] text-navy-500">
                    {formatUsd(group.estMonthlyUsd)}/mo est.
                  </span>
                  {group.flaggedCount > 0 && (
                    <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold text-amber-500">
                      {group.flaggedCount} flagged
                    </span>
                  )}
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full text-xs">
                    <thead>
                      <tr className="border-b border-navy-700/40">
                        <th className="pb-1.5 text-left font-medium text-navy-500">Name</th>
                        <th className="pb-1.5 text-left font-medium text-navy-500">Subscription</th>
                        <th className="pb-1.5 text-left font-medium text-navy-500">Region</th>
                        <th className="pb-1.5 text-left font-medium text-navy-500">SKU / Detail</th>
                        <th className="pb-1.5 text-right font-medium text-navy-500">
                          Est. $/mo&nbsp;†
                        </th>
                        <th className="pb-1.5 text-left font-medium text-navy-500">Flags</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-navy-700/30">
                      {group.rows.map((row, i) => (
                        <tr
                          key={`${row.subscriptionId}-${row.name}-${i}`}
                          className={
                            row.flags.length > 0 ? "bg-amber-50/30 dark:bg-amber-900/10" : undefined
                          }
                        >
                          <td className="py-1.5 pr-4 font-semibold text-navy-800 dark:text-navy-100">
                            {row.name}
                          </td>
                          <td className="py-1.5 pr-4 text-navy-400">
                            {row.subscriptionName ?? row.subscriptionId.slice(0, 8)}
                          </td>
                          <td className="py-1.5 pr-4 text-navy-400">{row.region}</td>
                          <td className="py-1.5 pr-4 font-mono text-navy-400">{row.sku}</td>
                          <td className="py-1.5 text-right font-mono">
                            {row.estMonthlyUsd != null ? (
                              formatUsd(row.estMonthlyUsd)
                            ) : (
                              <span className="text-navy-500">varies</span>
                            )}
                          </td>
                          <td className="py-1.5 pl-4">
                            {row.flags.length > 0 ? (
                              <span className="font-semibold text-amber-500">
                                {row.flags.join(", ")}
                              </span>
                            ) : (
                              <span className="text-navy-600">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── 3. Waste findings ── */}
      <div className="glass rounded-xl p-5">
        <h2 className="label-caps mb-4 text-navy-500">Waste Findings ({costFindings.length})</h2>
        {costFindings.length === 0 ? (
          <p className="py-6 text-center text-xs text-navy-500">
            No AZ-COST findings recorded for this engagement.{" "}
            <Link
              href={`/engagements/${id}/findings`}
              className="font-semibold text-teal-500 hover:underline"
            >
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
                  <th className="pb-2 text-right font-medium text-navy-500">
                    Est. $/mo&nbsp;†
                  </th>
                  <th className="pb-2 pl-4 text-left font-medium text-navy-500">Recommendation</th>
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
                    <td className="py-2.5 text-right align-top font-mono">
                      {f.estCostImpact != null && f.estCostImpact > 0 ? (
                        <span className="font-semibold text-navy-800 dark:text-navy-100">
                          {formatUsd(f.estCostImpact)}
                        </span>
                      ) : (
                        <span className="text-navy-500">—</span>
                      )}
                    </td>
                    <td className="py-2.5 pl-4 align-top text-navy-400">
                      {f.recommendation ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Estimate footnote ── */}
      <p className="text-[11px] text-navy-400 dark:text-navy-500">
        † Estimated from static East-US pay-as-you-go list rates. Confirm against the
        client&apos;s negotiated rates and actual usage before presenting.
      </p>
    </div>
  );
}
