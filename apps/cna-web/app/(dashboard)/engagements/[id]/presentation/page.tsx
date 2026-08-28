import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { notFound } from "next/navigation";
import Link from "next/link";
import {
  computeRiskScore,
  getRiskLabel,
  computeMaturityDimensions,
  getTopologyStats,
  SEV_ORDER,
  SEV_COLORS,
  type Finding,
} from "./_lib/metrics";
import { getMergedTopology } from "./_lib/get-merged-topology";
import { RiskGauge } from "@/components/charts/risk-gauge";
import { MaturityRadar } from "@/components/charts/maturity-radar";

interface PageProps {
  params: Promise<{ id: string }>;
}

const styleKey = "style";
const makeStyle = (props: Record<string, string>) => ({ [styleKey]: props }) as any;

// ── Nav Card ───────────────────────────────────────────────────────────────────
function NavCard({
  href,
  label,
  description,
  accent,
  children,
}: {
  href: string;
  label: string;
  description: string;
  accent: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="group glass flex flex-col gap-3 rounded-xl border border-navy-700/40 p-5 transition-all hover:border-teal-600/40 hover:shadow-lg"
    >
      <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${accent}`}>
        {children}
      </div>
      <div>
        <p className="text-sm font-semibold text-navy-800 group-hover:text-navy-900 dark:text-navy-100 dark:group-hover:text-white">{label}</p>
        <p className="mt-0.5 text-xs text-navy-400">{description}</p>
      </div>
      <span className="mt-auto text-xs font-medium text-teal-500 group-hover:text-teal-400">
        View →
      </span>
    </Link>
  );
}

export default async function PresentationOverviewPage({ params }: PageProps) {
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
  const riskScore = computeRiskScore(findings);
  const riskInfo  = getRiskLabel(riskScore);
  const dims      = computeMaturityDimensions(topology, findings);
  const stats     = getTopologyStats(topology);

  const bySev = Object.fromEntries(
    SEV_ORDER.map((sev) => [sev, findings.filter((f) => f.severity === sev)]),
  ) as Record<string, typeof findings>;

  const maxSevCount = Math.max(...SEV_ORDER.map((s) => bySev[s]?.length ?? 0), 1);

  const base = `/engagements/${id}/presentation`;

  return (
    <div className="space-y-5">
      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="label-caps text-navy-500">Assessment Overview</h2>
          <h1 className="mt-0.5 text-xl font-black text-navy-800 dark:text-navy-100">{engagement.clientOrg}</h1>
        </div>
        {jobDate && (
          <p className="text-xs text-navy-500">
            Last discovery:{" "}
            {new Date(jobDate).toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
              year: "numeric",
            })}
          </p>
        )}
      </div>

      {/* ── Row 1: Gauge + Radar ── */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        {/* Risk Gauge */}
        <div className="glass flex flex-col items-center gap-4 rounded-xl p-6 sm:flex-row">
          <RiskGauge score={riskScore} color={riskInfo.color} />
          <div className="text-center sm:text-left">
            <p className={`text-2xl font-black ${riskInfo.textClass}`}>{riskInfo.label}</p>
            <p className="mt-1 text-sm text-navy-400">
              Based on {findings.filter((f) => f.severity !== "INFORMATIONAL").length} actionable
              finding{findings.filter((f) => f.severity !== "INFORMATIONAL").length !== 1 ? "s" : ""}
            </p>
            <div className="mt-4 space-y-1.5">
              {SEV_ORDER.filter((s) => s !== "INFORMATIONAL" && (bySev[s]?.length ?? 0) > 0).map((sev) => (
                <div key={sev} className="flex items-center gap-2">
                  <span className={`text-xs font-semibold w-20 ${SEV_COLORS[sev as keyof typeof SEV_COLORS].text}`}>
                    {sev[0] + sev.slice(1).toLowerCase()}
                  </span>
                  <span className="text-sm font-black text-navy-800 dark:text-navy-100">{bySev[sev]?.length ?? 0}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Maturity Radar */}
        <div className="glass flex flex-col items-center gap-3 rounded-xl p-6 sm:flex-row">
          <MaturityRadar dims={dims} />
          <div className="w-full space-y-2">
            <h2 className="label-caps text-navy-500">Maturity Dimensions</h2>
            {dims.map((d) => (
              <div key={d.label} className="flex items-center gap-2">
                <span className="w-24 truncate text-xs text-navy-400">{d.fullLabel}</span>
                <div className="flex-1 overflow-hidden rounded-full bg-navy-100 dark:bg-navy-800">
                  {/* eslint-disable-next-line react/forbid-dom-props */}
                  <div
                    className="h-1.5 rounded-full bg-teal-500"
                    {...makeStyle({ width: `${(d.score / 10) * 100}%` })}
                  />
                </div>
                <span className="w-5 text-right text-xs font-bold text-teal-700 dark:text-teal-400">{d.score}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Row 2: Severity Distribution ── */}
      {findings.length > 0 && (
        <div className="glass rounded-xl p-5">
          <h2 className="label-caps mb-4 text-navy-500">Severity Distribution</h2>
          <div className="grid grid-cols-5 gap-3">
            {SEV_ORDER.map((sev) => {
              const count = bySev[sev]?.length ?? 0;
              const barPct = (count / maxSevCount) * 100;
              const style = SEV_COLORS[sev as keyof typeof SEV_COLORS];
              return (
                <div key={sev} className="flex flex-col items-center gap-2">
                  <div className="flex h-16 w-full flex-col items-center justify-end">
                    {/* eslint-disable-next-line react/forbid-dom-props */}
                    <div
                      className={`w-full rounded-t ${style.bar}`}
                      {...makeStyle({ height: `${Math.max(barPct, count > 0 ? 8 : 0)}%` })}
                    />
                  </div>
                  <p className={`text-xl font-black ${style.text}`}>{count}</p>
                  <p className={`text-xs font-semibold uppercase tracking-wide ${style.text}`}>
                    {sev === "INFORMATIONAL" ? "Info" : sev[0] + sev.slice(1).toLowerCase()}
                  </p>
                </div>
              );
            })}
          </div>
          {/* Stacked bar */}
          <div className="mt-4 flex h-2.5 w-full overflow-hidden rounded-full">
            {SEV_ORDER.map((sev) => {
              const pct = ((bySev[sev]?.length ?? 0) / Math.max(findings.length, 1)) * 100;
              return pct > 0 ? (
                /* eslint-disable-next-line react/forbid-dom-props */
                <div
                  key={sev}
                  className={SEV_COLORS[sev as keyof typeof SEV_COLORS].bar}
                  {...makeStyle({ width: `${pct}%` })}
                  title={`${sev}: ${bySev[sev]?.length ?? 0}`}
                />
              ) : null;
            })}
          </div>
        </div>
      )}

      {/* ── Row 3: Infrastructure Stats ── */}
      {topology && (
        <div className="glass rounded-xl p-5">
          <h2 className="label-caps mb-4 text-navy-500">Infrastructure Topology</h2>
          <div className="grid grid-cols-4 gap-3 sm:grid-cols-6 lg:grid-cols-12">
            {[
              { label: "Subscriptions", value: stats.subscriptions },
              { label: "VNets",         value: stats.vnets         },
              { label: "Subnets",       value: stats.subnets       },
              { label: "Firewalls",     value: stats.firewalls     },
              { label: "NVA / NGFW",   value: stats.nvas          },
              { label: "NSGs",          value: stats.nsgs          },
              { label: "Load Balancers",value: stats.loadBalancers },
              { label: "Public IPs",    value: stats.publicIps     },
              { label: "Private Eps",   value: stats.privateEndpoints },
              { label: "NAT Gateways",  value: stats.natGateways   },
              { label: "App Gateways",  value: stats.appGateways   },
              { label: "ExpressRoutes", value: stats.expressRoutes },
            ].map((s) => (
              <div
                key={s.label}
                className="col-span-2 flex flex-col items-center rounded-xl border border-navy-100/60 bg-navy-50 p-3 text-center dark:border-navy-700/40 dark:bg-navy-800/30"
              >
                <p className="text-2xl font-black text-navy-800 dark:text-navy-100">{s.value}</p>
                <p className="mt-0.5 text-xs text-navy-400">{s.label}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {!topology && findings.length === 0 && (
        <div className="glass flex flex-col items-center gap-3 rounded-xl border border-dashed border-navy-700 px-8 py-10 text-center">
          <svg aria-hidden="true" focusable="false" className="h-8 w-8 text-navy-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 9l10.5-3m0 6.553v3.75a2.25 2.25 0 01-1.632 2.163l-1.32.377a1.803 1.803 0 11-.99-3.467l2.31-.66a2.25 2.25 0 001.632-2.163zm0 0V2.25L9 5.25v10.303m0 0v3.75a2.25 2.25 0 01-1.633 2.163l-1.32.377a1.803 1.803 0 01-.99-3.467l2.31-.66A2.25 2.25 0 009 15.553z" />
          </svg>
          <p className="text-sm font-semibold text-navy-400 dark:text-navy-300">No assessment data yet</p>
          <p className="text-xs text-navy-500">
            Run discovery and AI analysis to populate this dashboard.
          </p>
        </div>
      )}

      {/* ── Row 4: Navigation Cards ── */}
      <div>
        <h2 className="label-caps mb-3 text-navy-500">Explore the Assessment</h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <NavCard
            href={`${base}/executive`}
            label="Executive Summary"
            description="Risk posture, key metrics, and leadership narrative"
            accent="bg-red-50 text-red-600 dark:bg-red-900/40 dark:text-red-400"
          >
            <svg aria-hidden="true" focusable="false" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
          </NavCard>

          <NavCard
            href={`${base}/technical`}
            label="Technical Findings"
            description="Full findings list, risk matrix, and network inventory"
            accent="bg-orange-50 text-orange-600 dark:bg-orange-900/40 dark:text-orange-400"
          >
            <svg aria-hidden="true" focusable="false" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" />
            </svg>
          </NavCard>

          <NavCard
            href={`${base}/remediation`}
            label="Remediation Plan"
            description="Phased action plan with timelines and priorities"
            accent="bg-amber-50 text-amber-600 dark:bg-amber-900/40 dark:text-amber-400"
          >
            <svg aria-hidden="true" focusable="false" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
            </svg>
          </NavCard>

          <NavCard
            href={`${base}/compliance`}
            label="Compliance & Maturity"
            description="Maturity radar, dimension scores, and framework mapping"
            accent="bg-teal-50 text-teal-700 dark:bg-teal-900/40 dark:text-teal-400"
          >
            <svg aria-hidden="true" focusable="false" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          </NavCard>
        </div>
      </div>
    </div>
  );
}
