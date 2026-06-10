import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { notFound } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import {
  computeRiskScore,
  getRiskLabel,
  computeMaturityDimensions,
  getTopologyStats,
  buildRemediationPlan,
  SEV_ORDER,
  SEV_COLORS,
  type Finding,
} from "../presentation/_lib/metrics";
import { getMergedTopology } from "../presentation/_lib/get-merged-topology";
import { deriveStatMasters } from "@/lib/derive-stat-masters";
import { RiskGauge } from "@/components/charts/risk-gauge";
import { MaturityRadar } from "@/components/charts/maturity-radar";
import { SeverityDonut } from "@/components/charts/severity-donut";
import { TRAFFIC_DIRECTION_LABELS } from "@/components/charts/chart-theme";
import { StatusBadge } from "@/components/ui/status-badge";
import { PrintButton } from "../presentation/print-button";

interface PageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ edition?: string }>;
}

const CHAPTERS = [
  { num: 1, title: "Executive Summary", desc: "Risk posture, maturity radar, key metrics" },
  { num: 2, title: "East-West Deep Dive", desc: "Internal segmentation & lateral movement" },
  { num: 3, title: "North-South Perimeter Audit", desc: "Internet exposure & edge defenses" },
  { num: 4, title: "FinOps Cost Matrix", desc: "Network spend optimization opportunities" },
  { num: 5, title: "Observability & BC/DR", desc: "Visibility gaps & continuity risks" },
  { num: 6, title: "Future-State Roadmap", desc: "Phased remediation plan" },
];

function ChapterHeader({ num, title }: { num: number; title: string }) {
  return (
    <div className="mb-4 border-b border-navy-700/40 pb-3">
      <p className="label-caps text-teal-500">Chapter {num}</p>
      <h2 className="mt-0.5 text-lg font-black text-navy-800 dark:text-navy-100">{title}</h2>
    </div>
  );
}

function FindingRow({ f }: { f: Finding }) {
  return (
    <li className="flex items-start gap-3 py-2.5">
      <StatusBadge value={f.severity} variant="severity" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-navy-800 dark:text-navy-100">{f.title}</p>
        <p className="mt-0.5 text-xs text-navy-400">{f.description}</p>
        {f.recommendation && (
          <p className="mt-1 text-xs text-teal-600 dark:text-teal-400">↳ {f.recommendation}</p>
        )}
      </div>
    </li>
  );
}

