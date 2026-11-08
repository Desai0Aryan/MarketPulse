"""Paper-portfolio accounting. PURE functions: no I/O, no framework imports.

NOT a brokerage: balances are hypothetical.

Conventions (also in docs/api.md)
* Money uses Decimal; floats appear only at the API boundary.
* Cost basis: AVERAGE COST. A buy adds quantity*price + fee to the position's basis (fees are capitalised).
  A sell removes basis proportionally (basis * sold/held). Realised P&L = (quantity*price - fee) - basis removed.
* No short selling, no margin: a sell may not exceed holdings and cash may never go negative, at ANY point in
  history. Back-dated entries are therefore validated by replaying the whole ledger.
* Replay order: by day, then deposit < buy < sell < withdraw, then entry id. (So a same-day deposit funds a buy
  regardless of the order they were typed.)
* Valuation uses the latest stored close on or before the valuation day. A symbol with no price is reported as
  missing (never valued at zero); a price older than STALE_AFTER_DAYS is flagged stale.
* Performance is time-weighted: cash flows (deposits/withdrawals) are treated as happening at the END of their
  day, so day-t return = (V_t - F_t) / V_{t-1} - 1. Buying or selling alone does not change value; fees do.
  Dividends are not modelled (price return only), for both the portfolio and the benchmark.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.analytics import indicators as ind
from app.domain import Txn

ZERO = Decimal(0)
STALE_AFTER_DAYS = 5
MAX_QTY = Decimal("1000000000")
MAX_PRICE = Decimal("10000000")
_RANK = {"deposit": 0, "buy": 1, "sell": 2, "withdraw": 3}
KINDS = tuple(_RANK)


class PortfolioError(ValueError):
    """Invalid ledger entry or ledger state (HTTP 422)."""


def order_key(t: Txn) -> tuple:
    return (t.day, _RANK.get(t.kind, 9), t.id if t.id else 10**18)


@dataclass
class Position:
    symbol: str
    quantity: Decimal = ZERO
    cost_basis: Decimal = ZERO  # total, fees included

    @property
    def avg_cost(self) -> Decimal:
        return self.cost_basis / self.quantity if self.quantity else ZERO


@dataclass
class Ledger:
    cash: Decimal = ZERO
    positions: dict[str, Position] = field(default_factory=dict)
    realized: Decimal = ZERO
    realized_by_symbol: dict[str, Decimal] = field(default_factory=dict)
    net_contributions: Decimal = ZERO  # deposits - withdrawals
    fees_paid: Decimal = ZERO


def check_fields(t: Txn) -> None:
    if t.kind not in _RANK:
        raise PortfolioError(f"kind must be one of {list(KINDS)}")
    if not all(x.is_finite() for x in (t.quantity, t.price, t.fee, t.amount)):
        raise PortfolioError("numbers must be finite")
    if t.fee < 0:
        raise PortfolioError("fee must not be negative")
    if t.kind in ("deposit", "withdraw"):
        if t.amount <= 0:
            raise PortfolioError("amount must be greater than zero")
        if t.amount > MAX_PRICE * 100:
            raise PortfolioError("amount is unreasonably large")
        if t.symbol or t.quantity or t.price or t.fee:
            raise PortfolioError(f"{t.kind} entries take only an amount")
        return
    if not t.symbol:
        raise PortfolioError("symbol is required for buy/sell")
    if not (ZERO < t.quantity <= MAX_QTY):
        raise PortfolioError("quantity must be greater than zero")
    if not (ZERO < t.price <= MAX_PRICE):
        raise PortfolioError("price must be greater than zero")
    if t.quantity.as_tuple().exponent < -6 or t.price.as_tuple().exponent < -4 or t.fee.as_tuple().exponent < -4:
        raise PortfolioError("at most 6 decimals for quantity and 4 for price/fee")


def apply(led: Ledger, t: Txn) -> None:
    """Apply one entry, raising PortfolioError (and leaving `led` untouched) if it would be invalid."""
    check_fields(t)
    if t.kind == "deposit":
        led.cash += t.amount
        led.net_contributions += t.amount
        return
    if t.kind == "withdraw":
        if t.amount > led.cash:
            raise PortfolioError(f"Withdrawal of {t.amount} on {t.day} exceeds available cash {led.cash:.2f}")
        led.cash -= t.amount
        led.net_contributions -= t.amount
        return
    sym = t.symbol or ""
    gross = t.quantity * t.price
    if t.kind == "buy":
        cost = gross + t.fee
        if cost > led.cash:
            raise PortfolioError(f"Buying {t.quantity} {sym} on {t.day} costs {cost:.2f} but only {led.cash:.2f} cash is available")
        led.cash -= cost
        pos = led.positions.setdefault(sym, Position(sym))
        pos.quantity += t.quantity
        pos.cost_basis += cost
        led.fees_paid += t.fee
        return
    pos = led.positions.get(sym)
    held = pos.quantity if pos else ZERO
    if t.quantity > held:
        raise PortfolioError(f"Selling {t.quantity} {sym} on {t.day} exceeds the {held} held (short selling is not supported)")
    assert pos is not None
    proceeds = gross - t.fee
    if led.cash + proceeds < 0:
        raise PortfolioError(f"Fee on {t.day} exceeds the sale proceeds and available cash")
    basis_sold = pos.cost_basis if t.quantity == held else pos.cost_basis * t.quantity / held
    led.cash += proceeds
    led.realized += proceeds - basis_sold
    led.realized_by_symbol[sym] = led.realized_by_symbol.get(sym, ZERO) + proceeds - basis_sold
    led.fees_paid += t.fee
    pos.quantity -= t.quantity
    pos.cost_basis -= basis_sold
    if pos.quantity == 0:
        del led.positions[sym]


def replay(txns: list[Txn], upto: date | None = None) -> Ledger:
    """Rebuild state from the full history; raises if ANY point in history is invalid."""
    led = Ledger()
    for t in sorted(txns, key=order_key):
        if upto is not None and t.day > upto:
            break
        apply(led, t)
    return led


def validate_history(txns: list[Txn], as_of: date | None = None) -> None:
    """Passed to the repository so validation runs inside the same lock/DB transaction as the write."""
    if as_of is not None:
        late = [t for t in txns if t.day > as_of]
        if late:
            raise PortfolioError(f"Transaction date {late[0].day} is after the latest data date {as_of}")
    replay(txns)


# --------------------------------------------------------------------------- valuation
@dataclass(frozen=True)
class Price:
    day: date
    close: float


def latest_prices(bars_by_symbol: dict[str, list], as_of: date) -> dict[str, Price]:
    out = {}
    for s, bars in bars_by_symbol.items():
        days = [b.day for b in bars]
        i = bisect_right(days, as_of) - 1
        if i >= 0:
            out[s] = Price(bars[i].day, bars[i].close)
    return out


def _f(v: Decimal | float | None, d: int = 4) -> float | None:
    return None if v is None else round(float(v), d)


def value(led: Ledger, prices: dict[str, Price], as_of: date) -> dict:
    """Snapshot at `as_of`. Market value, cost basis and unrealised P&L are reported separately."""
    rows, missing, stale = [], [], []
    mv_total = cost_total = unreal_total = ZERO
    for sym in sorted(led.positions):
        pos = led.positions[sym]
        p = prices.get(sym)
        row = {"symbol": sym, "quantity": _f(pos.quantity, 6), "avg_cost": _f(pos.avg_cost), "cost_basis": _f(pos.cost_basis, 2),
               "price": None, "price_day": None, "stale": False, "market_value": None, "unrealized_pnl": None, "unrealized_pct": None,
               "realized_pnl": _f(led.realized_by_symbol.get(sym, ZERO), 2), "weight": None}
        cost_total += pos.cost_basis
        if p is None:
            missing.append(sym)
        else:
            mv = pos.quantity * Decimal(str(p.close))
            row.update(price=p.close, price_day=p.day.isoformat(), market_value=_f(mv, 2),
                       unrealized_pnl=_f(mv - pos.cost_basis, 2),
                       unrealized_pct=_f((mv / pos.cost_basis - 1) * 100, 2) if pos.cost_basis else None)
            if (as_of - p.day).days > STALE_AFTER_DAYS:
                row["stale"] = True
                stale.append(sym)
            mv_total += mv
            unreal_total += mv - pos.cost_basis
            row["_mv"] = mv
        rows.append(row)
    complete = not missing
    total = led.cash + mv_total
    for r in rows:
        mv = r.pop("_mv", None)
        r["weight"] = _f(mv / total * 100, 2) if mv is not None and total > 0 else None
    allocation = [{"label": r["symbol"], "value": r["market_value"], "weight": r["weight"]} for r in rows if r["market_value"] is not None]
    if total > 0:
        allocation.append({"label": "Cash", "value": _f(led.cash, 2), "weight": _f(led.cash / total * 100, 2)})
    return {
        "as_of": as_of.isoformat(),
        "cash": _f(led.cash, 2),
        "positions_market_value": _f(mv_total, 2),
        "total_value": _f(total, 2),
        "invested_capital": _f(cost_total, 2),  # cost basis of OPEN positions
        "net_deposits": _f(led.net_contributions, 2),
        "unrealized_pnl": _f(unreal_total, 2),
        "realized_pnl": _f(led.realized, 2),
        "fees_paid": _f(led.fees_paid, 2),
        "total_pnl_vs_deposits": _f(total - led.net_contributions, 2),
        "positions": rows,
        "largest_positions": sorted([r for r in rows if r["market_value"] is not None], key=lambda r: -r["market_value"])[:5],
        "allocation": allocation,
        "complete": complete,
        "missing_prices": missing,
        "stale_prices": stale,
        "notes": ([f"No price available for {', '.join(missing)}; they are excluded from market value and totals are incomplete."] if missing else [])
        + ([f"Prices for {', '.join(stale)} are more than {STALE_AFTER_DAYS} days old."] if stale else []),
    }


# --------------------------------------------------------------------------- history
def performance(txns: list[Txn], bars_by_symbol: dict[str, list], benchmark: list, benchmark_symbol: str) -> dict:
    """Daily portfolio value and time-weighted return vs a benchmark, on the benchmark's trading calendar."""
    out: dict = {"benchmark": benchmark_symbol, "days": [], "value": [], "net_deposits": [], "twr_index": [], "benchmark_index": [],
                 "drawdown": [], "stats": None, "notes": []}
    if not txns or not benchmark:
        out["notes"].append("No transactions yet." if not txns else "Benchmark data unavailable.")
        return out
    ordered = sorted(txns, key=order_key)
    first = ordered[0].day
    cal = [b for b in benchmark if b.day >= first]
    if not cal:
        out["notes"].append("All transactions are after the last benchmark date.")
        return out
    series_days = {s: [b.day for b in bars] for s, bars in bars_by_symbol.items()}
    led, ti = Ledger(), 0
    idx = 100.0
    prev_v: Decimal | None = None
    prev_nc = ZERO
    base_bench: float | None = None
    skipped = 0
    for b in cal:
        while ti < len(ordered) and ordered[ti].day <= b.day:
            apply(led, ordered[ti])
            ti += 1
        mv, ok = ZERO, True
        for sym, pos in led.positions.items():
            days = series_days.get(sym, [])
            i = bisect_right(days, b.day) - 1
            if i < 0:
                ok = False
                break
            mv += pos.quantity * Decimal(str(bars_by_symbol[sym][i].close))
        v = led.cash + mv
        if not ok:
            skipped += 1
            continue
        if prev_v is None:
            if v <= 0:
                continue
            base_bench = b.close
        else:
            flow = led.net_contributions - prev_nc
            idx *= float((v - flow) / prev_v) if prev_v > 0 else 1.0
        prev_v, prev_nc = v, led.net_contributions
        out["days"].append(b.day.isoformat())
        out["value"].append(_f(v, 2))
        out["net_deposits"].append(_f(led.net_contributions, 2))
        out["twr_index"].append(round(idx, 4))
        out["benchmark_index"].append(round(b.close / base_bench * 100, 4))  # type: ignore[operator]
    if skipped:
        out["notes"].append(f"{skipped} day(s) skipped because a held symbol had no price yet; returns are chained across the gap.")
    if out["days"]:
        out["drawdown"] = [round(float(x), 6) for x in ind.drawdown_series(out["twr_index"])]
        out["stats"] = {
            "twr_return": round(out["twr_index"][-1] / 100 - 1, 6),
            "benchmark_return": round(out["benchmark_index"][-1] / 100 - 1, 6),
            "max_drawdown": round(float(ind.max_drawdown(out["twr_index"])), 6),
            "sessions": len(out["days"]),
        }
    out["basis"] = ("Time-weighted return on closing prices; deposits/withdrawals excluded from returns; dividends not modelled; "
                    f"benchmark {benchmark_symbol} is a price series.")
    return out


