from datetime import date, timedelta
from decimal import Decimal as D

import pytest

from app.domain import Txn
from app.ingestion.providers.base import Bar
from app.services import portfolio as pf

D1 = date(2026, 3, 2)


def T(kind, day=D1, sym=None, q="0", price="0", fee="0", amount="0", id=0):
    return Txn(id, 1, day, kind, sym, D(q), D(price), D(fee), D(amount))


def dep(amount, day=D1, id=0):
    return T("deposit", day, amount=amount, id=id)


def buy(sym, q, price, fee="0", day=D1, id=0):
    return T("buy", day, sym, q, price, fee, id=id)


def sell(sym, q, price, fee="0", day=D1, id=0):
    return T("sell", day, sym, q, price, fee, id=id)


def bars(closes, start=D1):
    return [Bar(start + timedelta(days=i), c, c, c, c, c, 1000) for i, c in enumerate(closes)]


def test_multiple_purchases_average_cost_fees_and_partial_sale():
    led = pf.replay([
        dep("10000", id=1), buy("AAPL", "10", "100", "5", id=2), buy("AAPL", "10", "120", "5", id=3),
    ])
    pos = led.positions["AAPL"]
    assert pos.quantity == 20 and pos.cost_basis == D("2210") and pos.avg_cost == D("110.5")  # fees capitalised
    assert led.cash == D("7790")

    led = pf.replay([dep("10000", id=1), buy("AAPL", "10", "100", "5", id=2), buy("AAPL", "10", "120", "5", id=3),
                     sell("AAPL", "5", "130", "2", day=D1 + timedelta(days=1), id=4)])
    pos = led.positions["AAPL"]
    assert pos.quantity == 15 and pos.cost_basis == D("1657.5")  # 2210 - 2210*5/20
    assert led.realized == D("95.5")  # (650-2) - 552.5
    assert led.cash == D("8438") and led.fees_paid == D("12")
    assert pos.avg_cost == D("110.5")  # average cost is unchanged by a sale


def test_full_sale_closes_position_and_keeps_realised():
    led = pf.replay([dep("1000"), buy("X", "4", "50"), sell("X", "4", "60")])
    assert "X" not in led.positions and led.realized == D("40") and led.cash == D("1040")
    assert led.realized_by_symbol == {"X": D("40")}


def test_loss_realised_negative():
    led = pf.replay([dep("1000"), buy("X", "10", "50"), sell("X", "10", "40", "1")])
    assert led.realized == D("-101")


@pytest.mark.parametrize(
    "txns,match",
    [
        ([dep("100"), sell("X", "1", "10")], "exceeds the 0 held"),
        ([dep("1000"), buy("X", "1", "10"), sell("X", "2", "10")], "exceeds the 1 held"),
        ([dep("100"), buy("X", "2", "60")], "only 100"),
        ([dep("100"), T("withdraw", amount="150")], "exceeds available cash"),
        ([buy("X", "1", "10")], "only 0"),
        ([dep("0")], "greater than zero"),
        ([dep("10"), buy("X", "0", "10")], "quantity"),
        ([dep("10"), buy("X", "1", "-1")], "price"),
        ([dep("10"), buy("X", "1", "1", "-1")], "fee"),
        ([dep("10"), buy("X", "1.0000001", "1")], "decimals"),
        ([Txn(0, 1, D1, "buy", None, D(1), D(1))], "symbol"),
        ([Txn(0, 1, D1, "gift", None)], "kind"),
        ([Txn(0, 1, D1, "deposit", None, amount=D("NaN"))], "finite"),
    ],
)
def test_invalid_entries_rejected(txns, match):
    with pytest.raises(pf.PortfolioError, match=match):
        pf.replay(txns)


def test_same_day_order_is_deposit_buy_sell_withdraw_regardless_of_entry_order():
    led = pf.replay([T("withdraw", amount="500", id=1), sell("X", "1", "10", id=2), buy("X", "1", "10", id=3), dep("510", id=4)])
    assert led.cash == D("10") and led.positions == {} and led.realized == 0


def test_backdated_entry_validated_against_whole_history():
    base = [dep("1500", id=1), buy("X", "10", "100", day=D1 + timedelta(days=5), id=2)]
    pf.validate_history(base)
    # A back-dated withdrawal that would leave the later buy unfunded must be refused...
    with pytest.raises(pf.PortfolioError):
        pf.validate_history(base + [T("withdraw", D1 + timedelta(days=1), amount="600")])
    # ...but an earlier buy that is fully funded is fine and changes the average cost correctly.
    ok = base + [buy("X", "5", "80", day=D1 + timedelta(days=2))]
    pf.validate_history(ok)
    assert pf.replay(ok).positions["X"].cost_basis == D("1400")
    # selling shares before they were bought is refused even though today's holdings would cover it
    with pytest.raises(pf.PortfolioError):
        pf.validate_history(base + [sell("X", "5", "100", day=D1 + timedelta(days=1))])


def test_future_dated_entries_rejected():
    with pytest.raises(pf.PortfolioError, match="after the latest data date"):
        pf.validate_history([dep("100", day=date(2026, 12, 1))], as_of=date(2026, 11, 1))


