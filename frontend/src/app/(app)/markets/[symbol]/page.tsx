"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect } from "react";
import { FavoriteStar } from "@/components/dashboard/Panels";
import { PriceSection } from "@/components/dashboard/MarketChartCard";
import { Change } from "@/components/shared/Change";
import { DataBadge, DemoBanner } from "@/components/shared/DataBadge";
import { Badge, Card, CardHeader, ErrorState, Skeleton } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { compact, num, usd } from "@/lib/utils";
import { useUI } from "@/stores/ui";

export default function SymbolPage() {
  const { symbol: raw } = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(raw).toUpperCase();
  const pushRecent = useUI((s) => s.pushRecent);
  const stock = useQuery({ queryKey: ["stock", symbol], queryFn: () => api.stock(symbol), retry: false });

  useEffect(() => {
    if (stock.data) pushRecent(symbol);
  }, [stock.data, symbol, pushRecent]);

  if (stock.isError) {
    const notFound = stock.error instanceof ApiError && stock.error.status === 404;
    return (
      <div className="space-y-4">
        <Link href="/markets" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft className="h-4 w-4" /> Markets</Link>
        <ErrorState message={notFound ? `“${symbol}” is not a tracked symbol.` : (stock.error as Error).message} onRetry={notFound ? undefined : () => stock.refetch()} />
      </div>
    );
  }

  const q = stock.data?.quote;
  const inst = stock.data?.instrument;
  const range52 = q ? ((q.price - q.low_52w) / (q.high_52w - q.low_52w || 1)) * 100 : 0;
  const fromHigh = q ? ((q.price - q.high_52w) / q.high_52w) * 100 : 0;

  const metrics: [string, string][] = q
    ? [
        ["Previous close", usd(q.prev_close)],
        ["Open", usd(q.open)],
        ["Day range", `${num(q.low)} – ${num(q.high)}`],
        ["Volume", compact(q.volume)],
        ["Avg volume (30D)", compact(q.avg_volume_30d)],
        ["Relative volume", q.rel_volume ? `${q.rel_volume.toFixed(2)}×` : "—"],
        ["52-week high", usd(q.high_52w)],
        ["52-week low", usd(q.low_52w)],
        ["From 52W high", `${num(fromHigh)}%`],
      ]
    : [];

  return (
    <>
      <Link href="/markets" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft className="h-4 w-4" /> Markets</Link>
      <DemoBanner meta={stock.data?.meta} />

      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          {inst ? (
            <>
              <div className="flex items-center gap-2">
                <h1 className="text-3xl font-semibold tracking-tight">{inst.symbol}</h1>
                <FavoriteStar symbol={inst.symbol} />
                <Badge>{inst.exchange}</Badge>
                {inst.kind === "index_proxy" && <Badge tone="accent">Index proxy</Badge>}
              </div>
              <p className="mt-1 text-sm text-muted">{inst.name} · {inst.currency}{inst.sector ? ` · ${inst.sector}` : ""}</p>
            </>
          ) : (
            <Skeleton className="h-14 w-72" />
          )}
        </div>
        {q ? (
          <div className="text-right">
            <div className="num text-4xl font-semibold tracking-tight">{usd(q.price)}</div>
            <div className="mt-1 flex items-center justify-end gap-3">
              <Change change={q.change} changePct={q.change_pct} />
              <DataBadge meta={stock.data?.meta} asOf={q.as_of} />
            </div>
          </div>
        ) : (
          <Skeleton className="h-16 w-52" />
        )}
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <Card className="p-4 xl:col-span-2"><PriceSection symbol={symbol} /></Card>

        <Card>
          <CardHeader title="Key statistics" subtitle="Calculated from daily bars" />
          {q ? (
            <div className="px-4 pb-4">
              <dl className="divide-y divide-border">
                {metrics.map(([k, v]) => (
                  <div key={k} className="flex justify-between py-2 text-sm">
                    <dt className="text-muted">{k}</dt>
                    <dd className="num font-medium">{v}</dd>
                  </div>
                ))}
              </dl>
              <div className="mt-3">
                <div className="mb-1 flex justify-between text-[11px] text-muted"><span>52W low</span><span>52W high</span></div>
                <div className="relative h-1.5 rounded-full bg-elevated" role="img" aria-label={`Price is ${Math.round(range52)}% of the way from the 52-week low to the high`}>
                  <div className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface bg-accent" style={{ left: `${Math.min(100, Math.max(0, range52))}%` }} />
                </div>
              </div>
              <p className="mt-4 text-[11px] leading-relaxed text-muted">
                Technical indicators (RSI, MACD, Bollinger Bands, ATR), returns, drawdown and the full terminal tabs arrive in Part 3.
              </p>
            </div>
          ) : (
            <div className="space-y-2 p-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-7" />)}</div>
          )}
        </Card>
      </div>
    </>
  );
}
