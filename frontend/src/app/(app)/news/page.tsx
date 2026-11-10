"use client";

import { useQuery } from "@tanstack/react-query";
import { Info } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { NewsList } from "@/components/news/NewsList";
import { Card, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const PAGE = 25;
const input = "h-9 rounded-lg border border-border bg-bg/60 px-2.5 text-sm outline-none focus:border-accent";

function NewsInner() {
  const params = useSearchParams();
  const [symbol, setSymbol] = useState((params.get("symbol") ?? "").toUpperCase());
  const [source, setSource] = useState("");
  const [sentiment, setSentiment] = useState("");
  const [minRel, setMinRel] = useState("0");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [page, setPage] = useState(0);
  const stocks = useQuery({ queryKey: ["stocks"], queryFn: api.stocks });
  const sources = useQuery({ queryKey: ["news-sources"], queryFn: api.newsSources });
  const filters = { symbol, source, sentiment, start, end, min_relevance: Number(minRel), limit: PAGE, offset: page * PAGE };
  const q = useQuery({ queryKey: ["news", filters], queryFn: () => api.news(filters), placeholderData: (p) => p, retry: false });
  const set = <T,>(fn: (v: T) => void) => (v: T) => { fn(v); setPage(0); };
  const d = q.data;
  const pages = d ? Math.max(1, Math.ceil(d.total / PAGE)) : 1;

  return (
    <>
      <PageHeader title="News" description="Headlines with source attribution and a labelled baseline sentiment." />
      {d?.notice && <div role="note" className="mb-3 flex gap-2 rounded-lg border border-warn/40 bg-warn/10 p-3 text-xs"><Info className="h-4 w-4 shrink-0 text-warn" aria-hidden />{d.notice}</div>}
      <div role="note" className="mb-5 rounded-lg border border-border bg-surface px-4 py-2.5 text-xs text-muted">{d?.sentiment_notice ?? "Headline sentiment is noisy and not a reliable predictor of stock performance."}</div>
      <Card className="mb-5 p-4">
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-[11px] text-muted">Symbol
            <select value={symbol} onChange={(e) => set(setSymbol)(e.target.value)} className={cn(input, "mt-1 block w-28")}><option value="">All</option>{(stocks.data?.items ?? []).map((s) => <option key={s.symbol}>{s.symbol}</option>)}</select>
          </label>
          <label className="text-[11px] text-muted">Source
            <select value={source} onChange={(e) => set(setSource)(e.target.value)} className={cn(input, "mt-1 block w-56")}><option value="">All</option>{(sources.data?.items ?? []).map((s) => <option key={s.source} value={s.source}>{s.source} ({s.count})</option>)}</select>
          </label>
          <label className="text-[11px] text-muted">Sentiment
            <select value={sentiment} onChange={(e) => set(setSentiment)(e.target.value)} className={cn(input, "mt-1 block")}><option value="">Any</option><option value="positive">Positive</option><option value="neutral">Neutral</option><option value="negative">Negative</option></select>
          </label>
          <label className="text-[11px] text-muted">Min relevance
            <select value={minRel} onChange={(e) => set(setMinRel)(e.target.value)} disabled={!symbol} title={symbol ? "" : "Choose a symbol first"} className={cn(input, "mt-1 block disabled:opacity-50")}><option value="0">Any</option><option value="0.4">Mentioned (0.4+)</option><option value="0.7">Named in headline (0.7+)</option><option value="1">Ticker in headline (1.0)</option></select>
          </label>
          <label className="text-[11px] text-muted">From<input type="date" value={start} onChange={(e) => set(setStart)(e.target.value)} className={cn(input, "mt-1 block")} /></label>
          <label className="text-[11px] text-muted">To<input type="date" value={end} onChange={(e) => set(setEnd)(e.target.value)} className={cn(input, "mt-1 block")} /></label>
          <button onClick={() => { setSymbol(""); setSource(""); setSentiment(""); setMinRel("0"); setStart(""); setEnd(""); setPage(0); }} className="h-9 rounded-lg border border-border px-3 text-sm text-muted hover:text-fg">Reset</button>
        </div>
      </Card>
      <Card>
        {q.isError ? <div className="p-4"><ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /></div>
          : !d ? <Skeleton className="m-4 h-64" />
          : d.items.length === 0 ? <div className="p-6"><EmptyState title="No articles match" hint="Loosen a filter or reset them." /></div>
          : <NewsList items={d.items} focusSymbol={symbol || undefined} />}
        {d && d.total > PAGE && (
          <div className="flex items-center justify-between border-t border-border p-3 text-xs text-muted">
            <span>{d.total} articles · page {page + 1} of {pages}</span>
            <div className="flex gap-2">
              <button disabled={page === 0} onClick={() => setPage(page - 1)} className="rounded-lg border border-border px-3 py-1 disabled:opacity-40">Previous</button>
              <button disabled={page + 1 >= pages} onClick={() => setPage(page + 1)} className="rounded-lg border border-border px-3 py-1 disabled:opacity-40">Next</button>
            </div>
          </div>
        )}
      </Card>
      <p className="mt-3 text-[11px] text-muted">{d?.attribution} Sentiment method: {d?.sentiment_method ?? "lexicon-baseline"}.</p>
    </>
  );
}

export default function NewsPage() {
  return <Suspense fallback={<Skeleton className="h-96" />}><NewsInner /></Suspense>;
}
