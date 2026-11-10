import pytest

pytest.importorskip("fastapi")


def test_health_and_ready(client):
    assert client.get("/health").json()["status"] == "ok"
    r = client.get("/ready")
    assert r.status_code == 200 and r.json()["checks"] == {"database": "ok", "provider": "ok"}


def test_prices_endpoint_and_labels(client):
    r = client.get("/api/v1/stocks/AAPL/prices?range=1M")
    body = r.json()
    assert r.status_code == 200 and body["meta"]["data_class"] == "simulated"
    assert 15 <= body["count"] <= 25


def test_unknown_symbol_404(client):
    assert client.get("/api/v1/stocks/NOPE/latest").status_code == 404


def test_invalid_date_range_422(client):
    assert client.get("/api/v1/stocks/AAPL/prices?start=2026-02-01&end=2026-01-01").status_code == 422


def test_limit_is_bounded(client):
    assert client.get("/api/v1/stocks/AAPL/prices?limit=999999").status_code == 422


def test_overview_breadth_adds_up(client):
    b = client.get("/api/v1/market/overview").json()["breadth"]
    assert b["advancing"] + b["declining"] + b["unchanged"] == b["tracked"] == 12


def test_indicators_endpoint_returns_nulls_not_zeros(client):
    body = client.get("/api/v1/stocks/NVDA/indicators?range=MAX&limit=5000").json()
    assert body["rows"][0]["sma20"] is None and body["rows"][-1]["sma200"] is not None
    assert 0 <= body["rows"][-1]["rsi14"] <= 100


def test_pipeline_status_and_quality(client):
    s = client.get("/api/v1/pipeline/status").json()
    assert s["database"]["ok"] and s["totals"]["success_rate"] == 1.0 and len(s["freshness"]) == 16
    assert not any(f["stale"] for f in s["freshness"])
    q = client.get("/api/v1/pipeline/quality").json()
    assert q["total_bars"] == 20800 and q["stale_symbols"] == [] and q["rejected_records"] == 0


def test_manual_ingest_is_idempotent_and_listed(client):
    r = client.post("/api/v1/pipeline/ingest", json={"symbols": ["AAPL"]})
    assert r.status_code == 202
    run = client.get(f"/api/v1/pipeline/runs/{r.json()['run_id']}").json()
    assert run["status"] == "success" and run["stats"]["inserted"] == 0
    runs = client.get("/api/v1/pipeline/runs?limit=5").json()
    assert runs["total"] >= 2 and runs["items"][0]["id"] == run["id"]


def test_backfill_validation_errors(client):
    bad = client.post("/api/v1/pipeline/backfill", json={"symbols": ["NOPE"], "start": "2026-01-01"})
    assert bad.status_code == 422
    rev = client.post("/api/v1/pipeline/backfill", json={"symbols": ["AAPL"], "start": "2026-05-01", "end": "2026-04-01"})
    assert rev.status_code == 422
    assert client.post("/api/v1/pipeline/backfill", json={"symbols": [], "start": "2026-01-01"}).status_code == 422


def test_unknown_run_404_and_filter(client):
    assert client.get("/api/v1/pipeline/runs/9999").status_code == 404
    assert client.get("/api/v1/pipeline/runs?status=failed").json()["total"] == 0


