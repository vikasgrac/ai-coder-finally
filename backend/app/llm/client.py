"""LLM client using LiteLLM → OpenRouter → Cerebras."""
import logging
import os
from typing import Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)

MODEL = "openrouter/openai/gpt-oss-120b"
_EXTRA_BODY = {"provider": {"order": ["cerebras"]}}

_MOCK_RESPONSE = {
    "message": "I'm your AI trading assistant. I've reviewed your portfolio. How can I help?",
    "trades": [{"ticker": "RELIANCE", "side": "buy", "quantity": 1}],
    "watchlist_changes": [],
}


class TradeAction(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float


class WatchlistChange(BaseModel):
    ticker: str
    action: Literal["add", "remove"]


class LLMResponse(BaseModel):
    message: str
    trades: list[TradeAction] = []
    watchlist_changes: list[WatchlistChange] = []


def _is_mock_mode() -> bool:
    return os.getenv("LLM_MOCK", "false").lower() == "true"


async def call_llm(messages: list[dict]) -> LLMResponse:
    """Call LLM asynchronously and return parsed structured response.

    Falls back to a mock response when LLM_MOCK=true.
    Handles malformed JSON gracefully.
    """
    if _is_mock_mode():
        return LLMResponse(**_MOCK_RESPONSE)

    try:
        from litellm import acompletion
        response = await acompletion(
            model=MODEL,
            messages=messages,
            response_format=LLMResponse,
            reasoning_effort="low",
            extra_body=_EXTRA_BODY,
        )
        raw = response.choices[0].message.content
        return LLMResponse.model_validate_json(raw)
    except Exception as exc:
        logger.error("LLM call failed: %s", exc, exc_info=True)
        return LLMResponse(
            message=f"I encountered an issue processing your request. Please try again.",
            trades=[],
            watchlist_changes=[],
        )
