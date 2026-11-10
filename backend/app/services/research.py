"""Research copilot: validated, read-only tools + a deterministic planner and answer composer.

* Every number in an answer comes from a tool call over STORED data. There is no SQL, shell or free-form query
  surface: each tool takes typed, bounds-checked arguments.
* The planner is rule-based (no LLM needed). If an LLM is configured it only phrases an `explanation` of the facts,
  shown separately and labelled model-generated. Facts and explanation are separate fields.
* Questions asking for advice or predictions get an explicit refusal plus the relevant historical facts.
"""

from __future__ import annotations

import math
import re
from datetime import date

import numpy as np

from app.analytics import indicators as ind
from app.analytics import stats as astats
from app.domain import utcnow
from app.processing.quality import quality_report
from app.services import compare as cmp
from app.services import news as nw
from app.services import screener as scr
from app.services.llm import LlmClient, LlmError
from app.services.watchlists import ensure_default
from app.storage.base import Repository

MAX_SYMBOLS, MIN_DAYS, MAX_DAYS, DEFAULT_DAYS = 10, 5, 1300, 90
MAX_QUESTION = 500
SUGGESTED = [
    "Compare NVDA and AMD over the last 90 trading days",
    "Which stocks in my watchlist have the highest historical volatility?",
    "Show the latest RSI and MACD values for AAPL",
    "Explain the recent drawdown in TSLA using stored prices",
    "Summarize the latest available news for MSFT",
    "Summarize the pipeline's data quality issues",
    "Which of my saved screens currently match?",
    "What does a moving-average crossover mean?",
]
_ALIAS_STOP = {"advanced", "spdr", "invesco", "ishares", "johnson"}
GLOSSARY = {
    "crossover": "A moving-average crossover compares a short and a long average of closing prices. When the short average moves above the long one it is called a bullish crossover (often 'golden cross' for 50/200); below is bearish ('death cross'). It describes past price direction with a lag; it does not forecast what happens next, and in sideways markets it often flips repeatedly.",
    "rsi": "RSI (Relative Strength Index, 14 by default) measures the balance of recent gains and losses on a 0-100 scale. By convention readings above 70 are called 'overbought' and below 30 'oversold', but strong trends can stay at those levels for long periods.",
    "macd": "MACD is the difference between a fast and a slow exponential moving average; the signal line smooths it and the histogram is their gap. A MACD line crossing above its signal line is read as momentum turning up, below as turning down. It lags price.",
    "drawdown": "Drawdown is the decline from a previous peak to a later trough, measured here on adjusted closing prices. It describes what happened, not why.",
    "volatility": "Historical volatility here is the sample standard deviation of daily returns, annualised by multiplying by the square root of 252. It measures how widely returns varied in the past, not how risky the stock will be.",
    "correlation": "Correlation (Pearson, on daily returns) ranges from -1 to +1. It measures how closely two series moved together in the window; it does not show that one causes the other and it changes over time.",
}


class ToolError(ValueError):
    pass


# ------------------------------------------------------------------ validated tools
def _symbols(repo: Repository, raw: list[str], lo: int = 1, hi: int = MAX_SYMBOLS) -> list[str]:
    known = {i.symbol for i in repo.get_instruments()}
    out: list[str] = []
    for s in raw:
        s = str(s).strip().upper()
        if s not in known:
            raise ToolError(f"Unknown symbol '{s}'")
        if s not in out:
            out.append(s)
    if not (lo <= len(out) <= hi):
        raise ToolError(f"Expected between {lo} and {hi} distinct symbols")
    return out


def _days(v: int) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not (MIN_DAYS <= v <= MAX_DAYS):
        raise ToolError(f"days must be an integer between {MIN_DAYS} and {MAX_DAYS}")
    return v


def _bars(repo: Repository, sym: str, days: int | None = None):
    bars = repo.get_bars(sym)
    if len(bars) < 2:
        raise ToolError(f"No stored data for {sym}")
    return bars[-(days + 1):] if days else bars


def _r(v, d=4):
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(float(v), d)


