"use client";

import { Star } from "lucide-react";
import Link from "next/link";
import { Sparkline } from "@/components/charts/Sparkline";
import { Change } from "@/components/shared/Change";
import { Badge, Card, CardHeader, EmptyState, ErrorState, ProgressBar, Skeleton } from "@/components/ui/primitives";
import { ROADMAP, progress } from "@/lib/roadmap";
import { cn, fmtDay, num, usd } from "@/lib/utils";
import { useDefaultWatchlist, useWatchlists } from "@/hooks/useWatchlists";
import type { IndexRow, MarketOverview, MoverRow } from "@/types/api";

export function IndexCards({ indexes }: { indexes: IndexRow[] }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {indexes.map((i) => (
        <Link key={i.symbol} href={`/markets/${i.symbol}`} className="group">
          <Card className="p-4 transition-colors group-hover:border-accent/50">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-sm font-semibold">{i.label}</div>
                <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted">
                  <span>via {i.symbol}</span>
                  <Badge tone="neutral">Proxy</Badge>
                </div>
              </div>
              <Sparkline data={i.sparkline} width={84} height={30} />
            </div>
            <div className="num mt-3 text-[26px] font-semibold leading-none tracking-tight">{num(i.price)}</div>
            <div className="mt-2 flex items-center justify-between">
              <Change change={i.change} changePct={i.change_pct} />
            </div>
            <div className="num mt-3 flex items-center justify-between border-t border-border pt-2 text-[11px] text-muted">
              <span>Prev close {num(i.price - i.change)}</span>
              <span>{fmtDay(i.as_of, { month: "short", day: "numeric" })}</span>
            </div>
          </Card>
        </Link>
      ))}
    </div>
  );
}

export function FavoriteStar({ symbol }: { symbol: string }) {
  const { has, toggle, watchlist, isLoading } = useDefaultWatchlist();
  const on = has(symbol);
  const label = !watchlist
    ? "Watchlist unavailable"
    : on
      ? `Remove ${symbol} from ${watchlist.name}`
      : `Add ${symbol} to ${watchlist.name}`;
  return (
    <button
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        toggle.mutate({ symbol, remove: on });
      }}
      disabled={!watchlist || isLoading || toggle.isPending}
      aria-label={label}
      title={label}
      aria-pressed={on}
      className="grid h-7 w-7 place-items-center rounded-md text-muted transition-colors hover:bg-elevated disabled:opacity-50"
    >
      <Star className={cn("h-4 w-4 transition-transform", on && "scale-110 fill-warn text-warn")} aria-hidden />
    </button>
  );
}

export function WatchlistPanel() {
  const q = useWatchlists();
  const wl = q.data?.items.find((w) => w.is_default) ?? q.data?.items[0];
  return (
    <Card className="flex h-full flex-col">
      <CardHeader
        title={wl ? wl.name : "Watchlist"}
        subtitle="Your default watchlist"
        action={<Link href="/watchlists" className="text-xs font-medium text-accent hover:underline">Manage</Link>}
      />
      {q.isError ? (
        <div className="p-4"><ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /></div>
      ) : q.isLoading ? (
        <div className="space-y-2 p-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}</div>
      ) : !wl || wl.items.length === 0 ? (
        <EmptyState title="Your watchlist is empty" hint="Star any symbol on the Markets page to pin it here." icon={<Star className="h-6 w-6" />} />
      ) : (
        <ul className="divide-y divide-border px-2 pb-2">
          {wl.items.map((s) => (
            <li key={s.symbol}>
              <Link href={`/markets/${s.symbol}`} className="flex items-center gap-3 rounded-lg px-2 py-2.5 transition-colors hover:bg-elevated">
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold">{s.symbol}</div>
                  <div className="truncate text-[11px] text-muted">{s.name}</div>
                </div>
                {s.has_data && s.sparkline ? (
                  <>
                    <Sparkline data={s.sparkline} width={64} height={24} fill={false} />
                    <div className="w-24 text-right">
                      <div className="num text-sm font-medium">{usd(s.price!)}</div>
                      <Change change={s.change!} changePct={s.change_pct!} showAbs={false} className="text-xs" />
                    </div>
                  </>
                ) : (
                  <span className="text-xs text-muted">No data yet</span>
                )}
                <FavoriteStar symbol={s.symbol} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function BreadthCard({ breadth }: { breadth: MarketOverview["breadth"] }) {
  const t = breadth.tracked || 1;
  const a = (breadth.advancing / t) * 100;
  const d = (breadth.declining / t) * 100;
  return (
    <Card>
      <CardHeader title="Market breadth" subtitle={`Across ${breadth.tracked} tracked stocks (not the full market)`} />
      <div className="px-4 pb-4">
        <div className="flex h-2.5 overflow-hidden rounded-full bg-elevated" role="img" aria-label={`${breadth.advancing} advancing, ${breadth.declining} declining, ${breadth.unchanged} unchanged`}>
          <div className="bg-up" style={{ width: `${a}%` }} />
          <div className="bg-muted/40" style={{ width: `${100 - a - d}%` }} />
          <div className="bg-down" style={{ width: `${d}%` }} />
        </div>
        <div className="num mt-3 flex justify-between text-xs">
          <span className="text-up">▲ {breadth.advancing} advancing</span>
          <span className="text-muted">{breadth.unchanged} flat</span>
          <span className="text-down">{breadth.declining} declining ▼</span>
        </div>
      </div>
    </Card>
  );
}

export function MoversCard({ title, subtitle, rows, metric }: { title: string; subtitle: string; rows: MoverRow[]; metric?: "relvol" }) {
  return (
    <Card>
      <CardHeader title={title} subtitle={subtitle} />
      {rows.length === 0 ? (
        <EmptyState title="No data" />
      ) : (
        <ul className="px-2 pb-2">
          {rows.map((r) => (
            <li key={r.symbol}>
              <Link href={`/markets/${r.symbol}`} className="flex items-center justify-between gap-3 rounded-lg px-2 py-2 hover:bg-elevated">
                <div className="min-w-0">
                  <div className="text-sm font-semibold">{r.symbol}</div>
                  <div className="truncate text-[11px] text-muted">{r.name}</div>
                </div>
                <div className="text-right">
                  {metric === "relvol" ? (
                    <div className="num text-sm font-medium text-accent">{r.rel_volume?.toFixed(2)}× avg vol</div>
                  ) : (
                    <Change change={r.change} changePct={r.change_pct} showAbs={false} />
                  )}
                  <div className="num text-[11px] text-muted">{usd(r.price)}</div>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function RoadmapCard() {
  const p = progress();
  return (
    <Card>
      <CardHeader title="Project roadmap" subtitle={`${p.pct}% complete · ${p.done} of ${p.total} parts shipped`} />
      <div className="px-4 pb-4">
        <ProgressBar value={p.pct} className="mb-4" />
        <ol className="space-y-2.5">
          {ROADMAP.map((r) => (
            <li key={r.id} className="flex items-start gap-3">
              <span className={cn("mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full text-[10px] font-bold", r.done ? "bg-up/15 text-up" : "bg-elevated text-muted")}>
                {r.done ? "✓" : r.id}
              </span>
              <div className="min-w-0">
                <div className={cn("text-[13px] font-medium", !r.done && "text-muted")}>{r.title}</div>
                <div className="text-[11px] text-muted">{r.summary}</div>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </Card>
  );
}
