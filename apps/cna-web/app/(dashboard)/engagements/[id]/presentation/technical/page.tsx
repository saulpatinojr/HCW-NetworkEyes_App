import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { notFound } from "next/navigation";
import {
  getTopologyStats,
  SEV_ORDER,
  SEV_COLORS,
  type Finding,
} from "../_lib/metrics";
import { getMergedTopology } from "../_lib/get-merged-topology";

interface PageProps {
  params: Promise<{ id: string }>;
}

const PLATFORM_SUBNETS = new Set([
  "GatewaySubnet",
  "AzureBastionSubnet",
  "AzureFirewallSubnet",
  "AzureFirewallManagementSubnet",
  "RouteServerSubnet",
]);

export default async function TechnicalPage({ params }: PageProps) {
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

  const findings = engagement.findings as Finding[];
  const stats = getTopologyStats(topology);

  const bySev = Object.fromEntries(
    SEV_ORDER.map((sev) => [sev, findings.filter((f) => f.severity === sev)]),
  ) as Record<string, typeof findings>;

  const categories = [...new Set(findings.map((f) => f.category))].sort();

  return (
    <div className="space-y-5">
      {/* ── Header ── */}
      <div>
        <h2 className="label-caps text-navy-500">Technical Network Findings</h2>
        <h1 className="mt-0.5 text-xl font-black text-navy-800 dark:text-navy-100">{engagement.clientOrg}</h1>
        {jobDate && (
          <p className="mt-0.5 text-xs text-navy-500">
            Discovery completed:{" "}
            {new Date(jobDate).toLocaleDateString("en-US", {
              month: "long",
              day: "numeric",
              year: "numeric",
            })}
          </p>
        )}
      </div>

      {/* ── Quick Stats ── */}
      {topology && (
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
          {[
            { label: "Subscriptions", value: stats.subscriptions },
            { label: "VNets",         value: stats.vnets         },
            { label: "Subnets",       value: stats.subnets       },
            { label: "Firewalls",     value: stats.firewalls     },
            { label: "NSGs",          value: stats.nsgs          },
            { label: "NVA / NGFW",   value: stats.nvas          },
          ].map((s) => (
            <div
              key={s.label}
              className="glass rounded-xl border border-navy-700/40 p-3 text-center"
            >
              <p className="text-2xl font-black text-navy-800 dark:text-navy-100">{s.value}</p>
              <p className="mt-0.5 text-xs text-navy-400">{s.label}</p>
            </div>
          ))}
        </div>
      )}

      {/* ── Risk Matrix ── */}
      {findings.length > 0 && categories.length > 0 && (
        <div className="glass overflow-hidden rounded-xl p-6">
          <h2 className="mb-4 text-base font-bold text-navy-800 dark:text-navy-100">Risk Matrix</h2>
          <div className="overflow-x-auto">
            <table className="min-w-full text-xs">
              <thead>
                <tr className="border-b border-navy-700/40">
                  <th className="pb-2.5 text-left text-xs font-semibold text-navy-400">Category</th>
                  {SEV_ORDER.map((s) => (
                    <th key={s} className={`pb-2.5 text-center text-xs font-semibold ${SEV_COLORS[s as keyof typeof SEV_COLORS].text}`}>
                      {s === "INFORMATIONAL" ? "Info" : s[0] + s.slice(1).toLowerCase()}
                    </th>
                  ))}
                  <th className="pb-2.5 text-center text-xs font-semibold text-navy-400">Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-navy-700/30">
                {categories.map((cat) => {
                  const cells = SEV_ORDER.map((sev) =>
                    findings.filter((f) => f.category === cat && f.severity === sev).length,
                  );
                  const total = cells.reduce((a, b) => a + b, 0);
                  return (
                    <tr key={cat}>
                      <td className="py-2 pr-4 text-xs font-medium text-navy-500 dark:text-navy-200">{cat}</td>
                      {cells.map((count, i) => (
                        <td key={i} className="py-2 text-center">
                          {count > 0 ? (
                            <span
                              className={`inline-flex h-6 w-6 items-center justify-center rounded text-xs font-bold text-white ${SEV_COLORS[SEV_ORDER[i] as keyof typeof SEV_COLORS].bar}`}
                            >
                              {count}
                            </span>
                          ) : (
                            <span className="text-navy-700">—</span>
                          )}
                        </td>
                      ))}
                      <td className="py-2 text-center text-xs font-bold text-navy-500 dark:text-navy-200">{total}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Finding Details ── */}
      {findings.length > 0 ? (
        <div className="glass rounded-xl p-6">
          <h2 className="mb-4 text-base font-bold text-navy-800 dark:text-navy-100">
            All Findings ({findings.length})
          </h2>
          <div className="space-y-6">
            {SEV_ORDER.map((sev) =>
              (bySev[sev]?.length ?? 0) > 0 ? (
                <div key={sev}>
                  <p
                    className={`mb-3 text-xs font-bold uppercase tracking-widest ${SEV_COLORS[sev as keyof typeof SEV_COLORS].text}`}
                  >
                    {sev === "INFORMATIONAL" ? "Informational" : sev[0] + sev.slice(1).toLowerCase()}{" "}
                    ({bySev[sev]?.length})
                  </p>
                  <div className="space-y-3">
                    {bySev[sev]?.map((f, i) => {
                      const style = SEV_COLORS[sev as keyof typeof SEV_COLORS];
                      return (
                        <div key={f.id ?? i} className={`rounded-xl border p-4 ${style.bg}`}>
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <p className="text-sm font-semibold text-navy-800 dark:text-navy-100">{f.title}</p>
                            <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${style.badge}`}>
                              {f.category}
                            </span>
                          </div>
                          <p className="mt-2 text-sm leading-relaxed text-navy-400 dark:text-navy-300">
                            {f.description}
                          </p>
                          {f.recommendation && (
                            <div className="mt-3 rounded-lg bg-navy-50 px-4 py-3 text-xs text-navy-500 dark:bg-navy-900/40 dark:text-navy-200">
                              <span className="font-bold text-navy-800 dark:text-navy-100">Recommendation: </span>
                              {f.recommendation}
                            </div>
                          )}
                          {f.aiGenerated && (
                            <p className="mt-2 text-xs text-navy-500">Source: AI Analysis</p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : null,
            )}
          </div>
        </div>
      ) : (
        <div className="glass rounded-xl border border-dashed border-navy-700 p-10 text-center">
          <p className="text-sm text-navy-400">
            No findings yet. Run AI analysis on the Analysis tab to generate findings.
          </p>
        </div>
      )}

      {/* ── Network Inventory ── */}
      {topology && (
        <div className="glass rounded-xl p-6">
          <h2 className="mb-4 text-base font-bold text-navy-800 dark:text-navy-100">Network Inventory</h2>
          {topology.subscriptions.map((sub) => (
            <div key={sub.subscription_id} className="mb-6 last:mb-0">
              <h3 className="label-caps mb-2 text-navy-500">
                {sub.subscription_name ?? sub.subscription_id}
              </h3>
              {sub.vnets.length > 0 ? (
                sub.vnets.map((vnet) => (
                  <div
                    key={vnet.name}
                    className="mb-3 overflow-hidden rounded-xl border border-navy-700/40 last:mb-0"
                  >
                    <div className="flex items-center justify-between bg-navy-50 px-4 py-2.5 dark:bg-navy-800/40">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-navy-800 dark:text-navy-100">{vnet.name}</span>
                        <span className="text-xs text-navy-500">{vnet.location}</span>
                      </div>
                      <span className="font-mono text-xs text-navy-400">
                        {vnet.address_space?.join(", ")}
                      </span>
                    </div>
                    {vnet.subnets?.length > 0 && (
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b border-navy-700/40">
                            <th className="px-4 py-1.5 text-left font-medium text-navy-500">Subnet</th>
                            <th className="px-4 py-1.5 text-left font-medium text-navy-500">CIDR</th>
                            <th className="px-4 py-1.5 text-center font-medium text-navy-500">NSG</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-navy-800/40">
                          {vnet.subnets.map((s) => {
                            const isPlatform = PLATFORM_SUBNETS.has(s.name);
                            const missingNsg = !s.nsg_id && !isPlatform;
                            return (
                              <tr
                                key={s.name}
                                className={missingNsg ? "bg-amber-50/60 dark:bg-amber-900/10" : ""}
                              >
                                <td className="px-4 py-1.5 text-navy-500 dark:text-navy-200">{s.name}</td>
                                <td className="px-4 py-1.5 font-mono text-navy-400">
                                  {s.address_prefix}
                                </td>
                                <td className="px-4 py-1.5 text-center">
                                  {s.nsg_name ? (
                                    <span className="text-teal-700 dark:text-teal-400" title={s.nsg_name}>✓</span>
                                  ) : isPlatform ? (
                                    <span className="text-navy-600">—</span>
                                  ) : (
                                    <span className="font-medium text-amber-600 dark:text-amber-400">None</span>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    )}
                  </div>
                ))
              ) : (
                <p className="text-xs text-navy-500">No VNets discovered in this subscription.</p>
              )}

              {/* Firewalls */}
              {(sub.firewalls?.length ?? 0) > 0 && (
                <div className="mt-3">
                  <h3 className="label-caps mb-2 text-navy-600">Azure Firewalls</h3>
                  <div className="divide-y divide-navy-700/30 rounded-xl border border-navy-700/40">
                    {sub.firewalls.map((fw) => (
                      <div key={fw.name} className="flex items-center justify-between px-4 py-2.5">
                        <span className="text-xs font-medium text-navy-500 dark:text-navy-200">{fw.name}</span>
                        <div className="flex items-center gap-2">
                          <span className="rounded bg-navy-100 px-2 py-0.5 text-xs text-navy-500 dark:bg-navy-700 dark:text-navy-300">
                            {fw.sku_tier}
                          </span>
                          <span
                            className={`rounded px-2 py-0.5 text-xs ${
                              fw.threat_intel_mode === "Deny"
                                ? "bg-teal-50 text-teal-700 dark:bg-teal-900/30 dark:text-teal-400"
                                : "bg-amber-50 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400"
                            }`}
                          >
                            Threat Intel: {fw.threat_intel_mode}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
