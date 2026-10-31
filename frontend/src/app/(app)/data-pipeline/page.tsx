"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Database, Play, RefreshCw, Server, Workflow, X } from "lucide-react";
import { useState } from "react";
import { Badge, Card, CardHeader, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { cn, compact, fmtDay } from "@/lib/utils";
import type { PipelineStatus, RunSummary } from "@/types/api";

const STATUS_TONE = { success: "up", partial: "warn", failed: "down", running: "accent" } as const;

function StatusDot({ ok }: { ok: boolean }) {
  return <span className={cn("inline-block h-2 w-2 rounded-full", ok ? "bg-up" : "bg-down")} aria-hidden />;
}

function HealthCards({ s }: { s: PipelineStatus }) {
  const items = [
    { icon: Server, label: "API", value: s.api === "ok" ? "Healthy" : "Down", ok: s.api === "ok" },
    { icon: Database, label: "Database", value: `${s.database.kind} · ${s.database.ok ? "connected" : "unreachable"}`, ok: s.database.ok },
    { icon: Activity, label: "Provider", value: `${s.provider.name} · ${s.provider.data_class}`, ok: s.provider.ok },
    { icon: Workflow, label: "Worker", value: s.worker.busy ? `Running job #${s.worker.current_run_id}` : "Idle", ok: true },
  ];
  return (
    <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
      {items.map((i) => (
        <Card key={i.label} className="p-4">
          <div className="flex items-center justify-between text-muted"><i.icon className="h-4 w-4" aria-hidden /><StatusDot ok={i.ok} /></div>
          <div className="mt-3 text-xs text-muted">{i.label}</div>
          <div className="mt-0.5 text-sm font-semibold">{i.value}</div>
        </Card>
      ))}
    </div>
  );
}

function Totals({ s }: { s: PipelineStatus }) {
  const t = s.totals;
  const cells: [string, string][] = [
    ["Success rate", t.success_rate === null ? "—" : `${Math.round(t.success_rate * 100)}%`],
    ["Runs", String(t.runs)],
    ["Rows inserted", compact(t.inserted)],
    ["Rows corrected", compact(t.updated)],
    ["Duplicate attempts", compact(t.unchanged_duplicates)],
    ["Rejected records", String(t.rejected)],
    ["API retries", String(t.retries)],
    ["Avg run time", t.avg_duration_ms === null ? "—" : `${Math.round(t.avg_duration_ms)} ms`],
  ];
  return (
    <Card>
      <CardHeader title="Ingestion totals" subtitle="Across the most recent 100 runs" />
      <dl className="grid grid-cols-2 gap-px bg-border/50 p-px sm:grid-cols-4">
        {cells.map(([k, v]) => (
          <div key={k} className="bg-surface p-4">
            <dt className="text-[11px] text-muted">{k}</dt>
            <dd className="num mt-1 text-xl font-semibold">{v}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}

function LatencyChart({ series }: { series: PipelineStatus["latency_series"] }) {
  const pts = series.filter((p) => p.duration_ms !== null);
  const max = Math.max(...pts.map((p) => p.duration_ms ?? 0), 1);
  return (
    <Card>
      <CardHeader title="Run latency" subtitle="Duration of the last finished runs (ms)" />
      <div className="px-4 pb-4">
        {pts.length === 0 ? (
          <EmptyState title="No finished runs yet" />
        ) : (
          <div className="flex h-32 items-end gap-1.5" role="img" aria-label={`Bar chart of ${pts.length} run durations, max ${Math.round(max)} milliseconds`}>
            {pts.map((p) => (
              <div key={p.run_id} className="group relative flex-1" title={`Run #${p.run_id}: ${Math.round(p.duration_ms ?? 0)} ms (${p.status})`}>
                <div className={cn("w-full rounded-t", p.status === "success" ? "bg-accent/70" : p.status === "partial" ? "bg-warn/70" : "bg-down/70")} style={{ height: `${Math.max(4, ((p.duration_ms ?? 0) / max) * 100)}%` }} />
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}

function Freshness({ rows, reference }: { rows: PipelineStatus["freshness"]; reference: string }) {
  return (
    <Card>
      <CardHeader title="Data freshness & checkpoints" subtitle={`Measured against ${fmtDay(reference)} · stale = more than 3 sessions behind`} />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="border-y border-border text-[11px] uppercase tracking-wider text-muted">
            <tr>
              <th className="px-4 py-2 text-left font-medium">Symbol</th>
              <th className="px-3 py-2 text-right font-medium">Bars</th>
              <th className="px-3 py-2 text-right font-medium">Latest bar</th>
              <th className="px-3 py-2 text-right font-medium">Checkpoint</th>
              <th className="px-3 py-2 text-right font-medium">Lag</th>
              <th className="px-4 py-2 text-right font-medium">State</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((r) => (
              <tr key={r.symbol} className="hover:bg-elevated/60">
                <td className="px-4 py-2 font-semibold">{r.symbol}</td>
                <td className="num px-3 py-2 text-right text-muted">{r.bars.toLocaleString()}</td>
                <td className="num px-3 py-2 text-right">{r.latest_day ? fmtDay(r.latest_day, { month: "short", day: "numeric" }) : "—"}</td>
                <td className="num px-3 py-2 text-right text-muted">{r.checkpoint ? fmtDay(r.checkpoint, { month: "short", day: "numeric" }) : "—"}</td>
                <td className="num px-3 py-2 text-right text-muted">{r.lag_sessions === null ? "—" : `${r.lag_sessions}d`}</td>
                <td className="px-4 py-2 text-right"><Badge tone={r.stale ? "warn" : "up"}>{r.stale ? "Stale" : "Fresh"}</Badge></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function RunDrawer({ id, onClose }: { id: number; onClose: () => void }) {
  const q = useQuery({ queryKey: ["run", id], queryFn: () => api.pipelineRun(id) });
  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label={`Run ${id} details`}>
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <aside className="relative h-full w-full max-w-lg animate-pop overflow-y-auto border-l border-border bg-surface p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Run #{id}</h2>
          <button onClick={onClose} aria-label="Close" className="rounded-md p-1.5 text-muted hover:bg-elevated"><X className="h-4 w-4" /></button>
        </div>
        {q.isLoading ? <Skeleton className="h-40" /> : q.isError ? <ErrorState message={(q.error as Error).message} /> : q.data && (
          <div className="space-y-5 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={STATUS_TONE[q.data.status]}>{q.data.status}</Badge>
              <Badge>{q.data.mode}</Badge><Badge>{q.data.trigger}</Badge>
              <span className="num text-xs text-muted">{q.data.duration_ms ? `${Math.round(q.data.duration_ms)} ms` : ""}</span>
            </div>
            {q.data.error && <p className="rounded-lg border border-down/30 bg-down/5 p-3 text-xs">{q.data.error}</p>}
            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Event log</h3>
              <ul className="space-y-1.5 font-mono text-[11.5px]">
                {q.data.events.map((e, i) => (
                  <li key={i} className={cn("rounded px-2 py-1", e.level === "error" ? "bg-down/10 text-down" : e.level === "warn" ? "bg-warn/10 text-warn" : "bg-elevated text-muted")}>
                    {e.symbol && <b className="mr-1.5 text-fg">{e.symbol}</b>}{e.msg}
                  </li>
                ))}
              </ul>
            </section>
            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Rejected / flagged records ({q.data.rejections.length})</h3>
              {q.data.rejections.length === 0 ? <p className="text-xs text-muted">None. Every fetched record passed validation.</p> : (
                <ul className="space-y-1.5 text-xs">
                  {q.data.rejections.map((r, i) => (
                    <li key={i} className="rounded-lg border border-border p-2">
                      <span className="font-semibold">{r.symbol}</span> {r.day} · <Badge tone={r.severity === "error" ? "down" : "warn"}>{r.code}</Badge>
                      <div className="mt-1 text-muted">{r.detail}</div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        )}
      </aside>
    </div>
  );
}

function History({ onOpen }: { onOpen: (id: number) => void }) {
  const [filter, setFilter] = useState<string>("");
  const q = useQuery({ queryKey: ["runs", filter], queryFn: () => api.pipelineRuns(filter || undefined), refetchInterval: 5000 });
  const when = (iso: string) => new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  return (
    <Card>
      <CardHeader
        title="Ingestion history"
        subtitle={q.data ? `${q.data.total} runs` : undefined}
        action={
          <select aria-label="Filter by status" value={filter} onChange={(e) => setFilter(e.target.value)} className="rounded-lg border border-border bg-bg/60 px-2 py-1 text-xs outline-none focus:border-accent">
            <option value="">All statuses</option>
            {["running", "success", "partial", "failed"].map((s) => <option key={s}>{s}</option>)}
          </select>
        }
      />
      {q.isError ? <div className="p-4"><ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /></div> : !q.data ? <Skeleton className="m-4 h-32" /> : q.data.items.length === 0 ? (
        <EmptyState title="No runs match" hint="Trigger an ingestion above." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="border-y border-border text-[11px] uppercase tracking-wider text-muted">
              <tr><th className="px-4 py-2 text-left font-medium">Run</th><th className="px-3 py-2 text-left font-medium">Mode</th><th className="px-3 py-2 text-left font-medium">Started</th><th className="px-3 py-2 text-right font-medium">+ / ~ / =</th><th className="px-3 py-2 text-right font-medium">Rejected</th><th className="px-4 py-2 text-right font-medium">Status</th></tr>
            </thead>
            <tbody className="divide-y divide-border">
              {q.data.items.map((r: RunSummary) => (
                <tr key={r.id} onClick={() => onOpen(r.id)} className="cursor-pointer hover:bg-elevated/60">
                  <td className="px-4 py-2"><button className="font-semibold text-accent" onClick={(e) => { e.stopPropagation(); onOpen(r.id); }}>#{r.id}</button></td>
                  <td className="px-3 py-2 text-muted">{r.mode} · {r.trigger}</td>
                  <td className="px-3 py-2 text-muted">{when(r.started_at)}</td>
                  <td className="num px-3 py-2 text-right text-muted">{String(r.stats.inserted ?? 0)} / {String(r.stats.updated ?? 0)} / {String(r.stats.unchanged ?? 0)}</td>
                  <td className="num px-3 py-2 text-right text-muted">{String(r.stats.rejected ?? 0)}</td>
                  <td className="px-4 py-2 text-right"><Badge tone={STATUS_TONE[r.status]}>{r.status}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function Controls({ symbols }: { symbols: string[] }) {
  const qc = useQueryClient();
  const [token, setToken] = useState("");
  const [sel, setSel] = useState("");
  const [start, setStart] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const done = (id: number) => {
    setMsg({ ok: true, text: `Started run #${id}.` });
    ["pipeline-status", "runs", "pipeline-quality", "stocks", "overview"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  };
  const fail = (e: Error) => setMsg({ ok: false, text: e.message });
  const ingest = useMutation({ mutationFn: (mode: "incremental" | "reindex") => api.triggerIngest({ mode, symbols: sel ? [sel] : undefined }, token || undefined), onSuccess: (r) => done(r.run_id), onError: fail });
  const backfill = useMutation({ mutationFn: () => api.triggerBackfill({ symbols: sel ? [sel] : symbols, start }, token || undefined), onSuccess: (r) => done(r.run_id), onError: fail });
  const field = "w-full rounded-lg border border-border bg-bg/60 px-2.5 py-1.5 text-sm outline-none focus:border-accent";
  const busy = ingest.isPending || backfill.isPending;
  return (
    <Card>
      <CardHeader title="Operations" subtitle="Guarded: one job at a time, symbols and dates validated server-side" />
      <div className="grid gap-3 px-4 pb-4 sm:grid-cols-3">
        <label className="text-xs text-muted">Symbol
          <select value={sel} onChange={(e) => setSel(e.target.value)} className={cn(field, "mt-1")}>
            <option value="">All symbols</option>{symbols.map((s) => <option key={s}>{s}</option>)}
          </select>
        </label>
        <label className="text-xs text-muted">Backfill start date
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className={cn(field, "mt-1")} />
        </label>
        <label className="text-xs text-muted">Admin token <span className="opacity-70">(only if MP_ADMIN_TOKEN is set)</span>
          <input type="password" value={token} onChange={(e) => setToken(e.target.value)} autoComplete="off" className={cn(field, "mt-1")} />
        </label>
      </div>
      <div className="flex flex-wrap items-center gap-2 border-t border-border px-4 py-3">
        <button disabled={busy} onClick={() => ingest.mutate("incremental")} className="inline-flex items-center gap-2 rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"><Play className="h-3.5 w-3.5" /> Run incremental</button>
        <button disabled={busy || !start} onClick={() => backfill.mutate()} className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium hover:border-accent/60 disabled:opacity-50">Backfill from date</button>
        <button disabled={busy} onClick={() => ingest.mutate("reindex")} className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-1.5 text-xs font-medium hover:border-accent/60 disabled:opacity-50"><RefreshCw className="h-3.5 w-3.5" /> Recompute indicators</button>
        {msg && <span role="status" className={cn("text-xs", msg.ok ? "text-up" : "text-down")}>{msg.text}</span>}
      </div>
    </Card>
  );
}

function Quality() {
  const q = useQuery({ queryKey: ["pipeline-quality"], queryFn: api.pipelineQuality, refetchInterval: 15000 });
  if (!q.data) return <Skeleton className="h-48" />;
  const r = q.data;
  const reasons = Object.entries(r.rejections_by_reason);
  return (
    <Card>
      <CardHeader title="Data quality report" subtitle={`Latest bar ${r.latest_timestamp ? fmtDay(r.latest_timestamp) : "n/a"}`} />
      <div className="space-y-3 px-4 pb-4 text-sm">
        <dl className="grid grid-cols-2 gap-3">
          {([["Stored bars", r.total_bars.toLocaleString()], ["Duplicate attempts", r.duplicate_attempts.toLocaleString()], ["Rejected", String(r.rejected_records)], ["Warnings", String(r.warnings)], ["Stale symbols", r.stale_symbols.length ? r.stale_symbols.join(", ") : "None"], ["Failed/partial runs", String(r.ingestion_failures)]] as const).map(([k, v]) => (
            <div key={k}><dt className="text-[11px] text-muted">{k}</dt><dd className="num font-medium">{v}</dd></div>
          ))}
        </dl>
        {reasons.length > 0 && <ul className="flex flex-wrap gap-1.5">{reasons.map(([k, v]) => <li key={k}><Badge tone={k.startsWith("error") ? "down" : "warn"}>{k.split(":")[1]} · {v}</Badge></li>)}</ul>}
        <p className="text-[11px] leading-relaxed text-muted">{r.missing_values}</p>
      </div>
    </Card>
  );
}

function Events({ events }: { events: PipelineStatus["recent_events"] }) {
  return (
    <Card>
      <CardHeader title="Recent events" subtitle="Structured pipeline log" />
      <ul className="max-h-72 space-y-1 overflow-y-auto px-4 pb-4 font-mono text-[11.5px]">
        {events.length === 0 && <li className="text-muted">No events yet.</li>}
        {[...events].reverse().map((e, i) => (
          <li key={i} className={cn("rounded px-2 py-1", e.level === "error" ? "bg-down/10 text-down" : e.level === "warn" ? "bg-warn/10 text-warn" : "text-muted")}>
            <span className="opacity-70">#{e.run_id}</span> {e.symbol && <b className="text-fg">{e.symbol} </b>}{e.msg}
          </li>
        ))}
      </ul>
    </Card>
  );
}

export default function DataPipelinePage() {
  const [openRun, setOpenRun] = useState<number | null>(null);
  const status = useQuery({ queryKey: ["pipeline-status"], queryFn: api.pipelineStatus, refetchInterval: 5000 });
  const s = status.data;
  return (
    <>
      <PageHeader title="Data pipeline" description="Operational control center: ingestion, checkpoints, data quality and freshness." actions={s?.worker.busy ? <Badge tone="accent">Job running</Badge> : undefined} />
      {status.isError ? (
        <ErrorState message={(status.error as Error).message} onRetry={() => status.refetch()} />
      ) : !s ? (
        <div className="space-y-4"><Skeleton className="h-24" /><Skeleton className="h-40" /><Skeleton className="h-64" /></div>
      ) : (
        <div className="space-y-5">
          <HealthCards s={s} />
          <Totals s={s} />
          <div className="grid gap-5 xl:grid-cols-3">
            <div className="space-y-5 xl:col-span-2">
              <Controls symbols={s.freshness.map((f) => f.symbol)} />
              <History onOpen={setOpenRun} />
              <Freshness rows={s.freshness} reference={s.reference_day} />
            </div>
            <div className="space-y-5">
              <LatencyChart series={s.latency_series} />
              <Quality />
              <Events events={s.recent_events} />
            </div>
          </div>
        </div>
      )}
      {openRun !== null && <RunDrawer id={openRun} onClose={() => setOpenRun(null)} />}
    </>
  );
}