def test_valuation_separates_market_value_and_cost_basis():
    led = pf.replay([dep("10000", id=1), buy("AAPL", "10", "100", "5", id=2), buy("AAPL", "10", "120", "5", id=3),
                     sell("AAPL", "5", "130", "2", id=4)])
    as_of = D1 + timedelta(days=3)
    v = pf.value(led, {"AAPL": pf.Price(as_of, 125.0)}, as_of)
    assert v["positions_market_value"] == 1875 and v["invested_capital"] == 1657.5
    assert v["unrealized_pnl"] == 217.5 and v["realized_pnl"] == 95.5
    assert v["cash"] == 8438 and v["total_value"] == 10313
    assert v["total_pnl_vs_deposits"] == 313 == pytest.approx(217.5 + 95.5)  # realised + unrealised (fees already inside both)
    weights = {a["label"]: a["weight"] for a in v["allocation"]}
    assert sum(weights.values()) == pytest.approx(100, abs=0.02)
    assert v["complete"] and not v["notes"]


def test_missing_price_is_flagged_not_zeroed():
    led = pf.replay([dep("1000"), buy("A", "1", "100"), buy("B", "1", "100")])
    v = pf.value(led, {"A": pf.Price(D1, 110.0)}, D1)
    assert v["complete"] is False and v["missing_prices"] == ["B"]
    row = next(r for r in v["positions"] if r["symbol"] == "B")
    assert row["market_value"] is None and row["unrealized_pnl"] is None and row["weight"] is None
    assert v["positions_market_value"] == 110 and "No price available for B" in v["notes"][0]


def test_stale_price_flagged():
    led = pf.replay([dep("1000"), buy("A", "1", "100")])
    v = pf.value(led, {"A": pf.Price(D1, 100.0)}, D1 + timedelta(days=30))
    assert v["stale_prices"] == ["A"] and v["positions"][0]["stale"] is True


def test_latest_prices_never_uses_future_bars():
    b = {"A": bars([10, 11, 12])}
    assert pf.latest_prices(b, D1 + timedelta(days=1))["A"].close == 11
    assert "A" not in pf.latest_prices(b, D1 - timedelta(days=1))


# ---- performance ----
def test_performance_twr_ignores_deposits_and_matches_hand_calc():
    px = bars([100, 110, 99, 120, 120])
    bench = bars([50, 55, 55, 60, 60])
    txns = [dep("1000", id=1), buy("A", "10", "100", id=2),
            dep("1000", D1 + timedelta(days=2), id=3)]  # more cash on day 3, after a 10% gain then a 10% fall
    p = pf.performance(txns, {"A": px}, bench, "SPY")
    # day0: V=1000 (cash 0 + 10*100). day1: 10*110=1100 (+10%). day2: 990 + deposit 1000 = 1990 -> (1990-1000)/1100-1 = -10%
    assert p["value"][:3] == [1000.0, 1100.0, 1990.0]
    assert p["twr_index"][1] == pytest.approx(110.0) and p["twr_index"][2] == pytest.approx(99.0)
    # day3: 10*120 + 1000 = 2200; (2200 - 0)/1990 - 1
    assert p["twr_index"][3] == pytest.approx(99.0 * 2200 / 1990)
    assert p["benchmark_index"] == pytest.approx([100, 110, 110, 120, 120])
    assert p["stats"]["twr_return"] == pytest.approx(p["twr_index"][-1] / 100 - 1)
    assert pf.daily_change(p)["change"] == 0.0  # last day flat at 120/120


def test_fees_reduce_return_but_buying_does_not():
    px = bars([100, 100, 100])
    p = pf.performance([dep("1000", id=1), buy("A", "5", "100", "10", id=2)], {"A": px}, px, "SPY")
    assert p["value"][0] == 990.0  # 1000 - 10 fee
    p2 = pf.performance([dep("1000", id=1), buy("A", "5", "100", id=2)], {"A": px}, px, "SPY")
    assert p2["value"][0] == 1000.0 and p2["twr_index"] == [100.0, 100.0, 100.0]


def test_performance_historical_transactions_start_at_first_entry():
    px = bars([100, 101, 102, 103, 104])
    txns = [dep("500", D1 + timedelta(days=2), id=1), buy("A", "1", "102", day=D1 + timedelta(days=2), id=2)]
    p = pf.performance(txns, {"A": px}, px, "SPY")
    assert p["days"][0] == (D1 + timedelta(days=2)).isoformat() and len(p["days"]) == 3
    assert p["benchmark_index"][0] == 100.0


def test_performance_missing_price_history_skips_days_and_says_so():
    late = bars([100, 100, 100], start=D1 + timedelta(days=2))  # symbol data begins 2 days after the holding does
    bench = bars([10, 10, 10, 10, 10])
    txns = [dep("1000", id=1), buy("A", "1", "100", day=D1, id=2)]
    p = pf.performance(txns, {"A": late}, bench, "SPY")
    assert len(p["days"]) == 3 and any("skipped" in n for n in p["notes"])


def test_performance_empty_and_rebase():
    assert pf.performance([], {}, bars([1, 2]), "SPY")["notes"] == ["No transactions yet."]
    px = bars([100, 110, 121, 133.1])
    p = pf.performance([dep("1000", id=1), buy("A", "10", "100", id=2)], {"A": px}, px, "SPY")
    r = pf.rebase(p, D1 + timedelta(days=2))
    assert r["twr_index"][0] == 100.0 and r["twr_index"][1] == pytest.approx(110.0) and r["days"][0] == (D1 + timedelta(days=2)).isoformat()
