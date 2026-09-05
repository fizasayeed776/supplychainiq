import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Loader2, Bell, Sliders } from "lucide-react";
import { toast } from "sonner";

import { api } from "../lib/api.js";
import PageHeader from "../components/PageHeader.jsx";
import Skeleton, { PageError } from "../components/Skeleton.jsx";
import { useAuth } from "../context/AuthContext.jsx";

export default function Settings() {
  return (
    <div>
      <PageHeader eyebrow="Configuration" title="Settings" />
      <div className="p-8 max-w-3xl space-y-8">
        <WebhookSection />
        <TriageRulesSection />
      </div>
    </div>
  );
}

/* ── Section header shared component ───────────────────────────────────── */
function SectionHeader({ icon: Icon, title, description }) {
  return (
    <div className="flex items-start gap-3 mb-5 pb-4 border-b border-line">
      <div className="mt-0.5 p-2 rounded-md bg-ledger/8 shrink-0">
        <Icon size={15} className="text-ledgerLight" strokeWidth={1.75} aria-hidden="true" />
      </div>
      <div>
        <div className="text-sm font-medium text-ink">{title}</div>
        <div className="text-xs text-ink/50 mt-0.5 leading-relaxed">{description}</div>
      </div>
    </div>
  );
}

/* ── Webhook section ─────────────────────────────────────────────────────── */
function WebhookSection() {
  const { workspaceId } = useAuth();
  const [url, setUrl] = useState("");
  const queryClient = useQueryClient();

  const { data: workspace, isLoading, isError, refetch } = useQuery({
    queryKey: ["workspace", workspaceId],
    queryFn: async () => (await api.get(`/core/workspaces/${workspaceId}/`)).data,
    enabled: !!workspaceId,
  });

  const save = useMutation({
    mutationFn: (urls) =>
      api.patch(`/core/workspaces/${workspaceId}/`, {
        settings_json: { ...workspace?.settings_json, outbound_webhook_urls: urls },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace", workspaceId] });
      toast.success("Webhook URLs saved");
    },
    onError: () => toast.error("Could not save webhook URLs"),
  });

  const urls = workspace?.settings_json?.outbound_webhook_urls || [];
  const canAdd = url.trim().length > 0 && !save.isPending;

  return (
    <section className="border border-line rounded-lg bg-white p-5">
      <SectionHeader
        icon={Bell}
        title="Outbound alerts"
        description="Critical discrepancies, SLA breaches, and the weekly report post to these URLs (Microsoft Teams Incoming Webhook or any generic endpoint)."
      />

      {isLoading && (
        <div className="space-y-2 mb-3">
          {[1, 2].map((n) => (
            <div key={n} className="flex items-center justify-between border border-line rounded-md px-3 py-2">
              <Skeleton className="h-3 w-64" />
              <Skeleton className="h-4 w-4 rounded" />
            </div>
          ))}
        </div>
      )}

      {isError && <PageError message="Could not load webhook settings." onRetry={refetch} />}

      {!isLoading && !isError && (
        <>
          <div className="space-y-2 mb-3">
            {urls.map((u, i) => (
              <div
                key={i}
                className="flex items-center justify-between border border-line rounded-md px-3 py-2 text-sm bg-paper/40"
              >
                <span className="truncate font-mono text-xs text-ink/60 flex-1 mr-2">{u}</span>
                <button
                  onClick={() => save.mutate(urls.filter((_, j) => j !== i))}
                  disabled={save.isPending}
                  aria-label={`Remove webhook ${u}`}
                  className="text-ink/25 hover:text-critical hover:bg-critical/10 rounded p-1 -mr-1 transition-colors duration-150 disabled:opacity-40 focus-visible:ring-2"
                >
                  {save.isPending ? (
                    <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                  ) : (
                    <Trash2 size={14} aria-hidden="true" />
                  )}
                </button>
              </div>
            ))}
            {!urls.length && (
              <div className="text-xs text-ink/40 py-2">No webhook URLs configured yet.</div>
            )}
          </div>

          <div className="flex gap-2">
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://outlook.office.com/webhook/…"
              aria-label="Webhook URL"
              className="flex-1 border border-line rounded-md px-3 py-2 text-sm outline-none bg-paper/40
                         focus:border-ledgerLight focus-visible:ring-2"
            />
            <button
              onClick={() => {
                if (!canAdd) return;
                save.mutate([...urls, url]);
                setUrl("");
              }}
              disabled={!canAdd}
              aria-label="Add webhook URL"
              className="px-3 py-2 rounded-md bg-ledger text-paper text-sm flex items-center gap-1.5
                         hover:bg-ledgerLight transition-colors duration-150
                         disabled:opacity-40 disabled:cursor-not-allowed
                         focus-visible:ring-2"
            >
              {save.isPending ? (
                <Loader2 size={14} className="animate-spin" aria-hidden="true" />
              ) : (
                <Plus size={14} aria-hidden="true" />
              )}
              Add
            </button>
          </div>
        </>
      )}
    </section>
  );
}

/* ── Triage rules section ────────────────────────────────────────────────── */
function TriageRulesSection() {
  const { workspaceId } = useAuth();
  const queryClient = useQueryClient();

  const { data: rules, isLoading, isError, refetch } = useQuery({
    queryKey: ["triage-rules"],
    queryFn: async () =>
      (await api.get("/workflow/triage-rules/", { params: { workspace: workspaceId } }))
        .data.results ?? [],
    enabled: !!workspaceId,
  });

  const [form, setForm] = useState({ name: "", max_amount: "", max_vendor_risk_score: "" });

  const create = useMutation({
    mutationFn: () =>
      api.post("/workflow/triage-rules/", {
        workspace: workspaceId,
        name: form.name,
        max_amount: form.max_amount || null,
        max_vendor_risk_score: form.max_vendor_risk_score || null,
        require_status: "matched",
        active: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["triage-rules"] });
      setForm({ name: "", max_amount: "", max_vendor_risk_score: "" });
      toast.success("Triage rule saved");
    },
    onError: () => toast.error("Could not save triage rule"),
  });

  const toggle = useMutation({
    mutationFn: ({ id, active }) => api.patch(`/workflow/triage-rules/${id}/`, { active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["triage-rules"] }),
    onError: () => toast.error("Could not update rule"),
  });

  const canCreate = form.name.trim().length > 0 && !create.isPending;

  return (
    <section className="border border-line rounded-lg bg-white p-5">
      <SectionHeader
        icon={Sliders}
        title="Triage rules"
        description="Auto-approve matched invoices under a threshold from low-risk vendors."
      />

      {isLoading && (
        <div className="space-y-2 mb-4">
          {[1, 2].map((n) => (
            <div key={n} className="flex items-center justify-between border border-line rounded-md px-3 py-2">
              <div className="space-y-1">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-3 w-48" />
              </div>
              <Skeleton className="h-4 w-4 rounded" />
            </div>
          ))}
        </div>
      )}

      {isError && <PageError message="Could not load triage rules." onRetry={refetch} />}

      {!isLoading && !isError && (
        <div className="space-y-2 mb-5">
          {(rules || []).map((r) => (
            <label
              key={r.id}
              className="flex items-center justify-between border border-line rounded-md px-3 py-2.5 text-sm cursor-pointer hover:bg-paper/60 hover:border-ink/20 transition-colors duration-150"
            >
              <div>
                <div className="font-medium text-ink">{r.name}</div>
                <div className="text-xs text-ink/40 mt-0.5">
                  {r.max_amount ? `Under $${r.max_amount}` : "Any amount"}
                  <span className="mx-1 text-ink/20">·</span>
                  risk ≤ {r.max_vendor_risk_score ?? "any"}
                </div>
              </div>
              <input
                type="checkbox"
                checked={r.active}
                onChange={(e) => toggle.mutate({ id: r.id, active: e.target.checked })}
                disabled={toggle.isPending}
                className="rounded border-line focus-visible:ring-2 accent-ledgerLight"
                aria-label={`Toggle rule ${r.name}`}
              />
            </label>
          ))}
          {!rules?.length && (
            <div className="text-xs text-ink/40 py-2">No triage rules yet.</div>
          )}
        </div>
      )}

      {/* Add rule form */}
      <div className="border border-line rounded-md p-4 bg-paper/40 space-y-3">
        <div className="text-xs text-ink/50 font-medium">New rule</div>
        <div className="grid grid-cols-3 gap-2">
          <input
            placeholder="Rule name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            aria-label="Rule name"
            className="border border-line rounded-md px-3 py-2 text-sm outline-none bg-white
                       focus:border-ledgerLight focus-visible:ring-2"
          />
          <input
            placeholder="Max amount ($)"
            value={form.max_amount}
            onChange={(e) => setForm({ ...form, max_amount: e.target.value })}
            type="number"
            min="0"
            aria-label="Max amount"
            className="border border-line rounded-md px-3 py-2 text-sm outline-none bg-white
                       focus:border-ledgerLight focus-visible:ring-2"
          />
          <input
            placeholder="Max vendor risk"
            value={form.max_vendor_risk_score}
            onChange={(e) => setForm({ ...form, max_vendor_risk_score: e.target.value })}
            type="number"
            min="0"
            max="100"
            aria-label="Max vendor risk score"
            className="border border-line rounded-md px-3 py-2 text-sm outline-none bg-white
                       focus:border-ledgerLight focus-visible:ring-2"
          />
        </div>
        <button
          onClick={() => canCreate && create.mutate()}
          disabled={!canCreate}
          aria-label="Add triage rule"
          className="px-3 py-2 rounded-md bg-ledger text-paper text-sm flex items-center gap-1.5
                     hover:bg-ledgerLight transition-colors duration-150
                     disabled:opacity-40 disabled:cursor-not-allowed
                     focus-visible:ring-2"
        >
          {create.isPending ? (
            <Loader2 size={14} className="animate-spin" aria-hidden="true" />
          ) : (
            <Plus size={14} aria-hidden="true" />
          )}
          Add rule
        </button>
      </div>
    </section>
  );
}
