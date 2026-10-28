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
