import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import clsx from "clsx";
import { Building2 } from "lucide-react";

import { api } from "../lib/api.js";
import PageHeader from "../components/PageHeader.jsx";
import Skeleton, { PageError } from "../components/Skeleton.jsx";
import { useAuth } from "../context/AuthContext.jsx";

/* ── Risk tier ──────────────────────────────────────────────────────────── */
function riskTier(score) {
  if (score > 70) return { label: "High",   color: "text-critical", bar: "bg-critical", badge: "bg-critical/10 text-critical border-critical/30" };
  if (score > 40) return { label: "Medium", color: "text-major",    bar: "bg-major",    badge: "bg-major/10 text-major border-major/30" };
  return              { label: "Low",    color: "text-matched",  bar: "bg-matched",  badge: "bg-matched/10 text-matched border-matched/30" };
}

function RiskMeter({ score = 0, compact }) {
  const tier = riskTier(score);
  if (compact) {
    return (
      <div className="flex items-center gap-2 shrink-0">
        <div className="w-16 h-1.5 rounded-full bg-line overflow-hidden">
          <motion.div
            className={`h-full rounded-full ${tier.bar}`}
            initial={{ width: 0 }}
            animate={{ width: `${Math.min(score, 100)}%` }}
            transition={{ duration: 0.4, ease: "easeOut" }}
          />
        </div>
        <span className={`font-mono text-xs font-medium w-7 text-right ${tier.color}`}>
          {Math.round(score)}
        </span>
      </div>
    );
  }
  return (
    <div className="text-right shrink-0">
      <span
        className={clsx(
          "inline-flex items-center gap-1 px-2.5 py-1 rounded border text-sm font-mono font-medium",
          tier.badge
        )}
        aria-label={`Risk score: ${Math.round(score)} — ${tier.label}`}
      >
        {Math.round(score)}
      </span>
      <div className={`text-[10px] mt-0.5 ${tier.color}`}>{tier.label} risk</div>
    </div>
  );
}

