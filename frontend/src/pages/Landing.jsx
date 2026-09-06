/**
 * Landing.jsx — SupplyChainIQ public marketing page
 *
 * Sections:
 *   1. Nav bar
 *   2. Hero (animated mock pipeline feed + match counter)
 *   3. Stat strip (4 KPI cards)
 *   4. Problem → Solution flip cards (6 cards)
 *   5. How it works / AI pipeline (5 agents)
 *   6. Final CTA
 *   7. Footer
 *
 * Design tokens: paper/ink/ledger/ledgerLight/signal/wheat/line
 * Fonts: Fraunces (display), Inter (body), IBM Plex Mono (mono)
 * Animation: framer-motion whileInView (once:true) + reduced-motion via CSS
 */
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";
import {
  CheckCircle2, AlertTriangle, Zap, FileText, ShieldCheck,
  GitCompareArrows, Eye, Clock, TrendingDown, Layers,
  Brain, Search, Scale, BarChart2, ArrowRight, ChevronRight,
} from "lucide-react";

import MarketingNav    from "../components/MarketingNav.jsx";
import MarketingFooter from "../components/MarketingFooter.jsx";

/* ── Shared animation helpers ────────────────────────────────────────────── */
function useFadeUp(once = true) {
  const reduced = useReducedMotion();
  if (reduced) return {};
  return {
    initial:   { opacity: 0, y: 28 },
    whileInView: { opacity: 1, y: 0 },
    viewport:  { once },
    transition: { duration: 0.45, ease: "easeOut" },
  };
}