def tool_price_summary(repo: Repository, symbol: str, days: int = DEFAULT_DAYS) -> dict:
    sym = _symbols(repo, [symbol])[0]
    days = _days(days)
    bars = _bars(repo, sym, days)
    adj = [b.adj_close for b in bars]
    st = astats.window_stats([b.day for b in bars], adj)
    inst = next(i for i in repo.get_instruments() if i.symbol == sym)
    return {"symbol": sym, "name": inst.name, "days_requested": days, "sessions": len(bars), "start_day": bars[0].day.isoformat(),
            "as_of": bars[-1].day.isoformat(), "last_close": _r(bars[-1].close, 2), "period_return": st["total_return"],
            "annualized_volatility": st["annualized_volatility"], "max_drawdown": st["max_drawdown"], "best_day": st["best_day"],
            "worst_day": st["worst_day"], "period_high_close": _r(max(b.close for b in bars), 2), "period_low_close": _r(min(b.close for b in bars), 2),
            "drawdown_trough_day": _trough(bars)}


def _trough(bars) -> str | None:
    dd = ind.drawdown_series([b.adj_close for b in bars])
    return bars[int(np.argmin(dd))].day.isoformat() if len(dd) else None


def tool_indicators(repo: Repository, symbol: str) -> dict:
    sym = _symbols(repo, [symbol])[0]
    bars = _bars(repo, sym)
    adj = np.array([b.adj_close for b in bars])
    line, sig, hist = ind.macd(adj)
    lo, mid, up = ind.bollinger(adj)
    last = lambda a: _r(a[-1], 4)  # noqa: E731
    return {"symbol": sym, "as_of": bars[-1].day.isoformat(), "close": _r(bars[-1].close, 2), "rsi14": last(ind.rsi(adj, 14)),
            "macd": last(line), "macd_signal": last(sig), "macd_hist": last(hist), "sma20": last(ind.sma(adj, 20)), "sma50": last(ind.sma(adj, 50)),
            "sma200": last(ind.sma(adj, 200)), "bb_lower": last(lo), "bb_upper": last(up),
            "atr14": _r(ind.atr([b.high for b in bars], [b.low for b in bars], [b.close for b in bars], 14)[-1], 4)}


def tool_compare(repo: Repository, symbols: list[str], days: int = DEFAULT_DAYS) -> dict:
    syms = _symbols(repo, symbols, 2)
    days = _days(days)
    try:
        res = cmp.compare({s: _bars(repo, s, days) for s in syms})
    except cmp.CompareError as e:
        raise ToolError(str(e)) from None
    return {"symbols": syms, "days_requested": days, "sessions": len(res["days"]), "start_day": res["days"][0], "as_of": res["days"][-1],
            "stats": {s: {k: res["stats"][s][k] for k in ("total_return", "annualized_volatility", "max_drawdown")} for s in syms},
            "correlation": {"symbols": syms, "matrix": res["correlation"]["matrix"]}, "notes": res["notes"]}


def tool_volatility_ranking(repo: Repository, symbols: list[str], days: int = DEFAULT_DAYS) -> dict:
    syms = _symbols(repo, symbols, 1, 50)
    days = _days(days)
    rows = []
    for s in syms:
        p = tool_price_summary(repo, s, days)
        rows.append({"symbol": s, "annualized_volatility": p["annualized_volatility"], "max_drawdown": p["max_drawdown"], "as_of": p["as_of"]})
    rows.sort(key=lambda r: (r["annualized_volatility"] is None, -(r["annualized_volatility"] or 0)))
    return {"days_requested": days, "ranking": rows, "as_of": max(r["as_of"] for r in rows)}


def tool_news(repo: Repository, symbol: str, limit: int = 5) -> dict:
    sym = _symbols(repo, [symbol])[0]
    items, total = repo.list_articles(symbol=sym, min_relevance=0.4, limit=max(1, min(limit, 10)))
    allitems, _ = repo.list_articles(symbol=sym, min_relevance=0.4, limit=200)
    return {"symbol": sym, "total_matching": total, "articles": [a.to_dict() for a in items], "sentiment": nw.sentiment_summary(allitems),
            "as_of": items[0].published_at.date().isoformat() if items else None}


