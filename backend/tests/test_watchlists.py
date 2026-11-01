import pytest

from app.domain import ConflictError, LimitError, NotFoundError
from app.ingestion.providers.mock import MockProvider
from app.services.watchlists import ensure_default
from app.storage.memory import MemoryRepository
from datetime import date


@pytest.fixture()
def repo():
    r = MemoryRepository()
    r.upsert_instruments(MockProvider(date(2026, 10, 23), 10).instruments())
    return r


def test_first_list_is_default_and_exactly_one_default(repo):
    a = repo.create_watchlist("u1", "Alpha")
    b = repo.create_watchlist("u1", "Beta")
    assert a.is_default and not b.is_default
    repo.update_watchlist("u1", b.id, make_default=True)
    assert [w.is_default for w in repo.list_watchlists("u1")] == [False, True]


def test_deleting_default_promotes_another(repo):
    a = repo.create_watchlist("u1", "Alpha")
    b = repo.create_watchlist("u1", "Beta")
    repo.delete_watchlist("u1", a.id)
    assert repo.list_watchlists("u1")[0].id == b.id and repo.list_watchlists("u1")[0].is_default


def test_duplicate_names_conflict_case_insensitive_and_rename(repo):
    repo.create_watchlist("u1", "Tech")
    with pytest.raises(ConflictError):
        repo.create_watchlist("u1", "tech")
    wl = repo.create_watchlist("u1", "Other")
    with pytest.raises(ConflictError):
        repo.update_watchlist("u1", wl.id, name="TECH")
    assert repo.update_watchlist("u1", wl.id, name="Energy").name == "Energy"
    repo.create_watchlist("u2", "Tech")  # same name for a different owner is fine


def test_items_add_is_idempotent_unknown_symbol_and_remove(repo):
    wl = repo.create_watchlist("u1", "L")
    repo.add_watchlist_item("u1", wl.id, "AAPL")
    again = repo.add_watchlist_item("u1", wl.id, "AAPL")
    assert again.symbols == ["AAPL"]
    with pytest.raises(NotFoundError):
        repo.add_watchlist_item("u1", wl.id, "NOPE")
    with pytest.raises(NotFoundError):
        repo.remove_watchlist_item("u1", wl.id, "MSFT")
    assert repo.remove_watchlist_item("u1", wl.id, "AAPL").symbols == []


def test_reorder_requires_exact_permutation(repo):
    wl = repo.create_watchlist("u1", "L")
    for s in ("AAPL", "MSFT", "NVDA"):
        repo.add_watchlist_item("u1", wl.id, s)
    assert repo.reorder_watchlist("u1", wl.id, ["NVDA", "AAPL", "MSFT"]).symbols == ["NVDA", "AAPL", "MSFT"]
    with pytest.raises(ConflictError):
        repo.reorder_watchlist("u1", wl.id, ["NVDA", "AAPL"])
    with pytest.raises(ConflictError):
        repo.reorder_watchlist("u1", wl.id, ["NVDA", "AAPL", "TSLA"])


def test_owner_isolation_every_operation(repo):
    wl = repo.create_watchlist("alice", "Private")
    repo.add_watchlist_item("alice", wl.id, "AAPL")
    assert repo.list_watchlists("mallory") == []
    ops = [
        lambda: repo.update_watchlist("mallory", wl.id, name="x"),
        lambda: repo.delete_watchlist("mallory", wl.id),
        lambda: repo.add_watchlist_item("mallory", wl.id, "MSFT"),
        lambda: repo.remove_watchlist_item("mallory", wl.id, "AAPL"),
        lambda: repo.reorder_watchlist("mallory", wl.id, ["AAPL"]),
    ]
    for op in ops:
        with pytest.raises(NotFoundError):
            op()
    assert repo.list_watchlists("alice")[0].symbols == ["AAPL"]  # untouched


def test_limits(repo):
    for i in range(repo.MAX_LISTS):
        repo.create_watchlist("u1", f"L{i}")
    with pytest.raises(LimitError):
        repo.create_watchlist("u1", "one-too-many")


def test_ensure_default_seeds_once_and_only_known_symbols(repo):
    ensure_default(repo)
    ensure_default(repo)
    lists = repo.list_watchlists("demo")
    assert len(lists) == 1 and lists[0].is_default and lists[0].symbols == ["NVDA", "AAPL", "MSFT", "AMD"]
    empty = MemoryRepository()
    ensure_default(empty)
    assert empty.list_watchlists("demo")[0].symbols == []
