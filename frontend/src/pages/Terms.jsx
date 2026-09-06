import { Link } from "react-router-dom";
import MarketingLayout from "../components/MarketingLayout.jsx";

const LAST_UPDATED = new Date().toLocaleDateString("en-US", {
  month: "long",
  year:  "numeric",
});

export default function Terms() {
  return (
    <MarketingLayout title="Terms of Service">
      {/* Disclaimer callout — outside prose flow */}
      <div className="not-prose mb-6 rounded-md border border-line bg-paper/60 px-4 py-3 text-sm text-ink/50">
        This is a draft terms document for an early-access pilot product. It
        should be reviewed by legal counsel before commercial launch.
      </div>

      <p className="not-prose text-sm text-ink/50 mb-8">Last updated: {LAST_UPDATED}</p>

      <h2>1. Acceptance of terms</h2>
      <p>
        By creating an account and using SupplyChainIQ, you agree to these terms.
        If you don't agree, please don't use the service. These terms apply to
        all users of the platform.
      </p>

      <h2>2. What SupplyChainIQ is</h2>
      <p>
        SupplyChainIQ is an early-access procurement intelligence tool that
        automates three-way document matching, vendor risk scoring, and invoice
        approvals. It is provided "as is" during this early-access phase, without
        guarantees of completeness, accuracy, or continuous availability.
      </p>

      <h2>3. Your account</h2>
      <p>
        You are responsible for keeping your credentials secure and for all
        activity that occurs in your workspace. If you believe your account has
        been compromised, contact us immediately.
      </p>

      <h2>4. Acceptable use</h2>
      <p>
        You must not upload documents you lack the rights to process, use the
        service for any unlawful purpose, or attempt to disrupt, reverse-engineer,
        or gain unauthorised access to any part of the service. We reserve the
        right to suspend accounts that violate these conditions.
      </p>

      <h2>5. Your data</h2>
      <p>
        You own what you upload. We process your documents only to provide the
        service as described in our{" "}
        <Link to="/privacy">Privacy Policy</Link>. We do not sell your data.
      </p>

      <h2>6. Availability</h2>
      <p>
        Features may change during early access as the product evolves. We make
        no uptime guarantee during this phase and may perform maintenance or
        changes with or without notice.
      </p>

      <h2>7. Limitation of liability</h2>
      <p>
        SupplyChainIQ is provided without warranties of any kind during early
        access. To the maximum extent permitted by law, we are not liable for
        indirect, incidental, or consequential damages arising from your use of
        the service.
      </p>

      <h2>8. Termination</h2>
      <p>
        Either party may end this relationship at any time. You can delete your
        account from within the app; we may suspend or terminate accounts that
        violate these terms. On termination, your data will be deleted in
        accordance with our Privacy Policy.
      </p>

      <h2>9. Changes to these terms</h2>
      <p>
        We will update the "Last updated" date when we make material changes.
        Continued use of the service after changes are posted constitutes
        acceptance of the revised terms.
      </p>

      <h2>10. Contact</h2>
      <p>
        <a href="mailto:hello@supplychainiq.example">hello@supplychainiq.example</a>
      </p>
    </MarketingLayout>
  );
}
