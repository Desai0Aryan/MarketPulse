"use client";

import { ExternalLink, Minus, TrendingDown, TrendingUp } from "lucide-react";
import Link from "next/link";
import { Badge } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";
import type { NewsArticle } from "@/types/api";

const SENT = {
  positive: { icon: TrendingUp, label: "Positive", cls: "text-up" },
  negative: { icon: TrendingDown, label: "Negative", cls: "text-down" },
  neutral: { icon: Minus, label: "Neutral", cls: "text-muted" },
} as const;

/** Sentiment is shown with an icon AND a word (never colour alone) and always as a baseline estimate. */
export function SentimentChip({ a }: { a: NewsArticle }) {
  if (!a.sentiment) return <span className="text-[11px] text-muted">Not scored</span>;
  const s = SENT[a.sentiment.category];
  const Icon = s.icon;
  return (
    <span title={`${a.sentiment.method} v${a.sentiment.version}, score ${a.sentiment.score}. A noisy word-list baseline.`} className={cn("inline-flex items-center gap-1 text-[11px] font-medium", s.cls)}>
      <Icon className="h-3 w-3" aria-hidden />{s.label} <span className="font-normal text-muted">(baseline)</span>
    </span>
  );
}

export function NewsList({ items, focusSymbol }: { items: NewsArticle[]; focusSymbol?: string }) {
  return (
    <ul className="divide-y divide-border/60">
      {items.map((a) => (
        <li key={a.id} className="p-4">
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
            <span className="font-medium text-fg">{a.source}</span>
            <time dateTime={a.published_at}>{new Date(a.published_at).toLocaleString()}</time>
            {a.simulated && <Badge tone="warn">Simulated demo item</Badge>}
            <SentimentChip a={a} />
          </div>
          <h3 className="mt-1 text-sm font-medium">
            {a.url ? <a href={a.url} target="_blank" rel="noopener noreferrer nofollow" className="hover:text-accent">{a.headline}<ExternalLink className="ml-1 inline h-3 w-3" aria-label="opens the publisher's site" /></a> : a.headline}
          </h3>
          {a.summary && <p className="mt-1 text-xs text-muted">{a.summary}</p>}
          <div className="mt-2 flex flex-wrap gap-1.5">
            {a.symbols.filter((s) => !focusSymbol || s.symbol !== focusSymbol).map((s) => (
              <Link key={s.symbol} href={`/markets/${s.symbol}`} title={`Relevance ${s.relevance}`} className="rounded-full border border-border px-2 py-0.5 text-[11px] hover:border-accent/60">{s.symbol}</Link>
            ))}
            {focusSymbol && a.symbols.find((s) => s.symbol === focusSymbol) && <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[11px]">Relevance {a.symbols.find((s) => s.symbol === focusSymbol)!.relevance}</span>}
          </div>
        </li>
      ))}
    </ul>
  );
}
