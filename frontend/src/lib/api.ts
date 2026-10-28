import type { ApiMeta, Bar, MarketOverview, RangeKey, StockRow, Instrument, Quote } from "@/types/api";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function get<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}`, { headers: { Accept: "application/json" } });
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
  return (await res.json()) as T;
}

export const api = {
  overview: () => get<MarketOverview>("/market/overview"),
  stocks: () => get<{ meta: ApiMeta; items: StockRow[] }>("/stocks"),
  stock: (symbol: string) => get<{ meta: ApiMeta; instrument: Instrument; quote: Quote }>(`/stocks/${symbol}`),
  prices: (symbol: string, range: RangeKey) =>
    get<{ meta: ApiMeta; symbol: string; count: number; price_basis: string; bars: Bar[] }>(
      `/stocks/${symbol}/prices?range=${range}`,
    ),
};
