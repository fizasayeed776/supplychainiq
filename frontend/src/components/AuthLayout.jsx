/**
 * AuthLayout — split-screen wrapper for Login and Signup pages.
 *
 * Left panel (md+): bg-ledger branding + static pipeline terminal with a
 *   single pulsing "streaming" dot. Hidden below md; replaced by a slim
 *   header bar on mobile.
 * Right panel: centered form area, fade-up entrance on the content block.
 */
import { motion } from "framer-motion";

/* ── Static terminal rows (mirrors Landing.jsx MOCK_EVENTS, non-scrolling) ── */
const TERMINAL_ROWS = [
  { label: "Matched",     doc: "INV-3987 — clean",       color: "text-matched"      },
  { label: "Discrepancy", doc: "INV-4001 — rate Δ",       color: "text-signal"       },
  { label: "Matched",     doc: "INV-3988 — clean",        color: "text-matched"      },
  { label: "Extraction",  doc: "PO-5500.pdf",             color: "text-ledgerLight"  },
  { label: "Matched",     doc: "INV-3989 — clean",        color: "text-matched"      },
];

function StaticTerminal() {
  return (
    <div className="bg-ink/60 rounded-xl border border-white/10 overflow-hidden shadow-xl w-full max-w-xs">
      {/* Title bar */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-white/10">
        <span className="w-2.5 h-2.5 rounded-full bg-critical/70" aria-hidden="true" />
        <span className="w-2.5 h-2.5 rounded-full bg-minor/70"    aria-hidden="true" />
        <span className="w-2.5 h-2.5 rounded-full bg-matched/70"  aria-hidden="true" />
        <span className="ml-2 text-[11px] font-mono text-paper/40">Live pipeline feed</span>
        {/* The one deliberate animation: a pulsing streaming dot */}
        <span className="ml-auto flex items-center gap-1 text-[10px] text-matched/80 font-mono">
          <motion.span
            className="w-1.5 h-1.5 rounded-full bg-matched inline-block"
            animate={{ opacity: [1, 0.25, 1] }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
            aria-hidden="true"
          />
          streaming
        </span>
      </div>

      {/* Rows */}
      <div className="px-4 py-3 space-y-2 font-mono text-[11px]">
        {TERMINAL_ROWS.map((row, i) => (
          <div key={i} className="flex items-center gap-3">
            <span className="text-paper/25 w-8 shrink-0 tabular-nums">
              {String(9 + i).padStart(2, "0")}:0{i}
            </span>
            <span className={`w-20 shrink-0 font-medium ${row.color}`}>
              {row.label}
            </span>
            <span className="text-paper/55 truncate">{row.doc}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── AuthLayout ──────────────────────────────────────────────────────────── */
export default function AuthLayout({ title, subtitle, children }) {
  return (
    <div className="min-h-screen flex flex-col md:flex-row font-body text-ink">

      {/* ── Mobile-only slim header (no terminal, just wordmark + tagline) ── */}
      <div className="md:hidden bg-ledger px-6 py-4 shrink-0">
        <div className="font-display text-lg text-paper leading-none">SupplyChainIQ</div>
        <p className="text-xs text-wheat/80 mt-1">
          Three-way matching, reconciled before you open your inbox.
        </p>
      </div>

      {/* ── Left panel (md+) ─────────────────────────────────────────────── */}
      <div
        className="hidden md:flex md:w-[45%] shrink-0 bg-ledger flex-col justify-center px-12 relative overflow-hidden"
        style={{
          /* Faint ledger-paper horizontal line texture — ~3% opacity, 36px pitch */
          backgroundImage:
            "repeating-linear-gradient(180deg, transparent, transparent 35px, rgba(212,199,158,0.03) 35px, rgba(212,199,158,0.03) 36px)",
        }}
      >
        {/* Wordmark + tagline */}
        <div className="mb-10">
          <div className="font-display text-3xl text-paper leading-none mb-2">
            SupplyChainIQ
          </div>
          <p className="text-wheat/80 text-sm leading-relaxed max-w-xs">
            Three-way matching, reconciled before you open your inbox.
          </p>
        </div>

        {/* Static pipeline terminal */}
        <StaticTerminal />

        {/* Stat line */}
        <p className="mt-8 text-xs font-mono text-wheat/60 tracking-wide">
          98% match accuracy · 4 hrs saved per batch
        </p>
      </div>

      {/* ── Right panel ──────────────────────────────────────────────────── */}
      <div className="flex-1 bg-paper flex items-center justify-center px-6 py-10 overflow-y-auto">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.22, ease: "easeOut" }}
          className="w-full max-w-sm"
        >
          {/* Heading */}
          <div className="mb-7">
            <h1 className="font-display text-2xl text-ink leading-tight">{title}</h1>
            {subtitle && (
              <p className="text-sm text-ink/60 mt-1.5">{subtitle}</p>
            )}
          </div>

          {/* Form children */}
          {children}
        </motion.div>
      </div>
    </div>
  );
}