def tool_pipeline(repo: Repository, reference: date) -> dict:
    q = quality_report(repo, reference)
    runs, _ = repo.list_runs(limit=3)
    return {"as_of": q["latest_timestamp"], "total_bars": q["total_bars"], "stale_symbols": q["stale_symbols"], "rejected_records": q["rejected_records"],
            "warnings": q["warnings"], "ingestion_failures": q["ingestion_failures"], "rejections_by_reason": q["rejections_by_reason"],
            "recent_runs": [{"id": r.id, "status": r.status, "mode": r.mode, "started_at": r.started_at.isoformat()} for r in runs]}


def tool_watchlists(repo: Repository, owner: str) -> dict:
    ensure_default(repo, owner)
    return {"watchlists": [w.to_dict() for w in repo.list_watchlists(owner)], "as_of": None}


def tool_saved_screens(repo: Repository, owner: str) -> dict:
    rows = scr.universe_rows(repo)
    out = []
    for s in repo.list_screens(owner):
        d = s.definition
        res = scr.run_screen(rows, d.get("filters", []), d.get("kind"), d.get("sort", "symbol"), bool(d.get("descending")), 1, 100)
        out.append({"name": s.name, "filters": res["filters"], "matches": res["all_symbols"], "universe": res["universe"]})
    return {"screens": out, "as_of": max((r["as_of"] for r in rows), default=None)}


# ------------------------------------------------------------------ planner
def _extract_symbols(repo: Repository, q: str) -> list[str]:
    found: list[tuple[int, str]] = []
    for inst in repo.get_instruments():
        pos = [m.start() for m in re.finditer(rf"\b{re.escape(inst.symbol)}\b", q, re.I)]
        first = re.sub(r"[^a-z]", "", inst.name.lower().split()[0]) if inst.name else ""
        if first and len(first) > 3 and first not in _ALIAS_STOP:
            pos += [m.start() for m in re.finditer(rf"\b{first}\b", q, re.I)]
        if pos:
            found.append((min(pos), inst.symbol))
    return [s for _, s in sorted(found)]


def _extract_days(q: str) -> int:
    m = re.search(r"(\d{1,4})\s*(?:trading\s*)?(day|session|week|month|year)s?", q, re.I)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        return max(MIN_DAYS, min(MAX_DAYS, n * {"day": 1, "session": 1, "week": 5, "month": 21, "year": 252}[unit]))
    if re.search(r"\bquarter\b", q, re.I):
        return 63
    if re.search(r"\b(year|annual)\b", q, re.I):
        return 252
    return DEFAULT_DAYS


def _pct(v, d=2):
    return "unavailable" if v is None else f"{v * 100:+.{d}f}%"


def _pctn(v, d=1):
    return "unavailable" if v is None else f"{v * 100:.{d}f}%"


def _src(type_: str, label: str, href: str, as_of: str | None) -> dict:
    return {"type": type_, "label": label, "href": href, "as_of": as_of}


