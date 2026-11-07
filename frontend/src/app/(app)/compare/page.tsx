"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, Plus, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { IndicatorPanel } from "@/components/charts/IndicatorPanel";
import { DataBadge } from "@/components/shared/DataBadge";
import { Card, CardHeader, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui/primitives";
import { api, downloadCsv } from "@/lib/api";
import { cn, fmtDay, pct } from "@/lib/utils";
import type { CompareRequest } from "@/types/api";

const RANGES = ["1M", "3M", "6M", "1Y", "5Y", "MAX"] as const;
// Categorical palette; series are also identified by name in the legend, never by colour alone.
const COLORS = ["#4f8cff", "#f5a623", "#2ec4a6", "#e5586e", "#a78bfa", "#7dd3fc", "#f472b6", "#84cc16", "#fb923c", "#94a3b8"];
const p = (v: number | null | undefined, d = 2) => (v === null || v === undefined ? "Unavailable" : pct(v * 100, d));

/** Diverging cell: sign and magnitude are printed, colour only reinforces. */
function corrStyle(v: number | null): React.CSSProperties {
  if (v === null) return {};
  const a = Math.min(Math.abs(v), 1) * 0.55;
  return { background: v >= 0 ? `rgb(var(--accent) / ${a})` : `rgb(var(--down) / ${a})` };
}

function CompareInner() {
  const params = useSearchParams();
  const stocks = useQuery({ queryKey: ["stocks"], queryFn: api.stocks });
  const [symbols, setSymbols] = useState<string[]>([]);
  const [range, setRange] = useState<CompareRequest["range"]>("1Y");
  const [pair, setPair] = useState<[string, string] | null>(null);
  const [rollWindow, setRollWindow] = useState(60);
  const [hover, setHover] = useState<number | null>(null);
  const [hoverRoll, setHoverRoll] = useState<number | null>(null);
  const [adding, setAdding] = useState("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const raw = params.get("symbols");
    if (raw) setSymbols([...new Set(raw.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean))].slice(0, 10));
    else setSymbols((cur) => (cur.length ? cur : ["AAPL", "MSFT", "NVDA"]));
  }, [params]);

  const valid = symbols.length >= 2 && symbols.length <= 10;
  const activePair = pair && symbols.includes(pair[0]) && symbols.includes(pair[1]) && pair[0] !== pair[1] ? pair : null;
  const req: CompareRequest = { symbols, range, rolling_pair: activePair, rolling_window: rollWindow };
  const q = useQuery({ queryKey: ["compare", req], queryFn: () => api.compare(req), enabled: valid, retry: false, placeholderData: (x) => x });
  const csv = useMutation({ mutationFn: () => downloadCsv("/compare/export.csv", req, "marketpulse_compare.csv"), onError: (e) => setErr((e as Error).message) });
  const r = q.data;
  const available = useMemo(() => (stocks.data?.items ?? []).map((s) => s.symbol).filter((s) => !symbols.includes(s)), [stocks.data, symbols]);
  const colorOf = (s: string) => COLORS[symbols.indexOf(s) % COLORS.length] ?? COLORS[0]!;

  return (
    <>
      <PageHeader title="Compare" description="Rebased performance, risk and correlation over the sessions every selected stock shares." actions={<DataBadge meta={r?.meta} />} />
      <Card className="mb-5 p-4">
        <div className="flex flex-wrap items-center gap-2">
          {symbols.map((s) => (
            <span key={s} className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface py-1 pl-2.5 pr-1.5 text-xs font-medium">
              <span className="h-2 w-2 rounded-full" style={{ background: colorOf(s) }} aria-hidden />{s}
              <button aria-label={`Remove ${s}`} onClick={() => setSymbols(symbols.filter((x) => x !== s))} className="rounded p-0.5 text-muted hover:text-fg"><X className="h-3 w-3" /></button>
            </span>
          ))}
          {symbols.length < 10 && (
            <label className="inline-flex items-center gap-1">
              <Plus className="h-3.5 w-3.5 text-muted" aria-hidden />
              <select aria-label="Add a symbol" value={adding} onChange={(e) => { if (e.target.value) setSymbols([...symbols, e.target.value]); setAdding(""); }} className="h-8 rounded-lg border border-border bg-bg/60 px-2 text-xs outline-none focus:border-accent">
                <option value="">Add symbol…</option>
                {available.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
          )}
          <div className="ml-auto flex items-center gap-2">
            <div className="flex rounded-lg border border-border bg-bg/60 p-0.5" role="group" aria-label="Range">
              {RANGES.map((x) => <button key={x} aria-pressed={range === x} onClick={() => setRange(x)} className={cn("rounded-md px-2.5 py-1 text-xs font-medium", range === x ? "bg-accent text-white" : "text-muted hover:text-fg")}>{x}</button>)}
            </div>
            <button onClick={() => csv.mutate()} disabled={!r || !valid} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border px-2.5 text-xs font-medium hover:border-accent/50 disabled:opacity-40"><Download className="h-3.5 w-3.5" /> CSV</button>
          </div>
        </div>
        {!valid && <p role="alert" className="mt-2 text-xs text-muted">Pick between 2 and 10 symbols.</p>}
        {err && <p role="alert" className="mt-2 text-xs text-down">{err}</p>}
      </Card>

      {!valid ? <EmptyState title="Select at least two symbols" hint="Use the menu above to add stocks to compare." />
        : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} />
        : !r ? <Skeleton className="h-96" />
        : (
          <div className="space-y-5">
            <Card className="p-4">
              <CardHeader title="Performance, rebased to 100" subtitle={`${fmtDay(r.days[0]!)} – ${fmtDay(r.days[r.days.length - 1]!)} · ${r.days.length} common sessions`} />
              <div className="mb-2 flex flex-wrap gap-3 text-xs">{r.symbols.map((s) => <span key={s} className="inline-flex items-center gap-1.5"><span className="h-0.5 w-4 rounded" style={{ background: colorOf(s) }} aria-hidden />{s}</span>)}</div>
              <IndicatorPanel title="Rebased price" days={r.days} height={300} hover={hover} onHover={setHover} format={(v) => v.toFixed(1)} guides={[100]}
                series={r.symbols.map((s) => ({ label: s, color: colorOf(s), values: r.normalized[s]! }))} />
              <p className="mt-2 text-[11px] text-muted">{r.basis} Past performance does not predict future results.</p>
            </Card>

            <Card>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px] text-sm">
                  <thead><tr className="border-b border-border text-[11px] uppercase tracking-wide text-muted">
                    <th className="p-3 text-left font-medium">Symbol</th><th className="p-3 text-right font-medium">Total return</th><th className="p-3 text-right font-medium">Annualised</th>
                    <th className="p-3 text-right font-medium">Volatility</th><th className="p-3 text-right font-medium">Max drawdown</th><th className="p-3 text-right font-medium">Best day</th><th className="p-3 text-right font-medium">Worst day</th>
                  </tr></thead>
                  <tbody>{r.symbols.map((s) => { const st = r.stats[s]!; return (
                    <tr key={s} className="border-b border-border/60">
                      <td className="p-3 font-semibold"><span className="mr-2 inline-block h-2 w-2 rounded-full" style={{ background: colorOf(s) }} aria-hidden />{s}</td>
                      <td className="num p-3 text-right">{p(st.total_return)}</td><td className="num p-3 text-right">{p(st.annualized_return)}</td>
                      <td className="num p-3 text-right">{p(st.annualized_volatility, 1)}</td><td className="num p-3 text-right">{p(st.max_drawdown)}</td>
                      <td className="num p-3 text-right">{p(st.best_day?.return)}</td><td className="num p-3 text-right">{p(st.worst_day?.return)}</td>
                    </tr>); })}</tbody>
                </table>
              </div>
            </Card>

            <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
              <Card className="p-4">
                <CardHeader title="Correlation matrix" subtitle="Daily returns, Pearson" />
                <div className="overflow-x-auto">
                  <table className="text-xs" aria-label="Correlation matrix">
                    <thead><tr><th className="p-1" />{r.correlation.symbols.map((s) => <th key={s} scope="col" className="p-1.5 font-medium text-muted">{s}</th>)}</tr></thead>
                    <tbody>{r.correlation.symbols.map((a, i) => (
                      <tr key={a}><th scope="row" className="p-1.5 text-left font-medium text-muted">{a}</th>
                        {r.correlation.matrix[i]!.map((v, j) => <td key={j} style={corrStyle(v)} className="num min-w-[52px] rounded p-1.5 text-center">{v === null ? "n/a" : v.toFixed(2)}</td>)}
                      </tr>))}</tbody>
                  </table>
                </div>
                <p className="mt-2 text-[11px] text-muted">+1 move together, 0 unrelated, −1 move opposite. Correlation is not causation and changes over time.</p>
              </Card>

              <Card className="p-4">
                <CardHeader title="Rolling correlation" subtitle="Trailing window, no future data" />
                <div className="mb-3 flex flex-wrap items-end gap-2 text-[11px] text-muted">
                  {([0, 1] as const).map((k) => (
                    <label key={k}>{k === 0 ? "Stock A" : "Stock B"}
                      <select value={activePair?.[k] ?? ""} onChange={(e) => { const cur = activePair ?? [symbols[0]!, symbols[1]!]; const nxt = [...cur] as [string, string]; nxt[k] = e.target.value; setPair(nxt); }} className="mt-1 block h-8 rounded-lg border border-border bg-bg/60 px-2 text-xs text-fg">
                        <option value="">Choose…</option>{symbols.map((s) => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </label>
                  ))}
                  <label>Window (sessions)
                    <input type="number" min={10} max={250} value={rollWindow} onChange={(e) => setRollWindow(Math.min(250, Math.max(10, Number(e.target.value) || 60)))} className="mt-1 block h-8 w-24 rounded-lg border border-border bg-bg/60 px-2 text-xs text-fg" />
                  </label>
                </div>
                {r.rolling_correlation ? (
                  <IndicatorPanel title={`${r.rolling_correlation.pair[0]} vs ${r.rolling_correlation.pair[1]} (${r.rolling_correlation.window}d)`} days={r.rolling_correlation.days} height={170} hover={hoverRoll} onHover={setHoverRoll}
                    domain={[-1, 1]} guides={[0]} format={(v) => v.toFixed(2)} series={[{ label: "Correlation", color: "rgb(var(--accent))", values: r.rolling_correlation.values }]} />
                ) : <EmptyState title="Choose two different stocks" hint="Pick Stock A and Stock B to chart how their correlation evolves." />}
              </Card>
            </div>

            {r.notes.length > 0 && <ul className="list-disc space-y-0.5 pl-5 text-[11px] text-muted">{r.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
          </div>
        )}
    </>
  );
}

export default function ComparePage() {
  return <Suspense fallback={<Skeleton className="h-96" />}><CompareInner /></Suspense>;
}
