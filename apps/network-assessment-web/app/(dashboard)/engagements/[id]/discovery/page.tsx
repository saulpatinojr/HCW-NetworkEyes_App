import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { notFound } from "next/navigation";
import Link from "next/link";
import { StatusBadge } from "@/components/ui/status-badge";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function DiscoveryLandingPage({ params }: PageProps) {
  const { id } = await params;
  const session = await auth();

  const engagement = await prisma.engagement.findUnique({
    where: { id },
    include: {
      members: true,
      cloudCredentials: {
        orderBy: { createdAt: "asc" },
        select: { id: true, label: true, platform: true, subscriptionIds: true, createdAt: true },
      },
      documents: { select: { id: true } },
      discoveryJobs: {
        orderBy: { createdAt: "desc" },
        take: 8,
        include: { credential: { select: { label: true } } },
      },
    },
  });
  if (!engagement) notFound();
  const isMember = engagement.members.some((m) => m.userId === session?.user?.id);
  if (!isMember) notFound();

  const completedJobs = engagement.discoveryJobs.filter((j) => j.status === "COMPLETED");
  const lastCompleted = completedJobs[0] ?? null;
  const totalDiscoveryFindings = completedJobs.reduce((s, j) => s + (j.findingsCount ?? 0), 0);

  const LINKS = [
    {
      label: "Connections",
      desc: "Manage credentials & run discovery",
      href: "connections",
      icon: "M13 10V3L4 14h7v7l9-11h-7z",
    },
    {
      label: "Documents",
      desc: "Upload configs & architecture notes",
      href: "documents",
      icon: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
    },
    {
      label: "Inventory",
      desc: "Browse discovered resources",
      href: "inventory",
      icon: "M4 6h16M4 10h16M4 14h16M4 18h16",
    },
  ];

  return (
    <div className="space-y-5">
      {/* ── Header ── */}
      <div>
        <h2 className="label-caps text-navy-500">Discovery &amp; Ingestion</h2>
        <h1 className="mt-0.5 text-xl font-black text-navy-800 dark:text-navy-100">
          Data Ingestion Hub
        </h1>
        <p className="mt-1 text-xs text-navy-400">
          Everything that feeds the assessment: cloud credentials, discovery runs, and uploaded
          documents. Run discovery from Connections, then explore findings and dashboards.
        </p>
      </div>

      {/* ── Stat row ── */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[
          { label: "Cloud credentials", value: engagement.cloudCredentials.length, href: "connections" },
          { label: "Documents ingested", value: engagement.documents.length, href: "documents" },
          { label: "Discovery findings", value: totalDiscoveryFindings, href: "findings" },
          {
            label: "Last discovery",
            value: lastCompleted?.completedAt
              ? new Date(lastCompleted.completedAt).toLocaleDateString()
              : "Not run",
            href: "connections",
          },
        ].map((card) => (
          <Link key={card.label} href={`/engagements/${id}/${card.href}`} className="glass glass-hover p-5">
            <p className="text-3xl font-black tracking-tight text-navy-800 dark:text-navy-50">
              {card.value}
            </p>
            <p className="mt-1 text-xs font-semibold text-navy-400">{card.label}</p>
          </Link>
        ))}
      </div>

      {/* ── Credentials ── */}
      <div className="glass rounded-xl p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="label-caps text-navy-500">Cloud Credentials</h2>
          <Link href={`/engagements/${id}/connections`} className="text-xs font-semibold text-teal-600 hover:underline dark:text-teal-400">
            Manage →
          </Link>
        </div>
        {engagement.cloudCredentials.length === 0 ? (
          <p className="py-6 text-center text-xs text-navy-400 dark:text-navy-400">
            No cloud credentials yet — add one on the Connections page to begin discovery.
          </p>
        ) : (
          <ul className="divide-y divide-navy-700/30">
            {engagement.cloudCredentials.map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-navy-800 dark:text-navy-100">{c.label}</p>
                  <p className="text-xs text-navy-400">
                    {c.platform} ·{" "}
                    {c.subscriptionIds.length > 0
                      ? `${c.subscriptionIds.length} subscription${c.subscriptionIds.length !== 1 ? "s" : ""}`
                      : "all accessible subscriptions"}
                  </p>
                </div>
                <span className="pill-teal flex-shrink-0">{c.platform}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* ── Recent discovery jobs ── */}
      <div className="glass rounded-xl p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="label-caps text-navy-500">Recent Discovery Jobs</h2>
          <Link href={`/engagements/${id}/connections`} className="text-xs font-semibold text-teal-600 hover:underline dark:text-teal-400">
            Run discovery →
          </Link>
        </div>
        {engagement.discoveryJobs.length === 0 ? (
          <p className="py-6 text-center text-xs text-navy-400 dark:text-navy-400">No discovery jobs yet.</p>
        ) : (
          <ul className="divide-y divide-navy-700/30">
            {engagement.discoveryJobs.map((j) => (
              <li key={j.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-navy-800 dark:text-navy-100">
                    {j.credential?.label ?? "Removed credential"}
                  </p>
                  <p className="text-xs text-navy-400">
                    {new Date(j.createdAt).toLocaleString()}
                    {j.findingsCount != null && ` · ${j.findingsCount} finding${j.findingsCount !== 1 ? "s" : ""}`}
                  </p>
                </div>
                <StatusBadge value={j.status} variant="job" />
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* ── Quick links ── */}
      <div>
        <h2 className="label-caps mb-3 text-navy-500">Ingestion Pages</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {LINKS.map((item) => (
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
                <p className="text-sm font-bold text-navy-700 dark:text-navy-100">{item.label}</p>
                <p className="mt-0.5 text-xs text-navy-400">{item.desc}</p>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
