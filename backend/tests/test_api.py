from fastapi.testclient import TestClient

from app.main import app
from app.ingestion.providers.mock import MockProvider
from datetime import date

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_mock_is_deterministic():
    a = MockProvider(date(2026, 10, 23), 300).history("NVDA")
    b = MockProvider(date(2026, 10, 23), 300).history("NVDA")
    assert a == b and len(a) == 300


def test_bars_are_valid_ohlc():
    for bar in MockProvider(date(2026, 10, 23), 500).history("TSLA"):
        assert bar.low <= min(bar.open, bar.close) and bar.high >= max(bar.open, bar.close)
        assert bar.low > 0 and bar.volume >= 0


def test_prices_endpoint_and_labels():
    r = client.get("/api/v1/stocks/AAPL/prices?range=1M")
    body = r.json()
    assert r.status_code == 200 and body["meta"]["data_class"] == "simulated"
    assert 15 <= body["count"] <= 25


def test_unknown_symbol_404():
    assert client.get("/api/v1/stocks/NOPE/latest").status_code == 404


def test_invalid_range_422():
    assert client.get("/api/v1/stocks/AAPL/prices?start=2026-02-01&end=2026-01-01").status_code == 422


def test_overview_breadth_adds_up():
    b = client.get("/api/v1/market/overview").json()["breadth"]
    assert b["advancing"] + b["declining"] + b["unchanged"] == b["tracked"]
