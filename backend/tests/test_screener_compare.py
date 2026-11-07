from datetime import date, timedelta

import numpy as np
import pytest

from app.domain import ConflictError, LimitError, NotFoundError
from app.ingestion.providers.base import Bar, Instrument
from app.ingestion.providers.mock import MockProvider
from app.services import compare as cmp
from app.services import screener as sc
from app.storage.memory import MemoryRepository

P = MockProvider(date(2026, 10, 23), 600)
BARS = {s: P.history(s) for s in ("AAPL", "MSFT", "NVDA", "SPY")}
INST = {i.symbol: i for i in P.instruments()}


def rows():
    return [sc.compute_metrics(INST[s], b) for s, b in BARS.items()]


def synth(closes, start=date(2026, 1, 1), vol=1000):
    return [Bar(start + timedelta(days=i), c, c * 1.01, c * 0.99, c, c, vol) for i, c in enumerate(closes)]


# ---- metrics ----
def test_metrics_known_values():
    inst = Instrument("X", "X Inc", "NASDAQ", "USD", "equity")
    closes = [100.0] * 59 + [110.0]
    m = sc.compute_metrics(inst, synth(closes))
    assert m["price"] == 110.0 and m["change_pct"] == 10.0
    assert m["price_vs_sma50_pct"] == pytest.approx((110 / (100 * 49 / 50 + 110 / 50) - 1) * 100, abs=0.01)
    assert m["sma50_above_sma200"] is None and m["price_vs_sma200_pct"] is None  # too little history: unavailable, not False
    assert m["rel_volume"] == 1.0
    assert m["dist_52w_high_pct"] == pytest.approx((110 / (110 * 1.01) - 1) * 100, abs=0.01)


def test_metrics_need_two_bars():
    assert sc.compute_metrics(INST["AAPL"], BARS["AAPL"][:1]) is None


def test_metrics_do_not_look_ahead():
    cut = BARS["AAPL"][:-10]
    assert sc.compute_metrics(INST["AAPL"], cut)["as_of"] == cut[-1].day.isoformat()
    assert sc.compute_metrics(INST["AAPL"], cut)["price"] == round(cut[-1].close, 2)


# ---- filtering ----
def test_filters_and_null_metrics_excluded():
    r = rows()
    out = sc.run_screen(r, [{"field": "rsi14", "op": "between", "value": 0, "value2": 100}])
    assert out["total"] == len(r)
    short = [sc.compute_metrics(INST["AAPL"], BARS["AAPL"][:30])] + r  # rsi defined, sma200 not
    out = sc.run_screen(short, [{"field": "price_vs_sma200_pct", "op": "gt", "value": -1000}])
    assert out["total"] == len(r)  # the short-history row never matches a filter on an undefined metric


def test_bool_filter_and_kind():
    r = rows()
    up = sc.run_screen(r, [{"field": "sma50_above_sma200", "op": "eq", "value": True}])
    assert all(x["sma50_above_sma200"] is True for x in up["items"])
    down = sc.run_screen(r, [{"field": "sma50_above_sma200", "op": "eq", "value": False}])
    assert up["total"] + down["total"] == len(r)
    assert sc.run_screen(r, [], kind="index_proxy")["all_symbols"] == ["SPY"]


@pytest.mark.parametrize(
    "bad",
    [
        {"field": "nope", "op": "gt", "value": 1},
        {"field": "price", "op": "like", "value": 1},
        {"field": "price", "op": "gt", "value": "1; DROP TABLE"},
        {"field": "price", "op": "gt", "value": float("nan")},
        {"field": "price", "op": "gt", "value": True},
        {"field": "price", "op": "between", "value": 5, "value2": 1},
        {"field": "sma50_above_sma200", "op": "gt", "value": True},
        {"field": "sma50_above_sma200", "op": "eq", "value": 1},
    ],
)
def test_invalid_filters_rejected(bad):
    with pytest.raises(sc.ScreenError):
        sc.run_screen(rows(), [bad])


def test_limits_and_bad_args():
    with pytest.raises(sc.ScreenError):
        sc.run_screen(rows(), [{"field": "price", "op": "gt", "value": 0}] * (sc.MAX_FILTERS + 1))
    for kw in ({"sort": "password"}, {"page": 0}, {"page_size": 1000}, {"kind": "crypto"}):
        with pytest.raises(sc.ScreenError):
            sc.run_screen(rows(), [], **kw)


def test_sort_pagination_and_nulls_last():
    r = rows() + [{**rows()[0], "symbol": "ZZZ", "rsi14": None}]
    asc = sc.run_screen(r, [], sort="rsi14")["all_symbols"]
    desc = sc.run_screen(r, [], sort="rsi14", descending=True)["all_symbols"]
    assert asc[-1] == "ZZZ" and desc[-1] == "ZZZ"
    assert asc[:-1] == desc[:-1][::-1]
    p1 = sc.run_screen(r, [], page=1, page_size=2)
    p3 = sc.run_screen(r, [], page=3, page_size=2)
    assert len(p1["items"]) == 2 and len(p3["items"]) == 1 and p1["total"] == 5
    assert sc.run_screen(r, [], page=9, page_size=2)["items"] == []


