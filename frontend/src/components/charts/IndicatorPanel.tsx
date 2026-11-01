"use client";

import { useMemo } from "react";
import type { Nums } from "@/types/api";
import { fmtDay } from "@/lib/utils";
import { CHART_MARGIN as M, useWidth } from "./PriceChart";

export interface PanelSeries {
  label: string;
  color: string;
  values: Nums;
  dash?: string;
}

interface Props {
  title: string;
  days: string[];
  series: PanelSeries[];
  /** Histogram bars (e.g. MACD histogram), coloured by sign. */
  hist?: Nums;
  area?: boolean;
  guides?: number[]; // horizontal reference lines (e.g. RSI 30/70)
  domain?: [number, number];
  height?: number;
  hover: number | null;
  onHover: (i: number | null) => void;
  format?: (v: number) => string;
  note?: string;
}

export function IndicatorPanel({ title, days, series, hist, area, guides = [], domain, height = 120, hover, onHover, format = (v) => v.toFixed(2), note }: Props) {
  const { ref, width } = useWidth();
  const n = days.length;
  const plotW = width - M.left - M.right;
  const top = 6;
  const plotH = height - top - 6;

  const [lo, hi] = useMemo<[number, number]>(() => {
    if (domain) return domain;
    const all: number[] = [...guides];
    for (const s of series) for (const v of s.values) if (v !== null) all.push(v);
    if (hist) for (const v of hist) if (v !== null) all.push(v);
    if (all.length === 0) return [0, 1];
    const a = Math.min(...all);
    const b = Math.max(...all);
    const pad = (b - a) * 0.08 || 1;
    return [a - pad, b + pad];
  }, [domain, guides, series, hist]);

  if (n === 0) return null;
  const x = (i: number) => M.left + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const y = (v: number) => top + (1 - (v - lo) / (hi - lo)) * plotH;

  const path = (vals: Nums) => {
    let d = "";
    vals.forEach((v, i) => {
      if (v === null) return;
      d += `${d && vals[i - 1] !== null ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)} `;
    });
    return d.trim();
  };

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const idx = Math.round(((e.clientX - rect.left - M.left) / plotW) * (n - 1));
    onHover(Math.min(n - 1, Math.max(0, idx)));
  };

  const barW = Math.max(1, (plotW / n) * 0.62);
  const zeroY = lo < 0 && hi > 0 ? y(0) : null;
  const shown = hover !== null && hover < n ? hover : n - 1;

  return (
    <div ref={ref} className="w-full select-none">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 px-2 pb-1 text-[11px]">
        <span className="font-semibold text-fg">{title}</span>
        <span className="num flex flex-wrap gap-x-3 text-muted">
          <span>{fmtDay(days[shown]!, { month: "short", day: "numeric" })}</span>
          {series.map((s) => {
            const v = s.values[shown];
            return (
              <span key={s.label} className="flex items-center gap-1">
                <svg width="12" height="4" aria-hidden><line x1="0" x2="12" y1="2" y2="2" stroke={s.color} strokeWidth="2" strokeDasharray={s.dash} /></svg>
                {s.label} <b className="text-fg">{v === null || v === undefined ? "—" : format(v)}</b>
              </span>
            );
          })}
          {hist && <span>Hist <b className="text-fg">{hist[shown] === null || hist[shown] === undefined ? "—" : format(hist[shown]!)}</b></span>}
        </span>
      </div>
      <svg width={width} height={height} role="img" aria-label={`${title} indicator chart`} onPointerMove={onMove} onPointerLeave={() => onHover(null)} className="touch-pan-y">
        {guides.map((g) => (
          <g key={g}>
            <line x1={M.left} x2={width - M.right} y1={y(g)} y2={y(g)} stroke="rgb(var(--muted))" strokeOpacity="0.5" strokeDasharray="3 4" />
            <text x={width - M.right + 8} y={y(g) + 4} fontSize="10.5" fill="rgb(var(--muted))" className="num">{g}</text>
          </g>
        ))}
        {zeroY !== null && <line x1={M.left} x2={width - M.right} y1={zeroY} y2={zeroY} stroke="rgb(var(--border))" />}
        {hist?.map((v, i) =>
          v === null ? null : (
            <rect
              key={days[i]}
              x={x(i) - barW / 2}
              y={Math.min(y(v), y(0 < lo ? lo : 0))}
              width={barW}
              height={Math.max(0.5, Math.abs(y(v) - y(0 < lo ? lo : 0)))}
              fill={v >= 0 ? "rgb(var(--up))" : "rgb(var(--down))"}
              opacity="0.55"
            />
          ),
        )}
        {area && series[0] && <path d={`${path(series[0].values)} L${x(n - 1)},${y(Math.max(lo, Math.min(hi, 0)))} L${x(0)},${y(Math.max(lo, Math.min(hi, 0)))} Z`} fill={series[0].color} opacity="0.15" />}
        {series.map((s) => (
          <path key={s.label} d={path(s.values)} fill="none" stroke={s.color} strokeWidth="1.5" strokeDasharray={s.dash} strokeLinejoin="round" />
        ))}
        {[lo, (lo + hi) / 2, hi].map((t) => (
          <text key={t} x={width - M.right + 8} y={y(t) + 4} fontSize="10" fill="rgb(var(--muted))" className="num" opacity={guides.includes(Math.round(t)) ? 0 : 0.8}>
            {format(t)}
          </text>
        ))}
        {hover !== null && hover < n && <line x1={x(hover)} x2={x(hover)} y1={top} y2={height - 6} stroke="rgb(var(--fg))" strokeOpacity="0.35" strokeDasharray="3 3" pointerEvents="none" />}
      </svg>
      {note && <p className="px-2 text-[10.5px] text-muted">{note}</p>}
    </div>
  );
}
