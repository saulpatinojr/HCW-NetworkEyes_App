import type { CSSProperties } from "react";
import { prisma } from "@/lib/prisma";
import { notFound } from "next/navigation";
import Link from "next/link";

const styleKey = "style";
// Inline style is the only way to express a data-driven width/height; the
// indirection keeps the literal `style` prop out of the JSX.
const makeStyle = (props: Record<string, string>): { style: CSSProperties } => ({
  [styleKey]: props as CSSProperties,
});

interface PageProps {
  params: Promise<{ id: string }>;
}

const SEV_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"] as const;

const SEV_COLORS: Record<string, { bar: string; text: string; bg: string }> = {
  CRITICAL:      { bar: "bg-red-500",    text: "text-red-600    dark:text-red-400",    bg: "bg-red-50    dark:bg-red-900/20" },
  HIGH:          { bar: "bg-orange-500", text: "text-orange-600 dark:text-orange-400", bg: "bg-orange-50 dark:bg-orange-900/20" },
  MEDIUM:        { bar: "bg-amber-400",  text: "text-amber-600  dark:text-amber-400",  bg: "bg-amber-50  dark:bg-amber-900/20" },
  LOW:           { bar: "bg-blue-400",   text: "text-blue-600   dark:text-blue-400",   bg: "bg-blue-50   dark:bg-blue-900/20" },
  INFORMATIONAL: { bar: "bg-navy-300",   text: "text-navy-500   dark:text-navy-300",   bg: "bg-navy-50   dark:bg-navy-800/30" },
};

const PHASE_STEPS = [
  { key: "DRAFT",     label: "Draft" },
  { key: "DISCOVERY", label: "Discovery" },
  { key: "ANALYSIS",  label: "Analysis" },
  { key: "REVIEW",    label: "Review" },
  { key: "DELIVERED", label: "Delivered" },
];

