import queue
from datetime import UTC, date, datetime

import pytest

from app.domain import utcnow
from app.ingestion.providers.mock import MockProvider
from app.services import events as ev
from app.services import news as nw
from app.services import research as rs
from app.services.llm import LlmError
from app.storage.memory import MemoryRepository

REF = date(2026, 10, 23)


def seeded():
    repo = MemoryRepository()
    p = MockProvider(REF, 500)
    repo.upsert_instruments(p.instruments())
    for i in p.instruments():
        repo.upsert_bars(i.symbol, p.history(i.symbol), None)
    nw.refresh(repo, nw.SampleNewsProvider(repo, sessions=400, min_move_pct=2.0), datetime(2026, 10, 24, tzinfo=UTC))
    return repo


REPO = seeded()


def ask(q, repo=REPO, owner="demo", llm=None):
    return rs.answer(repo, owner, q, REF, llm)


# ---------------- tools validate input ----------------
@pytest.mark.parametrize("fn,args", [
    (rs.tool_price_summary, ("NOPE", 30)), (rs.tool_price_summary, ("AAPL", 1)), (rs.tool_price_summary, ("AAPL", 99999)),
    (rs.tool_price_summary, ("AAPL", "90; DROP TABLE prices")), (rs.tool_compare, (["AAPL"], 30)), (rs.tool_compare, (["AAPL", "NOPE"], 30)),
    (rs.tool_compare, (["AAPL", "MSFT"], True)), (rs.tool_indicators, ("'; --",)),
])
def test_tools_reject_invalid_arguments(fn, args):
    with pytest.raises(rs.ToolError):
        fn(REPO, *args)


def test_price_summary_matches_stored_data():
    p = rs.tool_price_summary(REPO, "aapl", 60)
    bars = REPO.get_bars("AAPL")
    assert p["last_close"] == round(bars[-1].close, 2) and p["as_of"] == bars[-1].day.isoformat() and p["sessions"] == 61
    assert p["period_return"] == pytest.approx(bars[-1].adj_close / bars[-61].adj_close - 1, abs=1e-5)


# ---------------- planner + grounding ----------------
def test_compare_question_uses_compare_tool_and_stored_numbers():
    a = ask("Compare NVDA and AMD over the last 90 trading days")
    assert a["intent"] == "compare" and a["symbols"] == ["NVDA", "AMD"] and a["tools"][0]["tool"] == "compare" and a["tools"][0]["args"]["days"] == 90
    c = rs.tool_compare(REPO, ["NVDA", "AMD"], 90)
    assert f"{c['stats']['NVDA']['total_return'] * 100:+.2f}%" in " ".join(a["facts"])
    assert any(s["href"] == "/compare?symbols=NVDA,AMD" for s in a["sources"]) and a["range"]["as_of"] == REPO.get_bars("NVDA")[-1].day.isoformat()
    assert "does not show that one causes" in a["explanation"]


def test_indicator_question():
    a = ask("Show the latest RSI and MACD values for AAPL")
    ix = rs.tool_indicators(REPO, "AAPL")
    assert a["intent"] == "indicators" and f"RSI(14) {ix['rsi14']}" in a["facts"][0]


def test_company_name_alias_and_days_parsing():
    a = ask("How did Apple do over the last 3 months?")
    assert a["symbols"] == ["AAPL"] and a["tools"][0]["args"]["days"] == 63
    assert ask("Show AAPL over 2 weeks")["tools"][0]["args"]["days"] == 10
    assert ask("AAPL over 99999 days")["tools"][0]["args"]["days"] == rs.MAX_DAYS  # clamped, never rejected silently into nonsense


def test_drawdown_question_reports_trough_from_stored_prices():
    a = ask("Explain the recent drawdown in TSLA using the stored price history")
    p = rs.tool_price_summary(REPO, "TSLA", 90)
    assert a["intent"] == "drawdown" and p["drawdown_trough_day"] in " ".join(a["facts"]) and "describes what happened, not why" in a["explanation"]


def test_watchlist_volatility_uses_default_watchlist_and_ranks():
    a = ask("Which stocks in my watchlist have the highest historical volatility?")
    assert a["intent"] == "watchlist_volatility" and a["tools"][0]["tool"] == "watchlists" and a["tools"][1]["tool"] == "volatility_ranking"
    ranked = rs.tool_volatility_ranking(REPO, rs.tool_watchlists(REPO, "demo")["watchlists"][0]["symbols"], 90)["ranking"]
    assert ranked[0]["symbol"] in a["facts"][0].split("highest first): ")[1].split(" ")[0]
    vols = [r["annualized_volatility"] for r in ranked]
    assert vols == sorted(vols, reverse=True)


def test_news_summary_labels_simulated_items_and_notice():
    sym = next(a.symbols[0]["symbol"] for a in REPO.list_articles(limit=1)[0])
    a = ask(f"Summarize the latest available news for {sym}")
    assert a["intent"] == "news" and any("[simulated demo item]" in f for f in a["facts"]) and any("not a reliable predictor" in c for c in a["caveats"])
    assert any(s["type"] == "news" for s in a["sources"])


