import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { notFound } from "next/navigation";
import Link from "next/link";
import { DiagramForms } from "./diagram-forms";
import { DiagramEditor } from "./diagram-editor";
import { GenerateDiagramButton } from "./generate-diagram-button";

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

  // Latest saved diagram source (editor saves and .drawio uploads both store
  // the XML in parsedText) — loaded back into the embedded editor.
  const latestSource = await prisma.ingestedDocument.findFirst({
    where: { engagementId: id, docType: "NETWORK_DIAGRAM", parsedText: { not: null } },
    orderBy: { createdAt: "desc" },
    select: { parsedText: true },
  });

  return (
    <div className="space-y-5">
      <section className="glass p-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-navy-800 dark:text-navy-100">Diagram Workspace</h2>
          {/* TODO(Phase E follow-up): future-state .drawio XML is produced by
              cna/diagram_engine/drawio_generator.py:generate_future_state_topology
              during assessment-report generation (worker) but is not yet persisted
              as an engagement document. Once it is, add a Current/Future state
              toggle here to swap between the two XML sources. */}
          <span className="rounded-lg bg-teal-50 dark:bg-teal-900/30 px-3 py-2 text-xs font-semibold text-teal-700 dark:text-teal-300">
            Current state
          </span>
          <a
            href="https://app.diagrams.net/"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-lg border border-teal-700/50 bg-teal-50 dark:bg-teal-900/20 px-3 py-2 text-sm font-semibold text-teal-700 dark:text-teal-300 transition-colors hover:bg-teal-50 dark:hover:bg-teal-900/40"
          >
            Launch draw.io
            <span className="sr-only"> (opens in new tab)</span>
          </a>
        </div>
        <p className="mb-4 text-sm text-navy-400">
          Generate a diagram from the topology discovery already found, then adjust it here —
          the editor&apos;s Save button writes changes straight back into this engagement.
          Exported artifacts (.png/.svg/.pdf) can be uploaded below.
        </p>
        <div className="mb-4">
          <GenerateDiagramButton engagementId={id} />
        </div>
        <DiagramEditor engagementId={id} initialXml={latestSource?.parsedText ?? ""} />
      </section>

      <DiagramForms engagementId={id} />

      <section className="glass p-5">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-base font-semibold text-navy-800 dark:text-navy-100">Recent Diagram Files</h3>
          <div className="flex items-center gap-3 text-xs">
            <Link href={`/engagements/${id}/documents`} className="text-teal-700 dark:text-teal-400 hover:underline">
              Open Documents
            </Link>
            <Link href={`/engagements/${id}/deliverables`} className="text-teal-700 dark:text-teal-400 hover:underline">
              Open Deliverables
            </Link>
          </div>
        </div>
        {engagement.documents.length === 0 ? (
          <p className="py-4 text-center text-sm text-navy-400">No diagram files uploaded yet.</p>
        ) : (
          <ul className="divide-y divide-navy-700/30">
            {engagement.documents.map((doc) => (
              <li key={doc.id} className="flex items-center justify-between gap-3 py-2.5">
                <span className="truncate text-sm text-navy-500 dark:text-navy-200">{doc.fileName}</span>
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
