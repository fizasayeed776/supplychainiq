import MarketingLayout from "../components/MarketingLayout.jsx";

const LAST_UPDATED = new Date().toLocaleDateString("en-US", {
  month: "long",
  year:  "numeric",
});

export default function Privacy() {
  return (
    <MarketingLayout title="Privacy Policy">
      {/* Disclaimer callout — outside prose flow */}
      <div className="not-prose mb-6 rounded-md border border-line bg-paper/60 px-4 py-3 text-sm text-ink/50">
        This is a draft policy for an early-access pilot product. It should be
        reviewed by legal counsel before commercial launch.
      </div>

      <p className="not-prose text-sm text-ink/50 mb-8">Last updated: {LAST_UPDATED}</p>

      <h2>1. Overview</h2>
      <p>
        SupplyChainIQ is a procurement intelligence tool that processes documents
        you upload to help you reconcile invoices, purchase orders, and delivery
        receipts. We collect and use information only to provide and improve this
        service. This policy explains what we collect, how we use it, and your
        rights over it.
      </p>

      <h2>2. Information we collect</h2>
      <p>
        We collect the account details you provide when signing up (name, email,
        password). We also store the documents you upload — purchase orders,
        invoices, contracts, delivery receipts — and the structured data we
        extract from them (line items, amounts, dates, vendor references). We
        collect basic usage data such as pages visited and actions taken, to
        understand how the product is used.
      </p>

      <h2>3. How we use it</h2>
      <p>
        Your data is used to perform three-way matching, calculate vendor risk
        scores, answer chat questions about your documents, and improve the
        product. Uploaded document content is sent to third-party AI providers
        solely to process your request; it is not used to train those providers'
        models beyond their own stated terms of service.
      </p>

      <h2>4. Data storage &amp; security</h2>
      <p>
        Each workspace is private and isolated — your documents and extracted
        data are not visible to other workspaces. Passwords are hashed and never
        stored in plain text. All access to your workspace requires authentication.
      </p>

      <h2>5. Data retention &amp; deletion</h2>
      <p>
        Documents can be deleted at any time from the Document History page.
        Deleting a document removes it and all extracted data associated with it.
        If you delete your account, all workspace data is removed.
      </p>

      <h2>6. Your rights</h2>
      <p>
        You can request a copy of the data we hold about you, or request deletion
        of your account and all associated data. To do either, contact us at the
        address below.
      </p>

      <h2>7. Changes to this policy</h2>
      <p>
        We will update the "Last updated" date at the top of this page when we
        make material changes. Continued use of the service after a change
        constitutes acceptance of the revised policy.
      </p>

      <h2>8. Contact</h2>
      <p>
        <a href="mailto:hello@supplychainiq.example">hello@supplychainiq.example</a>
      </p>
    </MarketingLayout>
  );
}