export default async function ReportBookModePage({ params, searchParams }: PageProps) {
  const { id } = await params;
  const { edition: editionParam } = await searchParams;
  const edition = editionParam === "expanded" ? "expanded" : "condensed";
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
  const records = deriveStatMasters(engagement.findings);

  const riskScore = computeRiskScore(findings);
  const riskInfo = getRiskLabel(riskScore);
  const dims = computeMaturityDimensions(topology, findings);
  const stats = getTopologyStats(topology);
  const phases = buildRemediationPlan(findings);

  const byDirection = (dir: string): Finding[] =>
    engagement.findings.filter((_, i) => records[i].traffic_direction === dir) as Finding[];
  const eastWest = byDirection("east_west");
  const northSouth = byDirection("north_south");

  const costFindings = engagement.findings.filter(
    (f) => /\bAZ-COST-\d+/i.test(f.title) || /cost|finops|optimi[sz]ation/i.test(f.category),
  ) as Finding[];
  const resilienceFindings = engagement.findings.filter((f) =>
    /\bAZ-BCDR-\d+|flow log|network watcher|diagnostic|monitor|observab|bc.?dr|resilien|backup|zone.redundan/i.test(
      `${f.title} ${f.category} ${f.description}`,
    ),
  ) as Finding[];

  const donutData = SEV_ORDER.map((sev) => ({
    severity: sev,
    count: findings.filter((f) => f.severity === sev).length,
  }));

  const listLimit = edition === "expanded" ? Infinity : 5;
  const limited = (items: Finding[]) =>
    items.slice(0, listLimit === Infinity ? items.length : listLimit);

  const hasData = findings.length > 0 || !!topology;
  const base = `/engagements/${id}/report`;

  return (
    <div className="space-y-6">
      {/* ── Toolbar (hidden in print) ── */}
      <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
        <div>
          <h2 className="label-caps text-navy-500">Report</h2>
          <h1 className="mt-0.5 text-xl font-black text-navy-800 dark:text-navy-100">Book Mode Preview</h1>
        </div>
        <div className="flex items-center gap-2">
          {/* Edition toggle */}
          <div className="flex rounded-lg border border-navy-200 p-0.5 dark:border-navy-700" role="group" aria-label="Report edition">
            {(["condensed", "expanded"] as const).map((e) => (
              <Link
                key={e}
                href={`${base}?edition=${e}`}
                aria-current={edition === e ? "page" : undefined}
                className={[
                  "rounded-md px-3 py-1.5 text-xs font-semibold transition-colors",
                  edition === e
                    ? "bg-teal-500 text-navy-900"
                    : "text-navy-500 hover:text-teal-600 dark:text-navy-300 dark:hover:text-teal-400",
                ].join(" ")}
              >
                {e[0].toUpperCase() + e.slice(1)}
              </Link>
            ))}
          </div>
          <PrintButton />
        </div>
      </div>

      {!hasData && (
        <div className="glass flex flex-col items-center gap-3 rounded-xl border border-dashed border-navy-700 px-8 py-10 text-center print:hidden">
          <p className="text-sm font-semibold text-navy-300">No assessment data yet</p>
          <p className="text-xs text-navy-500">
            Run discovery and AI analysis to populate the report.{" "}
            <Link href={`/engagements/${id}/discovery`} className="font-semibold text-teal-500 hover:underline">
              Go to Discovery →
            </Link>
          </p>
        </div>
      )}

      {/* ── Cover ── */}
      <section className="page-break glass flex min-h-[60vh] flex-col items-center justify-center gap-6 rounded-xl p-10 text-center">
        <Image src="/cbts-logo-dark-teal.svg" alt="CBTS" width={180} height={48} className="dark:invert-0" />
        <div>
          <p className="label-caps text-teal-500">Cloud Network Assessment</p>
          <h2 className="mt-2 text-3xl font-black text-navy-800 dark:text-navy-100">
            {engagement.clientOrg}
          </h2>
          <p className="mt-1 text-sm text-navy-400">{engagement.name}</p>
        </div>
        <div className="text-xs text-navy-500">
          <p>
            {edition === "expanded" ? "Expanded Edition" : "Condensed Edition"} ·{" "}
            {new Date().toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}
          </p>
          {jobDate && (
            <p className="mt-0.5">
              Data as of {new Date(jobDate).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}
            </p>
          )}
        </div>
      </section>

      {/* ── Table of Contents ── */}
      <section className="page-break glass rounded-xl p-6">
        <h2 className="label-caps mb-4 text-navy-500">Table of Contents</h2>
        <ol className="space-y-2.5">
          {CHAPTERS.map((ch) => (
            <li key={ch.num} className="flex items-baseline gap-3">
              <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-teal-50 text-xs font-black text-teal-700 dark:bg-teal-900/40 dark:text-teal-300">
                {ch.num}
              </span>
              <div>
                <p className="text-sm font-semibold text-navy-800 dark:text-navy-100">{ch.title}</p>
                <p className="text-xs text-navy-400">{ch.desc}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {/* ── Chapter 1: Executive Summary ── */}
      <section className="page-break glass rounded-xl p-6">
        <ChapterHeader num={1} title="Executive Summary" />
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <div className="flex flex-col items-center gap-2">
            <RiskGauge score={riskScore} color={riskInfo.color} />
            <p className={`text-lg font-black ${riskInfo.textClass}`}>{riskInfo.label}</p>
          </div>
          <div className="flex flex-col items-center gap-2">
            <MaturityRadar dims={dims} />
            <p className="label-caps text-navy-500">Maturity Dimensions</p>
          </div>
        </div>
        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-5">
          {SEV_ORDER.map((sev) => {
            const count = findings.filter((f) => f.severity === sev).length;
            const style = SEV_COLORS[sev];
            return (
              <div key={sev} className="rounded-xl border border-navy-700/40 p-3 text-center">
                <p className={`text-2xl font-black ${style.text}`}>{count}</p>
                <p className="mt-0.5 text-xs font-semibold uppercase tracking-wide text-navy-400">
                  {sev === "INFORMATIONAL" ? "Info" : sev[0] + sev.slice(1).toLowerCase()}
                </p>
              </div>
            );
          })}
        </div>
        {topology && (
          <p className="mt-4 text-xs text-navy-400">
            Assessment scope: {stats.subscriptions} subscription{stats.subscriptions !== 1 ? "s" : ""},{" "}
            {stats.vnets} VNets, {stats.subnets} subnets, {stats.firewalls} firewalls,{" "}
            {stats.publicIps} public IPs.
          </p>
        )}
      </section>

      {/* ── Chapter 2: East-West ── */}
      <section className="page-break glass rounded-xl p-6">
        <ChapterHeader num={2} title="East-West Deep Dive" />
        <p className="mb-3 text-xs text-navy-400">
          Internal traffic between VNets, subnets, and workloads — segmentation, peering, and
          lateral-movement exposure. {eastWest.length} finding{eastWest.length !== 1 ? "s" : ""} classified{" "}
          {TRAFFIC_DIRECTION_LABELS.east_west}.
        </p>
        {eastWest.length === 0 ? (
          <p className="py-4 text-center text-xs text-navy-500">No East-West findings recorded.</p>
        ) : (
          <ul className="divide-y divide-navy-700/30">
            {limited(eastWest).map((f, i) => <FindingRow key={f.id ?? i} f={f} />)}
          </ul>
        )}
        {edition === "condensed" && eastWest.length > 5 && (
          <p className="mt-2 text-xs text-navy-500">
            + {eastWest.length - 5} more in the Expanded edition.
          </p>
        )}
      </section>

      {/* ── Chapter 3: North-South ── */}
      <section className="page-break glass rounded-xl p-6">
        <ChapterHeader num={3} title="North-South Perimeter Audit" />
        <p className="mb-3 text-xs text-navy-400">
          Ingress/egress paths, internet exposure, and edge defenses (firewall, WAF, DDoS, gateways).{" "}
          {northSouth.length} finding{northSouth.length !== 1 ? "s" : ""} classified{" "}
          {TRAFFIC_DIRECTION_LABELS.north_south}.
        </p>
        {northSouth.length === 0 ? (
          <p className="py-4 text-center text-xs text-navy-500">No North-South findings recorded.</p>
        ) : (
          <ul className="divide-y divide-navy-700/30">
            {limited(northSouth).map((f, i) => <FindingRow key={f.id ?? i} f={f} />)}
          </ul>
        )}
        {edition === "condensed" && northSouth.length > 5 && (
          <p className="mt-2 text-xs text-navy-500">
            + {northSouth.length - 5} more in the Expanded edition.
          </p>
        )}
      </section>

      {/* ── Chapter 4: FinOps ── */}
      <section className="page-break glass rounded-xl p-6">
        <ChapterHeader num={4} title="FinOps Cost Matrix" />
        {costFindings.length === 0 ? (
          <p className="py-4 text-center text-xs text-navy-500">
            No cost-optimization findings recorded. FinOps analysis (AZ-COST rules) populates this
            chapter once enabled.
          </p>
        ) : (
          <ul className="divide-y divide-navy-700/30">
            {limited(costFindings).map((f, i) => <FindingRow key={f.id ?? i} f={f} />)}
          </ul>
        )}
      </section>

      {/* ── Chapter 5: Observability & BC/DR ── */}
      <section className="page-break glass rounded-xl p-6">
        <ChapterHeader num={5} title="Observability & BC/DR" />
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <div>
            <p className="label-caps mb-1 text-navy-500">All Findings by Severity</p>
            <SeverityDonut data={donutData} height={220} />
          </div>
          <div>
            {resilienceFindings.length === 0 ? (
              <p className="py-4 text-xs text-navy-500">
                No observability or continuity gaps identified.
              </p>
            ) : (
              <ul className="divide-y divide-navy-700/30">
                {limited(resilienceFindings).map((f, i) => <FindingRow key={f.id ?? i} f={f} />)}
              </ul>
            )}
          </div>
        </div>
      </section>

      {/* ── Chapter 6: Roadmap ── */}
      <section className="glass rounded-xl p-6">
        <ChapterHeader num={6} title="Future-State Roadmap" />
        {phases.length === 0 ? (
          <p className="py-4 text-center text-xs text-navy-500">
            No remediation items — the phased roadmap is built from actionable findings.
          </p>
        ) : (
          <div className="space-y-5">
            {phases.map((phase) => (
              <div key={phase.phase}>
                <div className="mb-2 flex items-baseline gap-2">
                  <p className={`text-sm font-black ${phase.phaseColor}`}>
                    Phase {phase.phase}: {phase.label}
                  </p>
                  <span className="text-xs text-navy-500">({phase.timeframe})</span>
                </div>
                <ul className="space-y-1.5">
                  {(edition === "expanded" ? phase.items : phase.items.slice(0, 4)).map((item, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs">
                      <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-teal-500" aria-hidden="true" />
                      <div>
                        <span className="font-semibold text-navy-800 dark:text-navy-100">{item.title}</span>
                        <span className="text-navy-400"> — {item.recommendation}</span>
                      </div>
                    </li>
                  ))}
                </ul>
                {edition === "condensed" && phase.items.length > 4 && (
                  <p className="mt-1.5 text-xs text-navy-500">
                    + {phase.items.length - 4} more in the Expanded edition.
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
        <p className="mt-5 border-t border-navy-700/40 pt-3 text-xs text-navy-500">
          The current and future-state architecture diagrams are available on the{" "}
          <Link href={`/engagements/${id}/diagram`} className="font-semibold text-teal-500 hover:underline">
            Diagram
          </Link>{" "}
          page. Generated PDF editions are published via{" "}
          <Link href={`/engagements/${id}/deliverables`} className="font-semibold text-teal-500 hover:underline">
            Assessments
          </Link>
          .
        </p>
      </section>
    </div>
  );
}
