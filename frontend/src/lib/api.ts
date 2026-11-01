import type { ApiMeta, Bar, MarketOverview, RangeKey, StockRow, Instrument, Quote, PipelineStatus, QualityReport, RunSummary, RunDetail, Watchlist, SearchItem, Technicals, TechParams, ReturnsResponse } from "@/types/api";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}`, { ...init, headers: { Accept: "application/json", ...(init?.headers ?? {}) } });
  } catch {
    throw new ApiError("Cannot reach the MarketPulse API. Is the backend running?", 0);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail || "Request failed", res.status);
  }
  if (res.status === 204) return null as T;
  return (await res.json()) as T;
}

const get = <T,>(path: string) => request<T>(path);

function send<T>(method: string, path: string, body?: unknown, adminToken?: string) {
  return request<T>(path, {
    method,
    headers: { "Content-Type": "application/json", ...(adminToken ? { "X-Admin-Token": adminToken } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

const post = <T,>(path: string, body: unknown, adminToken?: string) => send<T>("POST", path, body, adminToken);

export const api = {
  watchlists: () => get<{ items: Watchlist[] }>("/watchlists"),
  createWatchlist: (name: string) => post<Watchlist>("/watchlists", { name }),
  updateWatchlist: (id: number, body: { name?: string; is_default?: boolean }) => send<Watchlist>("PATCH", `/watchlists/${id}`, body),
  deleteWatchlist: (id: number) => request<null>(`/watchlists/${id}`, { method: "DELETE" }),
  addWatchlistItem: (id: number, symbol: string) => post<Watchlist>(`/watchlists/${id}/items`, { symbol }),
  removeWatchlistItem: (id: number, symbol: string) => send<Watchlist>("DELETE", `/watchlists/${id}/items/${symbol}`),
  reorderWatchlist: (id: number, symbols: string[]) => send<Watchlist>("PUT", `/watchlists/${id}/order`, { symbols }),
  search: (q: string) => get<{ items: SearchItem[] }>(`/search?q=${encodeURIComponent(q)}&limit=8`),
  technicals: (symbol: string, range: string, p: TechParams) =>
    get<Technicals>(
      `/stocks/${symbol}/technicals?range=${range}&sma=${encodeURIComponent(p.sma)}&ema=${encodeURIComponent(p.ema)}&rsi=${p.rsi}&macd=${encodeURIComponent(p.macd)}&bb_window=${p.bb_window}&bb_k=${p.bb_k}`,
    ),
  returns: (symbol: string, range: string) => get<ReturnsResponse>(`/stocks/${symbol}/returns?range=${range}`),
  pipelineStatus: () => get<PipelineStatus>("/pipeline/status"),
  pipelineQuality: () => get<QualityReport>("/pipeline/quality"),
  pipelineRuns: (status?: string) =>
    get<{ total: number; items: RunSummary[] }>(`/pipeline/runs?limit=25${status ? `&status=${status}` : ""}`),
  pipelineRun: (id: number) => get<RunDetail>(`/pipeline/runs/${id}`),
  triggerIngest: (body: { symbols?: string[]; mode: "incremental" | "reindex" }, token?: string) =>
    post<{ run_id: number }>("/pipeline/ingest", body, token),
  triggerBackfill: (body: { symbols: string[]; start: string; end?: string }, token?: string) =>
    post<{ run_id: number }>("/pipeline/backfill", body, token),
  overview: () => get<MarketOverview>("/market/overview"),
  stocks: () => get<{ meta: ApiMeta; items: StockRow[] }>("/stocks"),
  stock: (symbol: string) => get<{ meta: ApiMeta; instrument: Instrument; quote: Quote }>(`/stocks/${symbol}`),
  prices: (symbol: string, range: RangeKey) =>
    get<{ meta: ApiMeta; symbol: string; count: number; price_basis: string; bars: Bar[] }>(
      `/stocks/${symbol}/prices?range=${range}`,
    ),
};
