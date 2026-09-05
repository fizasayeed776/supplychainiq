import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Users, Loader2, Clock, CheckCircle2, AlertTriangle, CreditCard } from "lucide-react";
import { toast } from "sonner";
import clsx from "clsx";

import { api } from "../lib/api.js";
import { useWebSocket } from "../hooks/useWebSocket.js";
import PageHeader from "../components/PageHeader.jsx";
import Skeleton, { PageError } from "../components/Skeleton.jsx";
import { useAuth } from "../context/AuthContext.jsx";

/* ── Column definitions with semantic styling ────────────────────────────── */
const COLUMNS = [
  {
    state:   "pending_review",
    label:   "Pending review",
    icon:    Clock,
    dot:     "bg-major",
    header:  "text-major",
  },
  {
    state:   "approved",
    label:   "Approved",
    icon:    CheckCircle2,
    dot:     "bg-matched",
    header:  "text-matched",
  },
  {
    state:   "disputed",
    label:   "Disputed",
    icon:    AlertTriangle,
    dot:     "bg-critical",
    header:  "text-critical",
  },
  {
    state:   "paid",
    label:   "Paid",
    icon:    CreditCard,
    dot:     "bg-ledgerLight",
    header:  "text-ledgerLight",
  },
];

export default function Approvals() {
  const { workspaceId } = useAuth();
  const queryClient = useQueryClient();

  const { data: flows, isLoading, isError, refetch } = useQuery({
    queryKey: ["approvals"],
    queryFn: async () =>
      (await api.get("/workflow/approvals/", { params: { workspace: workspaceId } }))
        .data.results ?? [],
    enabled: !!workspaceId,
  });

  const decide = useMutation({
    mutationFn: ({ id, decision }) =>
      api.post(`/workflow/approvals/${id}/decide/`, { decision }),
    onSuccess: (_, { decision }) => {
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      toast.success(`Invoice ${decision === "approved" ? "approved" : "rejected"}`);
    },
    onError: (err) => {
      toast.error(err?.response?.data?.detail || "Could not update approval — please try again");
    },
  });

  return (
    <div>
      <PageHeader eyebrow="Human in the loop" title="Approvals" />

      <div className="p-8">
        {/* ── Loading skeleton ─────────────────────────────────────────── */}
        {isLoading && (
          <div className="grid grid-cols-4 gap-4">
            {COLUMNS.map((col) => (
              <div key={col.state} className="bg-paper/60 rounded-lg border border-line p-3 space-y-2">
                <Skeleton className="h-3 w-28" />
                {[1, 2].map((n) => (
                  <div key={n} className="bg-white border border-line rounded-md p-3 space-y-2">
                    <Skeleton className="h-3 w-20" />
                    <Skeleton className="h-4 w-32" />
                    <div className="flex gap-1.5">
                      <Skeleton className="h-7 flex-1" />
                      <Skeleton className="h-7 flex-1" />
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}

        {/* ── Error state ─────────────────────────────────────────────── */}
        {isError && (
          <PageError message="Could not load approvals. Check your connection." onRetry={refetch} />
        )}

        {/* ── Kanban board ─────────────────────────────────────────────── */}
        {!isLoading && !isError && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {COLUMNS.map((col) => {
              const cards = (flows || []).filter((f) => f.state === col.state);
              const ColIcon = col.icon;
              return (
                <div
                  key={col.state}
                  className="bg-paper/60 rounded-lg border border-line p-3"
                  role="region"
                  aria-label={col.label}
                >
                  {/* Column header with semantic icon + dot */}
                  <div className={clsx(
                    "flex items-center justify-between mb-3 px-1",
                  )}>
                    <div className="flex items-center gap-1.5">
                      <ColIcon size={12} className={col.header} aria-hidden="true" />
                      <span className="text-xs font-medium text-ink/60">{col.label}</span>
                    </div>
                    <span className={clsx(
                      "font-mono text-xs font-medium px-1.5 py-0.5 rounded-full",
                      cards.length > 0
                        ? `${col.dot.replace("bg-", "bg-")}/15 ${col.header}`
                        : "text-ink/30"
                    )}>
                      {cards.length}
                    </span>
                  </div>

                  {/* Empty column */}
                  {cards.length === 0 && (
                    <div className="text-[11px] text-ink/25 text-center py-5 border border-dashed border-line/60 rounded-md">
                      Empty
                    </div>
                  )}

                  <div className="space-y-2">
                    <AnimatePresence>
                      {cards.map((flow) => (
                        <FlowCard
                          key={flow.id}
                          flow={flow}
                          isPending={decide.isPending && decide.variables?.id === flow.id}
                          onDecide={(decision) => decide.mutate({ id: flow.id, decision })}
                        />
                      ))}
                    </AnimatePresence>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function FlowCard({ flow, onDecide, isPending }) {
  const queryClient = useQueryClient();

  const { connected } = useWebSocket(
    flow.invoice ? `/approval-room/${flow.invoice}/` : null,
    (msg) => {
      if (msg.type === "approval_updated" || msg.type === "state_change") {
        queryClient.invalidateQueries({ queryKey: ["approvals"] });
      }
    }
  );

  const pendingStep = flow.steps?.find((s) => s.decision === "pending");
  const canDecide = flow.state === "pending_review" && !!pendingStep;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.15 }}
      className="bg-white border border-line rounded-md p-3 text-sm transition-colors duration-150 hover:border-ledger/30 hover:bg-paper/40"
    >
      <div className="font-mono text-[11px] text-ink/40 mb-0.5">{flow.invoice_number}</div>
      <div className="text-sm font-medium text-ink mb-2 truncate">{flow.vendor_name}</div>

      {flow.amount && (
        <div className="font-mono text-xs text-ink/50 mb-2">
          ${Number(flow.amount).toLocaleString()}
        </div>
      )}

      {canDecide && (
        <div className="flex gap-1.5 mb-2">
          <button
            onClick={() => onDecide("approved")}
            disabled={isPending}
            aria-label={`Approve invoice ${flow.invoice_number}`}
            className="flex-1 px-2 py-1.5 rounded text-xs bg-ledger text-paper
                       hover:bg-ledgerLight disabled:opacity-50 disabled:cursor-not-allowed
                       focus-visible:ring-2 focus-visible:ring-ledgerLight
                       flex items-center justify-center gap-1 transition-colors duration-150"
          >
            {isPending ? <Loader2 size={11} className="animate-spin" /> : <CheckCircle2 size={11} />}
            Approve
          </button>
          <button
            onClick={() => onDecide("rejected")}
            disabled={isPending}
            aria-label={`Reject invoice ${flow.invoice_number}`}
            className="flex-1 px-2 py-1.5 rounded text-xs border border-signal text-signal
                       hover:bg-signal/10 disabled:opacity-50 disabled:cursor-not-allowed
                       focus-visible:ring-2 focus-visible:ring-signal transition-colors duration-150"
          >
            Reject
          </button>
        </div>
      )}

      {!canDecide && flow.state !== "pending_review" && (
        <div className="text-[11px] text-ink/30 mb-2 capitalize">
          {flow.state.replace(/_/g, " ")}
        </div>
      )}

      <div className="flex items-center gap-1 text-[11px] text-ink/25 pt-1 border-t border-line/50">
        <Users
          size={10}
          className={connected ? "text-matched" : "text-ink/25"}
          aria-hidden="true"
        />
        <span>{connected ? "Live" : "Reconnecting…"}</span>
      </div>
    </motion.div>
  );
}
