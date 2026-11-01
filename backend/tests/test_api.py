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