def answer(repo: Repository, owner: str, question: str, reference: date, llm: LlmClient | None = None) -> dict:
    q = " ".join((question or "").split())
    if not q:
        raise ToolError("Ask a question first")
    if len(q) > MAX_QUESTION:
        raise ToolError(f"Question is too long (max {MAX_QUESTION} characters)")
    ql = q.lower()
    syms = _extract_symbols(repo, q)
    days = _extract_days(q)
    facts: list[str] = []
    sources: list[dict] = []
    tools: list[dict] = []
    caveats: list[str] = []
    expl: list[str] = []
    refused = False
    intent = "help"

    def call(name: str, args: dict, fn):
        try:
            data = fn()
            tools.append({"tool": name, "args": args, "ok": True})
            return data
        except ToolError as e:
            tools.append({"tool": name, "args": args, "ok": False, "error": str(e)})
            facts.append(f"Could not run {name}: {e}.")
            return None

    advice = re.search(r"\b(should i (buy|sell|hold)|will .* (go up|rise|fall|drop|moon)|price target|predict|forecast|guarantee|best stock to buy|safe bet)\b", ql)
    wants = lambda *k: any(re.search(rf"\b{x}", ql) for x in k)  # noqa: E731
    data: dict = {}

    if advice:
        intent, refused = "advice", True
        facts.append("I can't predict prices or recommend buying or selling; historical data does not tell us what happens next.")
        for s in syms[:1]:
            p = call("price_summary", {"symbol": s, "days": days}, lambda s=s: tool_price_summary(repo, s, days))
            if p:
                data["price_summary"] = p
    elif wants("pipeline", "data quality", "ingest", "stale"):
        intent = "pipeline"
        p = call("pipeline_status", {}, lambda: tool_pipeline(repo, reference))
        if p:
            data["pipeline"] = p
    elif wants("screen"):
        intent = "screens"
        p = call("saved_screens", {}, lambda: tool_saved_screens(repo, owner))
        if p:
            data["screens"] = p
    elif wants("watchlist") and wants("volatil", "risky", "riskiest", "swing"):
        intent = "watchlist_volatility"
        wl = call("watchlists", {}, lambda: tool_watchlists(repo, owner))
        names = next((w["symbols"] for w in (wl or {"watchlists": []})["watchlists"] if w["is_default"]), [])
        if not names:
            facts.append("Your default watchlist has no symbols yet.")
        else:
            p = call("volatility_ranking", {"symbols": names, "days": days}, lambda: tool_volatility_ranking(repo, names, days))
            if p:
                data["ranking"], data["watchlist"] = p, wl
    elif wants("watchlist"):
        intent = "watchlists"
        wl = call("watchlists", {}, lambda: tool_watchlists(repo, owner))
        if wl:
            data["watchlist"] = wl
    elif wants("news", "headline"):
        intent = "news"
        if not syms:
            facts.append("Tell me which symbol you want news for, for example 'latest news for MSFT'.")
        for s in syms[:1]:
            n = call("news", {"symbol": s}, lambda s=s: tool_news(repo, s))
            if n:
                data["news"] = n
    elif wants("rsi", "macd", "indicator", "bollinger", "sma", "moving average", "atr") and syms and not wants("crossover", "cross", "mean"):
        intent = "indicators"
        for s in syms[:3]:
            p = call("indicators", {"symbol": s}, lambda s=s: tool_indicators(repo, s))
            if p:
                data.setdefault("indicators", []).append(p)
    elif (len(syms) >= 2 and not wants("volatil")) or (wants("compare", "versus", " vs") and len(syms) >= 2):
        intent = "compare"
        p = call("compare", {"symbols": syms[:MAX_SYMBOLS], "days": days}, lambda: tool_compare(repo, syms[:MAX_SYMBOLS], days))
        if p:
            data["compare"] = p
    elif wants("volatil") and syms:
        intent = "volatility"
        p = call("volatility_ranking", {"symbols": syms, "days": days}, lambda: tool_volatility_ranking(repo, syms, days))
        if p:
            data["ranking"] = p
    elif wants("drawdown", "drop", "decline", "fell", "crash") and syms:
        intent = "drawdown"
        p = call("price_summary", {"symbol": syms[0], "days": days}, lambda: tool_price_summary(repo, syms[0], days))
        if p:
            data["price_summary"] = p
    elif wants("crossover", "golden cross", "death cross", "what does", "what is", "explain", "mean") and not syms:
        intent = "glossary"
    elif syms:
        intent = "price"
        for s in syms[:3]:
            p = call("price_summary", {"symbol": s, "days": days}, lambda s=s: tool_price_summary(repo, s, days))
            if p:
                data.setdefault("price_summaries", []).append(p)

    # ---- compose facts + sources from tool data (never from the model) ----
    ps = data.get("price_summary")
    if ps:
        facts.append(f"{ps['symbol']} ({ps['name']}): closed at {ps['last_close']} on {ps['as_of']}; over the last {ps['sessions'] - 1} sessions (from {ps['start_day']}) the adjusted return was {_pct(ps['period_return'])}.")
        facts.append(f"Max drawdown in that window: {_pctn(ps['max_drawdown'])}" + (f", with the low point on {ps['drawdown_trough_day']}" if ps["drawdown_trough_day"] and intent == "drawdown" else "") + f"; annualised volatility: {_pctn(ps['annualized_volatility'])}.")
        if ps["best_day"] and ps["worst_day"]:
            facts.append(f"Best day {ps['best_day']['day']} ({_pct(ps['best_day']['return'])}); worst day {ps['worst_day']['day']} ({_pct(ps['worst_day']['return'])}).")
        sources.append(_src("stock", f"{ps['symbol']} price history", f"/markets/{ps['symbol']}", ps["as_of"]))
    for ps in data.get("price_summaries", []):
        facts.append(f"{ps['symbol']}: last close {ps['last_close']} on {ps['as_of']}; {ps['sessions'] - 1}-session return {_pct(ps['period_return'])}; annualised volatility {_pctn(ps['annualized_volatility'])}; max drawdown {_pctn(ps['max_drawdown'])}.")
        sources.append(_src("stock", f"{ps['symbol']} price history", f"/markets/{ps['symbol']}", ps["as_of"]))
    for ix in data.get("indicators", []):
        rsi = ix["rsi14"]
        tag = "" if rsi is None else " (above the conventional 70 'overbought' line)" if rsi > 70 else " (below the conventional 30 'oversold' line)" if rsi < 30 else " (between the 30 and 70 conventional lines)"
        facts.append(f"{ix['symbol']} as of {ix['as_of']}: RSI(14) {rsi}{tag}; MACD {ix['macd']} vs signal {ix['macd_signal']} (histogram {ix['macd_hist']}); SMA20 {ix['sma20']}, SMA50 {ix['sma50']}, SMA200 {ix['sma200']}; close {ix['close']}.")
        sources.append(_src("indicators", f"{ix['symbol']} technicals", f"/markets/{ix['symbol']}", ix["as_of"]))
        expl += [GLOSSARY["rsi"], GLOSSARY["macd"]]
    if "compare" in data:
        c = data["compare"]
        for s in c["symbols"]:
            st = c["stats"][s]
            facts.append(f"{s}: return {_pct(st['total_return'])}, annualised volatility {_pctn(st['annualized_volatility'])}, max drawdown {_pctn(st['max_drawdown'])} ({c['sessions'] - 1} common sessions from {c['start_day']} to {c['as_of']}).")
        m, ss = c["correlation"]["matrix"], c["symbols"]
        pairs = [(ss[i], ss[j], m[i][j]) for i in range(len(ss)) for j in range(i + 1, len(ss))]
        for a, b, v in pairs[:6]:
            facts.append(f"Correlation of daily returns {a}/{b}: {'unavailable' if v is None else f'{v:.2f}'}.")
        sources.append(_src("compare", "Comparison workspace", f"/compare?symbols={','.join(ss)}", c["as_of"]))
        expl += [GLOSSARY["correlation"], GLOSSARY["volatility"]]
        caveats += c["notes"]
    if "ranking" in data:
        r = data["ranking"]
        facts.append(f"Historical volatility ranking over the last {r['days_requested']} sessions (annualised, highest first): " + "; ".join(f"{x['symbol']} {_pctn(x['annualized_volatility'])}" for x in r["ranking"][:10]) + ".")
        sources += [_src("stock", f"{x['symbol']} price history", f"/markets/{x['symbol']}", x["as_of"]) for x in r["ranking"][:5]]
        if "watchlist" in data:
            sources.append(_src("watchlist", "Your watchlists", "/watchlists", None))
        expl.append(GLOSSARY["volatility"])
    if "watchlist" in data and "ranking" not in data:
        for w in data["watchlist"]["watchlists"]:
            facts.append(f"Watchlist '{w['name']}'{' (default)' if w['is_default'] else ''}: {', '.join(w['symbols']) or 'empty'}.")
        sources.append(_src("watchlist", "Your watchlists", "/watchlists", None))
    if "news" in data:
        n = data["news"]
        if not n["articles"]:
            facts.append(f"No stored news matches {n['symbol']}.")
        for a in n["articles"]:
            lab = " [simulated demo item]" if a["simulated"] else ""
            facts.append(f"{a['published_at'][:10]} · {a['source']}{lab}: {a['headline']}" + (f" (baseline sentiment: {a['sentiment']['category']})" if a["sentiment"] else ""))
        s = n["sentiment"]
        if s["scored"]:
            facts.append(f"Of {s['scored']} stored articles about {n['symbol']}: {s['counts']['positive']} positive, {s['counts']['neutral']} neutral, {s['counts']['negative']} negative by the word-list baseline.")
        sources.append(_src("news", f"{n['symbol']} news", f"/news?symbol={n['symbol']}", n["as_of"]))
        caveats.append(nw.SENTIMENT_NOTICE)
    if "pipeline" in data:
        p = data["pipeline"]
        facts.append(f"{p['total_bars']} stored daily bars; latest session {p['as_of']}; stale symbols: {', '.join(p['stale_symbols']) or 'none'}.")
        facts.append(f"{p['rejected_records']} rejected records and {p['warnings']} validation warnings recorded; {p['ingestion_failures']} failed or partial ingestion runs.")
        if p["rejections_by_reason"]:
            facts.append("Rejections by reason: " + "; ".join(f"{k} ({v})" for k, v in p["rejections_by_reason"].items()) + ".")
        sources.append(_src("pipeline", "Data pipeline", "/data-pipeline", p["as_of"]))
    if "screens" in data:
        sc = data["screens"]
        if not sc["screens"]:
            facts.append("You have no saved screens yet. Create one on the Screener page.")
        for s in sc["screens"]:
            facts.append(f"Screen '{s['name']}': {len(s['matches'])} of {s['universe']} instruments match" + (f" ({', '.join(s['matches'][:10])})." if s["matches"] else "."))
        sources.append(_src("screener", "Screener", "/screener", sc["as_of"]))
    if intent == "glossary":
        for k, text in GLOSSARY.items():
            if k in ql or (k == "crossover" and re.search(r"cross|moving average", ql)):
                expl.append(text)
        if not expl:
            facts.append("I can explain moving-average crossovers, RSI, MACD, drawdown, volatility and correlation. Which one would you like?")
    if intent == "drawdown":
        expl.append(GLOSSARY["drawdown"])
    if intent == "help" and not facts:
        facts.append("I can answer from this platform's stored data: price moves, returns, volatility and drawdown, RSI/MACD/moving averages, comparisons and correlation, watchlists, saved screens, news with a baseline sentiment, and pipeline data quality. Try one of the suggestions.")
    if refused:
        expl.append("Past performance does not predict future results. I can show what the data did, not what it will do.")

    ref_day = max([s["as_of"] for s in sources if s.get("as_of")], default=None)
    s = _settings()
    if s["demo"]:
        caveats.append("All prices are simulated demo data, not real market prices.")
    explanation, mode, llm_error = " ".join(dict.fromkeys(expl)) or None, "deterministic", None
    if llm is not None and data and not refused:
        try:
            explanation, mode = llm.explain(q, {"intent": intent, "data": data, "facts": facts}), "model-generated"
        except LlmError as e:
            llm_error = str(e)  # fall back to the deterministic text; the key is never included
    return {
        "question": q, "intent": intent, "symbols": syms[:MAX_SYMBOLS], "range": {"sessions_requested": days, "as_of": ref_day},
        "facts": facts, "explanation": explanation, "explanation_mode": mode, "llm_error": llm_error, "sources": sources, "tools": tools,
        "caveats": list(dict.fromkeys(caveats + ["Not investment advice. Historical data cannot predict future returns."])),
        "refused": refused, "generated_at": utcnow().isoformat(),
    }


def _settings() -> dict:
    from app.core.config import get_settings

    return {"demo": get_settings().is_demo}
