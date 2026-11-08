from datetime import date
from decimal import Decimal as D

import pytest

from app.domain import ConflictError, LimitError, NotFoundError, Txn
from app.services import portfolio as pf
from app.storage.memory import MemoryRepository

DAY = date(2026, 3, 2)
AS_OF = date(2026, 10, 23)


def validate(full):
    pf.validate_history(full, AS_OF)


def dep(a):
    return Txn(0, 0, DAY, "deposit", amount=D(a))


def test_create_with_initial_cash_is_atomic_and_unique_per_owner():
    r = MemoryRepository()
    p = r.create_portfolio("me", "Growth", dep("5000"))
    assert pf.replay(r.list_txns("me", p.id)).cash == D("5000")
    with pytest.raises(ConflictError):
        r.create_portfolio("me", "growth")
    r.create_portfolio("you", "Growth")  # other owner may reuse the name
    for i in range(r.MAX_PORTFOLIOS - 1):
        r.create_portfolio("me", f"p{i}")
    with pytest.raises(LimitError):
        r.create_portfolio("me", "overflow")


def test_rejected_transaction_stores_nothing():
    r = MemoryRepository()
    p = r.create_portfolio("me", "P", dep("100"))
    bad = Txn(0, 0, DAY, "buy", "X", D(10), D(50))
    with pytest.raises(pf.PortfolioError):
        r.add_txn("me", p.id, bad, validate)
    assert len(r.list_txns("me", p.id)) == 1
    ok = r.add_txn("me", p.id, Txn(0, 0, DAY, "buy", "X", D(1), D(50)), validate)
    assert ok.id > 0 and pf.replay(r.list_txns("me", p.id)).cash == D("50")


def test_deleting_a_funding_deposit_is_refused_when_later_buys_depend_on_it():
    r = MemoryRepository()
    p = r.create_portfolio("me", "P", dep("100"))
    deposit_id = r.list_txns("me", p.id)[0].id
    r.add_txn("me", p.id, Txn(0, 0, DAY, "buy", "X", D(1), D(50)), validate)
    with pytest.raises(pf.PortfolioError):
        r.delete_txn("me", p.id, deposit_id, validate)
    assert len(r.list_txns("me", p.id)) == 2
    with pytest.raises(NotFoundError):
        r.delete_txn("me", p.id, 9999, validate)


def test_owner_isolation_for_portfolios():
    r = MemoryRepository()
    p = r.create_portfolio("alice", "A", dep("100"))
    for call in (lambda: r.get_portfolio("bob", p.id), lambda: r.list_txns("bob", p.id), lambda: r.delete_portfolio("bob", p.id),
                 lambda: r.add_txn("bob", p.id, dep("1"), validate)):
        with pytest.raises(NotFoundError):
            call()
    assert r.list_portfolios("bob") == []


def test_ledger_changes_do_not_alias_returned_objects():
    r = MemoryRepository()
    p = r.create_portfolio("me", "P", dep("100"))
    r.list_txns("me", p.id)[0].amount = D("999999")
    assert r.list_txns("me", p.id)[0].amount == D("100")


def test_future_dated_rejected_through_repo():
    r = MemoryRepository()
    p = r.create_portfolio("me", "P", dep("100"))
    with pytest.raises(pf.PortfolioError, match="after the latest data date"):
        r.add_txn("me", p.id, Txn(0, 0, date(2027, 1, 1), "deposit", amount=D(5)), validate)