export default function Vendors() {
  const { workspaceId } = useAuth();
  const [selected, setSelected] = useState(null);

  const {
    data: vendors,
    isLoading: vendorsLoading,
    isError: vendorsError,
    refetch: refetchVendors,
  } = useQuery({
    queryKey: ["vendors"],
    queryFn: async () =>
      (await api.get("/core/vendors/", { params: { workspace: workspaceId } }))
        .data.results ?? [],
    enabled: !!workspaceId,
  });

  useEffect(() => {
    if (!selected && vendors?.length) {
      setSelected(vendors[0].id);
    }
  }, [vendors, selected]);

  const {
    data: contracts,
    isLoading: contractsLoading,
    isError: contractsError,
  } = useQuery({
    queryKey: ["contracts", selected],
    queryFn: async () =>
      (await api.get("/core/contracts/", { params: { vendor: selected } }))
        .data.results ?? [],
    enabled: !!selected,
  });

  const active = vendors?.find((v) => v.id === selected) ?? vendors?.[0];

  return (
    <div>
      <PageHeader eyebrow="Vendor intelligence" title="Vendors" />

      <div className="p-8 grid grid-cols-12 gap-6">
        {/* ── Vendor list ─────────────────────────────────────────────────── */}
        <div className="col-span-5 space-y-1">
          {vendorsLoading &&
            [1, 2, 3].map((n) => (
              <div key={n} className="flex items-center justify-between px-4 py-3 border border-line rounded-md bg-white">
                <div className="space-y-1.5 flex-1">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-3 w-20" />
                </div>
                <div className="flex items-center gap-2 shrink-0 ml-4">
                  <Skeleton className="h-1.5 w-16 rounded-full" />
                  <Skeleton className="h-4 w-7" />
                </div>
              </div>
            ))
          }

          {vendorsError && (
            <PageError message="Could not load vendors." onRetry={refetchVendors} />
          )}

          {!vendorsLoading && !vendorsError &&
            (vendors || []).map((v) => (
              <button
                key={v.id}
                onClick={() => setSelected(v.id)}
                className={clsx(
                  "w-full flex items-center justify-between px-4 py-3 rounded-md border text-left transition-colors duration-150 focus-visible:ring-2",
                  active?.id === v.id
                    ? "border-ledgerLight bg-ledgerLight/5"
                    : "border-line bg-white hover:border-ledger/30 hover:bg-line/20"
                )}
              >
                <div className="min-w-0 mr-4">
                  <div className="text-sm font-medium text-ink truncate">{v.name}</div>
                  <div className="text-xs text-ink/40 mt-0.5">{v.payment_terms_days}-day payment terms</div>
                </div>
                <RiskMeter score={v.risk_score} compact />
              </button>
            ))
          }

          {!vendorsLoading && !vendorsError && !vendors?.length && (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <Building2 size={24} className="text-ink/20" strokeWidth={1.5} aria-hidden="true" />
              <div className="text-sm text-ink/40">
                No vendors yet — they will appear as invoices are processed.
              </div>
            </div>
          )}
        </div>

        {/* ── Vendor detail ───────────────────────────────────────────────── */}
        <div className="col-span-7 border border-line rounded-lg bg-white overflow-hidden">
          {!active && !vendorsLoading && (
            <div className="flex flex-col items-center justify-center gap-2 h-full py-16 text-center text-ink/30">
              <Building2 size={28} strokeWidth={1.25} aria-hidden="true" />
              <div className="text-sm">Select a vendor to view details.</div>
            </div>
          )}

          {vendorsLoading && (
            <div className="p-6 space-y-4">
              <div className="flex items-start justify-between">
                <Skeleton className="h-8 w-40" />
                <Skeleton className="h-8 w-20" />
              </div>
              <Skeleton lines={3} />
            </div>
          )}

          {active && !vendorsLoading && (
            <motion.div
              key={active.id}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.15 }}
            >
              {/* Detail header band */}
              <div className="px-6 py-5 border-b border-line flex items-start justify-between gap-4">
                <div>
                  <div className="font-display text-2xl text-ink leading-tight">{active.name}</div>
                  <div className="text-xs text-ink/40 mt-1">{active.payment_terms_days}-day payment terms</div>
                </div>
                <RiskMeter score={active.risk_score} />
              </div>

              <div className="p-6">
                {/* Risk explanation */}
                <div className="text-sm text-ink/70 leading-relaxed mb-6 p-4 bg-paper/60 rounded-md border border-line">
                  {active.risk_explanation ||
                    "Risk score has not been computed yet — it recomputes nightly as invoices arrive."}
                </div>

                {/* Contracts */}
                <div className="text-[11px] font-mono uppercase tracking-wider text-ink/40 mb-3">
                  Contracts
                </div>

                {contractsLoading && (
                  <div className="space-y-2">
                    {[1, 2].map((n) => (
                      <div key={n} className="flex items-center justify-between border border-line rounded-md px-3 py-2">
                        <Skeleton className="h-4 w-40" />
                        <Skeleton className="h-5 w-16" />
                      </div>
                    ))}
                  </div>
                )}

                {contractsError && (
                  <div className="text-xs text-critical">Could not load contracts.</div>
                )}

                {!contractsLoading && !contractsError && (
                  <div className="space-y-2">
                    {(contracts || []).map((c) => (
                      <div
                        key={c.id}
                        className="flex items-center justify-between border border-line rounded-md px-3 py-2.5 text-sm"
                      >
                        <div>
                          <span className="text-ink/70">Valid </span>
                          <span className="font-mono text-xs">{c.valid_from}</span>
                          <span className="text-ink/40 mx-1">→</span>
                          <span className="font-mono text-xs">{c.valid_until}</span>
                        </div>
                        <ContractBadge status={c.status} />
                      </div>
                    ))}
                    {!contracts?.length && (
                      <div className="text-xs text-ink/40 py-2">No contracts on file.</div>
                    )}
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
}

function ContractBadge({ status }) {
  const styles = {
    active:   "bg-matched/10 text-matched border-matched/30",
    expiring: "bg-minor/10   text-[#7A6520] border-minor/30",
    expired:  "bg-critical/10 text-critical border-critical/30",
    draft:    "bg-ink/5       text-ink/50   border-line",
  };
  return (
    <span
      className={clsx(
        "text-xs px-2 py-0.5 rounded border capitalize font-medium",
        styles[status] || styles.draft
      )}
    >
      {status}
    </span>
  );
}
