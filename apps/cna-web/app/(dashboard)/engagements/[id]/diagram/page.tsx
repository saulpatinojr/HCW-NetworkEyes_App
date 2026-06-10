import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { notFound } from "next/navigation";
import Link from "next/link";
import { DiagramForms } from "./diagram-forms";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function DiagramPage({ params }: PageProps) {
  const { id } = await params;
  const session = await auth();

  const engagement = await prisma.engagement.findUnique({
    where: { id },
    select: {
      id: true,
      members: { select: { userId: true } },
      documents: {
        where: { docType: "NETWORK_DIAGRAM" },
        orderBy: { createdAt: "desc" },
        take: 8,
        select: { id: true, fileName: true, createdAt: true },
      },
    },
  });
  if (!engagement) notFound();

  const isMember = engagement.members.some((m) => m.userId === session?.user?.id);
  if (!isMember) notFound();

  return (
    <div className="space-y-5">
      <section className="glass p-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-navy-100">Diagram Workspace</h2>
          {/* Current / Future state toggle.
              TODO(Phase E follow-up): the future-state .drawio XML is produced by
              cna/diagram_engine/drawio_generator.py:generate_future_state_topology
              during assessment-report generation (worker), but this page only embeds
              a blank diagrams.net editor — there is no data flow that loads generated
              XML into the iframe yet. Once generated diagrams are persisted as
              engagement documents/deliverables and loadable here, enable this toggle
              and swap the iframe content between current- and future-state XML. */}
          <div
            className="inline-flex overflow-hidden rounded-lg border border-navy-700/40 text-xs font-semibold"
            role="group"
            aria-label="Diagram state"
          >
            <span className="bg-teal-900/30 px-3 py-2 text-teal-300">Current state</span>
            <button
              type="button"
              disabled
              title="Generated with the assessment report"
              className="cursor-not-allowed px-3 py-2 text-navy-500"
            >
              Future state
            </button>
          </div>
          <a
            href="https://app.diagrams.net/"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-lg border border-teal-700/50 bg-teal-900/20 px-3 py-2 text-sm font-semibold text-teal-300 transition-colors hover:bg-teal-900/40"
          >
            Launch draw.io
            <span className="sr-only"> (opens in new tab)</span>
          </a>
        </div>
        <p className="mb-4 text-sm text-navy-400">
          Build diagrams in draw.io, then save source `.drawio` files and exported artifacts back into this engagement.
        </p>
        <div className="overflow-hidden rounded-lg border border-navy-700/40 bg-white">
          <iframe
            title="draw.io editor"
            src="https://embed.diagrams.net/?embed=1&ui=min&spin=1&proto=json&libraries=1"
            className="h-[560px] w-full"
          />
        </div>
      </section>

      <DiagramForms engagementId={id} />

      <section className="glass p-5">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-base font-semibold text-navy-100">Recent Diagram Files</h3>
          <div className="flex items-center gap-3 text-xs">
            <Link href={`/engagements/${id}/documents`} className="text-teal-400 hover:underline">
              Open Documents
            </Link>
            <Link href={`/engagements/${id}/deliverables`} className="text-teal-400 hover:underline">
              Open Deliverables
            </Link>
          </div>
        </div>
        {engagement.documents.length === 0 ? (
          <p className="text-sm text-navy-500">No diagram files uploaded yet.</p>
        ) : (
          <ul className="divide-y divide-navy-700/30">
            {engagement.documents.map((doc) => (
              <li key={doc.id} className="flex items-center justify-between gap-3 py-2.5">
                <span className="truncate text-sm text-navy-200">{doc.fileName}</span>
                <span className="text-xs text-navy-500">
                  {new Date(doc.createdAt).toLocaleDateString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
