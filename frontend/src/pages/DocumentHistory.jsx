import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  FileText, Receipt, FileSignature, Package,
  CheckCircle2, Loader2, AlertTriangle, Trash2, X, Check,
} from "lucide-react";
import { toast } from "sonner";
import clsx from "clsx";

import { api } from "../lib/api.js";
import PageHeader from "../components/PageHeader.jsx";
import Skeleton, { PageError } from "../components/Skeleton.jsx";
import { useAuth } from "../context/AuthContext.jsx";

/* ── OCR / extraction status metadata (mirrors Documents.jsx) ────────────── */
const STATUS_META = {
  pending:        { icon: Loader2,       label: "Queued",         cls: "text-ink/30",    spin: true  },
  running:        { icon: Loader2,       label: "OCR running",    cls: "text-signal",    spin: true  },
  not_needed:     { icon: CheckCircle2,  label: "Native text",    cls: "text-matched",   spin: false },
  done:           { icon: CheckCircle2,  label: "OCR done",       cls: "text-matched",   spin: false },
  low_confidence: { icon: AlertTriangle, label: "Low confidence", cls: "text-[#7A6520]", spin: false },
  failed:         { icon: AlertTriangle, label: "Failed",         cls: "text-critical",  spin: false },
};

/* ── Document type icons (mirrors Documents.jsx) ─────────────────────────── */
const TYPE_ICONS = {
  invoice:          { icon: Receipt,       label: "Invoice",          cls: "text-signal"       },
  po:               { icon: Package,       label: "Purchase order",   cls: "text-ledgerLight"  },
  contract:         { icon: FileSignature, label: "Contract",         cls: "text-major"        },
  delivery_receipt: { icon: Package,       label: "Delivery receipt", cls: "text-matched"      },
};

function DocTypeIcon({ type, size = 14 }) {
  const meta = TYPE_ICONS[type] || { icon: FileText, label: type, cls: "text-ink/40" };
  const Icon = meta.icon;
  return <Icon size={size} className={meta.cls} aria-hidden="true" />;
}

function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric", month: "short", day: "numeric",
  });
}

/* ── Inline confirm widget ───────────────────────────────────────────────── */
function DeleteButton({ onConfirm, isPending }) {
  const [confirming, setConfirming] = useState(false);

  if (isPending) {
    return <Loader2 size={14} className="animate-spin text-ink/30" aria-hidden="true" />;
  }

  if (confirming) {
    return (
      <span className="flex items-center gap-1">
        <button
          onClick={() => { setConfirming(false); onConfirm(); }}
          className="flex items-center gap-0.5 text-[11px] text-critical hover:text-critical/80 font-medium transition-colors duration-150 focus-visible:ring-2"
          aria-label="Confirm delete"
        >
          <Check size={12} aria-hidden="true" /> Yes
        </button>
        <span className="text-ink/20 text-[11px]">/</span>
        <button
          onClick={() => setConfirming(false)}
          className="flex items-center gap-0.5 text-[11px] text-ink/40 hover:text-ink transition-colors duration-150 focus-visible:ring-2"
          aria-label="Cancel delete"
        >
          <X size={12} aria-hidden="true" /> No
        </button>
      </span>
    );
  }

  return (
    <button
      onClick={() => setConfirming(true)}
      className="text-ink/25 hover:text-critical hover:bg-critical/10 rounded p-1 -mr-1 transition-colors duration-150 focus-visible:ring-2"
      aria-label="Delete document"
    >
      <Trash2 size={14} aria-hidden="true" />
    </button>
  );
}

