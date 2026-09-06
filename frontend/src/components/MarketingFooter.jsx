import { Link } from "react-router-dom";

const FOOTER_LINKS = [
  { label: "Product", to: "/product" },
  { label: "Pricing", to: "/pricing" },
  { label: "Docs",    to: "/docs"    },
  { label: "Privacy", to: "/privacy" },
  { label: "Terms",   to: "/terms"   },
];

export default function MarketingFooter() {
  return (
    <footer className="bg-ledger border-t border-white/10 py-10">
      <div className="max-w-6xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="font-display text-lg text-paper/80">SupplyChainIQ</div>
        <nav className="flex flex-wrap gap-6 text-sm font-medium text-paper/60" aria-label="Footer links">
          {FOOTER_LINKS.map((l) => (
            <Link
              key={l.label}
              to={l.to}
              className="hover:text-paper/90 transition-colors focus-visible:outline-paper/40"
            >
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="text-xs text-paper/25 font-mono">
          © {new Date().getFullYear()} SupplyChainIQ
        </div>
      </div>
    </footer>
  );
}
