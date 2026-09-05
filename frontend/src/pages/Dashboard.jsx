import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AreaChart, Area, LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, ReferenceDot,
} from "recharts";
import { motion } from "framer-motion";
import {
  Radio, CheckCircle2, Loader2, Clock, Zap,
  TrendingDown, AlertTriangle, ClipboardCheck, ShieldAlert, BarChart2,
} from "lucide-react";

import { api } from "../lib/api.js";
import { useWebSocket } from "../hooks/useWebSocket.js";
import PageHeader from "../components/PageHeader.jsx";
import StatCard from "../components/StatCard.jsx";
import Skeleton, { SkeletonCard, PageError } from "../components/Skeleton.jsx";
import { useAuth } from "../context/AuthContext.jsx";

/* ── Pipeline stage metadata ─────────────────────────────────────────────── */
const STAGE_META = {
  ocr:        { icon: Loader2,      color: "text-signal",      label: "OCR"        },
  extraction: { icon: Loader2,      color: "text-minor",       label: "Extraction" },
  indexing:   { icon: Loader2,      color: "text-ledgerLight", label: "Indexing"   },
  matching:   { icon: Zap,          color: "text-major",       label: "Matching"   },
  done:       { icon: CheckCircle2, color: "text-matched",     label: "Done"       },
  failed:     { icon: AlertTriangle,color: "text-critical",    label: "Failed"     },
};

function stageIcon(event) {
  const stage = (event.stage || event.agent_step || "").toLowerCase();
  for (const key of Object.keys(STAGE_META)) {
    if (stage.includes(key)) return STAGE_META[key];
  }
  return STAGE_META.done;
}

/* ── Custom chart tooltip ────────────────────────────────────────────────── */
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-line rounded-md px-3 py-2 shadow-sm text-xs font-mono">
      <div className="text-ink/40 mb-0.5">{label}</div>
      <div className="text-signal font-medium">{payload[0].value} discrepancies</div>
    </div>
  );
}

