"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Sparkline } from "@/components/charts/Sparkline";
import { FavoriteStar } from "@/components/dashboard/Panels";
import { Change } from "@/components/shared/Change";
import { DataBadge, DemoBanner } from "@/components/shared/DataBadge";
import { Badge, Card, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { cn, compact, usd } from "@/lib/utils";
import type { StockRow } from "@/types/api";

type SortKey = "symbol" | "price" | "change_pct" | "volume" | "rel_volume";

export default function MarketsPage() {
  const q = useQuery({ queryKey: ["stocks"], queryFn: api.stocks });
  const [term, setTerm] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "symbol", dir: 1 });

  const rows = useMemo(() => {
    const t = term.trim().toLowerCase();
    const list = (q.data?.items ?? []).filter((s) => !t || s.symbol.toLowerCase().includes(t) || s.name.toLowerCase().includes(t));
    return [...list].sort((a, b) => {
      const av = a[sort.key] ?? 0;
      const bv = b[sort.key] ?? 0;
      return (av < bv ? -1 : av > bv ? 1 : 0) * sort.dir;
    });
  }, [q.data, term, sort]);

  const head = (key: SortKey, label: string, align = "text-right") => (
    <th scope="col" className={cn("px-3 py-2.5 font-medium", align)} aria-sort={sort.key === key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
      <button
        onClick={() => setSort((s) => (s.key === key ? { key, dir: (s.dir * -1) as 1 | -1 } : { key, dir: key === "symbol" ? 1 : -1 }))}
        className="inline-flex items-center gap-1 hover:text-fg"
      >
        {label}
        {sort.key === key && (sort.dir === 1 ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
      </button>
    </th>
  );

  return (
    <>
      <PageHeader title="Markets" description="Every tracked instrument. Click a row to open its detail view." actions={<DataBadge meta={q.data?.meta} />} />
      <DemoBanner meta={q.data?.meta} />
      <Card>
        <div className="flex items-center gap-2 border-b border-border p-3">
          <Search className="h-4 w-4 text-muted" aria-hidden />
          <input
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            aria-label="Filter symbols"
            placeholder="Filter by symbol or company…"
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted"
          />
          <span className="num text-xs text-muted">{rows.length} shown</span>
        </div>

        {q.isError ? (
          <div className="p-4"><ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /></div>
        ) : q.isLoading ? (
          <div className="space-y-2 p-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-11" />)}</div>
        ) : rows.length === 0 ? (
          <EmptyState title="No matches" hint={`Nothing matches “${term}”.`} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead className="border-b border-border text-[11px] uppercase tracking-wider text-muted">
                <tr>
                  <th className="w-10" />
                  {head("symbol", "Symbol", "text-left")}
                  {head("price", "Price")}
                  {head("change_pct", "Change")}
                  {head("volume", "Volume")}
                  {head("rel_volume", "Rel. vol")}
                  <th scope="col" className="px-3 py-2.5 text-right font-medium">30D</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rows.map((s: StockRow) => (
                  <tr key={s.symbol} className="transition-colors hover:bg-elevated/70">
                    <td className="pl-2"><FavoriteStar symbol={s.symbol} /></td>
                    <td className="px-3 py-2.5">
                      <Link href={`/markets/${s.symbol}`} className="block">
                        <div className="flex items-center gap-2 font-semibold">{s.symbol}{s.kind === "index_proxy" && <Badge>Proxy</Badge>}</div>
                        <div className="max-w-[260px] truncate text-[11px] text-muted">{s.name} · {s.exchange}</div>
                      </Link>
                    </td>
                    <td className="num px-3 py-2.5 text-right font-medium">{usd(s.price)}</td>
                    <td className="px-3 py-2.5 text-right"><Change change={s.change} changePct={s.change_pct} showAbs={false} /></td>
                    <td className="num px-3 py-2.5 text-right text-muted">{compact(s.volume)}</td>
                    <td className="num px-3 py-2.5 text-right text-muted">{s.rel_volume?.toFixed(2) ?? "—"}×</td>
                    <td className="px-3 py-2.5"><div className="flex justify-end"><Sparkline data={s.sparkline} width={80} height={26} fill={false} /></div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
