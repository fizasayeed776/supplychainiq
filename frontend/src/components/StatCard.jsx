import clsx from "clsx";

/**
 * StatCard — polished KPI tile with icon, semantic accent, and tight layout.
 *
 * accent values → visual treatment:
 *   "positive"  – matched green left border + icon
 *   "warning"   – signal/major orange left border + icon
 *   "critical"  – critical red left border + icon
 *   "neutral"   – ledgerLight teal left border + icon (default)
 */
const ACCENT = {
  positive: {
    border: "border-l-matched",
    icon:   "text-matched bg-matched/10",
  },
  warning: {
    border: "border-l-major",
    icon:   "text-major bg-major/10",
  },
  critical: {
    border: "border-l-critical",
    icon:   "text-critical bg-critical/10",
  },
  neutral: {
    border: "border-l-ledgerLight",
    icon:   "text-ledgerLight bg-ledgerLight/10",
  },
};

export default function StatCard({ label, value, sub, icon: Icon, accent = "neutral" }) {
  const a = ACCENT[accent] || ACCENT.neutral;

  return (
    <div
      className={clsx(
        "border border-line border-l-4 rounded-lg bg-white px-5 py-4 flex items-start gap-4",
        a.border
      )}
    >
      {Icon && (
        <div className={clsx("mt-0.5 rounded-md p-2 shrink-0", a.icon)}>
          <Icon size={16} strokeWidth={1.75} aria-hidden="true" />
        </div>
      )}
      <div className="min-w-0">
        <div className="text-[11px] font-mono uppercase tracking-wider text-ink/40 mb-1 leading-none">
          {label}
        </div>
        <div className="font-display text-3xl text-ink leading-none">{value}</div>
        {sub && (
          <div className="text-xs text-ink/40 mt-1.5 leading-snug">{sub}</div>
        )}
      </div>
    </div>
  );
}
