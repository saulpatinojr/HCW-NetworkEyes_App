"use client";
import { useActionState, useRef, useState } from "react";
import { deleteEngagement } from "@/app/(dashboard)/dashboard/actions";

interface Props {
  engagementId: string;
  engagementName: string;
  /** Visual style: "inline" for list rows, "header" for the engagement detail header */
  variant?: "inline" | "header";
}

export function DeleteEngagementButton({
  engagementId,
  engagementName,
  variant = "header",
}: Props) {
  const [showDialog, setShowDialog] = useState(false);
  const dialogRef = useRef<HTMLDialogElement>(null);

  const [, formAction, isPending] = useActionState(
    async (prevState: null, formData: FormData) => {
      await deleteEngagement(formData);
      return prevState;
    },
    null
  );

  function openModal(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setShowDialog(true);
    // Dialog needs to be opened via .showModal() for native focus trap and accessibility
    setTimeout(() => {
      dialogRef.current?.showModal();
    }, 0);
  }

  function closeModal() {
    dialogRef.current?.close();
    setShowDialog(false);
  }

  function handleConfirm() {
    closeModal();
  }

  return (
    <>
      {variant === "inline" ? (
        <button
          type="button"
          onClick={openModal}
          disabled={isPending}
          className="rounded border border-red-200 px-2 py-1 text-xs font-medium text-red-500 hover:bg-red-50 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-1"
        >
          {isPending ? "Deleting…" : "Delete"}
        </button>
      ) : (
        <button
          type="button"
          onClick={openModal}
          disabled={isPending}
          className="rounded-lg border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-1"
        >
          {isPending ? "Deleting…" : "Delete engagement"}
        </button>
      )}

      {showDialog && (
        <dialog
          ref={dialogRef}
          onClose={closeModal}
          className="rounded-xl border border-navy-100 bg-white p-6 text-navy-800 shadow-2xl backdrop:bg-black/50 w-full max-w-md focus-visible:outline-none dark:border-navy-700 dark:bg-navy-900 dark:text-navy-100"
        >
          <div className="space-y-4">
            <h2 className="text-lg font-bold text-navy-800 dark:text-navy-50">Delete Engagement?</h2>
            <p className="text-sm text-navy-400 dark:text-navy-300 font-normal">
              Are you sure you want to delete <strong className="text-navy-800 dark:text-navy-100">&quot;{engagementName}&quot;</strong>? This will permanently remove all documents, findings, and deliverables. This cannot be undone.
            </p>
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={closeModal}
                className="rounded-lg border border-navy-100 bg-navy-50 px-4 py-2 text-xs font-medium text-navy-500 hover:bg-navy-100 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 dark:border-navy-700 dark:bg-navy-800/40 dark:text-navy-300 dark:hover:bg-navy-800"
              >
                Cancel
              </button>
              <form action={formAction} onSubmit={handleConfirm}>
                <input type="hidden" name="engagementId" value={engagementId} />
                <button
                  type="submit"
                  disabled={isPending}
                  className="rounded-lg bg-red-700 px-4 py-2 text-xs font-semibold text-white hover:bg-red-600 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 disabled:opacity-50"
                >
                  {isPending ? "Deleting…" : "Confirm Delete"}
                </button>
              </form>
            </div>
          </div>
        </dialog>
      )}
    </>
  );
}
