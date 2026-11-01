export interface ApiMeta {
  provider: string;
  data_class: "live" | "delayed" | "historical" | "simulated";
  demo: boolean;
  notice: string | null;
}

export interface Quote {
  price: number;
  prev_close: number;
  change: number;
  change_pct: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  avg_volume_30d: number;
  rel_volume: number | null;
  high_52w: number;
  low_52w: number;
  as_of: string;
  sparkline: number[];
}

export interface Instrument {
  symbol: string;
  name: string;
  exchange: string;
  currency: string;
  kind: "equity" | "index_proxy";
  sector: string | null;
}

export type StockRow = Instrument & Quote;

export interface Bar {
  day: string;
  open: number;
  high: number;
  low: number;
  close: number;
  adj_close: number;
  volume: number;
}

export interface MoverRow {
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_pct: number;
  rel_volume: number | null;
  sparkline: number[];
  as_of: string;
  sector: string | null;
}

export interface IndexRow extends MoverRow {
  label: string;
  is_proxy: boolean;
}

export interface MarketOverview {
  meta: ApiMeta;
  indexes: IndexRow[];
  breadth: { advancing: number; declining: number; unchanged: number; tracked: number };
  top_gainers: MoverRow[];
  top_losers: MoverRow[];
  unusual_volume: MoverRow[];
  watchlist_default: MoverRow[];
}

export type RangeKey = "1W" | "1M" | "3M" | "6M" | "1Y" | "5Y";

export interface RunSummary {
  id: number;
  mode: "incremental" | "backfill" | "reindex";
  trigger: string;
  provider: string;
  status: "running" | "success" | "partial" | "failed";
  symbols: string[];
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  stats: Record<string, number | Record<string, unknown>>;
  error: string | null;
}

export interface RunDetail extends RunSummary {
  events: { ts: string; level: string; msg: string; symbol: string | null }[];
  rejections: { symbol: string; day: string | null; code: string; severity: string; detail: string }[];
}

export interface FreshnessRow {
  symbol: string;
  bars: number;
  first_day: string | null;
  latest_day: string | null;
  lag_sessions: number | null;
  stale: boolean;
  checkpoint: string | null;
  checkpoint_updated_at: string | null;
  checkpoint_run_id: number | null;
}

export interface PipelineStatus {
  api: string;
  database: { kind: string; ok: boolean };
  provider: { name: string; data_class: string; ok: boolean };
  worker: { busy: boolean; current_run_id: number | null; schedule_minutes: number };
  last_success: RunSummary | null;
  totals: {
    runs: number; success_rate: number | null; inserted: number; updated: number;
    unchanged_duplicates: number; rejected: number; retries: number; avg_duration_ms: number | null;
  };
  freshness: FreshnessRow[];
  reference_day: string;
  latency_series: { run_id: number; duration_ms: number | null; status: string }[];
  recent_events: { ts: string; level: string; msg: string; symbol: string | null; run_id: number }[];
}

export interface QualityReport {
  generated_for: string;
  total_bars: number;
  duplicate_attempts: number;
  rejections_by_reason: Record<string, number>;
  rejected_records: number;
  warnings: number;
  stale_symbols: string[];
  latest_timestamp: string | null;
  ingestion_failures: number;
  missing_values: string;
}

export interface WatchlistItem {
  symbol: string;
  name: string;
  exchange: string | null;
  has_data: boolean;
  price?: number;
  change?: number;
  change_pct?: number;
  sparkline?: number[];
  as_of?: string;
}

export interface Watchlist {
  id: number;
  name: string;
  is_default: boolean;
  symbols: string[];
  items: WatchlistItem[];
}

export interface SearchItem {
  symbol: string;
  name: string;
  exchange: string;
  kind: "equity" | "index_proxy";
  match: string;
}

export type Nums = (number | null)[];

export interface Technicals {
  meta: ApiMeta;
  symbol: string;
  days: string[];
  parameters: { sma: number[]; ema: number[]; rsi: number; macd: number[]; bollinger: number[]; atr: number };
  sma: Record<string, Nums>;
  ema: Record<string, Nums>;
  rsi: Nums;
  macd: { line: Nums; signal: Nums; hist: Nums };
  bollinger: { lower: Nums; mid: Nums; upper: Nums };
  atr: Nums;
  formulas: Record<string, string>;
  disclaimer: string;
  price_basis: string;
}

export interface TechParams {
  sma: string;
  ema: string;
  rsi: number;
  macd: string;
  bb_window: number;
  bb_k: number;
}

export interface ReturnsResponse {
  meta: ApiMeta;
  symbol: string;
  range: string;
  price_basis: string;
  conventions: string;
  stats: {
    sessions: number;
    total_return: number | null;
    annualized_return: number | null;
    annualized_volatility: number | null;
    max_drawdown: number | null;
    best_day: { day: string; return: number | null } | null;
    worst_day: { day: string; return: number | null } | null;
    notes: string[];
  };
  series: { days: string[]; daily_return: Nums; cumulative_return: Nums; drawdown: Nums };
}
