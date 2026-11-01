"use client";

import { useQuery } from "@tanstack/react-query";
import { CandlestickChart, LineChart, AreaChart } from "lucide-react";
import { useState } from "react";
import { PriceChart, type ChartMode } from "@/components/charts/PriceChart";
import { Change } from "@/components/shared/Change";
import { DataBadge } from "@/components/shared/DataBadge";
import { Card, EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { cn, usd } from "@/lib/utils";
import { useUI } from "@/stores/ui";
import { useHydrated } from "@/hooks/useHydrated";
import type { RangeKey } from "@/types/api";

export const RANGES: RangeKey[] = ["1W", "1M", "3M", "6M", "1Y", "5Y"];

const MODES: { id: ChartMode; label: string; icon: typeof LineChart }[] = [
  { id: "area", label: "Area", icon: AreaChart },
  { id: "line", label: "Line", icon: LineChart },
  { id: "candles", label: "Candles", icon: CandlestickChart },
];

export function ChartControls({
  range, onRange, mode, onMode, sma, onSma, hideSma = false,
}: { range: RangeKey; onRange: (r: RangeKey) => void; mode: ChartMode; onMode: (m: ChartMode) => void; sma: boolean; onSma: (v: boolean) => void; hideSma?: boolean }) {
  const seg = "flex rounded-lg border border-border bg-bg/60 p-0.5";
  const item = (on: boolean) => cn("rounded-md px-2.5 py-1 text-xs font-medium transition-colors", on ? "bg-accent text-white" : "text-muted hover:text-fg");
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className={seg} role="group" aria-label="Date range">
        {RANGES.map((r) => (
          <button key={r} onClick={() => onRange(r)} aria-pressed={range === r} className={item(range === r)}>{r}</button>
        ))}
      </div>
      <div className={seg} role="group" aria-label="Chart type">
        {MODES.map((m) => (
          <button key={m.id} onClick={() => onMode(m.id)} aria-pressed={mode === m.id} aria-label={m.label} title={m.label} className={item(mode === m.id)}>
            <m.icon className="h-3.5 w-3.5" aria-hidden />
          </button>
        ))}
      </div>
      {!hideSma && (
        <button onClick={() => onSma(!sma)} aria-pressed={sma} className={cn(seg, "px-3 py-1.5 text-xs font-medium", sma ? "border-accent/60 text-accent" : "text-muted hover:text-fg")}>
          SMA 20/50
        </button>
      )}
    </div>
  );
}

export function PriceSection({ symbol }: { symbol: string }) {
  const hydrated = useHydrated();
  const storedRange = useUI((s) => s.chartRange);
  const setRange = useUI((s) => s.setChartRange);
  const range = hydrated ? storedRange : "6M";
  const [mode, setMode] = useState<ChartMode>("area");
  const [sma, setSma] = useState(false);

  const prices = useQuery({ queryKey: ["prices", symbol, range], queryFn: () => api.prices(symbol, range) });
  const bars = prices.data?.bars ?? [];

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <ChartControls range={range} onRange={setRange} mode={mode} onMode={setMode} sma={sma} onSma={setSma} />
        <div className="flex items-center gap-2 text-[11px] text-muted">
          {prices.isFetching && !prices.isLoading && <span>Refreshing…</span>}
          <DataBadge meta={prices.data?.meta} asOf={bars[bars.length - 1]?.day} />
        </div>
      </div>
      {prices.isLoading ? (
        <Skeleton className="h-[340px] w-full" />
      ) : prices.isError ? (
        <ErrorState message={(prices.error as Error).message} onRetry={() => prices.refetch()} />
      ) : bars.length === 0 ? (
        <EmptyState title="No price history in this range" hint="Try a longer range." />
      ) : (
        <PriceChart bars={bars} mode={mode} showSma={sma} />
      )}
      {prices.data && <p className="mt-2 text-[10.5px] text-muted">Daily bars. {prices.data.price_basis}.</p>}
    </div>
  );
}

export function MarketChartCard({ symbols, labels }: { symbols: string[]; labels: Record<string, string> }) {
  const [symbol, setSymbol] = useState(symbols[0] ?? "SPY");
  const quote = useQuery({ queryKey: ["stock", symbol], queryFn: () => api.stock(symbol) });
  const q = quote.data?.quote;

  return (
    <Card className="p-4">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <label htmlFor="chart-symbol" className="sr-only">Instrument</label>
          <select
            id="chart-symbol"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="rounded-lg border border-border bg-bg/60 px-2.5 py-1.5 text-sm font-semibold outline-none focus:border-accent"
          >
            {symbols.map((s) => (
              <option key={s} value={s}>{s} — {labels[s] ?? s}</option>
            ))}
          </select>
        </div>
        {q ? (
          <div className="text-right">
            <div className="num text-2xl font-semibold tracking-tight">{usd(q.price)}</div>
            <Change change={q.change} changePct={q.change_pct} />
          </div>
        ) : (
          <Skeleton className="h-10 w-36" />
        )}
      </div>
      <PriceSection symbol={symbol} />
    </Card>
  );
}
