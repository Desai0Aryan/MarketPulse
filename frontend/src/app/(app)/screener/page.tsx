"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Bookmark, Download, GitCompare, Plus, Star, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Change } from "@/components/shared/Change";
import { DataBadge } from "@/components/shared/DataBadge";
import { Badge, Card, CardHeader, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui/primitives";
import { useDefaultWatchlist } from "@/hooks/useWatchlists";
import { api, downloadCsv } from "@/lib/api";
import { cn, compact, num, pct, usd } from "@/lib/utils";
import type { ScreenField, ScreenFilter, ScreenOp, ScreenQuery, ScreenRow } from "@/types/api";

const OP_LABEL: Record<string, string> = { gt: ">", gte: "≥", lt: "<", lte: "≤", between: "between", eq: "is" };
const DEFAULT_QUERY: ScreenQuery = { filters: [], kind: "equity", sort: "symbol", descending: false, page: 1, page_size: 25 };
const PRESETS: { name: string; hint: string; filters: ScreenFilter[] }[] = [
  { name: "Oversold (RSI < 30)", hint: "Momentum has faded; not a buy signal", filters: [{ field: "rsi14", op: "lt", value: 30 }] },
  { name: "Near 52-week high", hint: "Within 5% of the high", filters: [{ field: "dist_52w_high_pct", op: "gte", value: -5 }] },
  { name: "Unusual volume", hint: "Volume ≥ 1.5× its 30-day average", filters: [{ field: "rel_volume", op: "gte", value: 1.5 }] },
  { name: "Uptrend", hint: "SMA50 above SMA200 and price above SMA50", filters: [{ field: "sma50_above_sma200", op: "eq", value: true }, { field: "price_vs_sma50_pct", op: "gt", value: 0 }] },
];

function fmt(f: ScreenField | undefined, v: number | boolean | null | undefined): string {
  if (v === null || v === undefined) return "Unavailable";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  switch (f?.unit) {
    case "usd": return usd(v);
    case "pct": return pct(v);
    case "x": return `${num(v)}×`;
    case "count": return compact(v);
    default: return num(v);
  }
}

function FilterChip({ f, fields, onRemove }: { f: ScreenFilter; fields: Map<string, ScreenField>; onRemove: () => void }) {
  const fd = fields.get(f.field);
  const value = f.op === "between" ? `${f.value} – ${f.value2}` : typeof f.value === "boolean" ? (f.value ? "yes" : "no") : String(f.value);
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1 text-xs">
      <span className="text-muted">{fd?.label ?? f.field}</span>
      <span className="font-medium">{OP_LABEL[f.op]} {value}</span>
      <button onClick={onRemove} aria-label={`Remove filter ${fd?.label ?? f.field}`} className="rounded p-0.5 text-muted hover:text-fg"><X className="h-3 w-3" /></button>
    </span>
  );
}