# ---- saved screens ----
def test_saved_screens_owner_scoped_and_limits():
    repo = MemoryRepository()
    d = {"filters": [], "sort": "symbol"}
    a = repo.create_screen("alice", "Momentum", d)
    with pytest.raises(ConflictError):
        repo.create_screen("alice", "momentum", d)
    repo.create_screen("bob", "Momentum", d)  # same name, other owner: fine
    assert [s.name for s in repo.list_screens("alice")] == ["Momentum"]
    with pytest.raises(NotFoundError):
        repo.delete_screen("bob", a.id)  # not theirs
    repo.delete_screen("alice", a.id)
    for i in range(repo.MAX_SCREENS):
        repo.create_screen("carol", f"s{i}", d)
    with pytest.raises(LimitError):
        repo.create_screen("carol", "one-too-many", d)


def test_saved_screen_definition_is_copied():
    repo = MemoryRepository()
    d = {"filters": [{"field": "price", "op": "gt", "value": 1.0}]}
    repo.create_screen("a", "x", d)
    d["filters"].clear()
    assert repo.list_screens("a")[0].definition["filters"]


# ---- compare ----
def test_alignment_inner_join_no_fill():
    a = synth(list(np.linspace(100, 120, 60)))
    b = [x for i, x in enumerate(synth(list(np.linspace(50, 70, 60)))) if i % 5 != 0]  # b is missing every 5th day
    r = cmp.compare({"A": a, "B": b})
    assert len(r["days"]) == len(b)
    assert r["coverage"]["A"]["dropped"] == 60 - len(b) and r["coverage"]["B"]["dropped"] == 0
    assert any("dropped" in n for n in r["notes"])


def test_normalised_starts_at_100_and_matches_returns():
    r = cmp.compare({"A": BARS["AAPL"][-200:], "B": BARS["MSFT"][-200:]})
    assert r["normalized"]["A"][0] == 100 == r["normalized"]["B"][0]
    tr = r["stats"]["A"]["total_return"]
    assert r["normalized"]["A"][-1] == pytest.approx(100 * (1 + tr), rel=1e-4)


def test_correlation_properties():
    r = cmp.compare({s: BARS[s][-300:] for s in ("AAPL", "MSFT", "NVDA")})
    m = np.array(r["correlation"]["matrix"], dtype=float)
    assert np.allclose(np.diag(m), 1.0) and np.allclose(m, m.T) and (np.abs(m) <= 1 + 1e-9).all()


def test_perfect_and_inverse_correlation():
    base = np.cumprod(1 + np.random.default_rng(1).normal(0, 0.01, 120)) * 100
    a = synth(list(base))
    same = synth(list(base * 3))  # identical returns
    r = cmp.compare({"A": a, "B": same})
    assert r["correlation"]["matrix"][0][1] == pytest.approx(1.0, abs=1e-9)
    assert cmp.pearson(np.array([1.0, 2, 3, 4]), np.array([4.0, 3, 2, 1])) == pytest.approx(-1.0)


def test_constant_series_correlation_is_unavailable_not_zero():
    r = cmp.compare({"A": synth([100.0] * 60), "B": synth(list(np.linspace(1, 2, 60)))})
    assert r["correlation"]["matrix"][0][1] is None
    assert any("unavailable" in n for n in r["notes"])


def test_rolling_correlation_window_and_no_lookahead():
    a, b = BARS["AAPL"][-250:], BARS["MSFT"][-250:]
    r = cmp.compare({"A": a, "B": b}, ("A", "B"), 40)
    v = r["rolling_correlation"]["values"]
    assert len(v) == len(r["days"]) - 1
    assert all(x is None for x in v[:39]) and v[39] is not None
    # value at t equals the plain correlation of the trailing 40 returns, using nothing after t
    ra = np.diff([x.adj_close for x in a]) / np.array([x.adj_close for x in a][:-1])
    rb = np.diff([x.adj_close for x in b]) / np.array([x.adj_close for x in b][:-1])
    t = 100
    assert v[t] == pytest.approx(np.corrcoef(ra[t - 39 : t + 1], rb[t - 39 : t + 1])[0, 1], abs=1e-5)


def test_compare_validation():
    a = BARS["AAPL"][-100:]
    with pytest.raises(cmp.CompareError):
        cmp.compare({"A": a})
    with pytest.raises(cmp.CompareError):
        cmp.compare({f"S{i}": a for i in range(11)})
    with pytest.raises(cmp.CompareError):
        cmp.compare({"A": a, "B": BARS["MSFT"][-100:]}, ("A", "A"))
    with pytest.raises(cmp.CompareError):
        cmp.compare({"A": a, "B": BARS["MSFT"][-100:]}, ("A", "B"), 5)
    with pytest.raises(cmp.CompareError):
        cmp.compare({"A": a[:10], "B": BARS["MSFT"][-10:]})
