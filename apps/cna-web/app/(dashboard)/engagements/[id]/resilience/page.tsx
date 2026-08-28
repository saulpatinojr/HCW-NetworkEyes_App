import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { notFound } from "next/navigation";
import Link from "next/link";
import { EmptyState } from "@/components/ui/empty-state";
import { SeverityDonut } from "@/components/charts/severity-donut";
import { StatusBadge } from "@/components/ui/status-badge";
import { SEV_ORDER } from "../presentation/_lib/metrics";

interface PageProps {
  params: Promise<{ id: string }>;
}

// Observability / BC-DR signal matchers (Phase B rule prefixes + legacy heuristics)
const RESILIENCE_CATEGORY_RE = /observab|monitor|bc.?dr|resilien|continuity|backup|availability|disaster/i;
const RESILIENCE_TITLE_RE =
  /\bAZ-BCDR-\d+|flow log|network watcher|diagnostic|log analytics|monitor|zone.redundan|active.passive|single.point|spof|backup|disaster recovery/i;

export default async function ResiliencePage({ params }: PageProps) {
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

  const resilienceFindings = engagement.findings.filter(
    (f) =>
      RESILIENCE_CATEGORY_RE.test(f.category) ||
      RESILIENCE_TITLE_RE.test(`${f.title} ${f.description}`),
  );

  const donutData = SEV_ORDER.map((sev) => ({
    severity: sev,
    count: resilienceFindings.filter((f) => f.severity === sev).length,
  }));

  const observability = resilienceFindings.filter((f) =>
    /flow log|network watcher|diagnostic|log analytics|monitor|observab/i.test(`${f.title} ${f.category} ${f.description}`),
  );
  const bcdr = resilienceFindings.filter((f) => !observability.includes(f));

  return (
    <div className="space-y-5">
      {/* ── Header ── */}
      <div>
        <h2 className="label-caps text-navy-500">Observability &amp; Resilience</h2>
        <h1 className="mt-0.5 text-xl font-black text-navy-800 dark:text-navy-100">
          Monitoring, Logging &amp; BC/DR Posture
        </h1>
        <p className="mt-1 text-xs text-navy-400">
          Visibility gaps (flow logs, diagnostics, monitoring) and business-continuity risks
          (zone redundancy, single points of failure, gateway resiliency).
        </p>
      </div>

      {resilienceFindings.length === 0 ? (
        <EmptyState title="No observability or BC/DR findings">
          Either no gaps were detected or analysis has not run yet.{" "}
          <Link href={`/engagements/${id}/analysis`} className="font-semibold text-teal-600 dark:text-teal-400 hover:underline">
            Run AI analysis →
          </Link>
        </EmptyState>
      ) : (
        <>
          {/* ── Severity donut + summary ── */}
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <div className="glass rounded-xl p-5">
              <h2 className="label-caps mb-2 text-navy-500">Severity Distribution</h2>
              <SeverityDonut data={donutData} />
            </div>
            <div className="glass flex flex-col justify-center gap-4 rounded-xl p-6">
              {[
                { label: "Observability gaps", value: observability.length, desc: "Flow logs, diagnostics, monitoring coverage" },
                { label: "BC/DR risks", value: bcdr.length, desc: "Redundancy, failover, single points of failure" },
                { label: "Total resilience findings", value: resilienceFindings.length, desc: "Across all severities" },
              ].map((s) => (
                <div key={s.label}>
                  <p className="text-3xl font-black text-navy-800 dark:text-navy-100">{s.value}</p>
                  <p className="text-sm font-semibold text-navy-500 dark:text-navy-300">{s.label}</p>
                  <p className="text-xs text-navy-400">{s.desc}</p>
                </div>
              ))}
            </div>
          </div>

          {/* ── Finding lists ── */}
          {[
            { title: "Observability & Monitoring", items: observability },
            { title: "Business Continuity & DR", items: bcdr },
          ]
            .filter((g) => g.items.length > 0)
            .map((group) => (
              <div key={group.title} className="glass rounded-xl p-5">
                <h2 className="label-caps mb-4 text-navy-500">
                  {group.title} ({group.items.length})
                </h2>
                <ul className="divide-y divide-navy-700/30">
                  {group.items.map((f) => (
                    <li key={f.id} className="flex items-start gap-3 py-3">
                      <StatusBadge value={f.severity} variant="severity" />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold text-navy-800 dark:text-navy-100">{f.title}</p>
                        <p className="mt-0.5 line-clamp-2 text-xs text-navy-400">{f.description}</p>
                        {f.recommendation && (
                          <p className="mt-1 text-xs text-teal-600 dark:text-teal-400">
                            ↳ {f.recommendation}
                          </p>
                        )}
                      </div>
                      <span className="flex-shrink-0 rounded-full border border-navy-200 px-2 py-0.5 text-xs text-navy-400 dark:border-navy-700">
                        {f.category}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
        </>
      )}
    </div>
  );
}
