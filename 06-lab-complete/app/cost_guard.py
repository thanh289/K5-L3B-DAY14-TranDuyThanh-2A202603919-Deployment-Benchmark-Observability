"""
Cost guard (tiêu chí 8).

Yêu cầu:
  • Cộng dồn chi phí LLM (tính theo token) vào Redis
  • Tổng chi phí vượt DAILY_BUDGET_USD (hoặc MONTHLY_BUDGET_USD) → HTTP 402
"""

from datetime import datetime, timezone

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import r


# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _budget_key() -> str:
    return f"cost:{datetime.now(timezone.utc):%Y-%m-%d}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    try:
        spent = float(r.get(_budget_key()) or 0)
    except RedisError:
        raise HTTPException(status_code=503, detail="Cost guard unavailable") from None
    if spent >= settings.daily_budget_usd:
        raise HTTPException(status_code=402, detail="Daily budget exceeded")


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = input_tokens * PRICE_INPUT_PER_1K / 1000 + output_tokens * PRICE_OUTPUT_PER_1K / 1000
    try:
        key = _budget_key()
        with r.pipeline() as pipe:
            pipe.incrbyfloat(key, cost)
            pipe.expire(key, 2 * 24 * 60 * 60)
            pipe.execute()
    except RedisError:
        raise HTTPException(status_code=503, detail="Cost guard unavailable") from None
    return cost
