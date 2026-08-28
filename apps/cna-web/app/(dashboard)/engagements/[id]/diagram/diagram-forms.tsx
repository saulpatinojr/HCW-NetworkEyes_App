"use client";

import { useActionState } from "react";
import { saveDiagramSource, uploadDiagramExport } from "./actions";
import { SubmitButton } from "@/components/ui/submit-button";

export function DiagramForms({ engagementId }: { engagementId: string }) {
  const [sourceState, sourceAction] = useActionState(saveDiagramSource, null);
  const [exportState, exportAction] = useActionState(uploadDiagramExport, null);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <form action={sourceAction} className="glass space-y-4 p-5">
        <input type="hidden" name="engagementId" value={engagementId} />
        <h2 className="text-base font-semibold text-navy-800 dark:text-navy-100">Save Source Diagram</h2>
        <p className="text-sm text-navy-400">
          Upload `.drawio` or `.xml` so the editable source is tracked in Documents.
        </p>
        {sourceState?.error && (
          <p className="rounded-lg border border-red-800/40 bg-red-50 dark:bg-red-900/20 px-3 py-2 text-sm text-red-600 dark:text-red-400">
            {sourceState.error}
          </p>
        )}
        {sourceState?.success && (
          <p className="rounded-lg border border-teal-800/40 bg-teal-50 dark:bg-teal-900/20 px-3 py-2 text-sm text-teal-700 dark:text-teal-300">
            Source diagram saved.
          </p>
        )}
        <input
          name="sourceFile"
          type="file"
          required
          accept=".drawio,.xml"
          className="block w-full rounded-lg border border-navy-600/50 bg-white/60 dark:bg-navy-800/60 px-3 py-2 text-sm text-navy-400 dark:text-navy-300 file:mr-3 file:rounded file:border-0 file:bg-teal-50 dark:file:bg-teal-900/40 file:px-3 file:py-1 file:text-xs file:font-medium file:text-teal-700 dark:file:text-teal-300"
        />
        <div className="flex justify-end">
          <SubmitButton loadingText="Saving...">Save source</SubmitButton>
        </div>
      </form>

      <form action={exportAction} className="glass space-y-4 p-5">
        <input type="hidden" name="engagementId" value={engagementId} />
        <h2 className="text-base font-semibold text-navy-800 dark:text-navy-100">Upload Export Artifact</h2>
        <p className="text-sm text-navy-400">
          Upload `.png`, `.svg`, or `.pdf` export. Optionally publish it into Deliverables.
        </p>
        {exportState?.error && (
          <p className="rounded-lg border border-red-800/40 bg-red-50 dark:bg-red-900/20 px-3 py-2 text-sm text-red-600 dark:text-red-400">
            {exportState.error}
          </p>
        )}
        {exportState?.success && (
          <p className="rounded-lg border border-teal-800/40 bg-teal-50 dark:bg-teal-900/20 px-3 py-2 text-sm text-teal-700 dark:text-teal-300">
            Export uploaded.
          </p>
        )}
        <input
          name="exportFile"
          type="file"
          required
          accept=".png,.svg,.pdf"
          className="block w-full rounded-lg border border-navy-600/50 bg-white/60 dark:bg-navy-800/60 px-3 py-2 text-sm text-navy-400 dark:text-navy-300 file:mr-3 file:rounded file:border-0 file:bg-teal-50 dark:file:bg-teal-900/40 file:px-3 file:py-1 file:text-xs file:font-medium file:text-teal-700 dark:file:text-teal-300"
        />
        <label className="flex items-center gap-2 text-sm text-navy-400 dark:text-navy-300">
          <input
            name="addToDeliverables"
            type="checkbox"
            className="h-4 w-4 rounded border-navy-500 bg-white dark:bg-navy-800 text-teal-700 dark:text-teal-500 focus:ring-teal-500"
          />
          Create a deliverable entry for this export
        </label>
        <div className="flex justify-end">
          <SubmitButton loadingText="Uploading...">Upload export</SubmitButton>
        </div>
      </form>
    </div>
  );
}
