from datetime import date, timedelta

import numpy as np
import pytest

from app.domain import Alert, NotFoundError, utcnow
from app.ingestion.providers.base import Bar
from app.services import alerts as al
from app.storage.memory import MemoryRepository

D0 = date(2026, 1, 5)


def mk(closes, vols=None, start=D0):
    vols = vols or [1000] * len(closes)
    return [Bar(start + timedelta(days=i), c, c, c, c, c, v) for i, (c, v) in enumerate(zip(closes, vols))]


def alert(kind, thr, bars_at_creation, window=None, cooldown=0):
    return al.new_alert("me", "X", kind, thr, window, cooldown, "", bars_at_creation)


def run(a, bars):
    ev = al.evaluate(a, bars)
    return ev


def apply_state(a, ev):
    a.last_observed_day, a.last_condition = ev.last_observed_day, ev.last_condition
    a.fired_in_episode, a.last_fired_day = ev.fired_in_episode, ev.last_fired_day
    return a


# ---- definition validation ----
@pytest.mark.parametrize(
    "kind,thr,win,cd",
    [("nope", 1, None, 1), ("price_above", 0, None, 1), ("price_above", float("nan"), None, 1), ("price_above", True, None, 1),
     ("rsi_above", 101, None, 1), ("rsi_below", -1, None, 1), ("change_pct_above", 5000, None, 1), ("rel_volume_above", 0, None, 1),
     ("cross_above_sma", 0, None, 1), ("cross_above_sma", 0, 3, 1), ("price_above", 10, None, 99)],
)
def test_invalid_definitions(kind, thr, win, cd):
    with pytest.raises(al.AlertError):
        al.validate_definition(kind, thr, win, cd)


def test_no_data_rejected():
    with pytest.raises(al.AlertError, match="No stored data"):
        alert("price_above", 10, mk([1.0]))


# ---- edge-triggered level alerts ----
def test_fires_once_on_false_to_true_then_not_while_true():
    bars = mk([90, 95, 99])
    a = alert("price_above", 100, bars)
    assert a.last_condition is False and a.last_observed_day == bars[-1].day
    bars += mk([101, 105, 110], start=bars[-1].day + timedelta(days=1))  # crosses on first new session, stays above
    ev = run(a, bars)
    assert [e["observed_day"] for e in ev.events] == [D0 + timedelta(days=3)]
    assert ev.events[0]["observed_value"] == 101 and "closed at 101.00" in ev.events[0]["message"]
    assert ev.fired_in_episode and ev.last_condition is True


def test_already_true_at_creation_does_not_fire_until_reset():
    bars = mk([120, 121])
    a = alert("price_above", 100, bars)
    assert a.last_condition is True and a.to_dict()["waiting_for_reset"] is True
    more = bars + mk([122, 123], start=bars[-1].day + timedelta(days=1))
    assert run(a, more).events == []  # still true: no event
    more += mk([95, 105], start=more[-1].day + timedelta(days=1))  # clears, then re-occurs
    ev = run(a, more)
    assert len(ev.events) == 1 and ev.events[0]["observed_value"] == 105


def test_repeated_evaluation_same_data_never_duplicates():
    bars = mk([90, 95])
    a = alert("price_above", 100, bars)
    bars += mk([101], start=bars[-1].day + timedelta(days=1))
    ev = run(a, bars)
    assert len(ev.events) == 1
    apply_state(a, ev)
    for _ in range(5):  # simulated repeated ingestion cycles with no new session
        again = run(a, bars)
        assert again.events == []


def test_no_lookahead_only_sessions_after_last_observed():
    bars = mk([90, 95, 101, 90])  # a spike above 100 existed BEFORE the alert was created
    a = alert("price_above", 100, bars)
    assert run(a, bars).events == []


def test_multiple_sessions_between_evaluations_replayed_in_order():
    bars = mk([90, 95])
    a = alert("price_above", 100, bars, cooldown=0)
    bars += mk([101, 99, 102], start=bars[-1].day + timedelta(days=1))  # two separate crossings in the gap
    ev = run(a, bars)
    assert [e["observed_value"] for e in ev.events] == [101, 102]


def test_cooldown_suppresses_close_refires():
    bars = mk([90, 95])
    a = alert("price_above", 100, bars, cooldown=5)
    bars += mk([101, 99, 102, 98, 103], start=bars[-1].day + timedelta(days=1))
    ev = run(a, bars)
    assert [e["observed_value"] for e in ev.events] == [101]  # 102 (1d later) and 103 (3d later) are within 5 days
    a0 = alert("price_above", 100, mk([90, 95]), cooldown=5)
    far = mk([90, 95]) + mk([101] + [99] * 6 + [102], start=D0 + timedelta(days=2))
    assert [e["observed_value"] for e in run(a0, far).events] == [101, 102]  # 7 days apart


