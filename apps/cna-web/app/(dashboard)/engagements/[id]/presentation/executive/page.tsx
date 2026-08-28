import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { notFound } from "next/navigation";
import {
  computeRiskScore,
  getRiskLabel,
  computeMaturityDimensions,
  getTopologyStats,
  SEV_ORDER,
  SEV_COLORS,
  type Finding,
} from "../_lib/metrics";
import { getMergedTopology } from "../_lib/get-merged-topology";

interface PageProps {
  params: Promise<{ id: string }>;
}

const styleKey = "style";
const makeStyle = (props: Record<string, string>) => ({ [styleKey]: props }) as any;

export default async function ExecutivePage({ params }: PageProps) {
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

  const avgMaturity = Math.round(dims.reduce((s, d) => s + d.score, 0) / dims.length);

  // Top risks: CRITICAL first, then HIGH, up to 6
  const topRisks = [
    ...bySev["CRITICAL"] ?? [],
    ...bySev["HIGH"] ?? [],
  ].slice(0, 6);

  const actionableCount = findings.filter((f) => f.severity !== "INFORMATIONAL").length;
  const date = jobDate
    ? new Date(jobDate).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })
    : new Date().toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });

  return (
    <div className="space-y-5">
      {/* ── Header ── */}
      <div>
        <h2 className="label-caps text-navy-500">Executive Risk Assessment</h2>
        <h1 className="mt-0.5 text-xl font-black text-navy-800 dark:text-navy-100">{engagement.clientOrg}</h1>
      </div>

      {/* ── Key Metrics ── */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="glass rounded-xl p-4 text-center">
          <p className={`text-4xl font-black ${riskInfo.textClass}`}>{riskScore}</p>
          <p className="mt-1 text-xs font-semibold text-navy-400">Risk Score</p>
          <p className={`mt-1 text-xs font-bold ${riskInfo.textClass}`}>{riskInfo.label}</p>
        </div>
        <div className="glass rounded-xl p-4 text-center">
          <p className="text-4xl font-black text-red-600 dark:text-red-400">{bySev["CRITICAL"]?.length ?? 0}</p>
          <p className="mt-1 text-xs font-semibold text-navy-400">Critical Findings</p>
          <p className="mt-1 text-xs text-navy-500">Immediate attention</p>
        </div>
        <div className="glass rounded-xl p-4 text-center">
          <p className="text-4xl font-black text-navy-800 dark:text-navy-100">{actionableCount}</p>
          <p className="mt-1 text-xs font-semibold text-navy-400">Total Findings</p>
          <p className="mt-1 text-xs text-navy-500">{findings.length} including info</p>
        </div>
        <div className="glass rounded-xl p-4 text-center">
          <p className="text-4xl font-black text-teal-700 dark:text-teal-400">{avgMaturity}/10</p>
          <p className="mt-1 text-xs font-semibold text-navy-400">Avg Maturity</p>
          <p className="mt-1 text-xs text-navy-500">Across 5 dimensions</p>
        </div>
      </div>

      {/* ── Risk Narrative ── */}
      <div className="glass rounded-xl p-6">
        <h2 className="mb-3 text-base font-bold text-navy-800 dark:text-navy-100">Assessment Summary</h2>
        <div className="space-y-3 text-sm leading-relaxed text-navy-400 dark:text-navy-300">
          <p>
            This Cloud Network Assessment was conducted on{" "}
            <strong className="text-navy-800 dark:text-navy-100">{engagement.clientOrg}</strong>{" "}
            {date && `as of ${date}`}.{" "}
            {topology
              ? `The assessment covered ${stats.subscriptions} Azure subscription${stats.subscriptions !== 1 ? "s" : ""}, ${stats.vnets} virtual network${stats.vnets !== 1 ? "s" : ""}, and ${stats.subnets} subnet${stats.subnets !== 1 ? "s" : ""}.`
              : "No topology discovery data was available at time of assessment."}
          </p>
          <p>
            The environment received an overall risk score of{" "}
            <strong className={riskInfo.textClass}>{riskScore}/100 ({riskInfo.label})</strong>.{" "}
            {actionableCount > 0
              ? `A total of ${actionableCount} actionable security finding${actionableCount !== 1 ? "s" : ""} ${actionableCount !== 1 ? "were" : "was"} identified, including ${bySev["CRITICAL"]?.length ?? 0} critical and ${bySev["HIGH"]?.length ?? 0} high severity issues requiring near-term remediation.`
              : "No actionable security findings were identified during this assessment."}
          </p>
          {avgMaturity < 7 && (
            <p>
              The security maturity assessment indicates that multiple foundational capabilities
              require strengthening. Priority investment areas include{" "}
              {dims
                .filter((d) => d.score < 6)
                .map((d) => d.fullLabel)
                .join(", ") || "monitoring and access control"}.
            </p>
          )}
          {avgMaturity >= 7 && (
            <p>
              The organization demonstrates a solid baseline security posture across most maturity
              dimensions. Continued investment in the identified gaps will further reduce exposure
              and support regulatory compliance objectives.
            </p>
          )}
        </div>
      </div>

      {/* ── Severity Breakdown ── */}
      <div className="glass rounded-xl p-6">
        <h2 className="mb-4 text-base font-bold text-navy-800 dark:text-navy-100">Finding Summary by Severity</h2>
        <div className="space-y-3">
          {SEV_ORDER.filter((s) => s !== "INFORMATIONAL").map((sev) => {
            const count = bySev[sev]?.length ?? 0;
            const style = SEV_COLORS[sev as keyof typeof SEV_COLORS];
            const pct = findings.length > 0 ? (count / findings.length) * 100 : 0;
            return (
              <div key={sev} className="flex items-center gap-4">
                <span className={`w-20 text-xs font-semibold ${style.text}`}>
                  {sev[0] + sev.slice(1).toLowerCase()}
                </span>
                <div className="flex-1 overflow-hidden rounded-full bg-navy-100 dark:bg-navy-800">
                  {/* eslint-disable-next-line react/forbid-dom-props */}
                  <div className={`h-3 rounded-full ${style.bar}`} {...makeStyle({ width: `${pct}%` })} />
                </div>
                <span className={`w-6 text-right text-sm font-black ${style.text}`}>{count}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Top Risks ── */}
      {topRisks.length > 0 && (
        <div className="glass rounded-xl p-6">
          <h2 className="mb-4 text-base font-bold text-navy-800 dark:text-navy-100">Top Risks Requiring Attention</h2>
          <div className="space-y-3">
            {topRisks.map((f, i) => {
              const style = SEV_COLORS[f.severity as keyof typeof SEV_COLORS];
              return (
                <div key={f.id ?? i} className={`rounded-xl border p-4 ${style.bg}`}>
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-sm font-semibold text-navy-800 dark:text-navy-100">{f.title}</p>
                    <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${style.badge}`}>
                      {f.severity[0] + f.severity.slice(1).toLowerCase()}
                    </span>
                  </div>
                  <p className="mt-1.5 text-xs leading-relaxed text-navy-400 dark:text-navy-300">{f.description}</p>
                  {f.recommendation && (
                    <p className="mt-2 text-xs text-navy-400">
                      <span className="font-semibold text-navy-500 dark:text-navy-200">Recommendation: </span>
                      {f.recommendation}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Maturity Summary ── */}
      <div className="glass rounded-xl p-6">
        <h2 className="mb-4 text-base font-bold text-navy-800 dark:text-navy-100">Security Maturity Summary</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-5">
          {dims.map((d) => {
            const scoreColor =
              d.score >= 8 ? "text-green-700 border-green-200 bg-green-50/60 dark:text-green-400 dark:border-green-800/40 dark:bg-green-900/10"
              : d.score >= 6 ? "text-amber-700 border-amber-200 bg-amber-50/60 dark:text-amber-400 dark:border-amber-800/40 dark:bg-amber-900/10"
              : "text-red-700 border-red-200 bg-red-50/60 dark:text-red-400 dark:border-red-800/40 dark:bg-red-900/10";
            return (
              <div
                key={d.label}
                className={`rounded-xl border p-3 text-center ${scoreColor}`}
              >
                <p className="text-2xl font-black">{d.score}/10</p>
                <p className="mt-1 text-xs font-semibold">{d.fullLabel}</p>
                <p className="mt-1.5 text-xs text-navy-400">{d.detail}</p>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Recommended Next Steps ── */}
      <div className="glass rounded-xl p-6">
        <h2 className="mb-4 text-base font-bold text-navy-800 dark:text-navy-100">Recommended Next Steps</h2>
        <ol className="space-y-3">
          {(bySev["CRITICAL"]?.length ?? 0) > 0 && (
            <li className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-red-50 text-xs font-bold text-red-600 dark:bg-red-900/40 dark:text-red-400">1</span>
              <p className="text-sm text-navy-400 dark:text-navy-300">
                <strong className="text-navy-800 dark:text-navy-100">Immediate:</strong> Address all{" "}
                {bySev["CRITICAL"]?.length} critical finding{bySev["CRITICAL"]?.length !== 1 ? "s" : ""} within 30 days. These represent immediate security exposure.
              </p>
            </li>
          )}
          {(bySev["HIGH"]?.length ?? 0) > 0 && (
            <li className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-orange-50 text-xs font-bold text-orange-600 dark:bg-orange-900/40 dark:text-orange-400">
                {(bySev["CRITICAL"]?.length ?? 0) > 0 ? 2 : 1}
              </span>
              <p className="text-sm text-navy-400 dark:text-navy-300">
                <strong className="text-navy-800 dark:text-navy-100">Short-term:</strong> Remediate{" "}
                {bySev["HIGH"]?.length} high severity finding{bySev["HIGH"]?.length !== 1 ? "s" : ""} within 90 days through targeted sprint work.
              </p>
            </li>
          )}
          {dims.some((d) => d.score < 5) && (
            <li className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber-50 text-xs font-bold text-amber-600 dark:bg-amber-900/40 dark:text-amber-400">
                {((bySev["CRITICAL"]?.length ?? 0) > 0 ? 1 : 0) + ((bySev["HIGH"]?.length ?? 0) > 0 ? 1 : 0) + 1}
              </span>
              <p className="text-sm text-navy-400 dark:text-navy-300">
                <strong className="text-navy-800 dark:text-navy-100">Strategic:</strong> Invest in maturing{" "}
                {dims
                  .filter((d) => d.score < 5)
                  .map((d) => d.fullLabel)
                  .join(" and ")}{" "}
                capabilities as part of a 6-month roadmap.
              </p>
            </li>
          )}
          <li className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-teal-50 text-xs font-bold text-teal-700 dark:bg-teal-900/40 dark:text-teal-400">✓</span>
            <p className="text-sm text-navy-400 dark:text-navy-300">
              <strong className="text-navy-800 dark:text-navy-100">Ongoing:</strong> Review the full technical findings
              and remediation plan for detailed action items with implementation guidance.
            </p>
          </li>
        </ol>
      </div>
    </div>
  );
}
