"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, History, Play, Trash2 } from "lucide-react";
import { useState } from "react";
import { IndicatorPanel } from "@/components/charts/IndicatorPanel";
import { DataBadge } from "@/components/shared/DataBadge";
import { Badge, Card, CardHeader, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { cn, fmtDay, num, pct, trendClass, usd } from "@/lib/utils";
import type { BacktestRequest, BacktestResult } from "@/types/api";

const input = "h-9 rounded-lg border border-border bg-bg/60 px-2.5 text-sm outline-none focus:border-accent";
const PARAM_LABELS: Record<string, string> = { fast: "Fast SMA", slow: "Slow SMA", period: "RSI period", buy_below: "Buy below", sell_above: "Sell above", lookback: "Lookback (sessions)", threshold_pct: "Threshold (%)" };
const p = (v: number | null | undefined, d = 2) => (v === null || v === undefined ? "Unavailable" : pct(v * 100, d));

function Metric({ label, value, tone, hint }: { label: string; value: string; tone?: string; hint?: string }) {
  return (
    <div className="bg-surface p-4">
      <dt className="text-[11px] text-muted">{label}</dt>
      <dd className={cn("num mt-1 text-lg font-semibold", tone)}>{value}</dd>
      {hint && <div className="mt-0.5 text-[10.5px] text-muted">{hint}</div>}
    </div>
  );
}

function Results({ r }: { r: BacktestResult }) {
  const [hover, setHover] = useState<number | null>(null);
  const m = r.metrics;
  const beat = m.total_return !== null && r.buy_hold_metrics.total_return !== null ? m.total_return - r.buy_hold_metrics.total_return : null;
  return (
    <div className="space-y-5">
      {r.warnings.length > 0 && (
        <div role="status" className="flex gap-2 rounded-lg border border-warn/40 bg-warn/10 p-3 text-xs"><AlertTriangle className="h-4 w-4 shrink-0 text-warn" aria-hidden /><div>{r.warnings.map((w) => <p key={w}>{w}</p>)}</div></div>
      )}
      <Card>
        <dl className="grid grid-cols-2 gap-px bg-border/50 p-px md:grid-cols-4 xl:grid-cols-8">
          <Metric label="Total return" value={p(m.total_return)} tone={trendClass(m.total_return ?? 0)} hint={`Buy & hold ${p(r.buy_hold_metrics.total_return)}`} />
          <Metric label="Annualised" value={p(m.annualized_return)} hint={m.annualized_return === null ? "Needs ≥ 252 sessions" : undefined} />
          <Metric label="Volatility" value={p(m.annualized_volatility, 1)} hint="Annualised" />
          <Metric label="Sharpe" value={m.sharpe === null ? "Unavailable" : num(m.sharpe, 2)} hint={`rf ${String(r.config.risk_free_pct ?? 0)}%`} />
          <Metric label="Max drawdown" value={p(m.max_drawdown)} tone="text-down" hint={`Buy & hold ${p(r.buy_hold_metrics.max_drawdown)}`} />
          <Metric label="Win rate" value={m.win_rate === null ? "Unavailable" : p(m.win_rate, 0)} hint={`${m.completed_trades} completed trades`} />
          <Metric label="Exposure" value={p(m.exposure, 0)} hint="Share of days in market" />
          <Metric label="Benchmark (SPY)" value={p(r.benchmark_return)} hint="Proxy, same dates" />
        </dl>
      </Card>
      <Card className="p-4">
        <CardHeader title="Equity curve vs buy & hold" subtitle={`${fmtDay(r.days[0]!)} – ${fmtDay(r.days[r.days.length - 1]!)} · ${r.days.length} sessions · ran in ${r.execution_ms} ms`} action={
          <span className="text-[11px] text-muted">▲ buy · ▽ sell{beat !== null && <> · vs buy &amp; hold <b className={cn("num", trendClass(beat))}>{pct(beat * 100)}</b></>}</span>
        } />
        <IndicatorPanel title="Equity" days={r.days} height={260} hover={hover} onHover={setHover} format={(v) => usd(v, 0)} markers={r.markers}
          series={[{ label: "Strategy", color: "#4f8cff", values: r.equity }, { label: "Buy & hold", color: "#f5a623", values: r.buy_hold, dash: "4 3" }]} />
        <IndicatorPanel title="Strategy drawdown" days={r.days} height={110} hover={hover} onHover={setHover} area format={(v) => `${(v * 100).toFixed(1)}%`}
          series={[{ label: "Drawdown", color: "rgb(var(--down))", values: r.drawdown }]} />
        {m.notes.length > 0 && <ul className="mt-2 list-disc pl-5 text-[11px] text-muted">{m.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
      </Card>
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <div className="border-b border-border p-4"><CardHeader title="Trade history" subtitle="Fills at the next session's open, with costs and slippage" /></div>
          {r.trades.length === 0 ? <div className="p-6"><EmptyState title="No trades" hint="The strategy never signalled in this window." /></div> : (
            <div className="max-h-96 overflow-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead className="sticky top-0 bg-card"><tr className="border-b border-border text-[11px] uppercase tracking-wide text-muted">{["Entry", "Exit", "Qty", "Entry px", "Exit px", "Costs", "P&L", "Return"].map((h, i) => <th key={h} className={cn("p-3 font-medium", i > 1 ? "text-right" : "text-left")}>{h}</th>)}</tr></thead>
                <tbody>{r.trades.map((t, i) => (
                  <tr key={i} className="border-b border-border/60">
                    <td className="num p-3">{fmtDay(t.entry_day)}</td>
                    <td className="num p-3">{t.exit_day ? fmtDay(t.exit_day) : <Badge tone="warn">Open</Badge>}</td>
                    <td className="num p-3 text-right">{num(t.qty, 3)}</td><td className="num p-3 text-right">{usd(t.entry_price)}</td><td className="num p-3 text-right">{usd(t.exit_price)}</td>
                    <td className="num p-3 text-right">{usd(t.costs)}</td>
                    <td className={cn("num p-3 text-right", trendClass(t.pnl))}>{t.pnl > 0 ? "+" : t.pnl < 0 ? "−" : ""}{usd(Math.abs(t.pnl))}</td>
                    <td className={cn("num p-3 text-right", trendClass(t.return_pct))}>{pct(t.return_pct)}</td>
                  </tr>))}</tbody>
              </table>
            </div>
          )}
        </Card>
        <Card className="h-fit p-4">
          <CardHeader title="Reproducibility" subtitle={`Strategy v${r.reproducibility.strategy_version}`} />
          <dl className="space-y-1.5 text-xs">
            <div className="flex justify-between"><dt className="text-muted">Parameters</dt><dd className="num">{Object.entries(r.config.params).map(([k, v]) => `${k}=${v}`).join(", ")}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">Data range</dt><dd className="num">{r.reproducibility.data_range.join(" → ")}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">Data fingerprint</dt><dd className="num">{r.reproducibility.data_fingerprint}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">Capital</dt><dd className="num">{usd(r.config.initial_capital, 0)}</dd></div>
          </dl>
          <p className="mb-1 mt-3 text-[11px] font-medium">Assumptions</p>
          <ul className="list-disc space-y-1 pl-4 text-[11px] text-muted">{r.reproducibility.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
        </Card>
      </div>
      <p className="text-[11px] text-muted">{r.disclaimer}</p>
    </div>
  );
}

export default function BacktestingPage() {
  const qc = useQueryClient();
  const strategies = useQuery({ queryKey: ["strategies"], queryFn: api.strategies, staleTime: Infinity });
  const stocks = useQuery({ queryKey: ["stocks"], queryFn: api.stocks });
  const history = useQuery({ queryKey: ["backtests"], queryFn: api.backtests });
  const [symbol, setSymbol] = useState("AAPL");
  const [strategy, setStrategy] = useState("ma_cross");
  const [params, setParams] = useState<Record<string, string>>({});
  const [capital, setCapital] = useState("10000");
  const [commission, setCommission] = useState("5");
  const [slippage, setSlippage] = useState("5");
  const [sizing, setSizing] = useState<"full" | "fraction">("full");
  const [fraction, setFraction] = useState("0.5");
  const [rf, setRf] = useState("0");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const info = strategies.data?.items.find((s) => s.key === strategy);
  const val = (k: string) => params[`${strategy}.${k}`] ?? String(info?.params[k] ?? "");

  const run = useMutation({
    mutationFn: () => {
      const num_ = (s: string, name: string) => { const n = Number(s); if (s.trim() === "" || !Number.isFinite(n)) throw new Error(`${name} must be a number`); return n; };
      const body: BacktestRequest = {
        symbol, strategy, params: Object.fromEntries(Object.keys(info?.params ?? {}).map((k) => [k, num_(val(k), PARAM_LABELS[k] ?? k)])),
        start: start || null, end: end || null, initial_capital: num_(capital, "Capital"), commission_bps: num_(commission, "Commission"),
        slippage_bps: num_(slippage, "Slippage"), sizing, fraction: num_(fraction, "Fraction"), long_only: true, risk_free_pct: num_(rf, "Risk-free rate"), save: true,
      };
      return api.runBacktest(body);
    },
    onSuccess: (r) => { setErr(null); setResult(r); qc.invalidateQueries({ queryKey: ["backtests"] }); },
    onError: (e) => setErr((e as Error).message),
  });
  const load = useMutation({ mutationFn: (id: number) => api.backtest(id), onSuccess: (r) => { setErr(null); setResult(r); }, onError: (e) => setErr((e as Error).message) });
  const del = useMutation({ mutationFn: (id: number) => api.deleteBacktest(id), onSuccess: () => qc.invalidateQueries({ queryKey: ["backtests"] }) });

  return (
    <>
      <PageHeader title="Backtesting lab" description="Test simple long-only strategies on stored history. Research and education only." actions={<DataBadge meta={result?.meta} />} />
      <div role="note" className="mb-5 rounded-lg border border-border bg-surface px-4 py-2.5 text-xs text-muted">
        Signals use data through each close and trades fill at the <b>next session’s open</b> on adjusted prices, with commission and slippage. Past performance does not predict future results.
      </div>
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-4">
        <div className="space-y-5 xl:col-span-3">
          <Card className="p-4">
            <CardHeader title="Configuration" subtitle="Invalid combinations are rejected by the server." />
            <form onSubmit={(e) => { e.preventDefault(); run.mutate(); }} className="space-y-3">
              <div className="flex flex-wrap items-end gap-2">
                <label className="text-[11px] text-muted">Symbol<select value={symbol} onChange={(e) => setSymbol(e.target.value)} className={cn(input, "mt-1 block w-28")}>{(stocks.data?.items ?? []).map((s) => <option key={s.symbol}>{s.symbol}</option>)}</select></label>
                <label className="text-[11px] text-muted">Strategy<select value={strategy} onChange={(e) => setStrategy(e.target.value)} className={cn(input, "mt-1 block min-w-[220px]")}>{(strategies.data?.items ?? []).map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}</select></label>
                {Object.keys(info?.params ?? {}).map((k) => (
                  <label key={k} className="text-[11px] text-muted">{PARAM_LABELS[k] ?? k}<input inputMode="decimal" value={val(k)} onChange={(e) => setParams({ ...params, [`${strategy}.${k}`]: e.target.value })} className={cn(input, "mt-1 block w-28")} /></label>
                ))}
              </div>
              <div className="flex flex-wrap items-end gap-2">
                <label className="text-[11px] text-muted">Start<input type="date" value={start} onChange={(e) => setStart(e.target.value)} className={cn(input, "mt-1 block")} /></label>
                <label className="text-[11px] text-muted">End<input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className={cn(input, "mt-1 block")} /></label>
                <label className="text-[11px] text-muted">Capital ($)<input inputMode="decimal" value={capital} onChange={(e) => setCapital(e.target.value)} className={cn(input, "mt-1 block w-28")} /></label>
                <label className="text-[11px] text-muted">Commission (bps/side)<input inputMode="decimal" value={commission} onChange={(e) => setCommission(e.target.value)} className={cn(input, "mt-1 block w-28")} /></label>
                <label className="text-[11px] text-muted">Slippage (bps)<input inputMode="decimal" value={slippage} onChange={(e) => setSlippage(e.target.value)} className={cn(input, "mt-1 block w-24")} /></label>
                <label className="text-[11px] text-muted">Sizing<select value={sizing} onChange={(e) => setSizing(e.target.value as "full" | "fraction")} className={cn(input, "mt-1 block")}><option value="full">All cash</option><option value="fraction">Fraction of equity</option></select></label>
                {sizing === "fraction" && <label className="text-[11px] text-muted">Fraction (0.05–1)<input inputMode="decimal" value={fraction} onChange={(e) => setFraction(e.target.value)} className={cn(input, "mt-1 block w-24")} /></label>}
                <label className="text-[11px] text-muted">Risk-free (% / yr)<input inputMode="decimal" value={rf} onChange={(e) => setRf(e.target.value)} className={cn(input, "mt-1 block w-24")} /></label>
                <label className="flex h-9 items-center gap-2 text-xs text-muted"><input type="checkbox" checked disabled /> Long-only (shorting not supported)</label>
                <button type="submit" disabled={run.isPending} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-accent px-4 text-sm font-medium text-white disabled:opacity-50"><Play className="h-4 w-4" />{run.isPending ? "Running…" : "Run backtest"}</button>
              </div>
              {err && <p role="alert" className="text-xs text-down">{err}</p>}
            </form>
          </Card>
          {run.isPending ? <Skeleton className="h-96" /> : result ? <Results r={result} /> : <EmptyState title="Run a backtest to see results" hint="Choose a symbol, a strategy and its parameters, then press Run." />}
        </div>
        <Card className="h-fit p-4">
          <CardHeader title="Saved runs" subtitle="Configuration + results are stored" />
          {history.isError ? <ErrorState message={(history.error as Error).message} onRetry={() => history.refetch()} /> : (
            <ul className="space-y-1">
              {history.data?.items.slice(0, 15).map((h) => (
                <li key={h.id} className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 hover:bg-surface">
                  <button onClick={() => load.mutate(h.id)} className="min-w-0 flex-1 text-left text-sm"><History className="mr-1.5 inline h-3 w-3 text-muted" aria-hidden />{h.symbol} · {h.strategy}<div className="num text-[11px] text-muted">{p(h.total_return)} vs B&amp;H {p(h.buy_hold_return)} · {new Date(h.created_at).toLocaleDateString()}</div></button>
                  <button onClick={() => del.mutate(h.id)} aria-label={`Delete run ${h.id}`} className="rounded p-1 text-muted hover:text-down"><Trash2 className="h-3.5 w-3.5" /></button>
                </li>
              ))}
              {history.data?.items.length === 0 && <li className="px-2 py-3 text-xs text-muted">No saved runs yet.</li>}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
