import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  UploadCloud, FileText, Receipt, FileSignature, Package,
  CheckCircle2, Loader2, AlertTriangle, Pencil, X, Save,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import clsx from "clsx";

import { api } from "../lib/api.js";
import PageHeader from "../components/PageHeader.jsx";
import Skeleton, { PageError } from "../components/Skeleton.jsx";
import { useAuth } from "../context/AuthContext.jsx";

/* ── OCR status metadata ─────────────────────────────────────────────────── */
const STATUS_META = {
  pending:        { icon: Loader2,       label: "Queued",         cls: "text-ink/30",   spin: true  },
  running:        { icon: Loader2,       label: "OCR running",    cls: "text-signal",   spin: true  },
  not_needed:     { icon: CheckCircle2,  label: "Native text",    cls: "text-matched",  spin: false },
  done:           { icon: CheckCircle2,  label: "OCR done",       cls: "text-matched",  spin: false },
  low_confidence: { icon: AlertTriangle, label: "Low confidence", cls: "text-[#7A6520]",spin: false },
  failed:         { icon: AlertTriangle, label: "Failed",         cls: "text-critical", spin: false },
};

/* ── Document type icons ─────────────────────────────────────────────────── */
const TYPE_ICONS = {
  invoice:          { icon: Receipt,       label: "Invoice",          cls: "text-signal" },
  po:               { icon: Package,       label: "Purchase order",   cls: "text-ledgerLight" },
  contract:         { icon: FileSignature, label: "Contract",         cls: "text-major" },
  delivery_receipt: { icon: Package,       label: "Delivery receipt", cls: "text-matched" },
};

function DocTypeIcon({ type, size = 15 }) {
  const meta = TYPE_ICONS[type] || { icon: FileText, label: type, cls: "text-ink/40" };
  const Icon = meta.icon;
  return <Icon size={size} className={meta.cls} aria-hidden="true" />;
}

function isProcessing(doc) {
  return (
    doc.ocr_status === "running" || doc.ocr_status === "pending" ||
    doc.extraction_status === "running" || doc.extraction_status === "pending"
  );
}

function processingLabel(doc) {
  if (doc.ocr_status === "running")          return "OCR in progress…";
  if (doc.ocr_status === "pending")          return "OCR queued…";
  if (doc.extraction_status === "running")   return "Extracting fields…";
  if (doc.extraction_status === "pending")   return "Extraction queued…";
  return null;
}

function guessType(name) {
  const lower = name.toLowerCase();
  if (lower.includes("invoice") || lower.includes("inv")) return "invoice";
  if (lower.includes("po") || lower.includes("purchase"))  return "po";
  if (lower.includes("contract"))                          return "contract";
  if (lower.includes("receipt") || lower.includes("delivery")) return "delivery_receipt";
  return "invoice";
}

