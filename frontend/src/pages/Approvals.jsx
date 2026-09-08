import { useState, useEffect, useReducer } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  Users, Loader2, Clock, CheckCircle2, AlertTriangle, CreditCard,
  X, GitCommitVertical, CircleDot, User,
} from "lucide-react";
import { toast } from "sonner";
import clsx from "clsx";

import { api } from "../lib/api.js";
import { useWebSocket } from "../hooks/useWebSocket.js";
import PageHeader from "../components/PageHeader.jsx";
import Skeleton, { PageError } from "../components/Skeleton.jsx";
import { useAuth } from "../context/AuthContext.jsx";

/* ── Column definitions ──────────────────────────────────────────────────── */
const COLUMNS = [
  { state: "pending_review", label: "Pending review", icon: Clock,         dot: "bg-major",       header: "text-major"       },
  { state: "approved",       label: "Approved",        icon: CheckCircle2,  dot: "bg-matched",     header: "text-matched"     },
  { state: "disputed",       label: "Disputed",        icon: AlertTriangle, dot: "bg-critical",    header: "text-critical"    },
  { state: "paid",           label: "Paid",            icon: CreditCard,    dot: "bg-ledgerLight", header: "text-ledgerLight" },
];

/* ── Decision badge ──────────────────────────────────────────────────────── */
const DECISION_STYLES = {
  approved:  { cls: "bg-matched/10 text-matched border-matched/30",  icon: CheckCircle2  },
  rejected:  { cls: "bg-critical/10 text-critical border-critical/30", icon: AlertTriangle },
  escalated: { cls: "bg-major/10 text-major border-major/30",        icon: Clock         },
  pending:   { cls: "bg-ink/5 text-ink/50 border-line",              icon: CircleDot     },
};

function DecisionBadge({ decision }) {
  const s = DECISION_STYLES[decision] || DECISION_STYLES.pending;
  const Icon = s.icon;
  return (
    <span className={clsx(
      "inline-flex items-center gap-1 px-2 py-0.5 rounded border text-xs font-medium capitalize",
      s.cls,
    )}>
      <Icon size={10} aria-hidden="true" />
      {decision}
    </span>
  );
}

/* ── State badge ─────────────────────────────────────────────────────────── */
const STATE_STYLES = {
  draft:          "bg-ink/5 text-ink/50 border-line",
  pending_review: "bg-major/10 text-major border-major/30",
  approved:       "bg-matched/10 text-matched border-matched/30",
  disputed:       "bg-critical/10 text-critical border-critical/30",
  paid:           "bg-ledgerLight/10 text-ledgerLight border-ledgerLight/30",
};

function StateBadge({ state }) {
  return (
    <span className={clsx(
      "inline-flex items-center px-2 py-0.5 rounded border text-xs font-medium capitalize",
      STATE_STYLES[state] || "bg-ink/5 text-ink/50 border-line",
    )}>
      {state.replace(/_/g, " ")}
    </span>
  );
}

/* ── Presence reducer ────────────────────────────────────────────────────── */
function presenceReducer(state, action) {
  const next = new Set(state);
  if (action.event === "joined") next.add(action.user);
  if (action.event === "left")   next.delete(action.user);
  return next;
}

