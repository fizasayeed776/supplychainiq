import clsx from "clsx";

/**
 * Generic skeleton shimmer block.
 * Usage:
 *   <Skeleton className="h-8 w-40" />          – single bar
 *   <Skeleton lines={4} />                       – 4 stacked bars
 *   <SkeletonCard />                             – full card placeholder
 */
export default function Skeleton({ className, lines }) {
  if (lines) {
    return (
      <div className="space-y-2">
        {Array.from({ length: lines }).map((_, i) => (
          <div
            key={i}
            className={clsx(
              "h-4 rounded bg-line animate-pulse",
              i === lines - 1 ? "w-2/3" : "w-full"
            )}
          />
        ))}
      </div>
    );
  }
  return (
    <div
      className={clsx("rounded bg-line animate-pulse", className || "h-4 w-full")}
    />
  );
}

export function SkeletonCard({ rows = 3 }) {
  return (
    <div className="border border-line rounded-lg bg-white p-5 space-y-3">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-8 w-32" />
      {rows > 1 && <Skeleton className="h-3 w-40" />}
      {rows > 2 && <Skeleton className="h-3 w-36" />}
    </div>
  );
}

export function SkeletonRow({ cols = 5 }) {
  return (
    <tr className="border-b border-line/60">
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} className="p-3">
          <Skeleton className={clsx("h-4", i === 0 ? "w-24" : "w-20")} />
        </td>
      ))}
    </tr>
  );
}

export function PageError({ message, onRetry }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <div className="text-critical text-sm font-medium">{message || "Something went wrong"}</div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="px-4 py-2 rounded-md border border-line text-sm text-ink/60 hover:bg-line/30 hover:border-ink/20 transition-colors duration-150 focus-visible:ring-2"
        >
          Retry
        </button>
      )}
    </div>
  );
}
