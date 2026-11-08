import type { ApiMeta, Bar, MarketOverview, RangeKey, StockRow, Instrument, Quote, PipelineStatus, QualityReport, RunSummary, RunDetail, Watchlist, SearchItem, Technicals, TechParams, ReturnsResponse, ScreenCatalog, ScreenQuery, ScreenResult, SavedScreen, CompareRequest, CompareResult, PortfolioListItem, PortfolioDetail, TxnRow, TxnInput, PortfolioPerformance, AlertKindInfo, AlertItem, AlertInput, AlertEventItem, NotificationsResponse } from "@/types/api";

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

/** POST a JSON body and save the CSV response as a file (CSV endpoints are POST because they take a filter body). */
export async function downloadCsv(path: string, body: unknown, fallbackName: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  } catch {
    throw new ApiError("Cannot reach the MarketPulse API. Is the backend running?", 0);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = ((await res.json()) as { detail?: string }).detail ?? detail; } catch { /* ignore */ }
    throw new ApiError(detail, res.status);
  }
  const m = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "");
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = m?.[1] ?? fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export const api = {
  portfolios: () => get<{ meta: ApiMeta; disclaimer: string; items: PortfolioListItem[] }>("/portfolios"),
  createPortfolio: (b: { name: string; initial_cash: number; start_day?: string }) => post<{ id: number; name: string }>("/portfolios", b),
  portfolio: (id: number) => get<PortfolioDetail>(`/portfolios/${id}`),
  deletePortfolio: (id: number) => request<null>(`/portfolios/${id}`, { method: "DELETE" }),
  transactions: (id: number) => get<{ items: TxnRow[] }>(`/portfolios/${id}/transactions`),
  addTransaction: (id: number, t: TxnInput) => post<{ transaction: TxnRow; warnings: string[] }>(`/portfolios/${id}/transactions`, t),
  deleteTransaction: (id: number, tid: number) => request<null>(`/portfolios/${id}/transactions/${tid}`, { method: "DELETE" }),
  performance: (id: number, range: string, benchmark: string) => get<PortfolioPerformance>(`/portfolios/${id}/performance?range=${range}&benchmark=${benchmark}`),
  alertKinds: () => get<{ items: AlertKindInfo[]; max_alerts: number }>("/alerts/kinds"),
  alerts: () => get<{ items: AlertItem[] }>("/alerts"),
  createAlert: (b: AlertInput) => post<AlertItem>("/alerts", b),
  updateAlert: (id: number, b: Partial<AlertInput> & { enabled?: boolean }) => send<AlertItem>("PATCH", `/alerts/${id}`, b),
  deleteAlert: (id: number) => request<null>(`/alerts/${id}`, { method: "DELETE" }),
  alertEvents: (limit = 50) => get<{ items: AlertEventItem[] }>(`/alerts/events?limit=${limit}`),
  notifications: () => get<NotificationsResponse>("/notifications"),
  markNotificationsRead: (ids: number[] | null) => post<{ marked: number }>("/notifications/read", { ids }),
  screenerFields: () => get<ScreenCatalog>("/screener/fields"),
  screenerQuery: (q: ScreenQuery) => post<ScreenResult>("/screener/query", q),
  savedScreens: () => get<{ items: SavedScreen[] }>("/screener/saved"),
  saveScreen: (name: string, definition: ScreenQuery) => post<SavedScreen>("/screener/saved", { name, definition }),
  deleteScreen: (id: number) => request<null>(`/screener/saved/${id}`, { method: "DELETE" }),
  compare: (req: CompareRequest) => post<CompareResult>("/compare", req),
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
