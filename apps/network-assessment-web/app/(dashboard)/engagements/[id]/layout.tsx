import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { notFound } from "next/navigation";
import Link from "next/link";
import { StatusBadge } from "@/components/ui/status-badge";
import { DeleteEngagementButton } from "@/components/ui/delete-engagement-button";
import { EngagementSidebar } from "@/components/ui/engagement-sidebar";

interface LayoutProps {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}

export default async function EngagementLayout({ children, params }: LayoutProps) {
  const { id } = await params;
  const session = await auth();

  const engagement = await prisma.engagement.findUnique({
    where: { id },
    include: { members: true },
  });

  if (!engagement) notFound();

  const isMember = engagement.members.some((m) => m.userId === session?.user?.id);
  if (!isMember) notFound();

  return (
    <div className="flex min-h-[calc(100vh-5rem)] flex-col">
      {/* ── Engagement header ── */}
      <div className="glass mb-5 flex items-start justify-between gap-4 rounded-xl p-5">
        <div className="min-w-0">
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-1 text-xs font-medium text-navy-400 hover:text-teal-600 dark:text-navy-400 dark:hover:text-teal-400 transition-colors"
          >
            <svg aria-hidden="true" focusable="false" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
            All engagements
          </Link>
          <div className="mt-2 flex items-center gap-3">
            <h1 className="text-2xl font-black tracking-tight text-navy-800 dark:text-navy-50">
              {engagement.name}
            </h1>
            <StatusBadge value={engagement.status} variant="status" />
          </div>
          <p className="mt-0.5 text-sm text-navy-400 dark:text-navy-300">
            {engagement.clientOrg}
          </p>
        </div>
        <DeleteEngagementButton
          engagementId={id}
          engagementName={engagement.name}
          variant="header"
        />
      </div>

      {/* ── Sidebar + content ── */}
      <div className="flex flex-1 items-start gap-4">
        <EngagementSidebar engagementId={id} />
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}
