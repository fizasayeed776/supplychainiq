import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { X, Loader2, GitCompareArrows, CheckCircle2, AlertTriangle, HelpCircle, Package, Receipt, Truck } from "lucide-react";
import { toast } from "sonner";
import clsx from "clsx";

import { api } from "../lib/api.js";
import PageHeader from "../components/PageHeader.jsx";
import SeverityBadge from "../components/SeverityBadge.jsx";
import Skeleton, { SkeletonRow, PageError } from "../components/Skeleton.jsx";
import { useAuth } from "../context/AuthContext.jsx";

/* ── Discrepancy value formatter ─────────────────────────────────────────── */
function formatDiscrepancyValue(value) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") {
    return Object.entries(value)
      .map(([k, v]) => `${k}: ${v}`)
      .join(", ");
  }
  return String(value);
}

/* ── Status pill ─────────────────────────────────────────────────────────── */
const STATUS_STYLES = {
  matched:    { cls: "bg-matched/10 text-matched border-matched/30",     icon: CheckCircle2  },
  discrepant: { cls: "bg-signal/10  text-signal  border-signal/30",      icon: AlertTriangle },
  unmatched:  { cls: "bg-ink/5      text-ink/50  border-line",           icon: HelpCircle    },
};

function StatusPill({ status }) {
  const s = STATUS_STYLES[status] || STATUS_STYLES.unmatched;
  const Icon = s.icon;
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded border text-xs font-medium capitalize",
        s.cls
      )}
    >
      <Icon size={10} aria-hidden="true" />
      {status}
    </span>
  );
}

