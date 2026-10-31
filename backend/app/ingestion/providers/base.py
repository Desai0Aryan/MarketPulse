from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Instrument:
    symbol: str
    name: str
    exchange: str
    currency: str
    kind: str  # "equity" | "index_proxy"
    sector: str | None = None


@dataclass(frozen=True)
class Bar:
    """One daily OHLCV observation. `adj_close` is split/dividend adjusted."""

    day: date
    open: float
    high: float
    low: float
    close: float
    adj_close: float
    volume: int


class MarketDataProvider(ABC):
    """Provider abstraction. Real providers (Alpha Vantage, Polygon, ...) implement this."""

    name: str
    data_class: str  # "live" | "delayed" | "historical" | "simulated"

    @abstractmethod
    def instruments(self) -> list[Instrument]: ...

    @abstractmethod
    def history(self, symbol: str, start: date | None = None, end: date | None = None) -> list[Bar]: ...

    def reference_day(self) -> date:
        """The 'today' used to judge data freshness. Real providers use the real date."""
        return date.today()

    def ping(self) -> bool:
        """Cheap connectivity check used by the pipeline monitor."""
        try:
            return len(self.instruments()) > 0
        except Exception:
            return False
