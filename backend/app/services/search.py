from __future__ import annotations

from app.ingestion.providers.base import Instrument


def search_instruments(items: list[Instrument], query: str, limit: int = 10) -> list[dict]:
    """Ranked symbol/company search. Ranking: exact symbol > symbol prefix > name word-prefix >
    name contains > symbol contains. Ties break alphabetically by symbol."""
    q = query.strip().lower()
    if not q:
        return []
    scored: list[tuple[int, str, Instrument, str]] = []
    for i in items:
        sym, name = i.symbol.lower(), i.name.lower()
        words = name.replace("(", " ").replace(")", " ").replace(",", " ").split()
        if sym == q:
            score, why = 100, "exact symbol"
        elif sym.startswith(q):
            score, why = 80, "symbol prefix"
        elif any(w.startswith(q) for w in words):
            score, why = 60, "company name"
        elif q in name:
            score, why = 40, "company name"
        elif q in sym:
            score, why = 30, "symbol"
        else:
            continue
        scored.append((score, i.symbol, i, why))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [
        {"symbol": i.symbol, "name": i.name, "exchange": i.exchange, "kind": i.kind, "match": why}
        for _, _, i, why in scored[:limit]
    ]