export default function Matches() {
  const { workspaceId } = useAuth();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("");
  const [openId, setOpenId] = useState(null);

  const { data: matches, isLoading, isError, refetch } = useQuery({
    queryKey: ["matches", statusFilter],
    queryFn: async () =>
      (await api.get("/matching/results/", {
        params: { workspace: workspaceId, ...(statusFilter ? { status: statusFilter } : {}) },
      })).data.results ?? [],
    enabled: !!workspaceId,
  });

  const review = useMutation({
    mutationFn: ({ id, action }) =>
      api.post(`/matching/results/${id}/review/`, { action }),
    onSuccess: (_, { action }) => {
      queryClient.invalidateQueries({ queryKey: ["matches"] });
      setOpenId(null);
      const labels = {
        accept:         "Discrepancy accepted",
        dispute:        "Dispute raised",
        false_positive: "Marked as false positive",
      };
      toast.success(labels[action] || "Match updated");
    },
    onError: (err) => {
      toast.error(err?.response?.data?.detail || "Could not save review — please try again");
    },
  });

  const open = matches?.find((m) => m.id === openId);

  /* ── Filter tab accent ──────────────────────────────────────────────── */
  const FILTER_ACCENT = {
    "":          "bg-ledger text-paper border-ledger",
    matched:     "bg-matched/10 text-matched border-matched/40",
    discrepant:  "bg-signal/10  text-signal  border-signal/40",
    unmatched:   "bg-ink/5      text-ink/50  border-line",
  };

  return (
    <div>
      <PageHeader
        eyebrow="Three-way match"
        title="Matches"
        action={
          <div className="flex gap-1" role="group" aria-label="Filter by status">
            {["", "matched", "discrepant", "unmatched"].map((s) => (
              <button
                key={s || "all"}
                onClick={() => setStatusFilter(s)}
                className={clsx(
                  "px-3 py-1.5 rounded-md text-xs capitalize border transition-colors duration-150 focus-visible:ring-2",
                  statusFilter === s
                    ? (FILTER_ACCENT[s] || "bg-ledger text-paper border-ledger")
                    : "border-line text-ink/60 hover:bg-line/30 hover:border-ink/20"
                )}
              >
                {s || "All"}
              </button>
            ))}
          </div>
        }
      />

      <div className="p-8">
        {isError && (
          <PageError message="Could not load matches. Check your connection." onRetry={refetch} />
        )}

        {!isError && (
          <div className="border border-line rounded-lg bg-white overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left border-b border-line bg-paper/60">
                  <th className="px-4 py-3 text-[11px] font-mono uppercase tracking-wider text-ink/40 font-normal">Invoice</th>
                  <th className="px-4 py-3 text-[11px] font-mono uppercase tracking-wider text-ink/40 font-normal">Vendor</th>
                  <th className="px-4 py-3 text-[11px] font-mono uppercase tracking-wider text-ink/40 font-normal">Status</th>
                  <th className="px-4 py-3 text-[11px] font-mono uppercase tracking-wider text-ink/40 font-normal">Severity</th>
                  <th className="px-4 py-3 text-[11px] font-mono uppercase tracking-wider text-ink/40 font-normal text-right">Issues</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line/60">
                {isLoading &&
                  [1, 2, 3, 4, 5].map((n) => <SkeletonRow key={n} cols={5} />)
                }
                {!isLoading &&
                  (matches || []).map((m) => (
                    <tr
                      key={m.id}
                      onClick={() => setOpenId(m.id)}
                      tabIndex={0}
                      role="button"
                      aria-label={`Open match ${m.invoice_number}`}
                      onKeyDown={(e) => e.key === "Enter" && setOpenId(m.id)}
                      className="hover:bg-paper/60 cursor-pointer transition-colors focus-visible:outline-none focus-visible:bg-paper/60"
                    >
                      <td className="px-4 py-3 font-mono text-xs text-ink/70">{m.invoice_number}</td>
                      <td className="px-4 py-3 text-sm">{m.vendor_name}</td>
                      <td className="px-4 py-3"><StatusPill status={m.status} /></td>
                      <td className="px-4 py-3"><SeverityBadge severity={m.severity} /></td>
                      <td className="px-4 py-3 text-right">
                        {(m.discrepancies?.length ?? 0) > 0 ? (
                          <span className="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full bg-signal/10 text-signal text-xs font-mono font-medium">
                            {m.discrepancies.length}
                          </span>
                        ) : (
                          <span className="text-ink/30 text-xs">—</span>
                        )}
                      </td>
                    </tr>
                  ))
                }
                {!isLoading && !matches?.length && (
                  <tr>
                    <td colSpan={5}>
                      <div className="flex flex-col items-center gap-2 py-12 text-center">
                        <GitCompareArrows size={24} className="text-ink/20" strokeWidth={1.5} aria-hidden="true" />
                        <div className="text-sm text-ink/40">
                          {statusFilter
                            ? `No ${statusFilter} matches found.`
                            : "No matches yet — upload and process invoices to see results here."}
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Detail drawer ──────────────────────────────────────────────────── */}
      <AnimatePresence>
        {open && (
          <>
            <motion.div
              className="fixed inset-0 bg-ink/30 z-20"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              onClick={() => setOpenId(null)}
            />
            <motion.div
              className="fixed top-0 right-0 bottom-0 w-[560px] max-w-full bg-white z-30 overflow-y-auto shadow-xl"
              initial={{ x: "100%" }}
              animate={{ x: 0 }}
              exit={{ x: "100%" }}
              transition={{ type: "spring", stiffness: 300, damping: 35 }}
              onClick={(e) => e.stopPropagation()}
              role="dialog"
              aria-modal="true"
              aria-label={`Match detail: ${open.invoice_number}`}
            >
              {/* Drawer header */}
              <div className="sticky top-0 bg-white border-b border-line px-6 py-4 flex items-start justify-between z-10">
                <div>
                  <div className="font-display text-xl text-ink">{open.invoice_number}</div>
                  <div className="text-sm text-ink/50 mt-0.5">{open.vendor_name}</div>
                </div>
                <button
                  onClick={() => setOpenId(null)}
                  className="text-ink/30 hover:text-ink hover:bg-line/40 rounded-full p-1 -mr-1 transition-colors duration-150 focus-visible:ring-2"
                  aria-label="Close detail"
                >
                  <X size={16} />
                </button>
              </div>

              <div className="p-6">
                <div className="flex items-center gap-2 mb-5">
                  <StatusPill status={open.status} />
                  <SeverityBadge severity={open.severity} />
                </div>

                {open.agent_reasoning && (
                  <div className="text-sm text-ink/70 leading-relaxed mb-5 p-3 bg-paper/60 rounded-md border border-line">
                    {open.agent_reasoning}
                  </div>
                )}

                {/* Discrepancy cards */}
                <div className="space-y-3 mb-6">
                  {(open.discrepancies || []).map((d, i) => (
                    <div key={i} className="border border-line rounded-md p-3 text-sm bg-signal/5 border-l-2 border-l-signal">
                      <div className="flex justify-between text-xs text-ink/40 mb-2">
                        <span className="capitalize font-medium">{d.type?.replace(/_/g, " ")}</span>
                        {d.sku && <span className="font-mono">{d.sku}</span>}
                      </div>
                      <div className="flex gap-6 text-xs mb-2 font-mono">
                        <div>
                          <div className="text-ink/30 mb-0.5">Expected</div>
                          <div className="text-ink font-medium">{formatDiscrepancyValue(d.expected)}</div>
                        </div>
                        <div>
                          <div className="text-ink/30 mb-0.5">Actual</div>
                          <div className="text-signal font-medium">{formatDiscrepancyValue(d.actual)}</div>
                        </div>
                      </div>
                      {d.reasoning && (
                        <div className="text-ink/60 text-xs leading-relaxed">{d.reasoning}</div>
                      )}
                    </div>
                  ))}
                  {!open.discrepancies?.length && (
                    <div className="flex items-center gap-2 text-xs text-matched p-3 bg-matched/5 rounded-md border border-matched/20">
                      <CheckCircle2 size={13} aria-hidden="true" />
                      No discrepancies — clean match.
                    </div>
                  )}
                </div>

                {/* Three-way document viewer */}
                <ThreeWayDocumentView match={open} />

                {/* Actions */}
                {open.status === "discrepant" && (
                  <div className="flex gap-2">
                    {[
                      { action: "accept",         label: "Accept",         cls: "bg-ledger text-paper hover:bg-ledgerLight" },
                      { action: "dispute",        label: "Raise dispute",  cls: "border border-signal text-signal hover:bg-signal/5" },
                      { action: "false_positive", label: "False positive", cls: "border border-line text-ink/60 hover:bg-line/20" },
                    ].map(({ action, label, cls }) => (
                      <button
                        key={action}
                        onClick={() => review.mutate({ id: open.id, action })}
                        disabled={review.isPending}
                        className={clsx(
                          "px-3 py-2 rounded-md text-sm flex items-center gap-1.5 transition-colors focus-visible:ring-2",
                          "disabled:opacity-50 disabled:cursor-not-allowed",
                          cls
                        )}
                      >
                        {review.isPending && review.variables?.id === open.id && (
                          <Loader2 size={13} className="animate-spin" />
                        )}
                        {label}
                      </button>
                    ))}
                  </div>
                )}
                {open.status !== "discrepant" && (
                  <div className="text-xs text-ink/30 italic">
                    This match has already been reviewed.
                  </div>
                )}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ── Three-way document viewer ───────────────────────────────────────────── */
function DocColumn({ icon: Icon, label, accent, header, lineItems, emptyMsg }) {
  return (
    <div className="flex-1 min-w-0">
      <div className={clsx("flex items-center gap-1.5 mb-2 text-xs font-medium", accent)}>
        <Icon size={12} aria-hidden="true" />
        {label}
      </div>
      {header && (
        <div className="text-[11px] font-mono text-ink/50 mb-2 space-y-0.5">
          {Object.entries(header).map(([k, v]) => (
            <div key={k} className="flex gap-1">
              <span className="text-ink/30 capitalize">{k.replace(/_/g, " ")}:</span>
              <span className="truncate">{String(v ?? "—")}</span>
            </div>
          ))}
        </div>
      )}
      {lineItems?.length ? (
        <table className="w-full text-[11px] font-mono">
          <thead>
            <tr className="text-ink/30 text-left border-b border-line/60">
              <th className="pb-1 font-normal">SKU</th>
              <th className="pb-1 font-normal text-right">Qty</th>
              <th className="pb-1 font-normal text-right">Unit $</th>
            </tr>
          </thead>
          <tbody>
            {lineItems.map((li, i) => (
              <tr key={i} className="border-b border-line/30 last:border-0">
                <td className="py-0.5 text-ink/60 truncate max-w-[60px]">{li.sku || "—"}</td>
                <td className="py-0.5 text-right">{li.quantity ?? "—"}</td>
                <td className="py-0.5 text-right">{li.unit_price ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="text-[11px] text-ink/30 italic">{emptyMsg || "—"}</div>
      )}
    </div>
  );
}

function ThreeWayDocumentView({ match }) {
  const inv = match.invoice_detail;
  const po = match.po_detail;
  const dr = match.dr_detail;

  if (!inv) return null;

  return (
    <div className="mb-6">
      <div className="text-[11px] font-mono uppercase tracking-wider text-ink/40 mb-3">
        Three-way document view
      </div>
      <div className="flex gap-3 border border-line rounded-md p-3 bg-paper/40 overflow-x-auto">
        <DocColumn
          icon={Receipt}
          label="Invoice"
          accent="text-signal"
          header={{ number: inv.invoice_number, date: inv.invoice_date, currency: inv.currency }}
          lineItems={inv.line_items}
        />
        <div className="w-px bg-line/60 shrink-0" />
        <DocColumn
          icon={Package}
          label="Purchase Order"
          accent="text-ledgerLight"
          header={po ? { number: po.po_number, date: po.order_date, currency: po.currency } : null}
          lineItems={po?.line_items}
          emptyMsg="No PO matched"
        />
        <div className="w-px bg-line/60 shrink-0" />
        <DocColumn
          icon={Truck}
          label="Delivery Receipt"
          accent="text-matched"
          header={dr ? { po_ref: dr.referenced_po_number, date: dr.delivery_date, partial: dr.is_partial ? "yes" : "no" } : null}
          lineItems={dr?.line_items}
          emptyMsg="No delivery receipt"
        />
      </div>
    </div>
  );
}
