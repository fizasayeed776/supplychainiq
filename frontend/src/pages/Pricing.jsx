import { Link } from "react-router-dom";
import MarketingLayout from "../components/MarketingLayout.jsx";

export default function Pricing() {
  return (
    <MarketingLayout title="Pricing">
      <p>
        SupplyChainIQ is currently in early access. Every signup gets a free
        private workspace with no time limit and no card required while we're in
        this phase. There's no tiered plan yet — everyone gets the full feature
        set: document ingestion, three-way matching, chat, vendor risk, and
        approvals.
      </p>
      <p>
        Paid plans will follow once we're out of early access. If you're using
        SupplyChainIQ for a team and want to talk about what's coming, reach out
        at{" "}
        <a href="mailto:hello@supplychainiq.example">
          hello@supplychainiq.example
        </a>
        .
      </p>
      <div className="not-prose mt-8">
        <Link
          to="/signup"
          className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-ledger text-paper text-sm font-medium hover:bg-ledgerLight transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-ledgerLight"
        >
          Get started free
        </Link>
      </div>
    </MarketingLayout>
  );
}