/* ── ApprovalDrawer ──────────────────────────────────────────────────────── */
function ApprovalDrawer({ flow, onClose }) {
  const queryClient = useQueryClient();
  const [presentUsers, dispatchPresence] = useReducer(presenceReducer, new Set());

  // Connect to the approval room WS only while this drawer is mounted.
  // useWebSocket is null-safe: path=null → no connection.
  const wsPath = flow?.invoice ? `/approval-room/${flow.invoice}/` : null;
  const { connected } = useWebSocket(wsPath, (msg) => {
    if (msg.type === "presence") {
      dispatchPresence(msg.payload);
    }
    if (msg.type === "status_change") {
      // The flow moved state — refresh the Kanban so the card repositions.
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
    }
  });

  if (!flow) return null;

  const steps = flow.steps ?? [];

  return (
    <>
      {/* Backdrop */}
      <motion.div
        className="fixed inset-0 bg-ink/30 z-20"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.15 }}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer panel */}
      <motion.div
        className="fixed top-0 right-0 bottom-0 w-[560px] max-w-full bg-white z-30 overflow-y-auto shadow-xl flex flex-col"
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", stiffness: 300, damping: 35 }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`Approval detail: ${flow.invoice_number}`}
      >
        {/* Sticky header */}
        <div className="sticky top-0 bg-white border-b border-line px-6 py-4 flex items-start justify-between z-10 shrink-0">
          <div>
            <div className="font-display text-xl text-ink">{flow.invoice_number}</div>
            <div className="text-sm text-ink/50 mt-0.5">{flow.vendor_name}</div>
          </div>
          <button
            onClick={onClose}
            className="text-ink/30 hover:text-ink hover:bg-line/40 rounded-full p-1 -mr-1 transition-colors duration-150 focus-visible:ring-2"
            aria-label="Close approval detail"
          >
            <X size={16} />
          </button>
        </div>

        <div className="p-6 space-y-6 flex-1">
          {/* ── Invoice context ─────────────────────────────────────────── */}
          <div className="flex items-center gap-2 flex-wrap">
            <StateBadge state={flow.state} />
            {flow.amount && (
              <span className="font-mono text-xs text-ink/50 px-2 py-0.5 rounded border border-line bg-paper/60">
                ${Number(flow.amount).toLocaleString()}
              </span>
            )}
          </div>

          {/* ── Live presence ────────────────────────────────────────────── */}
          <div>
            <div className="text-[11px] font-mono uppercase tracking-wider text-ink/40 mb-2">
              Live reviewers
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {/* WS status dot */}
              <span className="flex items-center gap-1 text-xs text-ink/40">
                <span
                  className={clsx(
                    "w-1.5 h-1.5 rounded-full inline-block",
                    connected ? "bg-matched animate-pulse" : "bg-ink/20",
                  )}
                  aria-hidden="true"
                />
                {connected ? "Connected" : "Connecting…"}
              </span>

              {presentUsers.size > 0 ? (
                [...presentUsers].map((username) => (
                  <span
                    key={username}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-ledger/10 text-ledger text-xs border border-ledger/20"
                  >
                    <User size={10} aria-hidden="true" />
                    {username}
                  </span>
                ))
              ) : (
                <span className="text-xs text-ink/30 italic">
                  {connected ? "No other reviewers here right now." : ""}
                </span>
              )}
            </div>
          </div>

          {/* ── Audit trail ─────────────────────────────────────────────── */}
          <div>
            <div className="text-[11px] font-mono uppercase tracking-wider text-ink/40 mb-3">
              Audit trail
            </div>

            {/* Empty state */}
            {steps.length === 0 && (
              <div className="flex flex-col items-center gap-2 py-8 text-center border border-dashed border-line/60 rounded-md">
                <GitCommitVertical size={20} className="text-ink/20" strokeWidth={1.5} aria-hidden="true" />
                <p className="text-xs text-ink/40">No approval steps recorded yet.</p>
              </div>
            )}

            {/* Timeline */}
            {steps.length > 0 && (
              <ol className="relative space-y-0" aria-label="Approval step timeline">
                {steps.map((step, idx) => {
                  const isLast = idx === steps.length - 1;
                  const actor = step.approver_name || step.decision_actor || "System";
                  const isAuto = !step.approver_name && !!step.decision_actor;

                  return (
                    <li key={step.id} className="flex gap-3">
                      {/* Timeline spine */}
                      <div className="flex flex-col items-center shrink-0 w-4">
                        <span
                          className={clsx(
                            "w-2 h-2 rounded-full border-2 mt-1 shrink-0",
                            step.decision === "approved"  && "bg-matched border-matched",
                            step.decision === "rejected"  && "bg-critical border-critical",
                            step.decision === "escalated" && "bg-major border-major",
                            step.decision === "pending"   && "bg-white border-ink/30",
                          )}
                          aria-hidden="true"
                        />
                        {!isLast && (
                          <span className="w-px flex-1 bg-line/60 my-1" aria-hidden="true" />
                        )}
                      </div>

                      {/* Step content */}
                      <div className={clsx("pb-4 flex-1 min-w-0", isLast && "pb-0")}>
                        <div className="flex items-center gap-2 flex-wrap mb-1">
                          <DecisionBadge decision={step.decision} />
                          <span className="text-xs text-ink/50 flex items-center gap-1">
                            <User size={10} aria-hidden="true" />
                            {actor}
                            {isAuto && (
                              <span className="text-[10px] text-ink/30 italic">(auto)</span>
                            )}
                          </span>
                        </div>

                        <div className="text-[11px] text-ink/40 font-mono space-y-0.5">
                          {step.decided_at ? (
                            <div>
                              Decided:{" "}
                              <time dateTime={step.decided_at}>
                                {new Date(step.decided_at).toLocaleString()}
                              </time>
                            </div>
                          ) : (
                            <div className="text-ink/25 italic">Awaiting decision</div>
                          )}
                          {step.escalation_deadline && (
                            <div>
                              Deadline:{" "}
                              <time
                                dateTime={step.escalation_deadline}
                                className={
                                  new Date(step.escalation_deadline) < new Date()
                                    ? "text-critical"
                                    : ""
                                }
                              >
                                {new Date(step.escalation_deadline).toLocaleString()}
                              </time>
                            </div>
                          )}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </div>
        </div>
      </motion.div>
    </>
  );
}

/* ── Main page ───────────────────────────────────────────────────────────── */
export default function Approvals() {
  const { workspaceId } = useAuth();
  const queryClient = useQueryClient();
  const [openFlowId, setOpenFlowId] = useState(null);

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

  const openFlow = flows?.find((f) => f.id === openFlowId) ?? null;

  // Close drawer with Escape key
  useEffect(() => {
    if (!openFlowId) return;
    const handler = (e) => { if (e.key === "Escape") setOpenFlowId(null); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [openFlowId]);

  return (
    <div>
      <PageHeader eyebrow="Human in the loop" title="Approvals" />

      <div className="p-8">
        {/* Loading skeleton */}
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

        {/* Error state */}
        {isError && (
          <PageError message="Could not load approvals. Check your connection." onRetry={refetch} />
        )}

        {/* Kanban board */}
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
                  <div className="flex items-center justify-between mb-3 px-1">
                    <div className="flex items-center gap-1.5">
                      <ColIcon size={12} className={col.header} aria-hidden="true" />
                      <span className="text-xs font-medium text-ink/60">{col.label}</span>
                    </div>
                    <span className={clsx(
                      "font-mono text-xs font-medium px-1.5 py-0.5 rounded-full",
                      cards.length > 0
                        ? `${col.dot}/15 ${col.header}`
                        : "text-ink/30",
                    )}>
                      {cards.length}
                    </span>
                  </div>

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
                          onOpen={() => setOpenFlowId(flow.id)}
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

      {/* Detail drawer */}
      <AnimatePresence>
        {openFlow && (
          <ApprovalDrawer
            key={openFlow.id}
            flow={openFlow}
            onClose={() => setOpenFlowId(null)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

/* ── FlowCard ────────────────────────────────────────────────────────────── */
function FlowCard({ flow, onDecide, isPending, onOpen }) {
  const queryClient = useQueryClient();

  // Per-card WS connection for live Kanban invalidation (existing behaviour).
  const { connected } = useWebSocket(
    flow.invoice ? `/approval-room/${flow.invoice}/` : null,
    (msg) => {
      if (msg.type === "approval_updated" || msg.type === "status_change") {
        queryClient.invalidateQueries({ queryKey: ["approvals"] });
      }
    },
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
      className={clsx(
        "bg-white border border-line rounded-md p-3 text-sm",
        "transition-colors duration-150",
        "hover:border-ledger/30 hover:bg-paper/40",
        "cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ledger/40",
      )}
      onClick={onOpen}
      tabIndex={0}
      role="button"
      aria-label={`Open approval detail for ${flow.invoice_number}`}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpen(); } }}
    >
      <div className="font-mono text-[11px] text-ink/40 mb-0.5">{flow.invoice_number}</div>
      <div className="text-sm font-medium text-ink mb-2 truncate">{flow.vendor_name}</div>

      {flow.amount && (
        <div className="font-mono text-xs text-ink/50 mb-2">
          ${Number(flow.amount).toLocaleString()}
        </div>
      )}

      {canDecide && (
        <div className="flex gap-1.5 mb-2" onClick={(e) => e.stopPropagation()}>
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
