"""News ingestion: provider abstraction, validation, de-duplication, relevance and a deterministic sentiment baseline.

HONESTY RULES
* No article, source or publication time is invented. Two providers exist:
    - `file`   : reads REAL articles you supply as JSON Lines (one article per line); nothing is added or altered.
    - `sample` : demo feed. Its headlines are TEMPLATES filled with price moves that really are in the stored
                 (simulated) data. They are not published journalism: every record carries `simulated=true`, the
                 source is "MarketPulse Sample Feed (simulated)", and there is no URL.
  A live vendor integration (needs API credentials and a licence) plugs in by implementing `NewsProvider.fetch`.
* The sentiment method is a small word-list baseline. It is noisy, ignores context/sarcasm/numbers, and is NOT a
  predictor of returns. The method name and version are stored with every score.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from app.domain import Article, utcnow
from app.ingestion.providers.base import Instrument
from app.storage.base import Repository

SENTIMENT_METHOD = "lexicon-baseline"
SENTIMENT_VERSION = "1"
SENTIMENT_NOTICE = ("Headline sentiment comes from a simple word-list baseline. It is noisy, misses context and sarcasm, "
                    "and is not a reliable predictor of stock performance.")
SAMPLE_SOURCE = "MarketPulse Sample Feed (simulated)"
MAX_HEADLINE, MAX_SOURCE, MAX_SUMMARY = 300, 80, 2000

_POS = {"surge": 1.5, "surges": 1.5, "soar": 1.5, "soars": 1.5, "jump": 1.0, "jumps": 1.0, "rally": 1.2, "rallies": 1.2, "gain": 1.0, "gains": 1.0,
        "rise": 0.8, "rises": 0.8, "climb": 0.8, "climbs": 0.8, "beat": 1.2, "beats": 1.2, "record": 0.8, "growth": 0.8, "upgrade": 1.2,
        "upgrades": 1.2, "strong": 0.8, "profit": 0.8, "profits": 0.8, "outperform": 1.2, "bullish": 1.2, "boost": 1.0, "expands": 0.6, "wins": 0.8}
_NEG = {"plunge": 1.5, "plunges": 1.5, "tumble": 1.5, "tumbles": 1.5, "slump": 1.3, "slumps": 1.3, "drop": 1.0, "drops": 1.0, "fall": 0.8, "falls": 0.8,
        "slide": 0.8, "slides": 0.8, "miss": 1.2, "misses": 1.2, "downgrade": 1.2, "downgrades": 1.2, "weak": 0.8, "loss": 0.8, "losses": 0.8,
        "lawsuit": 1.0, "probe": 1.0, "recall": 1.0, "bearish": 1.2, "cuts": 0.8, "warning": 1.0, "warns": 1.0, "sinks": 1.3, "selloff": 1.3, "decline": 0.8, "declines": 0.8}
_NEGATORS = {"not", "no", "never", "without", "fails", "failed", "isn't", "wasn't", "won't"}


def score_text(text: str) -> tuple[float, str]:
    """Deterministic baseline in [-1, 1]. A negator in the previous two tokens flips a word's sign."""
    toks = re.findall(r"[a-z']+", text.lower())
    total = 0.0
    hits = 0.0
    for i, t in enumerate(toks):
        w = _POS[t] if t in _POS else -_NEG[t] if t in _NEG else 0.0
        if not w:
            continue
        if any(x in _NEGATORS for x in toks[max(0, i - 2) : i]):
            w = -w
        total += w
        hits += abs(w)
    score = 0.0 if hits == 0 else max(-1.0, min(1.0, total / (hits + 1.0)))
    cat = "positive" if score > 0.15 else "negative" if score < -0.15 else "neutral"
    return round(score, 4), cat


def dedup_key(headline: str, published_at: datetime) -> str:
    norm = re.sub(r"[^a-z0-9 ]", "", headline.lower())
    norm = " ".join(norm.split())
    return hashlib.sha1(f"{norm}|{published_at.astimezone(UTC).date()}".encode()).hexdigest()


def relevance(inst: Instrument, headline: str, summary: str, tagged: bool) -> float | None:
    """1.0 ticker in headline; 0.7 company name in headline; 0.4 in summary; 0.3 provider-tagged only; None otherwise."""
    h, s = headline.lower(), summary.lower()
    if re.search(rf"\b{re.escape(inst.symbol.lower())}\b", h):
        return 1.0
    first = re.sub(r"[^a-z0-9 ]", "", inst.name.lower()).split()
    key = first[0] if first else ""
    if key and len(key) > 3 and re.search(rf"\b{re.escape(key)}", h):
        return 0.7
    if re.search(rf"\b{re.escape(inst.symbol.lower())}\b", s) or (key and len(key) > 3 and key in s):
        return 0.4
    return 0.3 if tagged else None


@dataclass
class Rejected:
    reason: str
    raw: str


