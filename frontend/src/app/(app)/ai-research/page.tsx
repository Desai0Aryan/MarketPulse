"use client";

import { useQuery } from "@tanstack/react-query";
import { BookOpen, Bot, Check, Copy, ExternalLink, RotateCw, Send, ShieldCheck, Trash2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Badge, Card, CardHeader, PageHeader } from "@/components/ui/primitives";
import { api, streamChat } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { AiAnswer } from "@/types/api";

type Turn = {
  id: number;
  question: string;
  status: "streaming" | "done" | "error";
  error?: string;
  meta?: Pick<AiAnswer, "intent" | "symbols" | "range" | "tools" | "refused">;
  facts: string[];
  explanation?: { text: string; mode: AiAnswer["explanation_mode"]; llm_error: string | null };
  sources: AiAnswer["sources"];
  caveats: string[];
};

const KEY = "mp-ai-history-v1";
const load = (): Turn[] => {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Turn[]).filter((t) => t.status === "done") : [];
  } catch {
    return []; // storage can be unavailable (private mode); the page works without history
  }
};
const save = (turns: Turn[]) => {
  try { localStorage.setItem(KEY, JSON.stringify(turns.filter((t) => t.status === "done").slice(-30))); } catch { /* ignore */ }
};
const plain = (t: Turn) =>
  [`Q: ${t.question}`, "", "Facts (from stored data):", ...t.facts.map((f) => `- ${f}`), t.explanation ? `\nExplanation (${t.explanation.mode}): ${t.explanation.text}` : "", t.sources.length ? `\nSources: ${t.sources.map((s) => `${s.label}${s.as_of ? ` (as of ${s.as_of})` : ""}`).join("; ")}` : "", `\n${t.caveats.join(" ")}`].join("\n");

function TurnView({ t, onRetry }: { t: Turn; onRetry: (q: string) => void }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(plain(t)); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard blocked */ }
  };
  return (
    <div className="space-y-3">
      <div className="ml-auto max-w-[85%] rounded-2xl rounded-tr-sm bg-accent px-4 py-2.5 text-sm text-white">{t.question}</div>
      <Card className="max-w-[95%] p-4">
        <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] text-muted">
          <Bot className="h-4 w-4 text-accent" aria-hidden /><span className="font-medium text-fg">Research copilot</span>
          {t.meta?.symbols.map((s) => <Link key={s} href={`/markets/${s}`} className="rounded-full border border-border px-2 py-0.5 hover:border-accent/60">{s}</Link>)}
          {t.meta?.range.as_of && <span>Data as of {t.meta.range.as_of} · up to {t.meta.range.sessions_requested} sessions</span>}
          {t.meta?.refused && <Badge tone="warn">No predictions or advice</Badge>}
        </div>
        {t.status === "error" ? (
          <p role="alert" className="text-sm text-down">{t.error}</p>
        ) : (
          <>
            {t.facts.length > 0 && (
              <section aria-label="Facts from stored data">
                <h3 className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted"><ShieldCheck className="h-3.5 w-3.5" aria-hidden />Facts from stored data</h3>
                <ul className="space-y-1.5 text-sm">{t.facts.map((f, i) => <li key={i} className="num">{f}</li>)}</ul>
              </section>
            )}
            {t.status === "streaming" && <p className="mt-2 text-xs text-muted" role="status">Working<span className="animate-pulse">…</span></p>}
            {t.explanation && (
              <section aria-label="Explanation" className="mt-3 rounded-lg bg-surface p-3">
                <h3 className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted"><BookOpen className="h-3.5 w-3.5" aria-hidden />Explanation <Badge tone={t.explanation.mode === "model-generated" ? "warn" : "neutral"}>{t.explanation.mode === "model-generated" ? "Model-generated" : "General background"}</Badge></h3>
                <p className="text-sm">{t.explanation.text}</p>
                {t.explanation.llm_error && <p className="mt-1 text-[11px] text-muted">The language model was unavailable ({t.explanation.llm_error}); showing the built-in explanation.</p>}
              </section>
            )}
            {t.sources.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2" aria-label="Sources">
                {t.sources.map((s, i) => (
                  <Link key={i} href={s.href} className="inline-flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs hover:border-accent/60">
                    <ExternalLink className="h-3 w-3 text-muted" aria-hidden />{s.label}{s.as_of && <span className="text-muted">· {s.as_of}</span>}
                  </Link>
                ))}
              </div>
            )}
            {t.meta && t.meta.tools.length > 0 && <p className="mt-2 text-[10.5px] text-muted">Tools used: {t.meta.tools.map((x) => `${x.tool}${x.ok ? "" : " (failed)"}`).join(", ")}</p>}
            {t.caveats.length > 0 && <ul className="mt-2 space-y-0.5 text-[10.5px] text-muted">{t.caveats.map((c) => <li key={c}>{c}</li>)}</ul>}
          </>
        )}
        {t.status !== "streaming" && (
          <div className="mt-3 flex gap-2 border-t border-border pt-2">
            <button onClick={copy} className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-muted hover:text-fg">{copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}{copied ? "Copied" : "Copy"}</button>
            <button onClick={() => onRetry(t.question)} className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-muted hover:text-fg"><RotateCw className="h-3.5 w-3.5" />Retry</button>
          </div>
        )}
      </Card>
    </div>
  );
}

