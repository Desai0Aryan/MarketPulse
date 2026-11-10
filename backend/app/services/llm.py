"""Optional LLM used ONLY to phrase an explanation of facts that deterministic tools already retrieved.

The model receives the tool results as JSON and may not call tools, run SQL or touch the network beyond this one
request. Its output is shown separately from the facts and labelled "model-generated". Errors never include the API
key. NOTE: this HTTP call has not been executed in the build sandbox (no network/key); the copilot is fully
functional without it.
"""

from __future__ import annotations

import json
from typing import Protocol

SYSTEM = (
    "You are a cautious market-data explainer inside a research tool. Use ONLY the JSON facts provided; never add numbers, "
    "dates, companies or news that are not in them. Do not give buy/sell advice, price targets or predictions. Do not claim that "
    "correlation implies causation. Say what the data cannot show. Plain language, at most 120 words. If the facts are "
    "insufficient, say so."
)


class LlmError(RuntimeError):
    pass


class LlmClient(Protocol):
    def explain(self, question: str, facts: dict) -> str: ...


class AnthropicClient:
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, model: str, timeout: float = 20.0) -> None:
        self._key, self.model, self.timeout = api_key, model, timeout

    def explain(self, question: str, facts: dict) -> str:
        import httpx  # lazy: only needed when a key is configured

        body = {"model": self.model, "max_tokens": 400, "system": SYSTEM,
                "messages": [{"role": "user", "content": f"Question: {question[:500]}\n\nFacts (JSON):\n{json.dumps(facts, default=str)[:12000]}"}]}
        try:
            r = httpx.post(self.URL, json=body, timeout=self.timeout,
                           headers={"x-api-key": self._key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        except httpx.HTTPError as e:
            raise LlmError(f"LLM request failed ({type(e).__name__})") from None
        if r.status_code != 200:
            raise LlmError(f"LLM provider returned HTTP {r.status_code}")
        try:
            parts = r.json()["content"]
            return "".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()
        except (KeyError, ValueError, TypeError):
            raise LlmError("LLM response was not in the expected format") from None
