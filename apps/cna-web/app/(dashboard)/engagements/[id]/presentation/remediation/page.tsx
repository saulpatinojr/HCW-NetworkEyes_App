import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { notFound } from "next/navigation";
import {
  buildRemediationPlan,
  SEV_COLORS,
  type Finding,
} from "../_lib/metrics";

interface PageProps {
  params: Promise<{ id: string }>;
}

const PHASE_ACCENTS = [
  { ring: "border-red-200 dark:border-red-700/60",       bg: "bg-red-50 dark:bg-red-900/10",       icon: "bg-red-50 text-red-600 dark:bg-red-900/40 dark:text-red-400",          num: "text-red-600 dark:text-red-400"    },
  { ring: "border-orange-200 dark:border-orange-700/60", bg: "bg-orange-50 dark:bg-orange-900/10", icon: "bg-orange-50 text-orange-600 dark:bg-orange-900/40 dark:text-orange-400", num: "text-orange-600 dark:text-orange-400" },
  { ring: "border-amber-200 dark:border-amber-700/60",   bg: "bg-amber-50 dark:bg-amber-900/10",   icon: "bg-amber-50 text-amber-600 dark:bg-amber-900/40 dark:text-amber-400",    num: "text-amber-600 dark:text-amber-400"  },
];

export default async function RemediationPage({ params }: PageProps) {
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

  const findings = engagement.findings as Finding[];
  const phases = buildRemediationPlan(findings);

  const totalActionable = findings.filter((f) => f.severity !== "INFORMATIONAL").length;

  return (
    <div className="space-y-5">
      {/* ── Header ── */}
      <div>
        <h2 className="label-caps text-navy-500">Remediation & Transformation Plan</h2>
        <h1 className="mt-0.5 text-xl font-black text-navy-800 dark:text-navy-100">{engagement.clientOrg}</h1>
      </div>

      {/* ── Summary ── */}
      <div className="glass rounded-xl p-5">
        <div className="flex flex-wrap items-center gap-6">
          <div className="text-center">
            <p className="text-3xl font-black text-navy-800 dark:text-navy-100">{totalActionable}</p>
            <p className="mt-0.5 text-xs text-navy-500">Actionable Items</p>
          </div>
          <div className="text-center">
            <p className="text-3xl font-black text-navy-800 dark:text-navy-100">{phases.length}</p>
            <p className="mt-0.5 text-xs text-navy-500">Remediation Phases</p>
          </div>
          <div className="flex-1">
            <div className="flex flex-wrap gap-2">
              {phases.map((phase, i) => {
                const accent = PHASE_ACCENTS[i] ?? PHASE_ACCENTS[2];
                return (
                  <div
                    key={phase.phase}
                    className={`rounded-lg border px-3 py-1.5 ${accent.ring} ${accent.bg}`}
                  >
                    <p className={`text-xs font-bold ${accent.num}`}>{phase.label}</p>
                    <p className="text-xs text-navy-400">{phase.timeframe} · {phase.items.length} item{phase.items.length !== 1 ? "s" : ""}</p>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* ── Introduction ── */}
      <div className="glass rounded-xl p-6">
        <h2 className="mb-3 text-base font-bold text-navy-800 dark:text-navy-100">Remediation Approach</h2>
        <p className="text-sm leading-relaxed text-navy-400 dark:text-navy-300">
          This plan organizes all identified security findings into three phased remediation
          tracks based on severity and business impact. Critical findings require immediate
          escalation and remediation within 30 days. High severity findings should be
          addressed in the 30–90 day window through targeted engineering sprints. Medium and
          low severity items are organized into a 90–180 day roadmap for systematic improvement.
        </p>
        {totalActionable === 0 && (
          <p className="mt-3 text-sm text-navy-500">
            No actionable findings identified. Run discovery and AI analysis to generate
            a remediation plan.
          </p>
        )}
      </div>

      {/* ── Phases ── */}
      {phases.map((phase, i) => {
        const accent = PHASE_ACCENTS[i] ?? PHASE_ACCENTS[2];
        return (
          <div key={phase.phase} className={`glass rounded-xl border p-6 ${accent.ring}`}>
            {/* Phase Header */}
            <div className="mb-5 flex items-center gap-3">
              <div
                className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-sm font-black ${accent.icon}`}
              >
                {phase.phase}
              </div>
              <div>
                <h2 className="text-base font-bold text-navy-800 dark:text-navy-100">{phase.label}</h2>
                <p className="text-xs text-navy-400">
                  Target timeframe: {phase.timeframe} · {phase.items.length} finding{phase.items.length !== 1 ? "s" : ""}
                </p>
              </div>
            </div>

            {/* Items */}
            <div className="space-y-3">
              {phase.items.map((item, j) => {
                const style = SEV_COLORS[item.severity as keyof typeof SEV_COLORS];
                return (
                  <div key={j} className="rounded-xl border border-navy-100/60 bg-navy-50 p-4 dark:border-navy-700/40 dark:bg-navy-800/30">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <p className="text-sm font-semibold text-navy-800 dark:text-navy-100">{item.title}</p>
                      <div className="flex items-center gap-1.5">
                        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${style.badge}`}>
                          {item.severity[0] + item.severity.slice(1).toLowerCase()}
                        </span>
                        <span className="rounded bg-navy-100/60 px-2 py-0.5 text-xs text-navy-500 dark:bg-navy-700/60 dark:text-navy-400">
                          {item.category}
                        </span>
                      </div>
                    </div>
                    <div className="mt-3 flex gap-2">
                      <svg
                        aria-hidden="true"
                        focusable="false"
                        className="mt-0.5 h-4 w-4 shrink-0 text-teal-500"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={2}
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
                        />
                      </svg>
                      <p className="text-xs leading-relaxed text-navy-400 dark:text-navy-300">{item.recommendation}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}

      {/* ── Strategic Roadmap ── */}
      {phases.length > 0 && (
        <div className="glass rounded-xl p-6">
          <h2 className="mb-4 text-base font-bold text-navy-800 dark:text-navy-100">
            Strategic Transformation Roadmap
          </h2>
          <div className="relative">
            {/* Timeline line */}
            <div className="absolute left-4 top-0 h-full w-0.5 bg-navy-200 dark:bg-navy-700/60" />
            <div className="space-y-6 pl-12">
              {[
                { label: "0–30 days",   title: "Immediate Stabilization",   desc: "Resolve all critical vulnerabilities, isolate exposed resources, and apply emergency network controls." },
                { label: "30–90 days",  title: "Security Hardening",        desc: "Deploy NSG policies, remediate high-severity findings, implement network segmentation improvements." },
                { label: "90–180 days", title: "Capability Enhancement",    desc: "Address medium and low findings, implement monitoring improvements, and establish security baselines." },
                { label: "180+ days",   title: "Continuous Improvement",    desc: "Ongoing security posture management, periodic reassessment, and maturity advancement across all dimensions." },
              ].map((item, i) => (
                <div key={i} className="relative">
                  <div className="absolute -left-8 flex h-6 w-6 items-center justify-center rounded-full border-2 border-navy-200 bg-navy-50 text-xs font-bold text-navy-400 dark:border-navy-700 dark:bg-navy-900">
                    {i + 1}
                  </div>
                  <p className="text-xs font-bold text-teal-500">{item.label}</p>
                  <p className="mt-0.5 text-sm font-semibold text-navy-800 dark:text-navy-100">{item.title}</p>
                  <p className="mt-1 text-xs leading-relaxed text-navy-400">{item.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