function FadeUp({ children, delay = 0, className = "" }) {
  const reduced = useReducedMotion();
  const props = reduced
    ? {}
    : {
        initial:     { opacity: 0, y: 28 },
        whileInView: { opacity: 1, y: 0 },
        viewport:    { once: true },
        transition:  { duration: 0.45, ease: "easeOut", delay },
      };
  return (
    <motion.div {...props} className={className}>
      {children}
    </motion.div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
   2. HERO — animated mock pipeline feed + live match rate counter
══════════════════════════════════════════════════════════════════════════ */
const MOCK_EVENTS = [
  { stage: "ocr",        label: "OCR",        doc: "INV-4001.pdf",     color: "text-minor"   },
  { stage: "extraction", label: "Extraction", doc: "PO-5500.pdf",      color: "text-ledgerLight" },
  { stage: "matching",   label: "Matching",   doc: "INV-4001 ↔ PO-5500", color: "text-major" },
  { stage: "done",       label: "Matched",    doc: "INV-3987 — clean",  color: "text-matched" },
  { stage: "alert",      label: "Discrepancy",doc: "INV-4001 — rate Δ", color: "text-signal"  },
  { stage: "done",       label: "Matched",    doc: "INV-3988 — clean",  color: "text-matched" },
  { stage: "extraction", label: "Extraction", doc: "DR-0042.pdf",       color: "text-ledgerLight" },
  { stage: "done",       label: "Matched",    doc: "INV-3989 — clean",  color: "text-matched" },
];

function AnimatedMatchCounter({ target = 98, duration = 1800 }) {
  const [count, setCount] = useState(0);
  const reduced = useReducedMotion();
  const started = useRef(false);

  function start() {
    if (started.current) return;
    started.current = true;
    if (reduced) { setCount(target); return; }
    const startTime = performance.now();
    function step(now) {
      const progress = Math.min((now - startTime) / duration, 1);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setCount(Math.round(eased * target));
      if (progress < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  return (
    <motion.div
      onViewportEnter={start}
      viewport={{ once: true }}
      className="text-center"
    >
      <div className="font-display text-6xl text-ledger leading-none tabular-nums">
        {count}<span className="text-signal">%</span>
      </div>
      <div className="text-sm text-ink/50 mt-1 font-mono uppercase tracking-wider">
        Match accuracy
      </div>
    </motion.div>
  );
}

function MockPipelineFeed() {
  const [visibleCount, setVisibleCount] = useState(1);
  const reduced = useReducedMotion();

  useEffect(() => {
    if (reduced) { setVisibleCount(MOCK_EVENTS.length); return; }
    const id = setInterval(() => {
      setVisibleCount((n) => {
        if (n >= MOCK_EVENTS.length) { clearInterval(id); return n; }
        return n + 1;
      });
    }, 420);
    return () => clearInterval(id);
  }, [reduced]);

  return (
    <div className="bg-ledger rounded-xl border border-white/10 overflow-hidden shadow-xl">
      {/* Title bar */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-white/10">
        <span className="w-3 h-3 rounded-full bg-critical/70" />
        <span className="w-3 h-3 rounded-full bg-minor/70" />
        <span className="w-3 h-3 rounded-full bg-matched/70" />
        <span className="ml-2 text-xs font-mono text-paper/40">Live pipeline feed</span>
        <span className="ml-auto flex items-center gap-1 text-[11px] text-matched/80 font-mono">
          <span className="w-1.5 h-1.5 rounded-full bg-matched animate-pulse" />
          streaming
        </span>
      </div>
      {/* Events */}
      <div className="px-4 py-3 space-y-1.5 font-mono text-xs min-h-[180px]">
        {MOCK_EVENTS.slice(0, visibleCount).map((ev, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.18 }}
            className="flex items-center gap-3"
          >
            <span className="text-paper/25 w-10 shrink-0">
              {String(9 + i).padStart(2, "0")}:0{i}
            </span>
            <span className={`w-20 shrink-0 font-medium ${ev.color}`}>
              {ev.label}
            </span>
            <span className="text-paper/55 truncate">{ev.doc}</span>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

function Hero() {
  return (
    <section className="relative min-h-screen flex flex-col justify-center pt-16 overflow-hidden bg-paper">
      {/* Subtle grid background */}
      <div
        aria-hidden="true"
        className="absolute inset-0 opacity-[0.03] pointer-events-none"
        style={{
          backgroundImage:
            "linear-gradient(#1F3B33 1px, transparent 1px), linear-gradient(90deg, #1F3B33 1px, transparent 1px)",
          backgroundSize: "40px 40px",
        }}
      />

      <div className="relative max-w-6xl mx-auto px-6 py-20 grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
        {/* Copy */}
        <div>
          <FadeUp delay={0.05}>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-ledger/10 border border-ledger/20 text-xs font-mono text-ledgerLight mb-6">
              <span className="w-1.5 h-1.5 rounded-full bg-ledgerLight animate-pulse" />
              AI-powered procurement intelligence
            </div>
          </FadeUp>

          <FadeUp delay={0.12}>
            <h1 className="font-display text-5xl lg:text-6xl text-ledger leading-[1.05] mb-6">
              Three-way matching,{" "}
              <span className="text-signal">finally automated</span>
            </h1>
          </FadeUp>

          <FadeUp delay={0.20}>
            <p className="text-lg text-ink/60 leading-relaxed mb-8 max-w-lg">
              SupplyChainIQ reconciles invoices, purchase orders and delivery receipts
              in seconds — flagging discrepancies, scoring vendor risk, and drafting
              dispute emails before your team even opens their inbox.
            </p>
          </FadeUp>

          <FadeUp delay={0.27}>
            <div className="flex flex-wrap gap-3">
              <Link
                to="/signup"
                className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-ledger text-paper font-medium hover:bg-ledgerLight transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-ledgerLight"
              >
                Get started free
                <ArrowRight size={16} aria-hidden="true" />
              </Link>
              <Link
                to="/login"
                className="inline-flex items-center gap-2 px-6 py-3 rounded-lg border border-line text-ink/70 font-medium hover:bg-line/40 hover:border-ink/20 transition-colors duration-150 focus-visible:ring-2"
              >
                Sign in
              </Link>
            </div>
          </FadeUp>
        </div>

        {/* Mock pipeline feed */}
        <FadeUp delay={0.18} className="w-full">
          <MockPipelineFeed />
        </FadeUp>
      </div>

      {/* Down caret */}
      <motion.div
        className="absolute bottom-8 left-1/2 -translate-x-1/2 text-ink/20"
        animate={{ y: [0, 6, 0] }}
        transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
        aria-hidden="true"
      >
        <ChevronRight size={22} className="rotate-90" />
      </motion.div>
    </section>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
   3. STAT STRIP
══════════════════════════════════════════════════════════════════════════ */
const STATS = [
  { label: "Documents processed",    value: "30+",  sub: "in seeded test corpus",    icon: FileText      },
  { label: "Match accuracy",         value: "98%",  sub: "precision on test corpus", icon: CheckCircle2  },
  { label: "Avg. review time saved", value: "4 hrs",sub: "per invoice batch",        icon: Clock         },
  { label: "Active vendors tracked", value: "Real-time", sub: "risk scoring + alerts", icon: ShieldCheck },
];

function StatStrip() {
  return (
    <section className="bg-ledger py-16">
      <div className="max-w-6xl mx-auto px-6">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-6">
          {STATS.map((s, i) => (
            <FadeUp key={s.label} delay={i * 0.08}>
              <div className="text-center">
                <s.icon
                  size={24}
                  className="mx-auto mb-3 text-wheat/70"
                  strokeWidth={1.5}
                  aria-hidden="true"
                />
                <div className="font-display text-3xl text-paper mb-1">{s.value}</div>
                <div className="text-sm font-medium text-wheat/90 mb-0.5">{s.label}</div>
                <div className="text-xs text-paper/40">{s.sub}</div>
              </div>
            </FadeUp>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
   4. PROBLEM → SOLUTION FLIP CARDS
══════════════════════════════════════════════════════════════════════════ */
const FLIP_CARDS = [
  {
    icon:        GitCompareArrows,
    problem:     "Manual three-way matching takes hours per batch",
    description: "Procurement teams manually cross-check POs, invoices, and delivery receipts line by line — a process that breaks down as order volume grows.",
    solution:    "SupplyChainIQ's multi-agent pipeline cross-checks POs, invoices, and delivery receipts automatically in seconds, flagging only genuine discrepancies with field-level detail.",
  },
  {
    icon:        Eye,
    problem:     "Discrepancies hide in spreadsheet rows",
    description: "A single mismatched unit price buried in a 500-row export can cost thousands — and manual review means it often goes unnoticed until month-end.",
    solution:    "Every flagged mismatch surfaces with full agent reasoning: the exact field, expected vs. actual value, severity rating, and a suggested resolution action.",
  },
  {
    icon:        TrendingDown,
    problem:     "No real-time pipeline visibility",
    description: "Once a document enters the process, it disappears into a black box — teams have no way to know if extraction stalled, matching failed, or a review is pending.",
    solution:    "The live dashboard streams every pipeline stage — OCR, extraction, matching, judgement — as documents flow through in real time, via WebSocket push.",
  },
  {
    icon:        AlertTriangle,
    problem:     "Vendor risk surprises at contract renewal",
    description: "Risk assessment happens once a year at renewal, not continuously — so a vendor's deteriorating delivery performance only becomes visible when it's too late to renegotiate.",
    solution:    "Continuous risk scoring updates after every invoice match, aggregating discrepancy history, contract violations, and SLA breaches into a live vendor risk score.",
  },
  {
    icon:        Layers,
    problem:     "Contract rate drift goes undetected",
    description: "Vendors occasionally invoice at rates slightly above the agreed contract price — small enough per line to slip past manual review, but significant in aggregate.",
    solution:    "Every invoice line is automatically checked against the active contract rate card. Any rate deviation, however small, is flagged before payment is approved.",
  },
  {
    icon:        Clock,
    problem:     "Dispute emails drafted manually, days late",
    description: "Writing a compliant dispute notice requires pulling context from three documents and referencing contract clauses — by the time it's sent, the payment window has often passed.",
    solution:    "Critical discrepancies trigger AI-drafted dispute emails referencing the exact invoice lines, contract clauses, and resolution deadlines — ready to review and send before the due date.",
  },
];

function FlipCard({ card }) {
  const [flipped, setFlipped] = useState(false);
  const reduced = useReducedMotion();
  const Icon = card.icon;

  return (
    <div
      className="cursor-pointer select-none"
      style={{ perspective: 900 }}
      onClick={() => setFlipped((f) => !f)}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setFlipped((f) => !f)}
      tabIndex={0}
      role="button"
      aria-pressed={flipped}
      aria-label={flipped ? card.solution : card.problem}
    >
      <motion.div
        className="relative w-full"
        style={{ transformStyle: "preserve-3d" }}
        animate={{ rotateY: flipped ? 180 : 0 }}
        transition={reduced ? { duration: 0 } : { duration: 0.42, ease: "easeInOut" }}
      >
        {/* Front — problem (in normal flow → drives card height) */}
        <div
          className="rounded-xl border border-line bg-white p-5 flex flex-col gap-3"
          style={{ backfaceVisibility: "hidden", minHeight: "13rem" }}
        >
          {/* Icon with soft signal backdrop circle */}
          <div className="w-9 h-9 rounded-full bg-signal/8 flex items-center justify-center shrink-0">
            <Icon size={18} className="text-signal" strokeWidth={1.5} aria-hidden="true" />
          </div>

          {/* Problem title + description */}
          <div className="flex-1 flex flex-col gap-1.5">
            <p className="text-sm font-semibold text-ink leading-snug">{card.problem}</p>
            <p className="text-xs text-ink/55 leading-relaxed">{card.description}</p>
          </div>

          {/* Interactive hint with animated arrow */}
          <div className="flex items-center gap-1 self-start mt-auto">
            <span className="text-[10px] text-ink/35 font-mono uppercase tracking-wide">
              flip for solution
            </span>
            <motion.span
              className="inline-flex text-ink/35"
              whileHover={{ x: 3 }}
              transition={{ type: "spring", stiffness: 400, damping: 20 }}
            >
              <ArrowRight size={11} strokeWidth={2} aria-hidden="true" />
            </motion.span>
          </div>
        </div>

        {/* Back — solution (absolutely overlaid, inherits height from front) */}
        <div
          className="absolute inset-0 rounded-xl bg-ledger p-5 flex flex-col gap-3"
          style={{ backfaceVisibility: "hidden", transform: "rotateY(180deg)" }}
        >
          <div className="w-9 h-9 rounded-full bg-paper/10 flex items-center justify-center shrink-0">
            <CheckCircle2 size={18} className="text-matched" strokeWidth={1.5} aria-hidden="true" />
          </div>
          <p className="text-sm text-paper/90 leading-relaxed flex-1">{card.solution}</p>
          <p className="text-[10px] text-paper/35 font-mono uppercase tracking-wide self-start mt-auto">
            tap to flip back
          </p>
        </div>
      </motion.div>
    </div>
  );
}

function FlipSection() {
  return (
    <section className="py-24 bg-paper">
      <div className="max-w-6xl mx-auto px-6">
        <FadeUp>
          <div className="text-center mb-14">
            <div className="text-[11px] font-mono uppercase tracking-widest text-signal mb-3">
              Pain points, solved
            </div>
            <h2 className="font-display text-4xl text-ledger">
              Every procurement headache,{" "}
              <span className="text-signal">automated away</span>
            </h2>
            <p className="mt-4 text-ink/50 max-w-xl mx-auto">
              Hover or tap any card to see how SupplyChainIQ handles it.
            </p>
          </div>
        </FadeUp>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {FLIP_CARDS.map((card, i) => (
            <FadeUp key={card.problem} delay={i * 0.07}>
              <FlipCard card={card} />
            </FadeUp>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
   5. HOW IT WORKS — AI agent pipeline
══════════════════════════════════════════════════════════════════════════ */
const AGENTS = [
  {
    icon:  FileText,
    name:  "Extractor",
    color: "bg-ledger/10 text-ledger border-ledger/20",
    dot:   "bg-ledger",
    desc:  "Reads PDFs (native or scanned via OCR) and pulls out structured fields — line items, amounts, dates, PO references — using a fast LLM.",
  },
  {
    icon:  Search,
    name:  "Matcher",
    color: "bg-ledgerLight/10 text-ledgerLight border-ledgerLight/20",
    dot:   "bg-ledgerLight",
    desc:  "Finds the matching Purchase Order for each invoice — exact PO number lookup first, then semantic vector search as fallback for informal references.",
  },
  {
    icon:  GitCompareArrows,
    name:  "Comparator",
    color: "bg-minor/10 text-[#7A6520] border-minor/20",
    dot:   "bg-minor",
    desc:  "Aligns every line item across the invoice, PO and delivery receipt. Emits raw discrepancy candidates: quantity, rate, currency and delivery shortfalls.",
  },
  {
    icon:  Scale,
    name:  "Judge",
    color: "bg-signal/10 text-signal border-signal/20",
    dot:   "bg-signal",
    desc:  "Filters false positives — rounding differences, unit conversions, partial deliveries still in transit — and assigns Minor / Major / Critical severity.",
  },
  {
    icon:  BarChart2,
    name:  "Risk Analyst",
    color: "bg-critical/10 text-critical border-critical/20",
    dot:   "bg-critical",
    desc:  "Updates the vendor risk score in real time after every match result. Aggregates discrepancy history, contract violations and SLA breaches.",
  },
];

function HowItWorks() {
  return (
    <section className="py-24 bg-white border-y border-line">
      <div className="max-w-6xl mx-auto px-6">
        <FadeUp>
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-ledger/8 border border-ledger/15 text-xs font-mono text-ledgerLight mb-4">
              <Brain size={13} aria-hidden="true" />
              Multi-agent pipeline
            </div>
            <h2 className="font-display text-4xl text-ledger">Powered by five specialised agents</h2>
            <p className="mt-4 text-ink/50 max-w-xl mx-auto">
              Each document passes through a chain of agents, each with a single
              job — so failures are isolated and the reasoning is always auditable.
            </p>
          </div>
        </FadeUp>

        {/* Timeline */}
        <div className="relative">
          {/* Connector line (hidden on mobile) */}
          <div
            aria-hidden="true"
            className="hidden lg:block absolute top-8 left-[10%] right-[10%] h-px bg-line"
          />

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-6 lg:gap-4">
            {AGENTS.map((agent, i) => (
              <FadeUp key={agent.name} delay={i * 0.1}>
                <div className="flex flex-col items-center text-center lg:relative">
                  {/* Step circle */}
                  <div
                    className={`w-16 h-16 rounded-full border-2 ${agent.color} flex items-center justify-center mb-4 relative z-10 bg-white`}
                  >
                    <agent.icon size={22} strokeWidth={1.5} aria-hidden="true" />
                  </div>
                  {/* Step number badge */}
                  <div className="flex items-center gap-1.5 mb-2">
                    <span className={`w-2 h-2 rounded-full ${agent.dot}`} aria-hidden="true" />
                    <span className="text-[11px] font-mono text-ink/40 uppercase tracking-wider">
                      Step {i + 1}
                    </span>
                  </div>
                  <div className="font-display text-lg text-ledger mb-2">{agent.name}</div>
                  <p className="text-sm text-ink/55 leading-relaxed">{agent.desc}</p>
                </div>
              </FadeUp>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
   6. FINAL CTA
══════════════════════════════════════════════════════════════════════════ */
function CTA() {
  return (
    <section className="py-24 bg-ledger overflow-hidden relative">
      {/* Decorative circle */}
      <div
        aria-hidden="true"
        className="absolute -right-32 -top-32 w-96 h-96 rounded-full bg-ledgerLight/30 blur-3xl pointer-events-none"
      />
      <div className="relative max-w-3xl mx-auto px-6 text-center">
        <FadeUp>
          <h2 className="font-display text-4xl lg:text-5xl text-paper leading-tight mb-4">
            Ready to close the{" "}
            <span className="text-wheat">discrepancy gap?</span>
          </h2>
          <p className="text-paper/60 text-lg mb-8">
            Set up in minutes. Every signup creates a private workspace — no shared credentials.
          </p>
          <div className="flex flex-wrap gap-3 justify-center">
            <Link
              to="/signup"
              className="inline-flex items-center gap-2 px-8 py-3.5 rounded-lg bg-paper text-ledger font-medium text-sm hover:bg-wheat transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-wheat"
            >
              Get started free
              <ArrowRight size={16} aria-hidden="true" />
            </Link>
            <Link
              to="/login"
              className="inline-flex items-center gap-2 px-8 py-3.5 rounded-lg border border-paper/30 text-paper/80 font-medium text-sm hover:bg-white/10 transition-colors duration-150 focus-visible:ring-2"
            >
              Sign in
            </Link>
          </div>
        </FadeUp>
      </div>
    </section>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
   ROOT
══════════════════════════════════════════════════════════════════════════ */
export default function Landing() {
  return (
    <div className="font-body text-ink antialiased">
      <MarketingNav />
      <Hero />
      <StatStrip />
      <FlipSection />
      <HowItWorks />
      <CTA />
      <MarketingFooter />
    </div>
  );
}