def test_pipeline_question():
    a = ask("Summarize the pipeline's data quality issues")
    assert a["intent"] == "pipeline" and any("stored daily bars" in f for f in a["facts"]) and a["sources"][0]["href"] == "/data-pipeline"


def test_saved_screens_question_runs_current_data_per_owner():
    repo = seeded()
    repo.create_screen("demo", "High RSI", {"filters": [{"field": "rsi14", "op": "gt", "value": 0}], "kind": "equity"})
    a = ask("Which of my saved screens currently match?", repo)
    assert a["intent"] == "screens" and "High RSI" in a["facts"][0] and "12 of 16" in a["facts"][0]
    assert "no saved screens" in ask("Which of my saved screens match?", repo, owner="someone-else")["facts"][0]


def test_glossary_answers_are_labelled_explanation_not_facts():
    a = ask("What does a moving-average crossover mean?")
    assert a["intent"] == "glossary" and a["facts"] == [] and "does not forecast" in a["explanation"] and a["tools"] == []


# ---------------- safety ----------------
@pytest.mark.parametrize("q", ["Should I buy NVDA?", "Will TSLA go up next week?", "Give me a price target for AAPL", "predict MSFT tomorrow"])
def test_advice_and_prediction_requests_are_refused_with_history_only(q):
    a = ask(q)
    assert a["refused"] and "can't predict" in a["facts"][0] and "does not predict future" in a["explanation"]
    assert all(t["tool"] == "price_summary" for t in a["tools"])


def test_unknown_or_empty_input_never_fabricates():
    a = ask("How is ZZZZ doing?")
    assert a["intent"] == "help" and a["symbols"] == [] and a["tools"] == [] and "stored data" in a["facts"][0]
    with pytest.raises(rs.ToolError):
        ask("   ")
    with pytest.raises(rs.ToolError):
        ask("x" * 600)


def test_sql_and_shell_text_is_just_text():
    a = ask("AAPL'; DROP TABLE prices; -- and rm -rf /")
    assert a["symbols"] == ["AAPL"] and len(REPO.get_bars("AAPL")) > 400  # nothing executed; only validated tools ran
    assert {t["tool"] for t in a["tools"]} <= {"price_summary"}


def test_demo_caveat_and_disclaimer_always_present():
    a = ask("Show AAPL")
    assert any("simulated demo data" in c for c in a["caveats"]) and any("Not investment advice" in c for c in a["caveats"])


# ---------------- optional LLM ----------------
class FakeLlm:
    def __init__(self, text=None, err=None):
        self.text, self.err, self.calls = text, err, []

    def explain(self, question, facts):
        self.calls.append(facts)
        if self.err:
            raise LlmError(self.err)
        return self.text


def test_llm_only_replaces_explanation_never_facts():
    base = ask("Compare NVDA and AMD")
    llm = FakeLlm("Both fell and rose together.")
    a = ask("Compare NVDA and AMD", llm=llm)
    assert a["facts"] == base["facts"] and a["explanation"] == "Both fell and rose together." and a["explanation_mode"] == "model-generated"
    assert llm.calls and "data" in llm.calls[0]  # it was given the tool results, nothing else


def test_llm_failure_falls_back_without_leaking_anything():
    a = ask("Compare NVDA and AMD", llm=FakeLlm(err="LLM provider returned HTTP 500"))
    assert a["explanation_mode"] == "deterministic" and a["llm_error"] == "LLM provider returned HTTP 500" and a["explanation"]


def test_llm_not_called_for_refusals_or_when_no_data():
    llm = FakeLlm("x")
    ask("Should I buy NVDA?", llm=llm)
    ask("hello there", llm=llm)
    assert llm.calls == []


# ---------------- SSE bus ----------------
def test_bus_publish_subscribe_and_isolation():
    bus = ev.EventBus()
    a, b = bus.subscribe(), bus.subscribe()
    assert bus.publish("ingestion", {"run": 1}) == 2
    assert a.get_nowait()["data"] == {"run": 1} and b.get_nowait()["event"] == "ingestion"
    bus.unsubscribe(b)
    assert bus.publish("x", {}) == 1 and bus.subscribers == 1


def test_slow_subscriber_is_dropped_not_blocking():
    bus = ev.EventBus()
    q = bus.subscribe()
    for i in range(ev._MAX_QUEUE + 5):
        bus.publish("tick", {"i": i})
    assert bus.subscribers == 0 and q.qsize() == ev._MAX_QUEUE


def test_sse_framing_and_stream_cleanup():
    frame = ev.format_sse({"id": 7, "event": "alert", "data": {"msg": "a\nb"}})
    assert frame == 'id: 7\nevent: alert\ndata: {"msg":"a\\nb"}\n\n'
    bus = ev.EventBus()
    g = ev.stream(bus, heartbeat_s=0.01)
    assert next(g) == "retry: 3000\n\n" and "event: hello" in next(g) and bus.subscribers == 1
    assert next(g) == ": heartbeat\n\n"  # idle -> heartbeat keeps proxies from closing the connection
    bus.publish("ingestion", {"run_id": 3})
    assert "event: ingestion" in next(g)
    g.close()  # client disconnect
    assert bus.subscribers == 0


def test_queue_import_used():
    assert isinstance(ev.EventBus().subscribe(), queue.Queue) and utcnow()