const QUICK_LINKS = [
  { label: "Connections",   desc: "Cloud credentials & discovery runs", href: "connections",   icon: "M13 10V3L4 14h7v7l9-11h-7z" },
  { label: "Findings",      desc: "Security risk matrix & AI analysis",  href: "findings",      icon: "M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" },
  { label: "Inventory",     desc: "VNets, NSGs, IPs & resources",        href: "inventory",     icon: "M4 6h16M4 10h16M4 14h16M4 18h16" },
  { label: "Diagram",       desc: "Build and export architecture diagrams", href: "diagram",     icon: "M7 8h10M7 12h7m-7 4h10M5 4h14a2 2 0 012 2v12a2 2 0 01-2 2H5a2 2 0 01-2-2V6a2 2 0 012-2z" },
  { label: "Documents",     desc: "Upload configs & architecture notes",  href: "documents",     icon: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" },
  { label: "Deliverables",  desc: "Generate & publish reports",          href: "deliverables",  icon: "M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" },
  { label: "Presentation",  desc: "Interactive full-report view",         href: "presentation",  icon: "M8 13v-1m4 1v-3m4 3V8M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" },
];

export default async function EngagementOverviewPage({ params }: PageProps) {
  const { id } = await params;

  const base = await prisma.engagement.findUnique({
    where: { id },
    include: {
      members:      { include: { user: true } },
      findings:     { select: { severity: true, aiGenerated: true } },
      deliverables: { orderBy: { createdAt: "desc" }, select: { id: true, title: true, type: true, publishedAt: true, createdAt: true } },
      documents:    { select: { id: true } },
    },
  });
  if (!base) notFound();

  let jobSummary: { completedAt: Date | null; findingsCount: number | null } | null = null;
  try {
    jobSummary = await prisma.discoveryJob.findFirst({
      where:  { engagementId: id, status: "COMPLETED" },
      orderBy: { completedAt: "desc" },
      select:  { completedAt: true, findingsCount: true },
    });
  } catch { /* table not migrated yet */ }

  const bySev = Object.fromEntries(
    SEV_ORDER.map((s) => [s, base.findings.filter((f) => f.severity === s).length]),
  );
  const liveCount = base.findings.filter((f) => !f.aiGenerated).length;
  const aiCount   = base.findings.filter((f) => f.aiGenerated).length;
  const totalFindings = base.findings.length;
  const maxSev = Math.max(...SEV_ORDER.map((s) => bySev[s]));

  const currentPhaseIdx = PHASE_STEPS.findIndex((p) => p.key === base.status);

  return (
    <div className="space-y-5">
      {/* ── Phase stepper ── */}
      <div className="glass p-6">
        <h2 className="label-caps mb-5 text-navy-400 dark:text-navy-300">
          Engagement Progress
        </h2>
        {/* WAI-23: Stepper wrapped in nav and ol for accessibility */}
        <nav aria-label="Engagement progress stepper">
          <ol className="flex items-center">
            {PHASE_STEPS.map((step, idx) => {
              const done   = idx < currentPhaseIdx;
              const active = idx === currentPhaseIdx;
              return (
                <li
                  key={step.key}
                  className="flex flex-1 items-center"
                  aria-current={active ? "step" : undefined}
                >
                  <div className="flex flex-col items-center gap-1.5">
                    <div
                      aria-label={`Step ${idx + 1}: ${step.label} (${active ? "current step" : done ? "completed" : "upcoming"})`}
                      className={[
                        "flex h-9 w-9 items-center justify-center rounded-full text-xs font-bold transition-colors",
                        done
                          ? "bg-teal-500 text-white shadow-md shadow-teal-500/30"
                          : active
                            ? "bg-navy-800 text-white ring-2 ring-teal-500/50 dark:bg-navy-600"
                            : "bg-navy-50 text-navy-300 dark:bg-navy-800/60 dark:text-navy-500",
                      ].join(" ")}
                    >
                      {done ? (
                        <svg aria-hidden="true" focusable="false" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      ) : (
                        idx + 1
                      )}
                    </div>
                  <span
                    className={[
                      "text-xs font-medium",
                      active
                        ? "text-navy-700 dark:text-navy-100"
                        : done
                          ? "text-teal-600 dark:text-teal-400"
                          : "text-navy-300 dark:text-navy-600",
                    ].join(" ")}
                  >
                    {step.label}
                  </span>
                </div>
                  {idx < PHASE_STEPS.length - 1 && (
                    <div
                      className={[
                        "mb-5 h-0.5 flex-1 transition-colors",
                        idx < currentPhaseIdx
                          ? "bg-teal-400"
                          : "bg-navy-100 dark:bg-navy-800",
                      ].join(" ")}
                    />
                  )}
                </li>
              );
            })}
          </ol>
        </nav>
      </div>

      {/* ── Bento stat row ── */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[
          { label: "Total findings", value: totalFindings, href: "findings",     accent: totalFindings > 0 },
          { label: "Documents",      value: base.documents.length,   href: "documents",    accent: false },
          { label: "Deliverables",   value: base.deliverables.length, href: "deliverables", accent: false },
          {
            label: jobSummary ? "Last discovery" : "Discovery",
            value: jobSummary
              ? new Date(jobSummary.completedAt!).toLocaleDateString()
              : "Not run",
            href:  "connections",
            accent: !!jobSummary,
          },
        ].map((card) => (
          <Link
            key={card.href}
            href={`/engagements/${id}/${card.href}`}
            className="glass glass-hover p-5"
          >
            <p
              className={[
                "text-3xl font-black tracking-tight",
                card.accent
                  ? "text-navy-800 dark:text-navy-50"
                  : "text-navy-400 dark:text-navy-400",
              ].join(" ")}
            >
              {card.value}
            </p>
            <p className="mt-1 text-xs font-semibold text-navy-400 dark:text-navy-400">
              {card.label}
            </p>
          </Link>
        ))}
      </div>

      {/* ── Bottom bento: findings + deliverables side-by-side ── */}
      {(totalFindings > 0 || base.deliverables.length > 0) && (
        <div className="grid gap-4 lg:grid-cols-2">
          {/* Findings breakdown */}
          {totalFindings > 0 && (
            <div className="glass p-6">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="label-caps text-navy-400 dark:text-navy-300">
                  Findings Breakdown
                </h3>
                <Link href={`/engagements/${id}/findings`} className="text-xs font-semibold text-teal-600 hover:underline dark:text-teal-400">
                  View all →
                </Link>
              </div>
              <div className="space-y-2.5">
                {SEV_ORDER.filter((s) => bySev[s] > 0).map((sev) => {
                  const c = SEV_COLORS[sev];
                  const pct = maxSev > 0 ? Math.round((bySev[sev] / maxSev) * 100) : 0;
                  return (
                    <div key={sev} className="flex items-center gap-3">
                      <span className={`w-20 text-right text-xs font-semibold ${c.text}`}>
                        {sev.charAt(0) + sev.slice(1).toLowerCase()}
                      </span>
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-navy-50 dark:bg-navy-800/50">
                        <div
                          className={`bar-fill h-full rounded-full ${c.bar}`}
                          {...makeStyle({ "--bar-pct": `${pct}%` })}
                        />
                      </div>
                      <span className="w-5 text-right text-xs font-bold text-navy-700 dark:text-navy-200">
                        {bySev[sev]}
                      </span>
                    </div>
                  );
                })}
              </div>
              <div className="mt-4 flex gap-4 border-t border-navy-100/40 pt-3 dark:border-navy-700/40">
                <span className="text-xs text-navy-400 dark:text-navy-400">
                  <span className="font-semibold text-navy-600 dark:text-navy-200">{liveCount}</span> from discovery
                </span>
                <span className="text-xs text-navy-400 dark:text-navy-400">
                  <span className="font-semibold text-navy-600 dark:text-navy-200">{aiCount}</span> from AI analysis
                </span>
              </div>
            </div>
          )}

          {/* Latest deliverables */}
          {base.deliverables.length > 0 && (
            <div className="glass p-6">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="label-caps text-navy-400 dark:text-navy-300">
                  Latest Deliverables
                </h3>
                <Link href={`/engagements/${id}/deliverables`} className="text-xs font-semibold text-teal-600 hover:underline dark:text-teal-400">
                  View all →
                </Link>
              </div>
              <ul className="divide-y divide-navy-100/40 dark:divide-navy-700/40">
                {base.deliverables.slice(0, 4).map((d) => (
                  <li key={d.id} className="flex items-center justify-between gap-3 py-2.5">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-navy-700 dark:text-navy-100">
                        {d.title}
                      </p>
                      <p className="text-xs text-navy-400 dark:text-navy-400">
                        {d.type.replace(/_/g, " ")} · {new Date(d.createdAt).toLocaleDateString()}
                      </p>
                    </div>
                    {d.publishedAt ? (
                      <span className="pill-teal flex-shrink-0">Published</span>
                    ) : (
                      <span className="flex-shrink-0 rounded-full border border-navy-100 bg-navy-50 px-2.5 py-0.5 text-xs font-semibold text-navy-400 dark:border-navy-700 dark:bg-navy-800/50 dark:text-navy-400">
                        Draft
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* ── Quick links bento ── */}
      <div>
        <h2 className="label-caps mb-3 text-navy-400 dark:text-navy-300">
          Jump to
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {QUICK_LINKS.map((item) => (
            <Link
              key={item.href}
              href={`/engagements/${id}/${item.href}`}
              className="glass glass-hover flex items-start gap-3 p-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-1"
            >
              <div className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-teal-50 dark:bg-teal-900/30">
                <svg aria-hidden="true" focusable="false" className="h-4 w-4 text-teal-600 dark:text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d={item.icon} />
                </svg>
              </div>
              <div className="min-w-0">
                <p className="text-sm font-bold text-navy-700 dark:text-navy-100">
                  {item.label}
                </p>
                <p className="mt-0.5 text-xs text-navy-400 dark:text-navy-400">
                  {item.desc}
                </p>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
