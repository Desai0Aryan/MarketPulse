from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.stocks import _meta
from app.services import market

router = APIRouter(tags=["market"])

INDEX_LABELS = {
    "SPY": "S&P 500",
    "QQQ": "Nasdaq-100",
    "DIA": "Dow Jones",
    "IWM": "Russell 2000",
}


@router.get("/market/overview")
def overview():
    """Indexes + breadth + movers, all computed from the tracked universe."""
    provider = market.get_provider()
    indexes, equities = [], []
    for inst in provider.instruments():
        q = market.quote(provider.history(inst.symbol))
        row = {"symbol": inst.symbol, "name": inst.name, **q}
        if inst.kind == "index_proxy":
            indexes.append({**row, "label": INDEX_LABELS.get(inst.symbol, inst.name), "is_proxy": True})
        else:
            equities.append({**row, "sector": inst.sector})
    adv = sum(1 for e in equities if e["change"] > 0)
    dec = sum(1 for e in equities if e["change"] < 0)
    ranked = sorted(equities, key=lambda e: e["change_pct"], reverse=True)
    by_relvol = sorted((e for e in equities if e["rel_volume"]), key=lambda e: e["rel_volume"], reverse=True)

    def slim(e: dict) -> dict:
        keys = ("symbol", "name", "price", "change", "change_pct", "rel_volume", "sparkline", "as_of", "sector")
        return {k: e[k] for k in keys}

    return {
        "meta": _meta(),
        "indexes": indexes,
        "breadth": {"advancing": adv, "declining": dec, "unchanged": len(equities) - adv - dec, "tracked": len(equities)},
        "top_gainers": [slim(e) for e in ranked[:4]],
        "top_losers": [slim(e) for e in ranked[::-1][:4]],
        "unusual_volume": [slim(e) for e in by_relvol[:4]],
        "watchlist_default": [slim(e) for e in equities if e["symbol"] in ("NVDA", "AAPL", "MSFT", "AMD", "TSLA", "META")],
    }
