import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

export default function MarketingNav() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", handler, { passive: true });
    return () => window.removeEventListener("scroll", handler);
  }, []);

  return (
    <header
      className={`fixed top-0 inset-x-0 z-50 transition-all duration-200 ${
        scrolled ? "bg-white/95 backdrop-blur-sm border-b border-line shadow-sm" : "bg-transparent"
      }`}
    >
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link to="/" className="font-display text-xl text-ledger hover:text-ledgerLight transition-colors">
          SupplyChainIQ
        </Link>
        <nav className="flex items-center gap-3" aria-label="Site navigation">
          <Link
            to="/login"
            className="px-4 py-2 text-sm font-medium text-ink/70 hover:text-ink rounded-md hover:bg-line/40 transition-colors duration-150 focus-visible:ring-2"
          >
            Sign in
          </Link>
          <Link
            to="/signup"
            className="px-4 py-2 text-sm font-medium bg-ledger text-paper rounded-md hover:bg-ledgerLight transition-colors duration-150 focus-visible:ring-2"
          >
            Get started
          </Link>
        </nav>
      </div>
    </header>
  );
}
