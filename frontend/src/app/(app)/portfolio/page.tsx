"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Download, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { IndicatorPanel } from "@/components/charts/IndicatorPanel";
import { Change } from "@/components/shared/Change";
import { DataBadge } from "@/components/shared/DataBadge";
import { Badge, Card, CardHeader, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { cn, fmtDay, num, pct, trendClass, usd } from "@/lib/utils";
import type { PortfolioDetail, TxnInput, TxnRow } from "@/types/api";

const COLORS = ["#4f8cff", "#f5a623", "#2ec4a6", "#e5586e", "#a78bfa", "#7dd3fc", "#f472b6", "#84cc16", "#fb923c", "#94a3b8", "#64748b"];
const RANGES = ["1M", "3M", "6M", "1Y", "MAX"] as const;
const input = "h-9 rounded-lg border border-border bg-bg/60 px-2.5 text-sm outline-none focus:border-accent";
const money = (v: number | null | undefined) => (v === null || v === undefined ? "Unavailable" : usd(v));
const signedMoney = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${usd(Math.abs(v))}`;

function Stat({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: string }) {
  return (
    <div className="bg-surface p-4">
      <dt className="text-[11px] text-muted">{label}</dt>
      <dd className={cn("num mt-1 text-xl font-semibold", tone)}>{value}</dd>
      {hint && <div className="mt-0.5 text-[10.5px] text-muted">{hint}</div>}
    </div>
  );
}

function Summary({ d }: { d: PortfolioDetail }) {
  const s = d.summary;
  return (
    <Card>
      <dl className="grid grid-cols-2 gap-px bg-border/50 p-px md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Total value" value={usd(s.total_value)} hint={s.complete ? "Cash + market value" : "Incomplete: missing prices"} />
        <Stat label="Cash" value={usd(s.cash)} />
        <Stat label="Invested capital" value={usd(s.invested_capital)} hint="Cost basis of open positions" />
        <Stat label="Unrealised P&L" value={signedMoney(s.unrealized_pnl)} tone={trendClass(s.unrealized_pnl)} hint="Market value − cost basis" />
        <Stat label="Realised P&L" value={signedMoney(s.realized_pnl)} tone={trendClass(s.realized_pnl)} hint={`Fees paid ${usd(s.fees_paid)}`} />
        <div className="bg-surface p-4">
          <dt className="text-[11px] text-muted">Daily change</dt>
          <dd className="mt-1 text-xl font-semibold">
            {d.daily_change && d.daily_change.change_pct !== null ? <Change change={d.daily_change.change} changePct={d.daily_change.change_pct} /> : <span className="num">Unavailable</span>}
          </dd>
          <div className="mt-0.5 text-[10.5px] text-muted">{d.daily_change ? `Session ${fmtDay(d.daily_change.day)}, excl. deposits` : "Needs two valued sessions"}</div>
        </div>
      </dl>
    </Card>
  );
}

function Allocation({ d }: { d: PortfolioDetail }) {
  const items = d.summary.allocation.filter((a) => a.weight !== null && a.weight > 0);
  if (!items.length) return <EmptyState title="Nothing to allocate yet" hint="Add cash and a purchase." />;
  return (
    <div>
      <div className="flex h-3 overflow-hidden rounded-full" role="img" aria-label={`Allocation: ${items.map((i) => `${i.label} ${i.weight}%`).join(", ")}`}>
        {items.map((a, i) => <div key={a.label} style={{ width: `${a.weight}%`, background: COLORS[i % COLORS.length] }} />)}
      </div>
      <ul className="mt-3 space-y-1.5 text-sm">
        {items.map((a, i) => (
          <li key={a.label} className="flex items-center justify-between">
            <span className="inline-flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ background: COLORS[i % COLORS.length] }} aria-hidden />{a.label}</span>
            <span className="num text-muted">{num(a.weight ?? 0, 1)}% · {money(a.value)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Positions({ d }: { d: PortfolioDetail }) {
  const rows = d.summary.positions;
  if (!rows.length) return <div className="p-6"><EmptyState title="No open positions" hint="Record a purchase below." /></div>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[760px] text-sm">
        <thead><tr className="border-b border-border text-[11px] uppercase tracking-wide text-muted">
          {["Symbol", "Qty", "Avg cost", "Price", "Market value", "Cost basis", "Unrealised", "Weight"].map((h, i) => <th key={h} className={cn("p-3 font-medium", i ? "text-right" : "text-left")}>{h}</th>)}
        </tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.symbol} className="border-b border-border/60">
              <td className="p-3"><Link href={`/markets/${r.symbol}`} className="font-semibold hover:text-accent">{r.symbol}</Link></td>
              <td className="num p-3 text-right">{num(r.quantity, 4)}</td>
              <td className="num p-3 text-right">{usd(r.avg_cost)}</td>
              <td className="num p-3 text-right">
                {r.price === null ? <span className="inline-flex items-center gap-1 text-warn"><AlertTriangle className="h-3 w-3" aria-hidden />No price</span> : usd(r.price)}
                {r.stale && <div className="text-[10px] text-warn">Stale: {r.price_day && fmtDay(r.price_day)}</div>}
              </td>
              <td className="num p-3 text-right">{money(r.market_value)}</td>
              <td className="num p-3 text-right">{usd(r.cost_basis)}</td>
              <td className={cn("num p-3 text-right", r.unrealized_pnl !== null && trendClass(r.unrealized_pnl))}>
                {r.unrealized_pnl === null ? "Unavailable" : <>{signedMoney(r.unrealized_pnl)}<div className="text-[10px] opacity-80">{r.unrealized_pct === null ? "" : pct(r.unrealized_pct)}</div></>}
              </td>
              <td className="num p-3 text-right">{r.weight === null ? "Unavailable" : `${num(r.weight, 1)}%`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Performance({ id }: { id: number }) {
  const [range, setRange] = useState<(typeof RANGES)[number]>("MAX");
  const [benchmark, setBenchmark] = useState("SPY");
  const [hover, setHover] = useState<number | null>(null);
  const q = useQuery({ queryKey: ["pf-perf", id, range, benchmark], queryFn: () => api.performance(id, range, benchmark), placeholderData: (p) => p });
  const p = q.data;
  return (
    <Card className="p-4">
      <CardHeader title="Performance vs benchmark" subtitle="Time-weighted return, rebased to 100" action={
        <div className="flex items-center gap-2">
          <select aria-label="Benchmark" value={benchmark} onChange={(e) => setBenchmark(e.target.value)} className="h-8 rounded-lg border border-border bg-bg/60 px-2 text-xs">
            {["SPY", "QQQ", "DIA", "IWM"].map((b) => <option key={b}>{b}</option>)}
          </select>
          <div className="flex rounded-lg border border-border bg-bg/60 p-0.5" role="group" aria-label="Range">
            {RANGES.map((x) => <button key={x} aria-pressed={range === x} onClick={() => setRange(x)} className={cn("rounded-md px-2 py-1 text-xs font-medium", range === x ? "bg-accent text-white" : "text-muted hover:text-fg")}>{x}</button>)}
          </div>
        </div>
      } />
      {q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} />
        : !p ? <Skeleton className="h-56" />
        : p.days.length < 2 ? <EmptyState title="Not enough history to chart" hint={p.notes[0] ?? "Performance needs at least two valued sessions."} />
        : (
          <>
            <div className="mb-2 flex flex-wrap gap-4 text-xs">
              <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-4 rounded" style={{ background: COLORS[0] }} aria-hidden />Portfolio {p.stats && <b className={cn("num", trendClass(p.stats.twr_return))}>{pct(p.stats.twr_return * 100)}</b>}</span>
              <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-4 rounded" style={{ background: COLORS[1] }} aria-hidden />{p.benchmark} {p.stats && <b className={cn("num", trendClass(p.stats.benchmark_return))}>{pct(p.stats.benchmark_return * 100)}</b>}</span>
              {p.stats && <span className="text-muted">Max drawdown <b className="num text-down">{pct(p.stats.max_drawdown * 100)}</b></span>}
            </div>
            <IndicatorPanel title="Rebased return" days={p.days} height={240} hover={hover} onHover={setHover} guides={[100]} format={(v) => v.toFixed(1)}
              series={[{ label: "Portfolio", color: COLORS[0]!, values: p.twr_index }, { label: p.benchmark, color: COLORS[1]!, values: p.benchmark_index }]} />
            <IndicatorPanel title="Portfolio value" days={p.days} height={110} hover={hover} onHover={setHover} format={(v) => usd(v, 0)}
              series={[{ label: "Value", color: COLORS[2]!, values: p.value }, { label: "Net deposits", color: "#94a3b8", values: p.net_deposits, dash: "4 3" }]} />
            {p.notes.length > 0 && <ul className="mt-2 list-disc pl-5 text-[11px] text-muted">{p.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
            {p.basis && <p className="mt-2 text-[11px] text-muted">{p.basis} Past performance does not predict future results.</p>}
          </>
        )}
    </Card>
  );
}

function TxnForm({ id, onDone }: { id: number; onDone: (warnings: string[]) => void }) {
  const [t, setT] = useState({ kind: "buy" as TxnRow["kind"], day: "", symbol: "", quantity: "", price: "", fee: "0", amount: "", note: "" });
  const [err, setErr] = useState<string | null>(null);
  const stocks = useQuery({ queryKey: ["stocks"], queryFn: api.stocks });
  const trade = t.kind === "buy" || t.kind === "sell";
  const save = useMutation({
    mutationFn: () => {
      const n = (s: string) => (s.trim() === "" ? NaN : Number(s));
      if (!t.day) throw new Error("Choose a date");
      const body: TxnInput = { day: t.day, kind: t.kind, note: t.note };
      if (trade) {
        if (!t.symbol) throw new Error("Choose a symbol");
        const q = n(t.quantity), p = n(t.price), f = n(t.fee);
        if (!Number.isFinite(q) || !Number.isFinite(p) || !Number.isFinite(f)) throw new Error("Quantity, price and fee must be numbers");
        Object.assign(body, { symbol: t.symbol, quantity: q, price: p, fee: f });
      } else {
        const a = n(t.amount);
        if (!Number.isFinite(a)) throw new Error("Amount must be a number");
        body.amount = a;
      }
      return api.addTransaction(id, body);
    },
    onSuccess: (r) => { setErr(null); setT((x) => ({ ...x, quantity: "", price: "", amount: "", note: "" })); onDone(r.warnings); },
    onError: (e) => setErr((e as Error).message),
  });
  return (
    <form onSubmit={(e) => { e.preventDefault(); save.mutate(); }} className="flex flex-wrap items-end gap-2">
      <label className="text-[11px] text-muted">Type
        <select value={t.kind} onChange={(e) => setT({ ...t, kind: e.target.value as TxnRow["kind"] })} className={cn(input, "mt-1 block")}>
          <option value="buy">Buy</option><option value="sell">Sell</option><option value="deposit">Deposit cash</option><option value="withdraw">Withdraw cash</option>
        </select>
      </label>
      <label className="text-[11px] text-muted">Date<input type="date" value={t.day} onChange={(e) => setT({ ...t, day: e.target.value })} className={cn(input, "mt-1 block")} /></label>
      {trade ? (
        <>
          <label className="text-[11px] text-muted">Symbol
            <select value={t.symbol} onChange={(e) => setT({ ...t, symbol: e.target.value })} className={cn(input, "mt-1 block w-28")}>
              <option value="">Choose…</option>
              {(stocks.data?.items ?? []).filter((s) => s.kind === "equity").map((s) => <option key={s.symbol}>{s.symbol}</option>)}
            </select>
          </label>
          <label className="text-[11px] text-muted">Quantity<input inputMode="decimal" value={t.quantity} onChange={(e) => setT({ ...t, quantity: e.target.value })} className={cn(input, "mt-1 block w-24")} /></label>
          <label className="text-[11px] text-muted">Price<input inputMode="decimal" value={t.price} onChange={(e) => setT({ ...t, price: e.target.value })} className={cn(input, "mt-1 block w-28")} /></label>
          <label className="text-[11px] text-muted">Fee<input inputMode="decimal" value={t.fee} onChange={(e) => setT({ ...t, fee: e.target.value })} className={cn(input, "mt-1 block w-20")} /></label>
        </>
      ) : (
        <label className="text-[11px] text-muted">Amount<input inputMode="decimal" value={t.amount} onChange={(e) => setT({ ...t, amount: e.target.value })} className={cn(input, "mt-1 block w-32")} /></label>
      )}
      <button type="submit" disabled={save.isPending} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-accent px-3 text-sm font-medium text-white disabled:opacity-50"><Plus className="h-4 w-4" />Record</button>
      {err && <p role="alert" className="basis-full text-xs text-down">{err}</p>}
    </form>
  );
}

function PortfolioView({ id, onDeleted }: { id: number; onDeleted: () => void }) {
  const qc = useQueryClient();
  const [warnings, setWarnings] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const detail = useQuery({ queryKey: ["portfolio", id], queryFn: () => api.portfolio(id) });
  const txns = useQuery({ queryKey: ["pf-txns", id], queryFn: () => api.transactions(id) });
  const refresh = () => {
    for (const k of ["portfolio", "pf-txns", "pf-perf", "portfolios"]) qc.invalidateQueries({ queryKey: [k] });
  };
  const delTxn = useMutation({ mutationFn: (tid: number) => api.deleteTransaction(id, tid), onSuccess: () => { setErr(null); refresh(); }, onError: (e) => setErr((e as Error).message) });
  const delPf = useMutation({ mutationFn: () => api.deletePortfolio(id), onSuccess: () => { refresh(); onDeleted(); } });
  const d = detail.data;

  if (detail.isError) return <ErrorState message={(detail.error as Error).message} onRetry={() => detail.refetch()} />;
  if (!d) return <Skeleton className="h-96" />;
  return (
    <div className="space-y-5">
      <Summary d={d} />
      {d.summary.notes.length > 0 && (
        <div role="status" className="flex gap-2 rounded-lg border border-warn/40 bg-warn/10 p-3 text-xs"><AlertTriangle className="h-4 w-4 shrink-0 text-warn" aria-hidden /><div>{d.summary.notes.map((n) => <p key={n}>{n}</p>)}</div></div>
      )}
      <Performance id={id} />
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <Card className="xl:col-span-2"><div className="border-b border-border p-4"><CardHeader title="Positions" subtitle={`Valued at the latest stored close · ${fmtDay(d.summary.as_of)}`} /></div><Positions d={d} /></Card>
        <Card className="h-fit p-4"><CardHeader title="Allocation" subtitle="Share of total value" /><Allocation d={d} />
          {d.summary.largest_positions.length > 0 && <p className="mt-3 border-t border-border pt-3 text-[11px] text-muted">Largest: {d.summary.largest_positions.slice(0, 3).map((p) => p.symbol).join(", ")}</p>}
        </Card>
      </div>

      <Card className="p-4">
        <CardHeader title="Record a transaction" subtitle="Dates may be in the past; the whole history is re-checked so cash and holdings never go negative." />
        <TxnForm id={id} onDone={(w) => { setWarnings(w); refresh(); }} />
        {warnings.map((w) => <p key={w} role="status" className="mt-2 text-xs text-warn">{w}</p>)}
      </Card>

      <Card>
        <div className="flex items-center justify-between border-b border-border p-4">
          <CardHeader title="Transactions" subtitle={`${d.transaction_count} entries · average-cost method, fees capitalised into cost basis`} />
          <a href={`/api/v1/portfolios/${id}/transactions.csv`} download className="inline-flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs font-medium hover:border-accent/50"><Download className="h-3.5 w-3.5" />CSV</a>
        </div>
        {err && <p role="alert" className="border-b border-border bg-down/10 px-4 py-2 text-xs text-down">{err}</p>}
        {txns.data && txns.data.items.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead><tr className="border-b border-border text-[11px] uppercase tracking-wide text-muted"><th className="p-3 text-left font-medium">Date</th><th className="p-3 text-left font-medium">Type</th><th className="p-3 text-left font-medium">Symbol</th><th className="p-3 text-right font-medium">Qty</th><th className="p-3 text-right font-medium">Price</th><th className="p-3 text-right font-medium">Fee / amount</th><th className="p-3"><span className="sr-only">Delete</span></th></tr></thead>
              <tbody>{txns.data.items.map((t) => (
                <tr key={t.id} className="border-b border-border/60">
                  <td className="num p-3">{fmtDay(t.day)}</td>
                  <td className="p-3"><Badge tone={t.kind === "buy" || t.kind === "deposit" ? "accent" : "neutral"}>{t.kind}</Badge></td>
                  <td className="p-3 font-medium">{t.symbol ?? "—"}</td>
                  <td className="num p-3 text-right">{t.symbol ? num(t.quantity, 4) : "—"}</td>
                  <td className="num p-3 text-right">{t.symbol ? usd(t.price) : "—"}</td>
                  <td className="num p-3 text-right">{t.symbol ? usd(t.fee) : usd(t.amount)}</td>
                  <td className="p-3 text-right"><button onClick={() => delTxn.mutate(t.id)} aria-label={`Delete ${t.kind} on ${t.day}`} className="rounded p-1 text-muted hover:text-down"><Trash2 className="h-3.5 w-3.5" /></button></td>
                </tr>))}</tbody>
            </table>
          </div>
        ) : <div className="p-6"><EmptyState title="No transactions yet" hint="Start by depositing paper cash." /></div>}
      </Card>

      <div className="flex justify-between text-[11px] text-muted">
        <p>{d.disclaimer}</p>
        <button onClick={() => { if (window.confirm(`Delete portfolio “${d.portfolio.name}” and all its transactions?`)) delPf.mutate(); }} className="text-down hover:underline">Delete portfolio</button>
      </div>
    </div>
  );
}

export default function PortfolioPage() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["portfolios"], queryFn: api.portfolios });
  const [sel, setSel] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [cash, setCash] = useState("10000");
  const [err, setErr] = useState<string | null>(null);
  const items = list.data?.items ?? [];

  useEffect(() => {
    if (items.length && (sel === null || !items.some((p) => p.id === sel))) setSel(items[0]!.id);
    if (!items.length) setSel(null);
  }, [items, sel]);

  const create = useMutation({
    mutationFn: () => {
      const c = Number(cash);
      if (!name.trim()) throw new Error("Name your portfolio");
      if (!Number.isFinite(c) || c < 0) throw new Error("Starting cash must be zero or more");
      return api.createPortfolio({ name: name.trim(), initial_cash: c });
    },
    onSuccess: (p) => { setErr(null); setName(""); setSel(p.id); qc.invalidateQueries({ queryKey: ["portfolios"] }); },
    onError: (e) => setErr((e as Error).message),
  });

  return (
    <>
      <PageHeader title="Paper portfolio" description="Hypothetical positions for learning. Not a brokerage account." actions={<DataBadge meta={list.data?.meta} />} />
      <div role="note" className="mb-5 rounded-lg border border-border bg-surface px-4 py-2.5 text-xs text-muted">{list.data?.disclaimer ?? "Paper portfolio: hypothetical positions for learning. It does not represent real brokerage balances or orders."}</div>
      {list.isError ? <ErrorState message={(list.error as Error).message} onRetry={() => list.refetch()} /> : (
        <div className="space-y-5">
          <Card className="p-4">
            <div className="flex flex-wrap items-end gap-3">
              {items.length > 0 && (
                <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Portfolios">
                  {items.map((p) => (
                    <button key={p.id} role="tab" aria-selected={sel === p.id} onClick={() => setSel(p.id)} className={cn("rounded-lg border px-3 py-1.5 text-sm", sel === p.id ? "border-accent bg-accent/10 font-medium" : "border-border text-muted hover:text-fg")}>
                      {p.name} <span className="num ml-1 text-xs text-muted">{usd(p.total_value, 0)}</span>
                    </button>
                  ))}
                </div>
              )}
              <form onSubmit={(e) => { e.preventDefault(); create.mutate(); }} className="ml-auto flex flex-wrap items-end gap-2">
                <label className="text-[11px] text-muted">New portfolio<input value={name} maxLength={60} onChange={(e) => setName(e.target.value)} placeholder="e.g. Long-term" className={cn(input, "mt-1 block w-44")} /></label>
                <label className="text-[11px] text-muted">Paper cash<input inputMode="decimal" value={cash} onChange={(e) => setCash(e.target.value)} className={cn(input, "mt-1 block w-28")} /></label>
                <button type="submit" disabled={create.isPending} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-accent px-3 text-sm font-medium text-white disabled:opacity-50"><Plus className="h-4 w-4" />Create</button>
              </form>
            </div>
            {err && <p role="alert" className="mt-2 text-xs text-down">{err}</p>}
          </Card>
          {list.isLoading ? <Skeleton className="h-96" /> : sel === null ? <EmptyState title="Create your first paper portfolio" hint="Give it a name and some hypothetical starting cash." /> : <PortfolioView key={sel} id={sel} onDeleted={() => setSel(null)} />}
        </div>
      )}
    </>
  );
}
