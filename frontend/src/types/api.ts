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

// ---- Part 4: screener & compare ----
export interface ScreenField { key: string; label: string; unit: "usd" | "pct" | "x" | "count" | "num" | "bool" | "text"; description: string }
export interface ScreenCatalog { numeric: ScreenField[]; boolean: ScreenField[]; ops: string[]; limits: { max_filters: number; max_page_size: number } }
export type ScreenOp = "gt" | "gte" | "lt" | "lte" | "between" | "eq";
export interface ScreenFilter { field: string; op: ScreenOp; value: number | boolean; value2?: number }
export interface ScreenQuery { filters: ScreenFilter[]; kind: "equity" | "index_proxy" | null; sort: string; descending: boolean; page: number; page_size: number }
export interface ScreenRow {
  symbol: string; name: string; kind: string; sector: string | null; as_of: string;
  price: number | null; change_pct: number | null; volume: number | null; rel_volume: number | null; rsi14: number | null;
  volatility_20d: number | null; dist_52w_high_pct: number | null; dist_52w_low_pct: number | null;
  price_vs_sma50_pct: number | null; price_vs_sma200_pct: number | null; return_1m_pct: number | null; return_3m_pct: number | null;
  sma50_above_sma200: boolean | null;
}
export interface ScreenResult { meta: ApiMeta; total: number; universe: number; page: number; page_size: number; filters: ScreenFilter[]; items: ScreenRow[]; all_symbols: string[] }
export interface SavedScreen { id: number; name: string; definition: ScreenQuery }

export interface WindowStats {
  sessions: number; total_return: number | null; annualized_return: number | null; annualized_volatility: number | null;
  max_drawdown: number | null; best_day: { day: string; return: number | null } | null; worst_day: { day: string; return: number | null } | null; notes: string[];
}
export interface CompareResult {
  meta: ApiMeta; range: string; days: string[]; symbols: string[];
  normalized: Record<string, Nums>; stats: Record<string, WindowStats>;
  correlation: { symbols: string[]; matrix: (number | null)[][]; basis: string };
  coverage: Record<string, { sessions: number; dropped: number }>;
  rolling_correlation?: { pair: [string, string]; window: number; days: string[]; values: Nums };
  notes: string[]; basis: string;
}
export interface CompareRequest { symbols: string[]; range: "1M" | "3M" | "6M" | "1Y" | "5Y" | "MAX"; rolling_pair?: [string, string] | null; rolling_window?: number }

// ---- Part 5: portfolio & alerts ----
export interface PositionRow {
  symbol: string; quantity: number; avg_cost: number; cost_basis: number; price: number | null; price_day: string | null; stale: boolean;
  market_value: number | null; unrealized_pnl: number | null; unrealized_pct: number | null; realized_pnl: number | null; weight: number | null;
}
export interface PortfolioSummary {
  as_of: string; cash: number; positions_market_value: number; total_value: number; invested_capital: number; net_deposits: number;
  unrealized_pnl: number; realized_pnl: number; fees_paid: number; total_pnl_vs_deposits: number; positions: PositionRow[];
  largest_positions: PositionRow[]; allocation: { label: string; value: number | null; weight: number | null }[];
  complete: boolean; missing_prices: string[]; stale_prices: string[]; notes: string[];
}
export interface PortfolioListItem { id: number; name: string; total_value: number; cash: number; unrealized_pnl: number; realized_pnl: number; complete: boolean }
export interface PortfolioDetail {
  meta: ApiMeta; disclaimer: string; portfolio: { id: number; name: string }; summary: PortfolioSummary;
  daily_change: { day: string; change: number; change_pct: number | null } | null; transaction_count: number;
}
export interface TxnRow { id: number; day: string; kind: "deposit" | "withdraw" | "buy" | "sell"; symbol: string | null; quantity: number; price: number; fee: number; amount: number; note: string }
export interface TxnInput { day: string; kind: TxnRow["kind"]; symbol?: string | null; quantity?: number; price?: number; fee?: number; amount?: number; note?: string }
export interface PortfolioPerformance {
  meta: ApiMeta; disclaimer: string; benchmark: string; range: string; days: string[]; value: Nums; net_deposits: Nums; twr_index: Nums; benchmark_index: Nums;
  drawdown: Nums; stats: { twr_return: number; benchmark_return: number; max_drawdown: number; sessions: number } | null; notes: string[]; basis?: string;
}
export interface AlertKindInfo { kind: string; label: string; crossing: boolean }
export interface AlertItem {
  id: number; symbol: string; kind: string; threshold: number; window: number | null; cooldown_days: number; enabled: boolean; note: string;
  status: "active" | "triggered" | "paused"; waiting_for_reset: boolean; last_observed_day: string | null; last_fired_day: string | null; created_day: string | null;
}
export interface AlertInput { symbol: string; kind: string; threshold: number; window?: number | null; cooldown_days: number; note?: string }
export interface AlertEventItem { id: number; alert_id: number; symbol: string; kind: string; observed_day: string; observed_value: number; threshold: number; message: string; evaluated_at: string; read: boolean }
export interface NotificationsResponse { unread: number; items: AlertEventItem[] }