def normalize(raw: dict, instruments: dict[str, Instrument], provider: str, now: datetime, simulated: bool = False) -> Article | Rejected:
    """Validate one raw record. Never repairs data by guessing: unusable records are rejected with a reason."""
    if not isinstance(raw, dict):
        return Rejected("not an object", str(raw)[:80])
    headline = " ".join(str(raw.get("headline") or "").split())
    if not headline:
        return Rejected("missing headline", str(raw)[:80])
    if len(headline) > MAX_HEADLINE:
        return Rejected("headline too long", headline[:60])
    source = " ".join(str(raw.get("source") or "").split())
    if not source or len(source) > MAX_SOURCE:
        return Rejected("missing or invalid source", headline[:60])
    ts = raw.get("published_at")
    try:
        pub = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return Rejected("invalid published_at", headline[:60])
    if pub.tzinfo is None:
        return Rejected("published_at has no timezone", headline[:60])
    if pub > now + timedelta(hours=1):
        return Rejected("published_at is in the future", headline[:60])
    url = raw.get("url")
    if url is not None and not (isinstance(url, str) and re.match(r"^https?://[^\s]+$", url) and len(url) <= 1000):
        url = None  # an unusable link is dropped; the article itself is kept
    summary = " ".join(str(raw.get("summary") or "").split())[:MAX_SUMMARY]
    tagged = {str(s).upper() for s in raw.get("symbols") or [] if isinstance(s, str)}
    syms = []
    for sym, inst in instruments.items():
        r = relevance(inst, headline, summary, sym in tagged)
        if r is not None:
            syms.append({"symbol": sym, "relevance": r})
    return Article(0, dedup_key(headline, pub), provider, headline, source, pub.astimezone(UTC), url, summary, syms, simulated=simulated)


def score_article(a: Article, now: datetime | None = None) -> Article:
    score, cat = score_text(f"{a.headline}. {a.summary}")
    return replace(a, sentiment_score=score, sentiment_category=cat, sentiment_method=SENTIMENT_METHOD,
                   sentiment_version=SENTIMENT_VERSION, sentiment_at=now or utcnow())


# --------------------------------------------------------------------------- providers
class NewsProvider(Protocol):
    name: str
    simulated: bool

    def fetch(self) -> list[dict]: ...


class FileNewsProvider:
    """Reads real articles from a JSON Lines file. Malformed lines surface as rejections, not silent drops."""

    name = "file"
    simulated = False

    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def fetch(self) -> list[dict]:
        if not self.path.is_file():
            raise FileNotFoundError(f"News file not found: {self.path}")
        out: list[dict] = []
        for n, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                out.append({"_bad_line": n})
        return out


class SampleNewsProvider:
    """Demo feed built from price moves present in the stored data (see module docstring)."""

    name = "sample"
    simulated = True

    def __init__(self, repo: Repository, sessions: int = 60, min_move_pct: float = 3.0) -> None:
        self.repo, self.sessions, self.min_move = repo, sessions, min_move_pct

    def fetch(self) -> list[dict]:
        out: list[dict] = []
        for inst in self.repo.get_instruments():
            if inst.kind != "equity":
                continue
            bars = self.repo.get_bars(inst.symbol)[-(self.sessions + 1):]
            for prev, cur in zip(bars, bars[1:]):
                chg = (cur.close / prev.close - 1) * 100
                if abs(chg) < self.min_move:
                    continue
                up = chg > 0
                verb = ("surges" if chg > 6 else "rises") if up else ("plunges" if chg < -6 else "falls")
                # headline wording and an explicit "simulated" tag in the summary keep this from passing as journalism
                out.append({
                    "headline": f"{inst.name} shares {verb} {abs(chg):.1f}% in session",
                    "source": SAMPLE_SOURCE,
                    "published_at": datetime(cur.day.year, cur.day.month, cur.day.day, 21, 0, tzinfo=UTC).isoformat(),
                    "summary": f"Simulated demo item generated from the stored closing prices of {inst.symbol} ({prev.close:.2f} to {cur.close:.2f}). Not a real news report.",
                    "symbols": [inst.symbol],
                })
        return out


def refresh(repo: Repository, provider: NewsProvider, now: datetime | None = None) -> dict:
    now = now or utcnow()
    instruments = {i.symbol: i for i in repo.get_instruments()}
    arts: list[Article] = []
    rejected: list[dict] = []
    seen: set[str] = set()
    in_batch_dups = 0
    for raw in provider.fetch():
        if isinstance(raw, dict) and "_bad_line" in raw:
            rejected.append({"reason": f"line {raw['_bad_line']} is not valid JSON", "raw": ""})
            continue
        res = normalize(raw, instruments, provider.name, now, provider.simulated)
        if isinstance(res, Rejected):
            rejected.append({"reason": res.reason, "raw": res.raw})
            continue
        if res.dedup_key in seen:
            in_batch_dups += 1
            continue
        seen.add(res.dedup_key)
        arts.append(score_article(res, now))
    inserted, dups = repo.upsert_articles(arts)
    return {"provider": provider.name, "simulated": provider.simulated, "fetched": len(arts) + len(rejected) + in_batch_dups,
            "inserted": inserted, "duplicates": dups + in_batch_dups, "rejected": len(rejected), "rejections": rejected[:20], "notice": SENTIMENT_NOTICE}


def sentiment_summary(articles: list[Article]) -> dict:
    scored = [a for a in articles if a.sentiment_score is not None]
    counts = {"positive": 0, "neutral": 0, "negative": 0}
    for a in scored:
        counts[a.sentiment_category or "neutral"] += 1
    return {"articles": len(articles), "scored": len(scored), "counts": counts,
            "mean_score": round(sum(a.sentiment_score for a in scored) / len(scored), 4) if scored else None, "notice": SENTIMENT_NOTICE}
