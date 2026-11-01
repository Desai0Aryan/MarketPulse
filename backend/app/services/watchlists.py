from __future__ import annotations

from app.storage.base import Repository

DEMO_OWNER = "demo"
STARTER_SYMBOLS = ["NVDA", "AAPL", "MSFT", "AMD"]


def ensure_default(repo: Repository, owner: str = DEMO_OWNER) -> None:
    """First run only: give the demo profile one editable starter list so the UI is not empty."""
    if repo.list_watchlists(owner):
        return
    wl = repo.create_watchlist(owner, "My Watchlist")
    known = {i.symbol for i in repo.get_instruments()}
    for sym in STARTER_SYMBOLS:
        if sym in known:
            repo.add_watchlist_item(owner, wl.id, sym)