export default function AiResearchPage() {
  const status = useQuery({ queryKey: ["ai-status"], queryFn: api.aiStatus, staleTime: 60_000 });
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const nextId = useRef(1);

  useEffect(() => { const h = load(); setTurns(h); nextId.current = h.reduce((m, t) => Math.max(m, t.id), 0) + 1; setHydrated(true); }, []);
  useEffect(() => { if (hydrated) save(turns); }, [turns, hydrated]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [turns]);

  const ask = useCallback(async (question: string) => {
    const q = question.trim();
    if (!q || busy) return;
    const id = nextId.current++;
    const patch = (fn: (t: Turn) => Turn) => setTurns((cur) => cur.map((t) => (t.id === id ? fn(t) : t)));
    setTurns((cur) => [...cur, { id, question: q, status: "streaming", facts: [], sources: [], caveats: [] }]);
    setText("");
    setBusy(true);
    try {
      await streamChat(q, {
        onMeta: (meta) => patch((t) => ({ ...t, meta })),
        onFact: (f) => patch((t) => ({ ...t, facts: [...t.facts, f] })),
        onExplanation: (explanation) => patch((t) => ({ ...t, explanation })),
        onSources: ({ sources, caveats }) => patch((t) => ({ ...t, sources, caveats })),
      });
      patch((t) => ({ ...t, status: "done" }));
    } catch (e) {
      patch((t) => ({ ...t, status: "error", error: (e as Error).message }));
    } finally {
      setBusy(false);
    }
  }, [busy]);

  return (
    <>
      <PageHeader title="Research copilot" description="Ask about the platform's stored data. Answers are built from validated tools, not guesses."
        actions={<Badge tone={status.data?.llm_enabled ? "warn" : "neutral"}>{status.data ? (status.data.llm_enabled ? "LLM-assisted explanations" : "Deterministic mode (no LLM key)") : "…"}</Badge>} />
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-4">
        <div className="space-y-4 xl:col-span-3">
          <div className="min-h-[360px] space-y-6" aria-live="polite">
            {turns.length === 0 && (
              <Card className="p-6 text-sm">
                <p className="font-medium">What can I answer?</p>
                <p className="mt-1 text-muted">Price moves, returns, volatility and drawdown, RSI/MACD/moving averages, comparisons and correlation, your watchlists and saved screens, stored news, and data-pipeline quality. I can’t predict prices or tell you what to buy or sell.</p>
              </Card>
            )}
            {turns.map((t) => <TurnView key={t.id} t={t} onRetry={ask} />)}
            <div ref={endRef} />
          </div>
          <form onSubmit={(e) => { e.preventDefault(); ask(text); }} className="sticky bottom-3 flex gap-2 rounded-xl border border-border bg-card p-2 shadow-lg">
            <input value={text} onChange={(e) => setText(e.target.value)} maxLength={500} aria-label="Ask a question" placeholder="e.g. Compare NVDA and AMD over the last 90 trading days" className="h-10 min-w-0 flex-1 bg-transparent px-3 text-sm outline-none" />
            {turns.length > 0 && <button type="button" onClick={() => setTurns([])} aria-label="Clear chat history" className="grid h-10 w-10 place-items-center rounded-lg text-muted hover:text-down"><Trash2 className="h-4 w-4" /></button>}
            <button type="submit" disabled={busy || !text.trim()} className="inline-flex h-10 items-center gap-1.5 rounded-lg bg-accent px-4 text-sm font-medium text-white disabled:opacity-50"><Send className="h-4 w-4" />Ask</button>
          </form>
        </div>
        <Card className="h-fit p-4">
          <CardHeader title="Suggested questions" />
          <ul className="space-y-1.5">
            {(status.data?.suggested ?? []).map((s) => <li key={s}><button disabled={busy} onClick={() => ask(s)} className="w-full rounded-lg border border-border px-3 py-2 text-left text-xs hover:border-accent/60 disabled:opacity-50">{s}</button></li>)}
          </ul>
          <p className={cn("mt-4 border-t border-border pt-3 text-[11px] text-muted")}>{status.data?.notice} Chat history is kept only in this browser. Not investment advice.</p>
        </Card>
      </div>
    </>
  );
}
