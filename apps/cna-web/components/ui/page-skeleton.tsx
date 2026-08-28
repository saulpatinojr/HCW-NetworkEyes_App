// Shared glass skeleton used by the route-level loading.tsx files.
// Mirrors the common page shape: heading block, stat tiles, then a body card.

function Shimmer({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-lg bg-navy-100/70 dark:bg-navy-700/40 ${className}`}
    />
  );
}

export function PageSkeleton({
  tiles = 4,
  showHeading = true,
}: {
  /** Number of stat-tile placeholders in the top row (0 to skip the row). */
  tiles?: number;
  showHeading?: boolean;
}) {
  return (
    <div className="space-y-6" role="status" aria-label="Loading page">
      {showHeading && (
        <div className="space-y-2">
          <Shimmer className="h-3 w-24" />
          <Shimmer className="h-8 w-64" />
          <Shimmer className="h-4 w-96 max-w-full" />
        </div>
      )}
      {tiles > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: tiles }).map((_, i) => (
            <div key={i} className="glass-sm p-5">
              <Shimmer className="h-3 w-20" />
              <Shimmer className="mt-3 h-7 w-14" />
            </div>
          ))}
        </div>
      )}
      <div className="glass p-6">
        <Shimmer className="h-4 w-40" />
        <div className="mt-5 space-y-3">
          <Shimmer className="h-3 w-full" />
          <Shimmer className="h-3 w-11/12" />
          <Shimmer className="h-3 w-full" />
          <Shimmer className="h-3 w-4/5" />
          <Shimmer className="h-3 w-10/12" />
        </div>
      </div>
      <span className="sr-only">Loading…</span>
    </div>
  );
}