export default function Documents() {
  const { workspaceId } = useAuth();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState(null);
  const [editingField, setEditingField] = useState(null);
  const [editValue, setEditValue] = useState("");

  const { data: documents, isLoading, isError, refetch } = useQuery({
    queryKey: ["documents", workspaceId],
    queryFn: async () =>
      (await api.get("/documents/documents/", { params: { workspace: workspaceId } }))
        .data.results ?? [],
    enabled: !!workspaceId,
    refetchInterval: 4000,
  });

  const upload = useMutation({
    mutationFn: async (file) => {
      const form = new FormData();
      form.append("file", file);
      form.append("workspace", workspaceId);
      form.append("type", guessType(file.name));
      return api.post("/documents/documents/", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
    },
    onSuccess: (_, file) => {
      queryClient.invalidateQueries({ queryKey: ["documents", workspaceId] });
      toast.success(`"${file.name}" uploaded — processing started`);
    },
    onError: (err, file) => {
      toast.error(`Upload failed for "${file.name}": ${err?.response?.data?.detail || "server error"}`);
    },
  });

  const correctExtraction = useMutation({
    mutationFn: async ({ docId, field, value }) =>
      api.patch(`/documents/documents/${docId}/correct-extraction/`, {
        corrections: { [field]: value },
      }),
    onSuccess: (_, { field }) => {
      queryClient.invalidateQueries({ queryKey: ["documents", workspaceId] });
      setEditingField(null);
      toast.success(`Field "${field}" corrected`);
    },
    onError: (err) => {
      toast.error(err?.response?.data?.detail || "Could not save correction");
    },
  });

  function onDrop(e) {
    e.preventDefault();
    [...e.dataTransfer.files].forEach((file) => upload.mutate(file));
  }

  const activeDoc = documents?.find((d) => d.id === selected) ?? documents?.[0];
  const processing = activeDoc ? isProcessing(activeDoc) : false;
  const processingMsg = activeDoc ? processingLabel(activeDoc) : null;

  return (
    <div>
      <PageHeader eyebrow="Ingestion" title="Documents" />

      <div className="p-8 grid grid-cols-12 gap-6">
        {/* ── Left: upload zone + document list ──────────────────────────── */}
        <div className="col-span-5">
          {/* Upload zone */}
          <label
            onDrop={onDrop}
            onDragOver={(e) => e.preventDefault()}
            className={clsx(
              "flex flex-col items-center justify-center gap-2 border-2 border-dashed rounded-lg py-8 text-center cursor-pointer transition-colors",
              upload.isPending
                ? "border-signal/50 bg-signal/5"
                : "border-line bg-white hover:border-ledgerLight/50 hover:bg-ledgerLight/5"
            )}
          >
            {upload.isPending ? (
              <>
                <Loader2 size={24} className="text-signal animate-spin" aria-hidden="true" />
                <div className="text-sm text-signal font-medium">Uploading…</div>
              </>
            ) : (
              <>
                <div className="w-10 h-10 rounded-full bg-ledger/10 flex items-center justify-center">
                  <UploadCloud size={18} className="text-ledgerLight" aria-hidden="true" />
                </div>
                <div>
                  <div className="text-sm text-ink/70 font-medium">
                    Drop files here to upload
                  </div>
                  <div className="text-xs text-ink/40 mt-0.5">
                    POs · invoices · contracts · delivery receipts
                  </div>
                </div>
                <div className="text-[11px] text-ink/30 mt-1 px-4 border-t border-line/40 pt-2 w-full text-center">
                  Native PDFs and scans both supported
                </div>
              </>
            )}
            <input
              type="file"
              multiple
              className="hidden"
              aria-label="Upload documents"
              onChange={(e) => [...e.target.files].forEach((f) => upload.mutate(f))}
            />
          </label>

          {/* Type legend */}
          <div className="flex items-center gap-3 mt-2 mb-4 px-1">
            {Object.entries(TYPE_ICONS).map(([type, meta]) => {
              const Icon = meta.icon;
              return (
                <span key={type} className="flex items-center gap-1 text-[10px] text-ink/30">
                  <Icon size={11} className={meta.cls} aria-hidden="true" />
                  {meta.label}
                </span>
              );
            })}
          </div>

          {/* List: loading */}
          {isLoading && (
            <div className="space-y-1">
              {[1, 2, 3].map((n) => (
                <div key={n} className="flex items-center gap-3 px-3 py-2.5 border border-line rounded-md bg-white">
                  <Skeleton className="h-4 w-4 rounded" />
                  <div className="flex-1 space-y-1.5">
                    <Skeleton className="h-3 w-40" />
                    <Skeleton className="h-2.5 w-24" />
                  </div>
                  <Skeleton className="h-3.5 w-3.5 rounded" />
                </div>
              ))}
            </div>
          )}

          {/* List: error */}
          {isError && <PageError message="Could not load documents." onRetry={refetch} />}

          {/* List: data */}
          {!isLoading && !isError && (
            <div className="space-y-1">
              {([...(documents || [])].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).slice(0, 4)).map((doc) => {
                const statusMeta = STATUS_META[doc.ocr_status] || STATUS_META.pending;
                const StatusIcon = statusMeta.icon;
                const docProcessing = isProcessing(doc);
                return (
                  <motion.button
                    key={doc.id}
                    layout
                    onClick={() => setSelected(doc.id)}
                    className={clsx(
                      "w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-left border transition-colors duration-150",
                      activeDoc?.id === doc.id
                        ? "border-ledgerLight bg-ledgerLight/5"
                        : "border-line bg-white hover:border-ledger/30 hover:bg-line/20"
                    )}
                  >
                    <DocTypeIcon type={doc.type} />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm truncate text-ink">
                        {doc.file?.split("/").pop() || doc.id}
                      </div>
                      <div className="text-xs mt-0.5">
                        {docProcessing ? (
                          <span className="text-signal">{processingLabel(doc)}</span>
                        ) : (
                          <span className="text-ink/40 capitalize">
                            {(TYPE_ICONS[doc.type]?.label || doc.type).replace(/_/g, " ")}
                          </span>
                        )}
                      </div>
                    </div>
                    <StatusIcon
                      size={13}
                      className={clsx(statusMeta.cls, statusMeta.spin && "animate-spin")}
                      aria-label={statusMeta.label}
                    />
                  </motion.button>
                );
              })}
              {documents?.length > 4 && (
                <Link
                  to="/documents/history"
                  className="block text-center text-xs text-ledgerLight hover:text-ledger py-2 transition-colors duration-150"
                >
                  View all documents →
                </Link>
              )}
              {!documents?.length && (
                <div className="text-xs text-ink/40 text-center py-6">
                  No documents yet — drop a file above to get started.
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Right: extraction detail panel ──────────────────────────────── */}
        <div className="col-span-7 border border-line rounded-lg bg-white overflow-hidden">
          {/* Panel header */}
          <div className="px-5 py-4 border-b border-line flex items-center justify-between">
            <div className="text-[11px] font-mono uppercase tracking-wider text-ink/40">
              Extracted fields
            </div>
            {activeDoc && (
              <div className="flex items-center gap-1.5 text-xs text-ink/40">
                <DocTypeIcon type={activeDoc.type} size={12} />
                <span className="capitalize">
                  {(TYPE_ICONS[activeDoc.type]?.label || activeDoc.type).replace(/_/g, " ")}
                </span>
              </div>
            )}
          </div>

          <div className="p-5">
            {/* No selection */}
            {!activeDoc && !isLoading && (
              <div className="flex flex-col items-center justify-center gap-2 py-12 text-center text-ink/25">
                <FileText size={28} strokeWidth={1.25} aria-hidden="true" />
                <div className="text-sm">Select a document to view its extraction.</div>
              </div>
            )}

            {/* Loading */}
            {isLoading && (
              <div className="space-y-3">
                <Skeleton className="h-3 w-full" />
                <div className="grid grid-cols-2 gap-x-6 gap-y-3 mt-4">
                  {[1, 2, 3, 4, 5, 6].map((n) => (
                    <div key={n} className="space-y-1">
                      <Skeleton className="h-2.5 w-20" />
                      <Skeleton className="h-4 w-28" />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Processing banner */}
            <AnimatePresence>
              {processing && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  className="mb-4 flex items-center gap-2 text-xs text-signal bg-signal/5 border border-signal/20 rounded-md px-3 py-2"
                >
                  <Loader2 size={12} className="animate-spin shrink-0" aria-hidden="true" />
                  <span>{processingMsg} Fields will appear when complete.</span>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Extraction data */}
            {activeDoc && !isLoading && (
              <div className="space-y-5">
                {typeof activeDoc.confidence === "number" && (
                  <ConfidenceBar value={activeDoc.confidence} />
                )}

                <dl className="grid grid-cols-2 gap-x-6 gap-y-4 text-sm">
                  {Object.entries(activeDoc.extraction || {})
                    .filter(([k]) => k !== "line_items")
                    .map(([key, value]) => (
                      <ExtractionField
                        key={key}
                        fieldKey={key}
                        value={value}
                        isEditing={editingField === key}
                        editValue={editValue}
                        isSaving={correctExtraction.isPending && correctExtraction.variables?.field === key}
                        onEdit={() => { setEditingField(key); setEditValue(String(value ?? "")); }}
                        onCancel={() => setEditingField(null)}
                        onSave={() => correctExtraction.mutate({ docId: activeDoc.id, field: key, value: editValue })}
                        onEditValueChange={setEditValue}
                      />
                    ))}
                </dl>

                {!!activeDoc.line_items?.length && (
                  <div>
                    <div className="text-[11px] font-mono uppercase tracking-wider text-ink/35 mb-2">
                      Line items
                    </div>
                    <div className="border border-line rounded-md overflow-hidden">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="bg-paper/60 border-b border-line text-left">
                            <th className="px-3 py-2 text-[11px] font-mono uppercase tracking-wider text-ink/35 font-normal">SKU</th>
                            <th className="px-3 py-2 text-[11px] font-mono uppercase tracking-wider text-ink/35 font-normal">Description</th>
                            <th className="px-3 py-2 text-[11px] font-mono uppercase tracking-wider text-ink/35 font-normal text-right">Qty</th>
                            <th className="px-3 py-2 text-[11px] font-mono uppercase tracking-wider text-ink/35 font-normal text-right">Unit $</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-line/60">
                          {activeDoc.line_items.map((li, i) => (
                            <tr key={i}>
                              <td className="px-3 py-2 font-mono text-xs text-ink/60">{li.sku || "—"}</td>
                              <td className="px-3 py-2 text-sm">{li.description || "—"}</td>
                              <td className="px-3 py-2 text-right font-mono text-xs">{li.quantity ?? "—"}</td>
                              <td className="px-3 py-2 text-right font-mono text-xs">{li.unit_price ?? "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function ExtractionField({ fieldKey, value, isEditing, editValue, isSaving, onEdit, onCancel, onSave, onEditValueChange }) {
  return (
    <div className="group relative">
      <dt className="text-[11px] font-mono uppercase tracking-wider text-ink/35 mb-0.5">
        {fieldKey.replace(/_/g, " ")}
      </dt>
      {isEditing ? (
        <dd className="flex items-center gap-1.5 mt-0.5">
          <input
            autoFocus
            value={editValue}
            onChange={(e) => onEditValueChange(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") onSave(); if (e.key === "Escape") onCancel(); }}
            className="flex-1 text-sm border border-ledgerLight rounded px-2 py-0.5 outline-none bg-white"
            aria-label={`Edit ${fieldKey}`}
          />
          <button
            onClick={onSave}
            disabled={isSaving}
            className="text-matched hover:text-matched/80 disabled:opacity-40"
            aria-label="Save correction"
          >
            {isSaving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
          </button>
          <button onClick={onCancel} className="text-ink/30 hover:text-ink/60" aria-label="Cancel">
            <X size={13} />
          </button>
        </dd>
      ) : (
        <dd className="flex items-center gap-1.5">
          <span className="text-sm text-ink font-medium">{String(value ?? "—")}</span>
          <button
            onClick={onEdit}
            className="opacity-0 group-hover:opacity-100 text-ink/25 hover:text-ledgerLight transition-opacity focus-visible:opacity-100"
            aria-label={`Correct ${fieldKey}`}
          >
            <Pencil size={11} />
          </button>
        </dd>
      )}
    </div>
  );
}

function ConfidenceBar({ value }) {
  const pct = Math.round(value * 100);
  const color = value > 0.8 ? "bg-matched" : value > 0.5 ? "bg-[#B79A2E]" : "bg-critical";
  const label = value > 0.8 ? "text-matched" : value > 0.5 ? "text-[#7A6520]" : "text-critical";
  return (
    <div className="p-3 bg-paper/60 rounded-md border border-line">
      <div className="flex justify-between items-center mb-2">
        <span className="text-[11px] font-mono uppercase tracking-wider text-ink/40">OCR confidence</span>
        <span className={`font-mono text-xs font-medium ${label}`}>{pct}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-line overflow-hidden">
        <motion.div
          className={`h-full rounded-full ${color}`}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.4, ease: "easeOut" }}
        />
      </div>
    </div>
  );
}
