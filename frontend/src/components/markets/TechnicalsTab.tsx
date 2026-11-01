"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { IndicatorPanel } from "@/components/charts/IndicatorPanel";
import { PriceChart, type ChartMode, type Overlay } from "@/components/charts/PriceChart";
import { ChartControls } from "@/components/dashboard/MarketChartCard";
import { DataBadge } from "@/components/shared/DataBadge";
import { Card, CardHeader, ErrorState, Skeleton } from "@/components/ui/primitives";
import { useHydrated } from "@/hooks/useHydrated";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useUI } from "@/stores/ui";
import type { Bar, TechParams } from "@/types/api";

const DEFAULTS: TechParams = { sma: "20,50,200", ema: "12,26", rsi: 14, macd: "12,26,9", bb_window: 20, bb_k: 2 };
// Colors come from semantic tokens; dash patterns keep lines distinguishable without color.
const PALETTE = ["rgb(var(--accent))", "rgb(var(--warn))", "rgb(var(--teal))", "rgb(var(--muted))"];
const DASHES = [undefined, "5 3", "2 3", "8 3 2 3"];

export function TechnicalsTab({ symbol, bars }: { symbol: string; bars: Bar[] }) {
  const [draft, setDraft] = useState<TechParams>(DEFAULTS);
  const [params, setParams] = useState<TechParams>(DEFAULTS);
  const [on, setOn] = useState<Set<string>>(new Set(["sma20", "sma50", "bb"]));
  const [hover, setHover] = useState<number | null>(null);
  const [mode, setMode] = useState<ChartMode>("line");
  const hydrated = useHydrated();
  const storedRange = useUI((s) => s.chartRange);
  const setRange = useUI((s) => s.setChartRange);

  const tech = useQuery({
    queryKey: ["technicals", symbol, hydrated ? storedRange : "6M", params],
    queryFn: () => api.technicals(symbol, hydrated ? storedRange : "6M", params),
    retry: false,
    placeholderData: (prev) => prev,
  });

  const t = tech.data;
  const aligned = !!t && t.days.length === bars.length && t.days[0] === bars[0]?.day;

  const overlays = useMemo<Overlay[]>(() => {
    if (!t || !aligned) return [];
    const out: Overlay[] = [];
    Object.entries(t.sma).forEach(([w, values], i) => on.has(`sma${w}`) && out.push({ label: `SMA ${w}`, color: PALETTE[i % 4]!, values, dash: DASHES[i % 4] }));
    Object.entries(t.ema).forEach(([w, values], i) => on.has(`ema${w}`) && out.push({ label: `EMA ${w}`, color: PALETTE[(i + 2) % 4]!, values, dash: DASHES[(i + 1) % 4] ?? "1 3" }));
    return out;
  }, [t, aligned, on]);

  const toggle = (k: string) =>
    setOn((s) => {
      const n = new Set(s);
      if (n.has(k)) n.delete(k);
      else n.add(k);
      return n;
    });

  const input = "w-full rounded-lg border border-border bg-bg/60 px-2 py-1.5 text-sm outline-none focus:border-accent";
  const dirty = JSON.stringify(draft) !== JSON.stringify(params);
  const num = (k: keyof TechParams, v: string) => setDraft((d) => ({ ...d, [k]: Number(v) }));

  return (
    <div className="grid gap-5 xl:grid-cols-[1fr_300px]">
      <Card className="p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <ChartControls range={hydrated ? storedRange : "6M"} onRange={setRange} mode={mode} onMode={setMode} sma={false} onSma={() => undefined} hideSma />
          <DataBadge meta={t?.meta} asOf={bars[bars.length - 1]?.day} />
        </div>

        {tech.isError ? (
          <ErrorState message={(tech.error as Error).message} onRetry={() => tech.refetch()} />
        ) : !t || !aligned ? (
          <Skeleton className="h-[560px]" />
        ) : (
          <div className="space-y-2">
            <PriceChart
              bars={bars}
              mode={mode}
              overlays={overlays}
              band={on.has("bb") ? { lower: t.bollinger.lower, upper: t.bollinger.upper, label: `Bollinger (${t.parameters.bollinger[0]}, ${t.parameters.bollinger[1]}σ)` } : undefined}
              hover={hover}
              onHover={setHover}
              height={320}
            />
            <IndicatorPanel
              title={`RSI (${t.parameters.rsi})`}
              days={t.days}
              series={[{ label: "RSI", color: "rgb(var(--accent))", values: t.rsi }]}
              guides={[30, 70]}
              domain={[0, 100]}
              hover={hover}
              onHover={setHover}
              format={(v) => v.toFixed(1)}
              note="30 / 70 are conventional reference levels, not signals."
            />
            <IndicatorPanel
              title={`MACD (${t.parameters.macd.join(", ")})`}
              days={t.days}
              series={[
                { label: "MACD", color: "rgb(var(--accent))", values: t.macd.line },
                { label: "Signal", color: "rgb(var(--warn))", values: t.macd.signal, dash: "5 3" },
              ]}
              hist={t.macd.hist}
              height={130}
              hover={hover}
              onHover={setHover}
            />
          </div>
        )}
        <p className="mt-3 text-[11px] text-muted">{t?.disclaimer ?? "Indicators describe past prices and are not buy or sell signals."}</p>
      </Card>

      <div className="space-y-5">
        <Card>
          <CardHeader title="Overlays" />
          <div className="flex flex-wrap gap-2 px-4 pb-4">
            {t &&
              [
                ...Object.keys(t.sma).map((w) => [`sma${w}`, `SMA ${w}`] as const),
                ...Object.keys(t.ema).map((w) => [`ema${w}`, `EMA ${w}`] as const),
                ["bb", "Bollinger"] as const,
              ].map(([k, label]) => (
                <button key={k} aria-pressed={on.has(k)} onClick={() => toggle(k)} className={cn("rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors", on.has(k) ? "border-accent bg-accent/10 text-fg" : "border-border text-muted hover:text-fg")}>
                  {label}
                </button>
              ))}
          </div>
        </Card>

        <Card>
          <CardHeader title="Parameters" subtitle="Validated server-side; indicators recompute from full history" />
          <form
            className="space-y-3 px-4 pb-4 text-xs text-muted"
            onSubmit={(e) => {
              e.preventDefault();
              setParams(draft);
            }}
          >
            <label className="block">SMA periods (max 4)<input className={cn(input, "mt-1")} value={draft.sma} onChange={(e) => setDraft({ ...draft, sma: e.target.value })} /></label>
            <label className="block">EMA periods (max 4)<input className={cn(input, "mt-1")} value={draft.ema} onChange={(e) => setDraft({ ...draft, ema: e.target.value })} /></label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block">RSI period<input type="number" min={2} max={100} className={cn(input, "mt-1")} value={draft.rsi} onChange={(e) => num("rsi", e.target.value)} /></label>
              <label className="block">MACD f,s,signal<input className={cn(input, "mt-1")} value={draft.macd} onChange={(e) => setDraft({ ...draft, macd: e.target.value })} /></label>
              <label className="block">Bollinger window<input type="number" min={5} max={200} className={cn(input, "mt-1")} value={draft.bb_window} onChange={(e) => num("bb_window", e.target.value)} /></label>
              <label className="block">Bollinger k (σ)<input type="number" min={0.5} max={4} step={0.5} className={cn(input, "mt-1")} value={draft.bb_k} onChange={(e) => num("bb_k", e.target.value)} /></label>
            </div>
            <div className="flex gap-2">
              <button type="submit" disabled={!dirty} className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50">Apply</button>
              <button type="button" onClick={() => { setDraft(DEFAULTS); setParams(DEFAULTS); }} className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-fg hover:border-accent/60">Reset</button>
            </div>
            {tech.isError && <p role="alert" className="text-down">{(tech.error as Error).message}</p>}
          </form>
        </Card>

        {t && (
          <Card>
            <CardHeader title="Formulas" subtitle={`Basis: ${t.price_basis}`} />
            <dl className="space-y-2 px-4 pb-4 text-[11.5px]">
              {Object.entries(t.formulas).map(([k, v]) => (
                <div key={k}><dt className="font-semibold uppercase tracking-wide text-fg">{k}</dt><dd className="text-muted">{v}</dd></div>
              ))}
            </dl>
          </Card>
        )}
      </div>
    </div>
  );
}