/* ── Risk heat bar ───────────────────────────────────────────────────────── */
function RiskHeatRow({ vendor }) {
  const score = vendor.risk_score ?? 0;
  const barColor =
    score > 70 ? "bg-critical" : score > 40 ? "bg-major" : "bg-matched";
  const textColor =
    score > 70 ? "text-critical" : score > 40 ? "text-major" : "text-matched";

  return (
    <div className="flex items-center gap-3 py-1.5">
      <div className="flex-1 min-w-0">
        <div className="text-sm truncate leading-none mb-1">{vendor.name}</div>
        <div className="h-1.5 rounded-full bg-line overflow-hidden">
          <motion.div
            className={`h-full rounded-full ${barColor}`}
            initial={{ width: 0 }}
            animate={{ width: `${Math.min(score, 100)}%` }}
            transition={{ duration: 0.5, ease: "easeOut" }}
          />
        </div>
      </div>
      <div className={`font-mono text-xs font-medium shrink-0 w-7 text-right ${textColor}`}>
        {Math.round(score)}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { workspaceId } = useAuth();
  const [feed, setFeed] = useState([]);

  const { connected } = useWebSocket(
    workspaceId ? `/dashboard/${workspaceId}/` : null,
    (msg) => {
      if (msg.type === "pipeline_progress") {
        setFeed((prev) =>
          [{ id: crypto.randomUUID(), ...msg.payload, at: new Date() }, ...prev].slice(0, 30)
        );
      }
    }
  );

  /* ── Queries ─────────────────────────────────────────────────────────── */
  const {
    data: vendors,
    isLoading: vendorsLoading,
    isError: vendorsError,
    refetch: refetchVendors,
  } = useQuery({
    queryKey: ["vendors", "risk-heat", workspaceId],
    queryFn: async () =>
      (await api.get("/core/vendors/", { params: { workspace: workspaceId } })).data.results ?? [],
    enabled: !!workspaceId,
  });

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["dashboard-stats", workspaceId],
    queryFn: async () => {
      const [matchRes, approvalRes, discRes] = await Promise.all([
        api.get("/matching/results/",   { params: { workspace: workspaceId, page_size: 1 } }),
        api.get("/workflow/approvals/", { params: { workspace: workspaceId, state: "pending_review", page_size: 1 } }),
        api.get("/matching/results/",   { params: { workspace: workspaceId, status: "discrepant", page_size: 1 } }),
      ]);
      const totalMatches      = matchRes.data.count ?? 0;
      const matchedCount      = matchRes.data.results?.filter((r) => r.status === "matched").length ?? 0;
      const pendingApprovals  = approvalRes.data.count ?? 0;
      const openDiscrepancies = discRes.data.count ?? 0;
      return { totalMatches, matchedCount, pendingApprovals, openDiscrepancies };
    },
    enabled: !!workspaceId,
  });

  const { data: trendData, isLoading: trendLoading } = useQuery({
    queryKey: ["discrepancy-trend", workspaceId],
    queryFn: async () => {
      const res = await api.get("/matching/results/", {
        params: { workspace: workspaceId, status: "discrepant", page_size: 200 },
      });
      const results = res.data.results ?? [];
      const weeks = {};
      results.forEach((r) => {
        const d = new Date(r.created_at || r.matched_at || Date.now());
        const week = `W${getWeekNumber(d)}`;
        weeks[week] = (weeks[week] || 0) + 1;
      });
      const entries = Object.entries(weeks).slice(-8);
      // Return real data only — empty array when there is no history yet.
      // Never substitute synthetic placeholder points.
      return entries.map(([week, discrepancies]) => ({ week, discrepancies }));
    },
    enabled: !!workspaceId,
  });

  const vendorsAtRisk = vendors?.filter((v) => v.risk_score > 60).length ?? 0;
  const matchRate = stats?.totalMatches
    ? Math.round((stats.matchedCount / stats.totalMatches) * 100)
    : null;

  /* ── Latest trend point for reference dot ───────────────────────────── */
  const latestTrend = trendData?.[trendData.length - 1];

  return (
    <div className="flex flex-col min-h-full">
      <PageHeader
        eyebrow="Live"
        title="Dashboard"
        action={
          <div className="flex items-center gap-2 text-xs text-ink/60">
            <Radio
              size={14}
              className={connected ? "text-matched" : "text-critical"}
              aria-hidden="true"
            />
            <span>{connected ? "Streaming" : "Reconnecting…"}</span>
          </div>
        }
      />

      <div className="flex-1 p-8 grid grid-cols-12 gap-5 auto-rows-min">

        {/* ── KPI stat cards ──────────────────────────────────────────────── */}
        {statsLoading ? (
          [1, 2, 3, 4].map((n) => (
            <div key={n} className="col-span-3"><SkeletonCard /></div>
          ))
        ) : (
          <>
            <div className="col-span-3">
              <StatCard
                label="Match rate (30d)"
                icon={BarChart2}
                accent={matchRate == null ? "neutral" : matchRate >= 90 ? "positive" : matchRate >= 70 ? "warning" : "critical"}
                value={matchRate != null ? `${matchRate}%` : "—"}
                sub="of invoices auto-matched clean"
              />
            </div>
            <div className="col-span-3">
              <StatCard
                label="Open discrepancies"
                icon={TrendingDown}
                accent={stats?.openDiscrepancies > 0 ? "warning" : "positive"}
                value={stats?.openDiscrepancies ?? "—"}
                sub={stats?.openDiscrepancies > 0 ? "Review required" : "None outstanding"}
              />
            </div>
            <div className="col-span-3">
              <StatCard
                label="Pending approvals"
                icon={ClipboardCheck}
                accent={stats?.pendingApprovals > 0 ? "warning" : "positive"}
                value={stats?.pendingApprovals ?? "—"}
                sub={stats?.pendingApprovals > 0 ? "Awaiting decision" : "Queue clear"}
              />
            </div>
            <div className="col-span-3">
              {vendorsLoading ? (
                <SkeletonCard />
              ) : (
                <StatCard
                  label="Vendors at risk"
                  icon={ShieldAlert}
                  accent={vendorsAtRisk > 0 ? "critical" : "positive"}
                  value={vendorsAtRisk}
                  sub="risk score above 60"
                />
              )}
            </div>
          </>
        )}

        {/* ── Discrepancy trend chart ─────────────────────────────────────── */}
        <div className="col-span-8 border border-line rounded-lg bg-white p-5">
          <div className="flex items-baseline justify-between mb-5">
            <div>
              <div className="text-[11px] font-mono uppercase tracking-wider text-ink/40 mb-0.5">
                Trend
              </div>
              <div className="text-sm font-medium text-ink">Discrepancies by week</div>
            </div>
            {latestTrend && (
              <div className="text-right">
                <div className="font-display text-2xl text-signal leading-none">
                  {latestTrend.discrepancies}
                </div>
                <div className="text-[11px] text-ink/40">this week</div>
              </div>
            )}
          </div>

          {trendLoading ? (
            <Skeleton className="h-[200px] w-full" />
          ) : !trendData?.length ? (
            <div className="h-[200px] flex flex-col items-center justify-center gap-2 text-center rounded-md border border-dashed border-line">
              <BarChart2 size={22} className="text-ink/20" strokeWidth={1.5} aria-hidden="true" />
              <div className="text-sm text-ink/40 font-medium">No discrepancy history yet</div>
              <div className="text-xs text-ink/30 max-w-[220px] leading-relaxed">
                This chart will populate as invoices are matched and discrepancies are detected.
              </div>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart
                data={trendData}
                margin={{ top: 4, right: 4, left: -20, bottom: 0 }}
              >
                <defs>
                  <linearGradient id="discrepancyGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%"   stopColor="#C7622B" stopOpacity={0.18} />
                    <stop offset="100%" stopColor="#C7622B" stopOpacity={0}    />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  stroke="#DDE3D6"
                  strokeDasharray="3 3"
                  vertical={false}
                />
                <XAxis
                  dataKey="week"
                  tick={{ fontSize: 11, fill: "#12211E80" }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: "#12211E80" }}
                  axisLine={false}
                  tickLine={false}
                  allowDecimals={false}
                />
                <Tooltip content={<ChartTooltip />} cursor={{ stroke: "#DDE3D6", strokeWidth: 1 }} />
                <Area
                  type="monotone"
                  dataKey="discrepancies"
                  stroke="#C7622B"
                  strokeWidth={2}
                  fill="url(#discrepancyGradient)"
                  dot={false}
                  activeDot={{ r: 4, fill: "#C7622B", strokeWidth: 0 }}
                  isAnimationActive={true}
                  animationDuration={700}
                  animationEasing="ease-out"
                />
                {latestTrend && (
                  <ReferenceDot
                    x={latestTrend.week}
                    y={latestTrend.discrepancies}
                    r={4}
                    fill="#C7622B"
                    stroke="#fff"
                    strokeWidth={2}
                  />
                )}
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>


        {/* ── Vendor risk heat list ───────────────────────────────────────── */}
        <div className="col-span-4 border border-line rounded-lg bg-white p-5">
          <div className="text-[11px] font-mono uppercase tracking-wider text-ink/40 mb-0.5">
            Risk
          </div>
          <div className="text-sm font-medium text-ink mb-4">Vendor heat list</div>

          {vendorsError ? (
            <PageError message="Could not load vendors" onRetry={refetchVendors} />
          ) : vendorsLoading ? (
            <div className="space-y-3">
              {[1, 2, 3, 4].map((n) => (
                <div key={n}>
                  <Skeleton className="h-3 w-28 mb-1.5" />
                  <Skeleton className="h-1.5 w-full" />
                </div>
              ))}
            </div>
          ) : (vendors || []).length === 0 ? (
            <div className="text-xs text-ink/40 py-2">No vendors yet.</div>
          ) : (
            <div className="divide-y divide-line/60">
              {(vendors || [])
                .slice()
                .sort((a, b) => b.risk_score - a.risk_score)
                .slice(0, 8)
                .map((v) => (
                  <RiskHeatRow key={v.id} vendor={v} />
                ))}
            </div>
          )}

          {/* Risk scale legend */}
          {!vendorsLoading && !vendorsError && (vendors?.length ?? 0) > 0 && (
            <div className="mt-4 pt-3 border-t border-line flex items-center justify-between text-[10px] text-ink/30 font-mono">
              <span className="text-matched">● Low</span>
              <span className="text-major">● Medium</span>
              <span className="text-critical">● High</span>
            </div>
          )}
        </div>

        {/* ── Live pipeline feed ──────────────────────────────────────────── */}
        <div className="col-span-12 border border-line rounded-lg bg-white">
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-line">
            <div className="flex items-center gap-2">
              <div className="text-sm font-medium text-ink">Live pipeline feed</div>
              {connected && (
                <span
                  className="inline-flex h-2 w-2 rounded-full bg-matched animate-pulse"
                  aria-hidden="true"
                />
              )}
            </div>
            <div className="text-[11px] font-mono text-ink/30">
              {feed.length > 0 ? `${feed.length} events` : "idle"}
            </div>
          </div>

          {/* Body */}
          <div
            className="font-mono text-xs max-h-56 overflow-y-auto"
            aria-live="polite"
            aria-label="Pipeline events"
          >
            {/* Empty state */}
            {!feed.length && (
              <div className="flex flex-col items-center justify-center gap-2 py-8 text-ink/30">
                <Clock size={20} strokeWidth={1.5} aria-hidden="true" />
                <div className="text-center">
                  <div className="text-xs font-medium text-ink/40">No pipeline activity yet</div>
                  <div className="text-[11px] mt-0.5">
                    Events appear here as documents are uploaded and processed
                  </div>
                </div>
              </div>
            )}

            {/* Events */}
            {feed.map((event) => {
              const meta = stageIcon(event);
              const Icon = meta.icon;
              return (
                <motion.div
                  key={event.id}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.12 }}
                  className="flex gap-3 items-center px-5 py-1.5 border-b border-line/40 last:border-0"
                >
                  <span className="text-ink/25 shrink-0 w-16 tabular-nums">
                    {event.at.toLocaleTimeString()}
                  </span>
                  <span
                    className={`inline-flex items-center gap-1 shrink-0 w-24 font-medium ${meta.color}`}
                  >
                    <Icon
                      size={11}
                      className={meta.icon === Loader2 ? "animate-spin" : ""}
                      aria-hidden="true"
                    />
                    {meta.label}
                  </span>
                  <span className="text-ink/60 truncate">
                    {event.agent_step || event.stage || event.document_id || JSON.stringify(event)}
                  </span>
                </motion.div>
              );
            })}
          </div>
        </div>

      </div>
    </div>
  );
}

/* ── Helpers ─────────────────────────────────────────────────────────────── */
function getWeekNumber(d) {
  const oneJan = new Date(d.getFullYear(), 0, 1);
  return Math.ceil(((d - oneJan) / 86400000 + oneJan.getDay() + 1) / 7);
}
