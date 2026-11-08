"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, BellOff, Pause, Pencil, Play, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Badge, Card, CardHeader, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui/primitives";
import { NOTIFICATIONS_KEY } from "@/hooks/useNotifications";
import { api } from "@/lib/api";
import { cn, fmtDay } from "@/lib/utils";
import type { AlertItem } from "@/types/api";

const input = "h-9 rounded-lg border border-border bg-bg/60 px-2.5 text-sm outline-none focus:border-accent";

function describe(a: AlertItem, label: string): string {
  if (a.kind.startsWith("cross")) return `${label} (${a.window})`;
  const unit = a.kind.startsWith("change") ? "%" : a.kind === "rel_volume_above" ? "×" : "";
  return `${label} ${a.threshold}${unit}`;
}

function StatusBadge({ a }: { a: AlertItem }) {
  if (a.status === "paused") return <Badge tone="neutral"><Pause className="h-3 w-3" aria-hidden />Paused</Badge>;
  if (a.status === "triggered") return <Badge tone="warn"><Bell className="h-3 w-3" aria-hidden />Triggered</Badge>;
  return <Badge tone="up">Active</Badge>;
}

function AlertsInner() {
  const qc = useQueryClient();
  const params = useSearchParams();
  const kinds = useQuery({ queryKey: ["alert-kinds"], queryFn: api.alertKinds, staleTime: Infinity });
  const stocks = useQuery({ queryKey: ["stocks"], queryFn: api.stocks });
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: api.alerts });
  const events = useQuery({ queryKey: ["alert-events"], queryFn: () => api.alertEvents(50), refetchInterval: 60_000 });

  const [symbol, setSymbol] = useState((params.get("symbol") ?? "").toUpperCase());
  const [kind, setKind] = useState("price_above");
  const [threshold, setThreshold] = useState("");
  const [win, setWin] = useState("50");
  const [cooldown, setCooldown] = useState("1");
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ id: number; threshold: string; window: string; cooldown: string } | null>(null);

  const labels = Object.fromEntries((kinds.data?.items ?? []).map((k) => [k.kind, k.label]));
  const crossing = kinds.data?.items.find((k) => k.kind === kind)?.crossing ?? false;
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["alerts"] });
    qc.invalidateQueries({ queryKey: ["alert-events"] });
    qc.invalidateQueries({ queryKey: NOTIFICATIONS_KEY });
  };

  const create = useMutation({
    mutationFn: () => {
      const cd = Number(cooldown);
      if (!symbol) throw new Error("Choose a symbol");
      if (!crossing && (threshold.trim() === "" || !Number.isFinite(Number(threshold)))) throw new Error("Enter a numeric threshold");
      return api.createAlert({ symbol, kind, threshold: crossing ? 0 : Number(threshold), window: crossing ? Number(win) : null, cooldown_days: Number.isInteger(cd) ? cd : 1, note });
    },
    onSuccess: () => { setErr(null); setThreshold(""); setNote(""); refresh(); },
    onError: (e) => setErr((e as Error).message),
  });
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Parameters<typeof api.updateAlert>[1] }) => api.updateAlert(id, body),
    onSuccess: () => { setErr(null); setEditing(null); refresh(); },
    onError: (e) => setErr((e as Error).message),
  });
  const del = useMutation({ mutationFn: (id: number) => api.deleteAlert(id), onSuccess: refresh });

  return (
    <>
      <PageHeader title="Alerts" description="Evaluated server-side against stored daily data. Edge-triggered: an alert fires when its condition turns true, not on every refresh." />
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="space-y-5 xl:col-span-2">
          <Card className="p-4">
            <CardHeader title="New alert" subtitle="Conditions use daily closes, not intraday prices." />
            <form onSubmit={(e) => { e.preventDefault(); create.mutate(); }} className="flex flex-wrap items-end gap-2">
              <label className="text-[11px] text-muted">Symbol
                <select value={symbol} onChange={(e) => setSymbol(e.target.value)} className={cn(input, "mt-1 block w-28")}>
                  <option value="">Choose…</option>
                  {(stocks.data?.items ?? []).map((s) => <option key={s.symbol} value={s.symbol}>{s.symbol}</option>)}
                </select>
              </label>
              <label className="text-[11px] text-muted">Condition
                <select value={kind} onChange={(e) => setKind(e.target.value)} className={cn(input, "mt-1 block min-w-[240px]")}>
                  {(kinds.data?.items ?? []).map((k) => <option key={k.kind} value={k.kind}>{k.label}</option>)}
                </select>
              </label>
              {crossing ? (
                <label className="text-[11px] text-muted">SMA window
                  <input value={win} onChange={(e) => setWin(e.target.value)} inputMode="numeric" className={cn(input, "mt-1 block w-24")} />
                </label>
              ) : (
                <label className="text-[11px] text-muted">Threshold
                  <input value={threshold} onChange={(e) => setThreshold(e.target.value)} inputMode="decimal" className={cn(input, "mt-1 block w-28")} />
                </label>
              )}
              <label className="text-[11px] text-muted">Cooldown (days)
                <input value={cooldown} onChange={(e) => setCooldown(e.target.value)} inputMode="numeric" className={cn(input, "mt-1 block w-24")} />
              </label>
              <label className="min-w-[160px] flex-1 text-[11px] text-muted">Note (optional)
                <input value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} className={cn(input, "mt-1 block w-full")} />
              </label>
              <button type="submit" disabled={create.isPending} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-accent px-3 text-sm font-medium text-white disabled:opacity-50"><Plus className="h-4 w-4" />Create</button>
            </form>
            <p className="mt-2 text-[11px] text-muted">
              {crossing ? "Fires on the session where the close moves across the moving average." : "If the condition is already true now, the alert waits for it to clear and happen again before firing."}
            </p>
            {err && <p role="alert" className="mt-2 text-xs text-down">{err}</p>}
          </Card>

          <Card>
            <div className="border-b border-border p-4"><CardHeader title="Your alerts" subtitle={`${alerts.data?.items.length ?? 0} of ${kinds.data?.max_alerts ?? 50}`} /></div>
            {alerts.isError ? <div className="p-4"><ErrorState message={(alerts.error as Error).message} onRetry={() => alerts.refetch()} /></div>
              : !alerts.data ? <Skeleton className="m-4 h-32" />
              : alerts.data.items.length === 0 ? <div className="p-6"><EmptyState title="No alerts yet" hint="Create one above, or use the Alert button on a stock page." icon={<BellOff className="h-5 w-5" />} /></div>
              : (
                <ul className="divide-y divide-border/60">
                  {alerts.data.items.map((a) => (
                    <li key={a.id} className="p-4">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <Link href={`/markets/${a.symbol}`} className="font-semibold hover:text-accent">{a.symbol}</Link>
                            <span className="text-sm">{describe(a, labels[a.kind] ?? a.kind)}</span>
                            <StatusBadge a={a} />
                          </div>
                          <p className="mt-1 text-[11px] text-muted">
                            Last evaluated session: {a.last_observed_day ? fmtDay(a.last_observed_day) : "Not yet"} · Last fired: {a.last_fired_day ? fmtDay(a.last_fired_day) : "Never"} · Cooldown {a.cooldown_days}d
                            {a.waiting_for_reset && " · Condition already met when set; waiting for it to clear first"}
                          </p>
                          {a.note && <p className="mt-0.5 text-xs">{a.note}</p>}
                        </div>
                        <div className="flex items-center gap-1">
                          <button onClick={() => patch.mutate({ id: a.id, body: { enabled: !a.enabled } })} aria-label={a.enabled ? `Pause alert on ${a.symbol}` : `Resume alert on ${a.symbol}`} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-surface hover:text-fg">{a.enabled ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}</button>
                          <button onClick={() => setEditing({ id: a.id, threshold: String(a.threshold), window: String(a.window ?? 50), cooldown: String(a.cooldown_days) })} aria-label={`Edit alert on ${a.symbol}`} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-surface hover:text-fg"><Pencil className="h-4 w-4" /></button>
                          <button onClick={() => { if (window.confirm(`Delete the ${a.symbol} alert and its history?`)) del.mutate(a.id); }} aria-label={`Delete alert on ${a.symbol}`} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-down/10 hover:text-down"><Trash2 className="h-4 w-4" /></button>
                        </div>
                      </div>
                      {editing?.id === a.id && (
                        <form onSubmit={(e) => { e.preventDefault(); const cross = a.kind.startsWith("cross"); patch.mutate({ id: a.id, body: { ...(cross ? { window: Number(editing.window) } : { threshold: Number(editing.threshold) }), cooldown_days: Number(editing.cooldown) } }); }} className="mt-3 flex flex-wrap items-end gap-2 rounded-lg bg-surface p-3">
                          {a.kind.startsWith("cross")
                            ? <label className="text-[11px] text-muted">SMA window<input value={editing.window} onChange={(e) => setEditing({ ...editing, window: e.target.value })} className={cn(input, "mt-1 block w-24")} /></label>
                            : <label className="text-[11px] text-muted">Threshold<input value={editing.threshold} onChange={(e) => setEditing({ ...editing, threshold: e.target.value })} className={cn(input, "mt-1 block w-28")} /></label>}
                          <label className="text-[11px] text-muted">Cooldown (days)<input value={editing.cooldown} onChange={(e) => setEditing({ ...editing, cooldown: e.target.value })} className={cn(input, "mt-1 block w-24")} /></label>
                          <button type="submit" className="h-9 rounded-lg bg-accent px-3 text-sm font-medium text-white">Save</button>
                          <button type="button" onClick={() => setEditing(null)} className="h-9 rounded-lg border border-border px-3 text-sm">Cancel</button>
                          <p className="basis-full text-[11px] text-muted">Changing the condition re-baselines the alert: it will not fire for state that already exists.</p>
                        </form>
                      )}
                    </li>
                  ))}
                </ul>
              )}
          </Card>
        </div>

        <Card className="h-fit p-4">
          <CardHeader title="History" subtitle="What each stored session showed when an alert fired." />
          {events.isError ? <ErrorState message={(events.error as Error).message} onRetry={() => events.refetch()} />
            : !events.data ? <Skeleton className="h-40" />
            : events.data.items.length === 0 ? <EmptyState title="Nothing has fired yet" hint="Alerts are checked after every data ingestion." />
            : (
              <ul className="space-y-3">
                {events.data.items.map((e) => (
                  <li key={e.id} className="border-b border-border/60 pb-3 text-xs last:border-0">
                    <div className="flex items-center justify-between">
                      <Link href={`/markets/${e.symbol}`} className="font-semibold hover:text-accent">{e.symbol}</Link>
                      <span className="text-[10.5px] text-muted">session {fmtDay(e.observed_day)}</span>
                    </div>
                    <p className="mt-1">{e.message}</p>
                    <p className="num mt-1 text-[10.5px] text-muted">Observed {e.observed_value} · evaluated {new Date(e.evaluated_at).toLocaleString()}</p>
                  </li>
                ))}
              </ul>
            )}
          <p className="mt-3 text-[11px] text-muted">Based on stored daily data. Email delivery is not implemented; notifications are in-app only.</p>
        </Card>
      </div>
    </>
  );
}

export default function AlertsPage() {
  return <Suspense fallback={<Skeleton className="h-96" />}><AlertsInner /></Suspense>;
}
