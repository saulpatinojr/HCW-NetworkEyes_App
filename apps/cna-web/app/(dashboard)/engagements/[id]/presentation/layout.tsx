import { prisma } from "@/lib/prisma";
import { PresentationNavBar } from "./_components/nav-bar";
import { CreateInteractiveAssessmentButton } from "./_components/create-assessment-button";

interface LayoutProps {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}

export default async function PresentationLayout({ children, params }: LayoutProps) {
  const { id } = await params;
  const base = `/engagements/${id}/presentation`;

  // The presentation site stays gated until the assessment has finished
  // generating — a RUNNING or FAILED row is not a usable assessment.
  let existing: { id: string; status: string } | null = null;
  try {
    existing = await prisma.deliverable.findFirst({
      where: { engagementId: id, type: "INTERACTIVE_ASSESSMENT" },
      orderBy: { createdAt: "desc" },
      select: { id: true, status: true },
    });
  } catch { /* migration pending */ }

  if (existing?.status !== "COMPLETED") {
    return (
      <div className="glass flex min-h-[50vh] flex-col items-center justify-center rounded-xl p-12 text-center">
        <svg aria-hidden="true" focusable="false" className="mb-4 h-12 w-12 text-navy-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8 13v-1m4 1v-3m4 3V8M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
        </svg>
        <h2 className="text-lg font-semibold text-navy-500 dark:text-navy-200">
          {existing?.status === "RUNNING" || existing?.status === "QUEUED"
            ? "Interactive assessment is generating"
            : "No interactive assessment yet"}
        </h2>
        <p className="mt-2 text-sm text-navy-400">
          {existing?.status === "RUNNING" || existing?.status === "QUEUED"
            ? "The AI is writing the report section by section. This page unlocks when it finishes."
            : "Create an interactive assessment to enable this presentation site."}
        </p>
        <div className="mt-6">
          <CreateInteractiveAssessmentButton engagementId={id} existing={existing} />
        </div>
      </div>
    );
  }

  return (
    <div>
      <PresentationNavBar base={base} />
      {children}
    </div>
  );
}
