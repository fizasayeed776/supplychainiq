import MarketingLayout from "../components/MarketingLayout.jsx";

export default function Product() {
  return (
    <MarketingLayout title="What SupplyChainIQ does">
      <p>
        SupplyChainIQ reconciles procurement documents and tells you what needs
        attention, automatically.
      </p>
      <ul>
        <li>
          <strong>Document ingestion</strong> — drag-and-drop POs, invoices,
          contracts, and delivery receipts; native PDFs or scans, both are read
          automatically.
        </li>
        <li>
          <strong>Three-way matching</strong> — every invoice is checked
          line-by-line against its purchase order and delivery receipt, with
          mismatches flagged by severity.
        </li>
        <li>
          <strong>Contract compliance</strong> — invoiced rates, payment terms,
          and validity dates are checked against the vendor's contract on file.
        </li>
        <li>
          <strong>Ask your documents</strong> — a chat interface answers
          questions like "what's our termination clause with this vendor" with
          citations back to the source document.
        </li>
        <li>
          <strong>Vendor risk scoring</strong> — a running score per vendor
          built from discrepancy history and contract status, with a
          plain-language explanation.
        </li>
        <li>
          <strong>Approvals with a paper trail</strong> — invoices move through
          review to approval or dispute, with drafted dispute emails ready for a
          human to check and send.
        </li>
        <li>
          <strong>A live dashboard</strong> — match rates, open discrepancies,
          and vendor risk, updated as documents are processed.
        </li>
      </ul>
    </MarketingLayout>
  );
}