/* ── Page ────────────────────────────────────────────────────────────────── */
export default function DocumentHistory() {
  const { workspaceId } = useAuth();
  const queryClient = useQueryClient();

  const { data: documents, isLoading, isError, refetch } = useQuery({
    queryKey: ["documents", workspaceId],
    queryFn: async () =>
      (await api.get("/documents/documents/", { params: { workspace: workspaceId } }))
        .data.results ?? [],
    enabled: !!workspaceId,
  });

  const deleteDoc = useMutation({
    mutationFn: (id) => api.delete(`/documents/documents/${id}/`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", workspaceId] });
      toast.success("Document deleted");
    },
    onError: (err) => {
      toast.error(err?.response?.data?.detail || "Could not delete document");
    },
  });

  const sorted = [...(documents || [])].sort(
    (a, b) => new Date(b.created_at) - new Date(a.created_at)
  );

  return (
    <div>
      <PageHeader eyebrow="Ingestion" title="Document history" />

      <div className="p-8 max-w-5xl">
        <div className="border border-line rounded-lg bg-white overflow-hidden">

          {/* Loading */}
          {isLoading && (
            <div className="divide-y divide-line/60">
              {[1, 2, 3, 4, 5].map((n) => (
                <div key={n} className="flex items-center gap-4 px-5 py-3">
                  <Skeleton className="h-4 w-4 rounded" />
                  <div className="flex-1 space-y-1.5">
                    <Skeleton className="h-3 w-56" />
                    <Skeleton className="h-2.5 w-32" />
                  </div>
                  <Skeleton className="h-3 w-20" />
                  <Skeleton className="h-3 w-20" />
                  <Skeleton className="h-4 w-4 rounded" />
                </div>
              ))}
            </div>
          )}

          {/* Error */}
          {isError && (
            <div className="p-6">
              <PageError message="Could not load document history." onRetry={refetch} />
            </div>
          )}

          {/* Data */}
          {!isLoading && !isError && (
            <>
              {/* Table header */}
              <div className="grid grid-cols-[auto_1fr_auto_auto_auto] items-center gap-4 px-5 py-2.5 bg-paper/60 border-b border-line text-[11px] font-mono uppercase tracking-wider text-ink/35">
                <span className="w-4" aria-hidden="true" />
                <span>File</span>
                <span className="w-28 text-left">Uploaded</span>
                <span className="w-28 text-left">OCR status</span>
                <span className="w-6" aria-hidden="true" />
              </div>

              {/* Rows */}
              <div className="divide-y divide-line/60">
                {sorted.map((doc) => {
                  const statusMeta = STATUS_META[doc.ocr_status] || STATUS_META.pending;
                  const StatusIcon = statusMeta.icon;
                  const filename = doc.file?.split("/").pop() || doc.id;

                  return (
                    <div
                      key={doc.id}
                      className="grid grid-cols-[auto_1fr_auto_auto_auto] items-center gap-4 px-5 py-3 hover:bg-paper/50 transition-colors duration-100"
                    >
                      {/* Type icon */}
                      <div className="w-4 flex items-center justify-center">
                        <DocTypeIcon type={doc.type} />
                      </div>

                      {/* Filename + type label */}
                      <div className="min-w-0">
                        <div className="text-sm text-ink truncate" title={filename}>
                          {filename}
                        </div>
                        <div className="text-xs text-ink/40 mt-0.5 capitalize">
                          {(TYPE_ICONS[doc.type]?.label || doc.type).replace(/_/g, " ")}
                        </div>
                      </div>

                      {/* Upload date */}
                      <div className="w-28 text-xs text-ink/50 font-mono">
                        {formatDate(doc.created_at)}
                      </div>

                      {/* OCR status badge */}
                      <div className="w-28">
                        <span
                          className={clsx(
                            "inline-flex items-center gap-1 text-xs",
                            statusMeta.cls
                          )}
                        >
                          <StatusIcon
                            size={11}
                            className={clsx(statusMeta.spin && "animate-spin")}
                            aria-hidden="true"
                          />
                          {statusMeta.label}
                        </span>
                      </div>

                      {/* Delete */}
                      <div className="w-6 flex items-center justify-center">
                        <DeleteButton
                          onConfirm={() => deleteDoc.mutate(doc.id)}
                          isPending={deleteDoc.isPending && deleteDoc.variables === doc.id}
                        />
                      </div>
                    </div>
                  );
                })}

                {!sorted.length && (
                  <div className="flex flex-col items-center justify-center gap-2 py-16 text-center text-ink/25">
                    <FileText size={28} strokeWidth={1.25} aria-hidden="true" />
                    <div className="text-sm">No documents yet.</div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