function FilterBuilder({ numeric, boolean, onAdd, max, count }: { numeric: ScreenField[]; boolean: ScreenField[]; onAdd: (f: ScreenFilter) => void; max: number; count: number }) {
  const all = [...numeric, ...boolean];
  const [field, setField] = useState(all[0]?.key ?? "");
  const [op, setOp] = useState<ScreenOp>("gt");
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const isBool = boolean.some((f) => f.key === field);
  const desc = all.find((f) => f.key === field)?.description;

  const submit = () => {
    setErr(null);
    if (isBool) return onAdd({ field, op: "eq", value: a !== "false" });
    const lo = Number(a);
    if (a.trim() === "" || !Number.isFinite(lo)) return setErr("Enter a number");
    if (op === "between") {
      const hi = Number(b);
      if (b.trim() === "" || !Number.isFinite(hi)) return setErr("Enter an upper bound");
      if (lo > hi) return setErr("Lower bound must not exceed the upper bound");
      return onAdd({ field, op, value: lo, value2: hi });
    }
    onAdd({ field, op, value: lo });
    setA("");
  };
  const input = "h-9 rounded-lg border border-border bg-bg/60 px-2.5 text-sm outline-none focus:border-accent";

  return (
    <div>
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-[11px] text-muted">Metric
          <select value={field} onChange={(e) => { setField(e.target.value); setErr(null); }} className={cn(input, "mt-1 block min-w-[200px]")}>
            <optgroup label="Numeric">{numeric.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}</optgroup>
            <optgroup label="Trend">{boolean.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}</optgroup>
          </select>
        </label>
        {isBool ? (
          <label className="text-[11px] text-muted">Value
            <select value={a || "true"} onChange={(e) => setA(e.target.value)} className={cn(input, "mt-1 block")}><option value="true">Yes</option><option value="false">No</option></select>
          </label>
        ) : (
          <>
            <label className="text-[11px] text-muted">Condition
              <select value={op} onChange={(e) => setOp(e.target.value as ScreenOp)} className={cn(input, "mt-1 block")}>
                {["gt", "gte", "lt", "lte", "between"].map((o) => <option key={o} value={o}>{OP_LABEL[o]}</option>)}
              </select>
            </label>
            <label className="text-[11px] text-muted">{op === "between" ? "From" : "Value"}
              <input value={a} onChange={(e) => setA(e.target.value)} inputMode="decimal" onKeyDown={(e) => e.key === "Enter" && submit()} className={cn(input, "mt-1 block w-28")} />
            </label>
            {op === "between" && (
              <label className="text-[11px] text-muted">To
                <input value={b} onChange={(e) => setB(e.target.value)} inputMode="decimal" onKeyDown={(e) => e.key === "Enter" && submit()} className={cn(input, "mt-1 block w-28")} />
              </label>
            )}
          </>
        )}
        <button onClick={submit} disabled={count >= max} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-accent px-3 text-sm font-medium text-white disabled:opacity-50">
          <Plus className="h-4 w-4" /> Add filter
        </button>
      </div>
      {desc && <p className="mt-2 text-[11px] text-muted">{desc}. Instruments where this metric is unavailable are excluded.</p>}
      {err && <p role="alert" className="mt-1 text-xs text-down">{err}</p>}
    </div>
  );
}

const COLUMNS: { key: keyof ScreenRow; label: string; align?: "right" }[] = [
  { key: "price", label: "Price", align: "right" },
  { key: "change_pct", label: "1D", align: "right" },
  { key: "rel_volume", label: "Rel vol", align: "right" },
  { key: "rsi14", label: "RSI", align: "right" },
  { key: "volatility_20d", label: "Vol 20d", align: "right" },
  { key: "dist_52w_high_pct", label: "From 52W high", align: "right" },
  { key: "price_vs_sma50_pct", label: "vs SMA50", align: "right" },
  { key: "return_3m_pct", label: "3M", align: "right" },
];

