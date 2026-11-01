"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { BreadthCard, IndexCards, MoversCard, RoadmapCard, WatchlistPanel } from "@/components/dashboard/Panels";
import { MarketChartCard } from "@/components/dashboard/MarketChartCard";
import { DataBadge, DemoBanner } from "@/components/shared/DataBadge";
import { ErrorState, PageHeader, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";

export default function DashboardPage() {
  const queryClient = useQueryClient();
  const overview = useQuery({ queryKey: ["overview"], queryFn: api.overview });
  const stocks = useQuery({ queryKey: ["stocks"], queryFn: api.stocks });
  const o = overview.data;
  const all = stocks.data?.items ?? [];
  const labels = Object.fromEntries(all.map((s) => [s.symbol, s.name]));
  const chartSymbols = [...(o?.indexes.map((i) => i.symbol) ?? []), ...all.filter((s) => s.kind === "equity").map((s) => s.symbol)];

  return (
    <>
      <PageHeader
        title="Market overview"
        description="Where the tracked market stands, at a glance."
        actions={
          <div className="flex items-center gap-3">
            <DataBadge meta={o?.meta} asOf={o?.indexes[0]?.as_of} />
            <button
              onClick={() => { overview.refetch(); stocks.refetch(); queryClient.invalidateQueries({ queryKey: ["watchlists"] }); }}
              aria-label="Refresh data"
              className="grid h-9 w-9 place-items-center rounded-lg border border-border bg-surface text-muted hover:border-accent/50 hover:text-fg"
            >
              <RefreshCw className={`h-4 w-4 ${overview.isFetching ? "animate-spin" : ""}`} />
            </button>
          </div>
        }
      />
      <DemoBanner meta={o?.meta} />

      {overview.isError ? (
        <ErrorState message={(overview.error as Error).message} onRetry={() => overview.refetch()} />
      ) : (
        <div className="space-y-5">
          {overview.isLoading || !o ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[158px]" />)}
            </div>
          ) : (
            <IndexCards indexes={o.indexes} />
          )}

          <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
            <div className="xl:col-span-2">
              {chartSymbols.length > 0 ? <MarketChartCard symbols={chartSymbols} labels={labels} /> : <Skeleton className="h-[460px]" />}
            </div>
            <WatchlistPanel />
          </div>

          {o && (
            <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">
              <BreadthCard breadth={o.breadth} />
              <MoversCard title="Top gainers" subtitle="Largest 1-day % gain" rows={o.top_gainers} />
              <MoversCard title="Top losers" subtitle="Largest 1-day % drop" rows={o.top_losers} />
              <MoversCard title="Unusual volume" subtitle="vs. 30-session average" rows={o.unusual_volume} metric="relvol" />
            </div>
          )}

          <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
            <RoadmapCard />
          </div>
        </div>
      )}
    </>
  );
}
