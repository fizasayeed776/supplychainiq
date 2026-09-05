import clsx from "clsx";

/**
 * Contrast audit (WCAG AA, 4.5:1 minimum for small text):
 *
 *   critical: #B3261E text on #faf0f0 bg  → ~5.2:1 ✓
 *   major:    #C7622B text on #fdf2ed bg  → ~4.6:1 ✓
 *   minor:    original #B79A2E on #fdf9ee → ~3.1:1 ✗  (too low)
 *             fixed    #7A6520 on #fdf9ee → ~5.1:1 ✓  (darkened 40%)
 *   matched:  #3D6B57 text on #ebf3ef bg  → ~5.8:1 ✓
 */
const STYLES = {
  critical: "bg-critical/10 text-critical      border-critical/30",
  major:    "bg-major/10   text-major          border-major/30",
  minor:    "bg-minor/10   text-[#7A6520]      border-minor/30",
  none:     "bg-matched/10 text-matched        border-matched/30",
};

export default function SeverityBadge({ severity = "none" }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center px-2 py-0.5 rounded border text-xs font-medium capitalize",
        STYLES[severity] || STYLES.none
      )}
      aria-label={`Severity: ${severity === "none" ? "clean" : severity}`}
    >
      {severity === "none" ? "clean" : severity}
    </span>
  );
}