export default function ScreenerPage() {
  const qc = useQueryClient();
  const [query, setQuery] = useState<ScreenQuery>(DEFAULT_QUERY);
  const [selected, setSelected] = useState<string[]>([]);
  const [saveName, setSaveName] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const catalog = useQuery({ queryKey: ["screener-fields"], queryFn: api.screenerFields, staleTime: Infinity });
  const result = useQuery({ queryKey: ["screen", query], queryFn: () => api.screenerQuery(query), placeholderData: (p) => p });
  const saved = useQuery({ queryKey: ["screens"], queryFn: api.savedScreens });
  const { watchlist, toggle } = useDefaultWatchlist();

  const fields = useMemo(() => new Map([...(catalog.data?.numeric ?? []), ...(catalog.data?.boolean ?? [])].map((f) => [f.key, f])), [catalog.data]);
  const patch = (p: Partial<ScreenQuery>) => setQuery((q) => ({ ...q, page: 1, ...p }));
  const r = result.data;

  const save = useMutation({
    mutationFn: () => api.saveScreen(saveName.trim(), query),
    onSuccess: () => { setSaveName(""); setNote("Screen saved."); qc.invalidateQueries({ queryKey: ["screens"] }); },
    onError: (e) => setNote((e as Error).message),
  });
  const del = useMutation({ mutationFn: (id: number) => api.deleteScreen(id), onSuccess: () => qc.invalidateQueries({ queryKey: ["screens"] }) });
  const exportCsv = useMutation({ mutationFn: () => downloadCsv("/screener/export.csv", query, "marketpulse_screener.csv"), onError: (e) => setNote((e as Error).message) });
  const addToWatchlist = useMutation({
    mutationFn: async () => {
      if (!watchlist) throw new Error("No watchlist available");
      let added = 0;
      for (const s of selected.filter((x) => !watchlist.symbols.includes(x))) {
        await toggle.mutateAsync({ symbol: s, remove: false });
        added += 1;
      }
      return added;
    },
    onSuccess: (n) => setNote(n ? `Added ${n} symbol${n === 1 ? "" : "s"} to “${watchlist?.name}”.` : "All selected symbols are already on the list."),
    onError: (e) => setNote((e as Error).message),
  });

  const sortBy = (key: string) => patch({ sort: key, descending: query.sort === key ? !query.descending : key !== "symbol" });
  const pages = r ? Math.max(1, Math.ceil(r.total / r.page_size)) : 1;
  const toggleSel = (s: string) => setSelected((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));

  return (
    <>
      <PageHeader title="Screener" description="Filter the tracked universe on server-computed metrics." actions={<DataBadge meta={r?.meta} />} />
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-4">
        <div className="space-y-5 xl:col-span-3">
          <Card className="p-4">
            <CardHeader title="Filters" subtitle="All conditions must match (AND)." action={
              <div className="flex rounded-lg border border-border bg-bg/60 p-0.5" role="group" aria-label="Universe">
                {([["equity", "Equities"], ["index_proxy", "Index proxies"], [null, "All"]] as const).map(([k, l]) => (
                  <button key={l} aria-pressed={query.kind === k} onClick={() => patch({ kind: k })} className={cn("rounded-md px-2.5 py-1 text-xs font-medium", query.kind === k ? "bg-accent text-white" : "text-muted hover:text-fg")}>{l}</button>
                ))}
              </div>
            } />
            {catalog.isError ? <ErrorState message={(catalog.error as Error).message} onRetry={() => catalog.refetch()} /> : !catalog.data ? <Skeleton className="h-20" /> : (
              <FilterBuilder numeric={catalog.data.numeric} boolean={catalog.data.boolean} max={catalog.data.limits.max_filters} count={query.filters.length} onAdd={(f) => patch({ filters: [...query.filters, f] })} />
            )}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {query.filters.map((f, i) => <FilterChip key={`${f.field}-${i}`} f={f} fields={fields} onRemove={() => patch({ filters: query.filters.filter((_, j) => j !== i) })} />)}
              {query.filters.length > 0 && <button onClick={() => patch({ filters: [] })} className="text-xs text-muted underline hover:text-fg">Clear all</button>}
              {query.filters.length === 0 && <span className="text-xs text-muted">No filters: showing the whole universe.</span>}
            </div>
            <div className="mt-3 flex flex-wrap gap-2 border-t border-border pt-3">
              <span className="self-center text-[11px] text-muted">Quick start</span>
              {PRESETS.map((p) => <button key={p.name} title={p.hint} onClick={() => patch({ filters: p.filters })} className="rounded-full border border-border px-2.5 py-1 text-xs text-muted hover:border-accent/50 hover:text-fg">{p.name}</button>)}
            </div>
          </Card>

          <Card>
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border p-4">
              <div className="text-sm"><span className="num font-semibold">{r?.total ?? "…"}</span> <span className="text-muted">of {r?.universe ?? "…"} instruments match</span></div>
              <div className="flex flex-wrap items-center gap-2">
                <button disabled={!selected.length || !watchlist} onClick={() => addToWatchlist.mutate()} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border px-2.5 text-xs font-medium hover:border-accent/50 disabled:opacity-40"><Star className="h-3.5 w-3.5" /> Add {selected.length || ""} to watchlist</button>
                {selected.length >= 2 && selected.length <= 10 ? (
                  <Link href={`/compare?symbols=${selected.join(",")}`} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border px-2.5 text-xs font-medium hover:border-accent/50"><GitCompare className="h-3.5 w-3.5" /> Compare {selected.length}</Link>
                ) : (
                  <span title="Select 2–10 rows to compare" className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border px-2.5 text-xs text-muted opacity-40"><GitCompare className="h-3.5 w-3.5" /> Compare</span>
                )}
                <button onClick={() => exportCsv.mutate()} disabled={!r || r.total === 0} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border px-2.5 text-xs font-medium hover:border-accent/50 disabled:opacity-40"><Download className="h-3.5 w-3.5" /> CSV</button>
              </div>
            </div>
            {note && <div role="status" className="border-b border-border bg-accent/10 px-4 py-2 text-xs">{note}</div>}
            {result.isError ? <div className="p-4"><ErrorState message={(result.error as Error).message} onRetry={() => result.refetch()} /></div>
              : !r ? <Skeleton className="m-4 h-64" />
              : r.items.length === 0 ? <div className="p-6"><EmptyState title="No instruments match these filters" hint="Loosen a condition or clear all filters." /></div>
              : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[860px] text-sm">
                    <thead>
                      <tr className="border-b border-border text-[11px] uppercase tracking-wide text-muted">
                        <th className="w-10 p-3"><span className="sr-only">Select</span></th>
                        {[{ key: "symbol", label: "Symbol" } as const, ...COLUMNS].map((c) => {
                          const align = "align" in c && c.align === "right";
                          return (
                            <th key={c.key} className={cn("p-3 font-medium", align ? "text-right" : "text-left")} aria-sort={query.sort === c.key ? (query.descending ? "descending" : "ascending") : "none"}>
                              <button onClick={() => sortBy(c.key)} className="inline-flex items-center gap-1 hover:text-fg">{c.label}{query.sort === c.key && (query.descending ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />)}</button>
                            </th>
                          );
                        })}
                      </tr>
                    </thead>
                    <tbody>
                      {r.items.map((row) => (
                        <tr key={row.symbol} className="border-b border-border/60 hover:bg-surface/60">
                          <td className="p-3"><input type="checkbox" checked={selected.includes(row.symbol)} onChange={() => toggleSel(row.symbol)} aria-label={`Select ${row.symbol}`} /></td>
                          <td className="p-3"><Link href={`/markets/${row.symbol}`} className="font-semibold hover:text-accent">{row.symbol}</Link><div className="max-w-[160px] truncate text-[11px] text-muted">{row.name}</div></td>
                          <td className="num p-3 text-right">{fmt(fields.get("price"), row.price)}</td>
                          <td className="p-3 text-right">{row.change_pct === null ? "Unavailable" : <Change change={0} changePct={row.change_pct} showAbs={false} />}</td>
                          {COLUMNS.slice(2).map((c) => <td key={c.key} className="num p-3 text-right">{fmt(fields.get(c.key), row[c.key] as number | null)}</td>)}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            {r && r.total > r.page_size && (
              <div className="flex items-center justify-between p-3 text-xs text-muted">
                <span>Page {r.page} of {pages}</span>
                <div className="flex gap-2">
                  <button disabled={r.page <= 1} onClick={() => setQuery((q) => ({ ...q, page: q.page - 1 }))} className="rounded-lg border border-border px-3 py-1 disabled:opacity-40">Previous</button>
                  <button disabled={r.page >= pages} onClick={() => setQuery((q) => ({ ...q, page: q.page + 1 }))} className="rounded-lg border border-border px-3 py-1 disabled:opacity-40">Next</button>
                </div>
              </div>
            )}
          </Card>
          <p className="text-[11px] text-muted">Screens describe the current state of the data, not a recommendation. Metrics use only data up to each instrument’s latest session.</p>
        </div>

        <Card className="h-fit p-4">
          <CardHeader title="Saved screens" subtitle="Stored on the server for this profile." />
          <form onSubmit={(e) => { e.preventDefault(); if (saveName.trim()) save.mutate(); }} className="flex gap-2">
            <input value={saveName} onChange={(e) => setSaveName(e.target.value)} maxLength={60} placeholder="Name this screen" aria-label="Screen name" className="h-9 min-w-0 flex-1 rounded-lg border border-border bg-bg/60 px-2.5 text-sm outline-none focus:border-accent" />
            <button type="submit" disabled={!saveName.trim() || save.isPending} className="inline-flex h-9 items-center gap-1 rounded-lg bg-accent px-3 text-sm font-medium text-white disabled:opacity-50"><Bookmark className="h-4 w-4" />Save</button>
          </form>
          <ul className="mt-3 space-y-1">
            {saved.data?.items.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 hover:bg-surface">
                <button onClick={() => { setQuery({ ...DEFAULT_QUERY, ...s.definition, page: 1 }); setSelected([]); }} className="min-w-0 flex-1 truncate text-left text-sm">{s.name}<span className="ml-2 text-[11px] text-muted">{s.definition.filters.length} filter{s.definition.filters.length === 1 ? "" : "s"}</span></button>
                <button onClick={() => del.mutate(s.id)} aria-label={`Delete screen ${s.name}`} className="rounded p-1 text-muted hover:text-down"><Trash2 className="h-3.5 w-3.5" /></button>
              </li>
            ))}
            {saved.data?.items.length === 0 && <li className="px-2 py-3 text-xs text-muted">Nothing saved yet.</li>}
          </ul>
          <div className="mt-4 border-t border-border pt-3"><Badge tone="neutral">Data is simulated in demo mode</Badge></div>
        </Card>
      </div>
    </>
  );
}
