export interface RoadmapPart {
  id: number;
  title: string;
  summary: string;
  done: boolean;
}

/** Build roadmap shown in the UI. Update `done` as each part ships. */
export const ROADMAP: RoadmapPart[] = [
  { id: 1, title: "Foundation & UI shell", summary: "Design system, dashboard, mock provider, API, Docker", done: true },
  { id: 2, title: "Data pipeline", summary: "Ingestion, validation, indicators, PostgreSQL schema", done: false },
  { id: 3, title: "Stock terminal", summary: "Candlesticks, technicals, search, persistent watchlists", done: false },
  { id: 4, title: "Screener & compare", summary: "Filters, correlation matrix, CSV export", done: false },
  { id: 5, title: "Portfolio & alerts", summary: "Paper trading accounting, alert engine", done: false },
  { id: 6, title: "Backtests, news, AI", summary: "Strategy lab, sentiment, grounded research copilot, SSE", done: false },
  { id: 7, title: "Quality & docs", summary: "Tests, CI, benchmarks, README, polish", done: false },
];

export const progress = () => {
  const done = ROADMAP.filter((p) => p.done).length;
  return { done, total: ROADMAP.length, pct: Math.round((done / ROADMAP.length) * 100) };
};
