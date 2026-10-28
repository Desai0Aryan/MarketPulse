"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { Bar } from "@/types/api";
import { compact, fmtDay, num } from "@/lib/utils";

export type ChartMode = "area" | "line" | "candles";

interface Props {
  bars: Bar[];
  mode: ChartMode;
  showSma?: boolean;
  height?: number;
}

const M = { top: 12, right: 56, bottom: 22, left: 8 };

function sma(values: number[], window: number): (number | null)[] {
  const out: (number | null)[] = [];
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i]!;
    if (i >= window) sum -= values[i - window]!;
    // No value until a full window exists (no look-ahead, no zero fill).
    out.push(i >= window - 1 ? sum / window : null);
  }
  return out;
}

export function PriceChart({ bars, mode, showSma = false, height = 340 }: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(720);
  const [hover, setHover] = useState<number | null>(null);
  const gid = useId();

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => e && setWidth(Math.max(280, Math.floor(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const geo = useMemo(() => {
    const volH = Math.round(height * 0.18);
    const plotH = height - M.top - M.bottom - volH - 6;
    const plotW = width - M.left - M.right;
    const closes = bars.map((b) => b.close);
    const lo = Math.min(...bars.map((b) => (mode === "candles" ? b.low : b.close)));
    const hi = Math.max(...bars.map((b) => (mode === "candles" ? b.high : b.close)));
    const padv = (hi - lo) * 0.06 || 1;
    const yMin = lo - padv;
    const yMax = hi + padv;
    const x = (i: number) => M.left + (bars.length === 1 ? plotW / 2 : (i / (bars.length - 1)) * plotW);
    const y = (v: number) => M.top + (1 - (v - yMin) / (yMax - yMin)) * plotH;
    const maxVol = Math.max(...bars.map((b) => b.volume), 1);
    const vy = (v: number) => height - M.bottom - (v / maxVol) * volH;
    return { plotW, plotH, yMin, yMax, x, y, vy, volH, closes, sma20: sma(closes, 20), sma50: sma(closes, 50) };
  }, [bars, mode, width, height]);

  if (bars.length === 0) return null;

  const first = bars[0]!;
  const last = bars[bars.length - 1]!;
  const up = last.close >= first.close;
  const tone = up ? "rgb(var(--up))" : "rgb(var(--down))";
  const step = Math.max(1, Math.floor(bars.length / 6));
  const ticks = Array.from({ length: 5 }, (_, i) => geo.yMin + ((geo.yMax - geo.yMin) * i) / 4);
  const barW = Math.max(1, (geo.plotW / bars.length) * 0.62);

  const path = (vals: (number | null)[]) =>
    vals
      .map((v, i) => (v === null ? null : `${i && vals[i - 1] !== null ? "L" : "M"}${geo.x(i).toFixed(1)},${geo.y(v).toFixed(1)}`))
      .filter(Boolean)
      .join(" ");

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - rect.left - M.left;
    const idx = Math.round((px / geo.plotW) * (bars.length - 1));
    setHover(Math.min(bars.length - 1, Math.max(0, idx)));
  };

  const hb = hover !== null ? bars[hover]! : null;
  const closePath = path(geo.closes);

  return (
    <div ref={wrap} className="relative w-full select-none">
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={`Price chart from ${fmtDay(first.day)} to ${fmtDay(last.day)}. Close moved from ${num(first.close)} to ${num(last.close)}.`}
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
        className="touch-pan-y"
      >
        <defs>
          <linearGradient id={gid} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={tone} stopOpacity="0.30" />
            <stop offset="100%" stopColor={tone} stopOpacity="0" />
          </linearGradient>
        </defs>

        {ticks.map((t) => (
          <g key={t}>
            <line x1={M.left} x2={width - M.right} y1={geo.y(t)} y2={geo.y(t)} stroke="rgb(var(--border))" strokeOpacity="0.6" strokeDasharray="2 4" />
            <text x={width - M.right + 8} y={geo.y(t) + 4} className="num" fontSize="10.5" fill="rgb(var(--muted))">
              {num(t)}
            </text>
          </g>
        ))}

        {bars.map((b, i) => (
          <rect
            key={b.day}
            x={geo.x(i) - barW / 2}
            y={geo.vy(b.volume)}
            width={barW}
            height={Math.max(0.5, height - M.bottom - geo.vy(b.volume))}
            fill={b.close >= b.open ? "rgb(var(--up))" : "rgb(var(--down))"}
            opacity="0.28"
          />
        ))}

        {mode === "area" && <path d={`${closePath} L${geo.x(bars.length - 1)},${M.top + geo.plotH} L${geo.x(0)},${M.top + geo.plotH} Z`} fill={`url(#${gid})`} />}
        {mode !== "candles" && <path d={closePath} fill="none" stroke={tone} strokeWidth="1.8" strokeLinejoin="round" />}

        {mode === "candles" &&
          bars.map((b, i) => {
            const c = b.close >= b.open ? "rgb(var(--up))" : "rgb(var(--down))";
            const top = geo.y(Math.max(b.open, b.close));
            return (
              <g key={b.day}>
                <line x1={geo.x(i)} x2={geo.x(i)} y1={geo.y(b.high)} y2={geo.y(b.low)} stroke={c} strokeWidth="1" />
                <rect x={geo.x(i) - barW / 2} y={top} width={barW} height={Math.max(1, Math.abs(geo.y(b.open) - geo.y(b.close)))} fill={c} />
              </g>
            );
          })}

        {showSma && (
          <>
            <path d={path(geo.sma20)} fill="none" stroke="rgb(var(--accent))" strokeWidth="1.3" />
            <path d={path(geo.sma50)} fill="none" stroke="rgb(var(--warn))" strokeWidth="1.3" />
          </>
        )}

        {bars.map((b, i) =>
          i % step === 0 ? (
            <text key={b.day} x={geo.x(i)} y={height - 6} textAnchor="middle" fontSize="10.5" fill="rgb(var(--muted))">
              {fmtDay(b.day, { month: "short", day: "numeric" })}
            </text>
          ) : null,
        )}

        {hb && hover !== null && (
          <g pointerEvents="none">
            <line x1={geo.x(hover)} x2={geo.x(hover)} y1={M.top} y2={height - M.bottom} stroke="rgb(var(--fg))" strokeOpacity="0.35" strokeDasharray="3 3" />
            <circle cx={geo.x(hover)} cy={geo.y(hb.close)} r="4" fill={tone} stroke="rgb(var(--surface))" strokeWidth="2" />
          </g>
        )}
      </svg>

      {showSma && (
        <div className="pointer-events-none absolute left-3 top-2 flex gap-3 text-[10.5px] text-muted">
          <span className="flex items-center gap-1"><i className="h-0.5 w-3 bg-accent" /> SMA 20</span>
          <span className="flex items-center gap-1"><i className="h-0.5 w-3 bg-warn" /> SMA 50</span>
        </div>
      )}

      {hb && hover !== null && (
        <div
          className="pointer-events-none absolute top-2 z-10 rounded-lg border border-border bg-elevated/95 px-3 py-2 text-xs shadow-card backdrop-blur"
          style={{ left: Math.min(Math.max(geo.x(hover) + 12, 8), width - 190) }}
        >
          <div className="mb-1 font-medium">{fmtDay(hb.day)}</div>
          <dl className="num grid grid-cols-[auto_auto] gap-x-4 gap-y-0.5 text-muted">
            <dt>Open</dt><dd className="text-right text-fg">{num(hb.open)}</dd>
            <dt>High</dt><dd className="text-right text-fg">{num(hb.high)}</dd>
            <dt>Low</dt><dd className="text-right text-fg">{num(hb.low)}</dd>
            <dt>Close</dt><dd className="text-right text-fg">{num(hb.close)}</dd>
            <dt>Volume</dt><dd className="text-right text-fg">{compact(hb.volume)}</dd>
          </dl>
        </div>
      )}
    </div>
  );
}
