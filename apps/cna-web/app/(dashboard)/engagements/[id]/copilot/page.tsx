import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { notFound } from "next/navigation";
import { ChatPanel } from "@/components/copilot/chat-panel";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function CopilotPage({ params }: PageProps) {
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
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold text-navy-900 dark:text-warmgray-100">
          Assessment Copilot
        </h1>
        <p className="text-sm text-navy-600 dark:text-warmgray-300 mt-1">
          Grounded Q&amp;A over {engagement.name}&apos;s discovered topology, findings,
          and cost signals. Every answer cites the rule IDs it draws from — the
          copilot will not speculate beyond assessment data.
        </p>
      </div>

      <ChatPanel engagementId={id} />
    </div>
  );
}
