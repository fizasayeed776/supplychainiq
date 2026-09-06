import MarketingLayout from "../components/MarketingLayout.jsx";

export default function Docs() {
  return (
    <MarketingLayout title="Documentation">
      <h2>Getting started</h2>
      <p>
        Sign up, which creates your own private workspace. Upload a purchase
        order, invoice, and delivery receipt for the same order to see a
        three-way match happen automatically.
      </p>

      <h2>How matching works</h2>
      <p>
        Invoices are matched to their PO by reference number first, falling back
        to a semantic search over your documents if the reference is informal or
        missing. Discrepancies are scored by severity: minor, major, or critical.
      </p>

      <h2>Using chat</h2>
      <p>
        Ask questions about anything in your uploaded documents. Answers include
        citations back to the exact source so you can verify them.
      </p>

      <h2>Approvals</h2>
      <p>
        Clean invoices move to approval; invoices with discrepancies can be
        accepted, disputed (which drafts an email for you to review), or marked
        a false positive.
      </p>

      <h2>Need help</h2>
      <p>
        This is an early-access product; if something looks wrong or you're
        stuck, reach out at{" "}
        <a href="mailto:hello@supplychainiq.example">
          hello@supplychainiq.example
        </a>
        .
      </p>
    </MarketingLayout>
  );
}
