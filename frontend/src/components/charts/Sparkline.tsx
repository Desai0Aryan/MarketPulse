import { useId } from "react";

interface Props {
  data: number[];
  width?: number;
  height?: number;
  /** Tone follows overall direction unless overridden. */
  positive?: boolean;
  fill?: boolean;
}

export function Sparkline({ data, width = 96, height = 32, positive, fill = true }: Props) {
  const id = useId();
  if (data.length < 2) return <div style={{ width, height }} aria-hidden />;
  const up = positive ?? data[data.length - 1]! >= data[0]!;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const pad = 2;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = pad + (1 - (v - min) / span) * (height - pad * 2);
    return [x, y] as const;
  });
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${line} L${width},${height} L0,${height} Z`;
  const color = up ? "rgb(var(--up))" : "rgb(var(--down))";
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`30-day trend, ${up ? "up" : "down"}`}>
      <defs>
        <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {fill && <path d={area} fill={`url(#${id})`} />}
      <path d={line} fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
