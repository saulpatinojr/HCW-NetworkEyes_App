// Shared empty state — modeled on the Inventory page's empty state, the
// strongest of the ~20 that had drifted apart. Renders a glass card with an
// icon well, a bold one-line title, and muted guidance text (which may embed
// links or actions via children).

import type { ReactNode } from "react";

function DefaultIcon() {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      className="h-6 w-6 text-navy-400 dark:text-navy-500"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={1.5}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
    </svg>
  );
}

export function EmptyState({
  title,
  children,
  icon,
  action,
  variant = "card",
  className = "",
}: {
  /** Bold one-line summary, e.g. "No inventory data yet". */
  title: string;
  /** Muted guidance line(s); may embed <Link> elements. */
  children?: ReactNode;
  /** Optional icon (an <svg>); defaults to the list glyph. */
  icon?: ReactNode;
  /** Optional call-to-action rendered below the guidance text. */
  action?: ReactNode;
  /**
   * "card": standalone glass card (page-level empty state).
   * "inline": dashed well for use INSIDE an existing glass card.
   */
  variant?: "card" | "inline";
  className?: string;
}) {
  const shell =
    variant === "card"
      ? "glass p-10 text-center"
      : "rounded-xl border border-dashed border-navy-200 dark:border-navy-700 px-6 py-8 text-center";
  return (
    <div className={`${shell} ${className}`}>
      {variant === "card" && (
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-navy-100 dark:bg-navy-800">
          {icon ?? <DefaultIcon />}
        </div>
      )}
      <p className="text-sm font-semibold text-navy-600 dark:text-navy-300">{title}</p>
      {children && (
        <p className="mx-auto mt-1 max-w-md text-xs text-navy-400 dark:text-navy-500">{children}</p>
      )}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}
