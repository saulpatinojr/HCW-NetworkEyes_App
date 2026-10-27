"use client";

// Submit button that asks for confirmation before submitting its enclosing
// <form>. Used to guard destructive one-click actions (deletes). Render it
// INSIDE the form whose action should run on confirm.

import { useEffect, useRef, useState } from "react";

export function ConfirmSubmitButton({
  confirmTitle = "Delete this item?",
  confirmMessage = "This cannot be undone.",
  confirmLabel = "Delete",
  className = "",
  ariaLabel,
  children,
}: {
  confirmTitle?: string;
  confirmMessage?: string;
  confirmLabel?: string;
  className?: string;
  ariaLabel?: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const handleConfirm = () => {
    setOpen(false);
    triggerRef.current?.closest("form")?.requestSubmit();
  };

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-label={ariaLabel}
        className={className}
        onClick={() => setOpen(true)}
      >
        {children}
      </button>

      <dialog
        ref={dialogRef}
        onClose={() => setOpen(false)}
        onClick={(e) => {
          if (e.target === dialogRef.current) setOpen(false);
        }}
        aria-labelledby="confirm-dialog-title"
        className="glass m-auto w-full max-w-sm p-0 outline-none backdrop:bg-black/40"
      >
        <div className="p-6">
          <h2
            id="confirm-dialog-title"
            className="text-base font-bold text-navy-800 dark:text-navy-100"
          >
            {confirmTitle}
          </h2>
          <p className="mt-1.5 text-sm text-navy-400 dark:text-navy-300">{confirmMessage}</p>
          <div className="mt-5 flex justify-end gap-3">
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded-lg px-4 py-2 text-sm font-semibold text-navy-500 dark:text-navy-300 hover:text-navy-700 dark:hover:text-navy-100"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleConfirm}
              className="rounded-lg bg-red-600 px-4 py-2 text-sm font-bold text-white hover:bg-red-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
            >
              {confirmLabel}
            </button>
          </div>
        </div>
      </dialog>
    </>
  );
}
