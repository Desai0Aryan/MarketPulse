"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { IndicatorPanel } from "@/components/charts/IndicatorPanel";
import { DataBadge } from "@/components/shared/DataBadge";
import { Card, CardHeader, ErrorState, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { cn, fmtDay, pct, trendClass } from "@/lib/utils";

const RANGES = ["1M", "3M", "6M", "1Y", "5Y", "MAX"] as const;
const p = (v: number | null | undefined, digits = 2) => (v === null || v === undefined ? "Unavailable" : pct(v * 100, digits));

export function ReturnsTab({ symbol }: { symbol: string }) {
  const [range, setRange] = useState<(typeof RANGES)[number]>("1Y");
  const [hover, setHover] = useState<number | null>(null);
  const q = useQuery({ queryKey: ["returns", symbol, range], queryFn: () => api.returns(symbol, range) });
  const r = q.data;

  const stat = (label: string, value: string, tone?: string, hint?: string) => (
    <div key={label} className="bg-surface p-4">
      <dt className="text-[11px] text-muted">{label}</dt>
      <dd className={cn("num mt-1 text-xl font-semibold", tone)}>{value}</dd>
      {hint && <div className="mt-0.5 text-[10.5px] text-muted">{hint}</div>}
    </div>
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex rounded-lg border border-border bg-bg/60 p-0.5" role="group" aria-label="Returns window">
          {RANGES.map((x) => (
            <button key={x} aria-pressed={range === x} onClick={() => setRange(x)} className={cn("rounded-md px-2.5 py-1 text-xs font-medium", range === x ? "bg-accent text-white" : "text-muted hover:text-fg")}>{x}</button>
          ))}
        </div>
        <DataBadge meta={r?.meta} />
      </div>

      {q.isError ? (
        <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} />
      ) : !r ? (
        <Skeleton className="h-72" />
      ) : (
        <>
          <Card>
            <dl className="grid grid-cols-2 gap-px bg-border/50 p-px lg:grid-cols-3 xl:grid-cols-6">
              {stat("Total return", p(r.stats.total_return), trendClass(r.stats.total_return ?? 0))}
              {stat("Annualised return", p(r.stats.annualized_return), undefined, r.stats.annualized_return === null ? "Needs ≥ 252 sessions" : "252 sessions/yr")}
              {stat("Annualised volatility", p(r.stats.annualized_volatility, 1), undefined, "σ(daily) × √252")}
              {stat("Max drawdown", p(r.stats.max_drawdown), "text-down", "Peak to trough")}
              {stat("Best day", p(r.stats.best_day?.return), "text-up", r.stats.best_day ? fmtDay(r.stats.best_day.day) : undefined)}
              {stat("Worst day", p(r.stats.worst_day?.return), "text-down", r.stats.worst_day ? fmtDay(r.stats.worst_day.day) : undefined)}
            </dl>
          </Card>
          <Card className="p-4">
            <CardHeader title="Performance" subtitle={`${r.stats.sessions} sessions · ${r.price_basis}`} />
            <div className="space-y-2">
              <IndicatorPanel
                title="Cumulative return"
                days={r.series.days}
                series={[{ label: "Return", color: "rgb(var(--accent))", values: r.series.cumulative_return.map((v) => (v === null ? null : v * 100)) }]}
                area
                height={160}
                hover={hover}
                onHover={setHover}
                format={(v) => `${v.toFixed(1)}%`}
              />
              <IndicatorPanel
                title="Drawdown from peak"
                days={r.series.days}
                series={[{ label: "Drawdown", color: "rgb(var(--down))", values: r.series.drawdown.map((v) => (v === null ? null : v * 100)) }]}
                area
                height={120}
                hover={hover}
                onHover={setHover}
                format={(v) => `${v.toFixed(1)}%`}
              />
            </div>
            {r.stats.notes.length > 0 && (
              <ul className="mt-3 list-disc space-y-0.5 pl-5 text-[11px] text-muted">{r.stats.notes.map((n) => <li key={n}>{n}</li>)}</ul>
            )}
            <p className="mt-3 text-[11px] text-muted">{r.conventions} Past performance does not predict future results.</p>
          </Card>
        </>
      )}
    </div>
  );
}
