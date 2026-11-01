"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Check, Download, ListPlus } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { FavoriteStar } from "@/components/dashboard/Panels";
import { PriceSection } from "@/components/dashboard/MarketChartCard";
import { ReturnsTab } from "@/components/markets/ReturnsTab";
import { TechnicalsTab } from "@/components/markets/TechnicalsTab";
import { Change } from "@/components/shared/Change";
import { DataBadge, DemoBanner } from "@/components/shared/DataBadge";
import { Badge, Card, CardHeader, EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { useHydrated } from "@/hooks/useHydrated";
import { useCacheUpdater, useWatchlists } from "@/hooks/useWatchlists";
import { api, ApiError } from "@/lib/api";
import { cn, compact, fmtDay, num, usd } from "@/lib/utils";
import { useUI } from "@/stores/ui";

const TABS = ["Overview", "Technicals", "Returns", "Data quality", "News & financials"] as const;
type Tab = (typeof TABS)[number];

function AddToWatchlist({ symbol }: { symbol: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const lists = useWatchlists();
  const update = useCacheUpdater();
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);

  const toggle = async (id: number, has: boolean) => {
    setErr(null);
    try {
      update(has ? await api.removeWatchlistItem(id, symbol) : await api.addWatchlistItem(id, symbol));
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-haspopup="menu" className="inline-flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2 text-xs font-medium hover:border-accent/60">
        <ListPlus className="h-4 w-4" aria-hidden /> Watchlists
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-11 z-20 w-60 animate-pop rounded-xl border border-border bg-surface p-2 shadow-2xl">
          {lists.isLoading && <p className="p-2 text-xs text-muted">Loading…</p>}
          {lists.isError && <p className="p-2 text-xs text-down">{(lists.error as Error).message}</p>}
          {lists.data?.items.map((w) => {
            const has = w.symbols.includes(symbol);
            return (
              <button key={w.id} role="menuitemcheckbox" aria-checked={has} onClick={() => toggle(w.id, has)} className="flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-sm hover:bg-elevated">
                <span className="truncate">{w.name}</span>
                {has && <Check className="h-4 w-4 text-up" aria-label="In this watchlist" />}
              </button>
            );
          })}
          {err && <p role="alert" className="p-2 text-xs text-down">{err}</p>}
          <Link href="/watchlists" className="mt-1 block rounded-lg px-2.5 py-2 text-xs text-accent hover:bg-elevated">Manage watchlists…</Link>
        </div>
      )}
    </div>
  );
}

export default function SymbolPage() {
  const { symbol: raw } = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(raw).toUpperCase();
  const pushRecent = useUI((s) => s.pushRecent);
  const hydrated = useHydrated();
  const range = useUI((s) => s.chartRange);
  const [tab, setTab] = useState<Tab>("Overview");
  const stock = useQuery({ queryKey: ["stock", symbol], queryFn: () => api.stock(symbol), retry: false });
  const prices = useQuery({ queryKey: ["prices", symbol, hydrated ? range : "6M"], queryFn: () => api.prices(symbol, hydrated ? range : "6M"), enabled: tab === "Technicals" });
  const quality = useQuery({ queryKey: ["pipeline-status"], queryFn: api.pipelineStatus, enabled: tab === "Data quality" });

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

  const mine = quality.data?.freshness.find((f) => f.symbol === symbol);

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
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex gap-2">
            <AddToWatchlist symbol={symbol} />
            <a
              href={`/api/v1/stocks/${symbol}/prices.csv?range=${hydrated ? (range === "1W" ? "1M" : range) : "1Y"}`}
              download
              className="inline-flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2 text-xs font-medium hover:border-accent/60"
            >
              <Download className="h-4 w-4" aria-hidden /> CSV
            </a>
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
      </div>

      <div role="tablist" aria-label="Stock sections" className="mb-5 flex gap-1 overflow-x-auto border-b border-border">
        {TABS.map((t) => (
          <button
            key={t}
            role="tab"
            id={`tab-${t}`}
            aria-selected={tab === t}
            aria-controls="tabpanel"
            onClick={() => setTab(t)}
            className={cn("-mb-px whitespace-nowrap border-b-2 px-3.5 py-2.5 text-sm font-medium transition-colors", tab === t ? "border-accent text-fg" : "border-transparent text-muted hover:text-fg")}
          >
            {t}
          </button>
        ))}
      </div>

      <div role="tabpanel" id="tabpanel" aria-labelledby={`tab-${tab}`}>
        {tab === "Overview" && (
          <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
            <Card className="p-4 xl:col-span-2"><PriceSection symbol={symbol} /></Card>
            <Card>
              <CardHeader title="Key statistics" subtitle="Calculated from stored daily bars" />
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
                  <p className="mt-4 text-[11px] leading-relaxed text-muted">Market cap and other provider-supplied fundamentals are unavailable from the demo provider.</p>
                </div>
              ) : (
                <div className="space-y-2 p-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-7" />)}</div>
              )}
            </Card>
          </div>
        )}

        {tab === "Technicals" &&
          (prices.isError ? (
            <ErrorState message={(prices.error as Error).message} onRetry={() => prices.refetch()} />
          ) : !prices.data ? (
            <Skeleton className="h-[640px]" />
          ) : (
            <TechnicalsTab symbol={symbol} bars={prices.data.bars} />
          ))}

        {tab === "Returns" && <ReturnsTab symbol={symbol} />}

        {tab === "Data quality" && (
          <Card className="max-w-2xl">
            <CardHeader title={`${symbol} data quality`} subtitle="From the ingestion pipeline" />
            {quality.isError ? (
              <div className="p-4"><ErrorState message={(quality.error as Error).message} onRetry={() => quality.refetch()} /></div>
            ) : !quality.data ? (
              <Skeleton className="m-4 h-40" />
            ) : !mine ? (
              <EmptyState title="No pipeline record for this symbol" />
            ) : (
              <dl className="divide-y divide-border px-4 pb-3 text-sm">
                {([
                  ["Stored bars", mine.bars.toLocaleString()],
                  ["First bar", mine.first_day ? fmtDay(mine.first_day) : "—"],
                  ["Latest bar", mine.latest_day ? fmtDay(mine.latest_day) : "—"],
                  ["Checkpoint", mine.checkpoint ? `${fmtDay(mine.checkpoint)} (run #${mine.checkpoint_run_id ?? "—"})` : "—"],
                  ["Lag vs reference day", mine.lag_sessions === null ? "—" : `${mine.lag_sessions} sessions`],
                  ["Freshness", mine.stale ? "Stale" : "Fresh"],
                  ["Provider", `${quality.data.provider.name} (${quality.data.provider.data_class})`],
                ] as const).map(([k, v]) => (
                  <div key={k} className="flex justify-between py-2"><dt className="text-muted">{k}</dt><dd className="num font-medium">{v}</dd></div>
                ))}
              </dl>
            )}
            <div className="border-t border-border px-4 py-3 text-xs"><Link href="/data-pipeline" className="text-accent hover:underline">Open the pipeline monitor →</Link></div>
          </Card>
        )}

        {tab === "News & financials" && (
          <Card className="max-w-2xl">
            <EmptyState
              title="Not available in this build"
              hint="The demo provider supplies prices only: no company financials, and no news. Headlines with sentiment arrive in Part 6; statements appear only when a licensed provider is configured."
            />
          </Card>
        )}
      </div>
    </>
  );
}