def rebase(perf: dict, start: date | None) -> dict:
    """Re-base index series to 100 at `start` (valid for time-weighted returns)."""
    if not start or not perf["days"]:
        return perf
    i = next((k for k, d in enumerate(perf["days"]) if d >= start.isoformat()), None)
    if i is None:
        return perf
    out = {**perf}
    for k in ("days", "value", "net_deposits", "drawdown"):
        out[k] = perf[k][i:]
    for k in ("twr_index", "benchmark_index"):
        b = perf[k][i]
        out[k] = [round(x / b * 100, 4) for x in perf[k][i:]]
    out["drawdown"] = [round(float(x), 6) for x in ind.drawdown_series(out["twr_index"])]
    out["stats"] = {
        "twr_return": round(out["twr_index"][-1] / 100 - 1, 6),
        "benchmark_return": round(out["benchmark_index"][-1] / 100 - 1, 6),
        "max_drawdown": round(float(ind.max_drawdown(out["twr_index"])), 6),
        "sessions": len(out["days"]),
    }
    return out


def daily_change(perf: dict) -> dict | None:
    """Latest session's value change excluding cash flows: V_t - V_{t-1} - F_t."""
    if len(perf["days"]) < 2:
        return None
    v1, v0 = perf["value"][-1], perf["value"][-2]
    flow = perf["net_deposits"][-1] - perf["net_deposits"][-2]
    chg = v1 - v0 - flow
    return {"day": perf["days"][-1], "change": round(chg, 2), "change_pct": round(chg / v0 * 100, 2) if v0 else None}
