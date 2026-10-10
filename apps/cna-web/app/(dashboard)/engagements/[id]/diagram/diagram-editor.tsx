"use client";

import { useCallback, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { DrawioEmbed } from "@/components/diagrams/DrawioEmbed";
import { saveDiagramXml } from "./actions";

type SaveState =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved"; at: Date }
  | { kind: "error"; message: string };

/**
 * Client wrapper around the embedded draw.io editor. The editor's Save button
 * (or Ctrl+S) hands the XML to the saveDiagramXml server action, which
 * versions it as an engagement document and upserts the Deliverables entry.
 */
export function DiagramEditor({
  engagementId,
  initialXml,
}: {
  engagementId: string;
  initialXml: string;
}) {
  const [saveState, setSaveState] = useState<SaveState>({ kind: "idle" });
  const [, startTransition] = useTransition();
  const router = useRouter();

  const handleSave = useCallback(
    (xml: string) => {
      setSaveState({ kind: "saving" });
      startTransition(async () => {
        try {
          const result = await saveDiagramXml(engagementId, xml);
          if (result.error) {
            setSaveState({ kind: "error", message: result.error });
          } else {
            setSaveState({ kind: "saved", at: new Date() });
            router.refresh();
          }
        } catch {
          setSaveState({ kind: "error", message: "Save failed — check your connection." });
        }
      });
    },
    [engagementId, router],
  );

  return (
    <div>
      <div className="overflow-hidden rounded-lg border border-navy-700/40 bg-white">
        <DrawioEmbed initialXml={initialXml} onSave={handleSave} />
      </div>
      <p className="mt-2 text-xs" aria-live="polite">
        {saveState.kind === "idle" && (
          <span className="text-navy-500">
            Use the editor&apos;s Save button (or Ctrl+S) to save the diagram into this engagement.
          </span>
        )}
        {saveState.kind === "saving" && <span className="text-navy-400">Saving…</span>}
        {saveState.kind === "saved" && (
          <span className="text-teal-700 dark:text-teal-400">
            Saved to engagement at {saveState.at.toLocaleTimeString()} — listed under Documents and
            Deliverables.
          </span>
        )}
        {saveState.kind === "error" && (
          <span className="font-semibold text-red-600 dark:text-red-400">{saveState.message}</span>
        )}
      </p>
    </div>
  );
}