def test_below_change_rsi_and_volume_kinds():
    a = alert("price_below", 100, mk([110, 105]))
    assert run(a, mk([110, 105, 99])).events[0]["observed_value"] == 99

    a = alert("change_pct_above", 5, mk([100, 101]))
    ev = run(a, mk([100, 101, 108]))
    assert ev.events[0]["observed_value"] == pytest.approx((108 / 101 - 1) * 100, abs=1e-3)
    a = alert("change_pct_below", -5, mk([100, 101]))
    assert run(a, mk([100, 101, 90])).events[0]["observed_value"] < -5

    rng = np.random.default_rng(3)
    drift = list(100 + np.cumsum(rng.normal(0, 1, 60)))
    bars = mk(drift)
    a = alert("rsi_above", 70, bars)
    rally = mk([drift[-1] + 3 * (i + 1) for i in range(15)], start=bars[-1].day + timedelta(days=1))
    ev = run(a, bars + rally)
    assert len(ev.events) == 1 and ev.events[0]["observed_value"] > 70 and "RSI(14)" in ev.events[0]["message"]

    vols = [1000] * 40
    bars = mk([10] * 40, vols)
    a = alert("rel_volume_above", 2, bars)
    ev = run(a, bars + mk([10], [2500], start=bars[-1].day + timedelta(days=1)))
    assert ev.events[0]["observed_value"] == 2.5 and "2.50x" in ev.events[0]["message"]


def test_sma_crossings_are_edge_events():
    base = [100.0] * 30
    a = alert("cross_above_sma", 0, mk(base + [95]), window=10)
    bars = mk(base + [95, 96, 104, 105, 106])  # crosses up once on 104
    ev = run(a, bars)
    assert [e["observed_value"] for e in ev.events] == [104] and "crossed above its 10-session average" in ev.events[0]["message"]
    b = alert("cross_below_sma", 0, mk(base + [105]), window=10)
    ev = run(b, mk(base + [105, 104, 90, 89]))
    assert [e["observed_value"] for e in ev.events] == [90]


def test_cross_not_defined_without_enough_history():
    a = alert("cross_above_sma", 0, mk([10, 11, 12]), window=20)
    assert run(a, mk([10, 11, 12, 13, 14])).events == []


# ---- repository + engine integration ----
def seed_repo(closes):
    repo = MemoryRepository()
    from app.ingestion.providers.base import Instrument

    repo.upsert_instruments([Instrument("X", "X Corp", "NASDAQ", "USD", "equity")])
    repo.upsert_bars("X", mk(closes), None)
    return repo


def test_evaluate_all_records_events_and_is_idempotent():
    repo = seed_repo([90, 95, 97])
    a = repo.create_alert("me", alert("price_above", 100, repo.get_bars("X")))
    assert al.evaluate_all(repo) == {"alerts_checked": 1, "events_created": 0}
    repo.upsert_bars("X", mk([101], start=D0 + timedelta(days=3)), None)
    assert al.evaluate_all(repo)["events_created"] == 1
    for _ in range(3):
        assert al.evaluate_all(repo)["events_created"] == 0
    evs = repo.list_events("me")
    assert len(evs) == 1 and evs[0].observed_day == D0 + timedelta(days=3) and evs[0].observed_value == 101
    assert repo.get_alert("me", a.id).status == "triggered"
    assert repo.unread_count("me") == 1 and repo.mark_events_read("me", None) == 1 and repo.unread_count("me") == 0


def test_stale_evaluator_cannot_double_fire():
    repo = seed_repo([90, 95])
    a = repo.create_alert("me", alert("price_above", 100, repo.get_bars("X")))
    repo.upsert_bars("X", mk([101], start=D0 + timedelta(days=2)), None)
    stale_view = repo.get_alert("me", a.id)
    ev = al.evaluate(stale_view, repo.get_bars("X"))
    assert repo.record_evaluation(a.id, stale_view.last_observed_day, ev, utcnow()) is True
    assert repo.record_evaluation(a.id, stale_view.last_observed_day, ev, utcnow()) is False  # second writer loses
    assert len(repo.list_events("me")) == 1


def test_paused_alerts_not_evaluated_and_owner_isolation():
    repo = seed_repo([90, 95])
    a = repo.create_alert("alice", alert("price_above", 100, repo.get_bars("X")))
    repo.update_alert("alice", a.id, {"enabled": False})
    repo.upsert_bars("X", mk([101], start=D0 + timedelta(days=2)), None)
    assert al.evaluate_all(repo)["alerts_checked"] == 0
    with pytest.raises(NotFoundError):
        repo.get_alert("bob", a.id)
    with pytest.raises(NotFoundError):
        repo.delete_alert("bob", a.id)
    assert repo.list_alerts("bob") == [] and repo.list_events("bob") == []
    assert repo.mark_events_read("bob", None) == 0


def test_resume_rebaselines_so_missed_sessions_do_not_fire():
    repo = seed_repo([90, 95])
    a = repo.create_alert("me", alert("price_above", 100, repo.get_bars("X")))
    repo.update_alert("me", a.id, {"enabled": False})
    repo.upsert_bars("X", mk([101, 102], start=D0 + timedelta(days=2)), None)
    cur = repo.get_alert("me", a.id)
    b = al.baseline(cur, repo.get_bars("X"))
    repo.update_alert("me", a.id, {"enabled": True, "last_observed_day": b.last_observed_day, "last_condition": b.last_condition, "fired_in_episode": False})
    assert al.evaluate_all(repo)["events_created"] == 0
    assert repo.get_alert("me", a.id).to_dict()["waiting_for_reset"] is True


def test_limits():
    repo = seed_repo([90, 95])
    base = alert("price_above", 100, repo.get_bars("X"))
    for _ in range(repo.MAX_ALERTS):
        repo.create_alert("me", base)
    from app.domain import LimitError

    with pytest.raises(LimitError):
        repo.create_alert("me", base)
    assert isinstance(base, Alert) and base.status == "active"