def test_ops_require_token_when_configured(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.main import create_app
    from app.services import container

    monkeypatch.setenv("MP_ADMIN_TOKEN", "s3cret")
    get_settings.cache_clear()
    container.reset_for_tests()
    try:
        with TestClient(create_app()) as c:
            assert c.post("/api/v1/pipeline/ingest", json={}).status_code == 401
            assert c.post("/api/v1/pipeline/ingest", json={}, headers={"X-Admin-Token": "wrong"}).status_code == 401
            assert c.post("/api/v1/pipeline/ingest", json={}, headers={"X-Admin-Token": "s3cret"}).status_code == 202
            assert c.get("/api/v1/pipeline/status").status_code == 200  # reads stay open
    finally:
        monkeypatch.delenv("MP_ADMIN_TOKEN")
        get_settings.cache_clear()
        container.reset_for_tests()


def test_ops_disabled_in_production_without_token(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.main import create_app
    from app.services import container

    monkeypatch.setenv("MP_ENVIRONMENT", "production")
    get_settings.cache_clear()
    container.reset_for_tests()
    try:
        with TestClient(create_app()) as c:
            assert c.post("/api/v1/pipeline/ingest", json={}).status_code == 403
    finally:
        monkeypatch.delenv("MP_ENVIRONMENT")
        get_settings.cache_clear()
        container.reset_for_tests()


# ---- Part 3 -----------------------------------------------------------------
def test_search_endpoint(client):
    r = client.get("/api/v1/search?q=nvd").json()
    assert r["items"][0]["symbol"] == "NVDA"
    assert client.get("/api/v1/search?q=zzzzz").json()["items"] == []
    assert client.get("/api/v1/search?q=").status_code == 422


def test_technicals_endpoint_and_param_validation(client):
    r = client.get("/api/v1/stocks/AAPL/technicals?range=3M&rsi=7&bb_k=2.5").json()
    assert r["parameters"]["rsi"] == 7 and len(r["rsi"]) == len(r["days"]) > 40
    assert client.get("/api/v1/stocks/AAPL/technicals?rsi=1").status_code == 422
    assert client.get("/api/v1/stocks/AAPL/technicals?macd=26,12,9").status_code == 422
    assert client.get("/api/v1/stocks/AAPL/technicals?sma=abc").status_code == 422


def test_returns_endpoint(client):
    r = client.get("/api/v1/stocks/MSFT/returns?range=1Y").json()
    assert r["stats"]["max_drawdown"] <= 0 and r["series"]["daily_return"][0] is None
    assert client.get("/api/v1/stocks/NOPE/returns").status_code == 404


def test_csv_export_headers_and_safety(client):
    r = client.get("/api/v1/stocks/AAPL/prices.csv?range=1M")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"] and "marketpulse_AAPL_prices_1M_2026-10-23.csv" in r.headers["content-disposition"]
    lines = r.text.splitlines()
    assert lines[0].startswith("# MarketPulse export") and any(l.startswith("date,open") for l in lines)
    assert any("simulated" in l for l in lines[:6])


def test_watchlist_lifecycle_over_http(client):
    lists = client.get("/api/v1/watchlists").json()["items"]
    assert len(lists) == 1 and lists[0]["is_default"] and lists[0]["symbols"][:2] == ["NVDA", "AAPL"]
    assert all(i["has_data"] and i["price"] > 0 for i in lists[0]["items"])
    new = client.post("/api/v1/watchlists", json={"name": "  Energy  "})
    assert new.status_code == 201 and new.json()["name"] == "Energy"
    wid = new.json()["id"]
    assert client.post("/api/v1/watchlists", json={"name": "energy"}).status_code == 409
    assert client.post("/api/v1/watchlists", json={"name": "   "}).status_code == 422
    assert client.post(f"/api/v1/watchlists/{wid}/items", json={"symbol": "xom"}).json()["symbols"] == ["XOM"]
    assert client.post(f"/api/v1/watchlists/{wid}/items", json={"symbol": "NOPE"}).status_code == 404
    assert client.post(f"/api/v1/watchlists/{wid}/items", json={"symbol": "bad symbol!"}).status_code == 422
    assert client.put(f"/api/v1/watchlists/{wid}/order", json={"symbols": ["AAPL"]}).status_code == 409
    assert client.patch(f"/api/v1/watchlists/{wid}", json={"is_default": True}).json()["is_default"] is True
    assert client.patch(f"/api/v1/watchlists/{wid}", json={"is_default": False}).status_code == 422
    assert client.delete(f"/api/v1/watchlists/{wid}/items/XOM").json()["symbols"] == []
    assert client.delete(f"/api/v1/watchlists/{wid}").status_code == 204
    assert client.delete(f"/api/v1/watchlists/{wid}").status_code == 404
    left = client.get("/api/v1/watchlists").json()["items"]
    assert len(left) == 1 and left[0]["is_default"]


# ---- Part 4: screener & compare (skipped unless FastAPI is installed) ----
def test_screener_fields_and_query(client):
    assert any(f["key"] == "rsi14" for f in client.get("/api/v1/screener/fields").json()["numeric"])
    r = client.post("/api/v1/screener/query", json={"filters": [{"field": "rsi14", "op": "between", "value": 0, "value2": 100}], "sort": "rsi14"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == len(body["all_symbols"]) and body["meta"]["data_class"] == "simulated"


def test_screener_rejects_bad_input(client):
    assert client.post("/api/v1/screener/query", json={"filters": [{"field": "x", "op": "gt", "value": 1}]}).status_code == 422
    assert client.post("/api/v1/screener/query", json={"sort": "password"}).status_code == 422
    assert client.post("/api/v1/screener/query", json={"page_size": 1000}).status_code == 422


def test_screener_csv_and_saved(client):
    csv = client.post("/api/v1/screener/export.csv", json={"filters": []})
    assert csv.status_code == 200 and csv.text.startswith("# MarketPulse export")
    body = {"name": "Oversold", "definition": {"filters": [{"field": "rsi14", "op": "lt", "value": 30}]}}
    created = client.post("/api/v1/screener/saved", json=body)
    assert created.status_code == 201
    assert client.post("/api/v1/screener/saved", json=body).status_code == 409
    bad = {"name": "Bad", "definition": {"filters": [{"field": "nope", "op": "gt", "value": 1}]}}
    assert client.post("/api/v1/screener/saved", json=bad).status_code == 422
    sid = created.json()["id"]
    assert client.delete(f"/api/v1/screener/saved/{sid}").status_code == 204
    assert client.delete(f"/api/v1/screener/saved/{sid}").status_code == 404


def test_compare_endpoint(client):
    r = client.post("/api/v1/compare", json={"symbols": ["aapl", "MSFT", "NVDA"], "range": "1Y", "rolling_pair": ["AAPL", "MSFT"]})
    assert r.status_code == 200
    j = r.json()
    assert j["symbols"] == ["AAPL", "MSFT", "NVDA"] and j["normalized"]["AAPL"][0] == 100
    assert len(j["rolling_correlation"]["values"]) == len(j["days"]) - 1
    csv = client.post("/api/v1/compare/export.csv", json={"symbols": ["AAPL", "MSFT"]})
    assert csv.status_code == 200 and "AAPL_rebased_100" in csv.text


def test_compare_validation(client):
    assert client.post("/api/v1/compare", json={"symbols": ["AAPL"]}).status_code == 422
    assert client.post("/api/v1/compare", json={"symbols": ["AAPL", "ZZZZ"]}).status_code == 404
    assert client.post("/api/v1/compare", json={"symbols": ["AAPL", "AAPL"]}).status_code == 422  # duplicates collapse to 1 symbol


# ---- Part 5: portfolio & alerts (skipped unless FastAPI is installed) ----
def _new_portfolio(client, cash=10000):
    r = client.post("/api/v1/portfolios", json={"name": "Test", "initial_cash": cash, "start_day": "2026-01-05"})
    assert r.status_code == 201
    return r.json()["id"]


def test_portfolio_lifecycle_and_accounting(client):
    pid = _new_portfolio(client)
    base = f"/api/v1/portfolios/{pid}"
    buy = {"day": "2026-01-06", "kind": "buy", "symbol": "aapl", "quantity": 10, "price": 100, "fee": 1}
    r = client.post(f"{base}/transactions", json=buy)
    assert r.status_code == 201 and r.json()["transaction"]["symbol"] == "AAPL"
    assert any("50%" in w for w in r.json()["warnings"]) or r.json()["warnings"] == []  # mock price may or may not be near 100
    d = client.get(base).json()
    assert d["summary"]["cash"] == 8999 and d["summary"]["invested_capital"] == 1001
    assert d["disclaimer"].startswith("Paper portfolio")
    over = client.post(f"{base}/transactions", json={**buy, "kind": "sell", "quantity": 11})
    assert over.status_code == 422 and "exceeds" in over.json()["detail"]
    perf = client.get(f"{base}/performance?range=MAX").json()
    assert perf["benchmark"] == "SPY" and perf["twr_index"][0] == 100.0
    assert client.get(f"{base}/transactions.csv").text.startswith("# MarketPulse export")


def test_portfolio_validation_and_isolation(client):
    pid = _new_portfolio(client, 100)
    base = f"/api/v1/portfolios/{pid}/transactions"
    assert client.post(base, json={"day": "2026-01-06", "kind": "buy", "symbol": "AAPL", "quantity": 1000, "price": 100}).status_code == 422  # no cash
    assert client.post(base, json={"day": "2099-01-01", "kind": "deposit", "amount": 5}).status_code == 422  # future
    assert client.post(base, json={"day": "2026-01-06", "kind": "buy", "symbol": "NOPE", "quantity": 1, "price": 1}).status_code == 422
    assert client.post(base, json={"day": "2026-01-06", "kind": "deposit", "amount": -5}).status_code == 422
    assert client.get("/api/v1/portfolios/9999").status_code == 404
    assert client.get(f"/api/v1/portfolios/{pid}/performance?benchmark=AAPL").status_code == 422  # not an index proxy


def test_alert_crud_and_notifications(client):
    k = client.get("/api/v1/alerts/kinds").json()
    assert any(i["kind"] == "rsi_above" for i in k["items"])
    r = client.post("/api/v1/alerts", json={"symbol": "NVDA", "kind": "price_above", "threshold": 1e9})
    assert r.status_code == 201 and r.json()["status"] == "active"
    aid = r.json()["id"]
    assert client.post("/api/v1/alerts", json={"symbol": "NVDA", "kind": "bogus", "threshold": 1}).status_code == 422
    assert client.post("/api/v1/alerts", json={"symbol": "ZZZZ", "kind": "price_above", "threshold": 1}).status_code == 404
    assert client.patch(f"/api/v1/alerts/{aid}", json={"enabled": False}).json()["status"] == "paused"
    assert client.patch(f"/api/v1/alerts/{aid}", json={"threshold": -1}).status_code == 422
    n = client.get("/api/v1/notifications").json()
    assert n["unread"] == 0 and n["items"] == []
    assert client.post("/api/v1/alerts/evaluate").json()["alerts_checked"] == 0  # paused
    assert client.delete(f"/api/v1/alerts/{aid}").status_code == 204
    assert client.delete(f"/api/v1/alerts/{aid}").status_code == 404


def test_alert_fires_after_new_session_ingested(client):
    from datetime import timedelta

    from app.services import container

    repo = container.get_repo()
    last = repo.get_bars("AAPL")[-1]
    thr = round(last.close * 1.02, 2)
    aid = client.post("/api/v1/alerts", json={"symbol": "AAPL", "kind": "price_above", "threshold": thr, "cooldown_days": 0}).json()["id"]
    from app.ingestion.providers.base import Bar

    nxt = Bar(last.day + timedelta(days=1), last.close, thr + 5, last.close, thr + 3, thr + 3, last.volume)
    repo.upsert_bars("AAPL", [nxt], None)
    assert client.post("/api/v1/alerts/evaluate").json()["events_created"] == 1
    assert client.post("/api/v1/alerts/evaluate").json()["events_created"] == 0  # no duplicate
    n = client.get("/api/v1/notifications").json()
    assert n["unread"] == 1 and n["items"][0]["observed_value"] == nxt.close
    assert client.post("/api/v1/notifications/read", json={"ids": None}).json()["marked"] == 1
    assert client.get("/api/v1/notifications").json()["unread"] == 0
    assert client.get("/api/v1/alerts").json()["items"][0]["status"] == "triggered" and aid


# ---- Part 6: backtests, news, AI, live events (skipped unless FastAPI is installed) ----
def test_backtest_run_persist_and_validation(client):
    body = {"symbol": "msft", "strategy": "ma_cross", "params": {"fast": 20, "slow": 50}, "commission_bps": 5, "slippage_bps": 5}
    r = client.post("/api/v1/backtests", json=body)
    assert r.status_code == 200
    j = r.json()
    assert j["config"]["symbol"] == "MSFT" and j["reproducibility"]["strategy_version"] and j["disclaimer"].startswith("Historical simulation")
    assert len(j["equity"]) == len(j["days"]) == len(j["buy_hold"])
    got = client.get(f"/api/v1/backtests/{j['id']}").json()
    assert got["metrics"] == j["metrics"] and any(i["id"] == j["id"] for i in client.get("/api/v1/backtests").json()["items"])
    assert client.post("/api/v1/backtests", json={**body, "params": {"fast": 50, "slow": 20}}).status_code == 422
    assert client.post("/api/v1/backtests", json={**body, "long_only": False}).status_code == 422
    assert client.post("/api/v1/backtests", json={**body, "symbol": "NOPE"}).status_code == 404
    assert client.post("/api/v1/backtests", json={**body, "strategy": "magic"}).status_code == 422
    assert client.delete(f"/api/v1/backtests/{j['id']}").status_code == 204
    assert client.get(f"/api/v1/backtests/{j['id']}").status_code == 404


def test_news_endpoints_label_demo_feed(client):
    r = client.get("/api/v1/news?limit=5").json()
    assert r["simulated"] is True and "not real news" in r["notice"] and "not a reliable predictor" in r["sentiment_notice"]
    assert all(a["simulated"] and a["sentiment"]["method"] == "lexicon-baseline" for a in r["items"])
    assert client.get("/api/v1/news?start=2026-12-01&end=2026-01-01").status_code == 422
    assert client.get("/api/v1/news?sentiment=great").status_code == 422
    assert client.get("/api/v1/news/sources").json()["items"]
    assert client.post("/api/v1/news/refresh").json()["inserted"] == 0  # idempotent


def test_ai_chat_grounded_and_refuses_advice(client):
    st = client.get("/api/v1/ai/status").json()
    assert st["mode"] == "deterministic" and st["suggested"]
    a = client.post("/api/v1/ai/chat", json={"question": "Compare NVDA and AMD over the last 90 trading days"}).json()
    assert a["intent"] == "compare" and a["facts"] and a["sources"] and "key" not in str(a).lower().replace("keyboard", "")
    assert client.post("/api/v1/ai/chat", json={"question": "Should I buy NVDA?"}).json()["refused"] is True
    assert client.post("/api/v1/ai/chat", json={"question": ""}).status_code == 422
    assert client.post("/api/v1/ai/chat", json={"question": "x" * 600}).status_code == 422
    s = client.post("/api/v1/ai/chat/stream", json={"question": "Show AAPL"})
    assert s.headers["content-type"].startswith("text/event-stream") and "event: done" in s.text and "event: meta" in s.text


def test_events_stream_route_registered(client):
    assert any(getattr(r, "path", "") == "/api/v1/events" for r in client.app.routes)  # streaming itself is covered at the generator level
