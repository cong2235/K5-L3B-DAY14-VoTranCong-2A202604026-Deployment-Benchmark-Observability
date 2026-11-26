"""
Cost guard (tiêu chí 8).

Yêu cầu:
  • Cộng dồn chi phí LLM (tính theo token) vào Redis
  • Tổng chi phí vượt DAILY_BUDGET_USD (hoặc MONTHLY_BUDGET_USD) → HTTP 402

Thiết kế:
  • Một bộ đếm USD cho mỗi ngày UTC: khóa `cost:YYYY-MM-DD`. Sang ngày mới là khóa mới bắt đầu từ
    0 nên không cần job reset; TTL 2 ngày để Redis tự dọn khóa cũ.
  • check_budget() chạy TRƯỚC khi gọi LLM (chặn sớm, không tốn tiền cho request đã biết là bị từ
    chối); record_cost() chạy SAU khi gọi (lúc đó mới biết số token thật).
  • Cộng dồn bằng INCRBYFLOAT: nguyên tử, nhiều worker/instance cộng chung một bộ đếm.
  • Giới hạn đã biết: kiểm tra trước, ghi nhận sau, nên N request chạy đồng thời đều có thể
    cùng qua kiểm tra khi còn sát ngưỡng và vượt budget tối đa khoảng N x chi phí một request.
    Với giá cỡ 1e-5 USD/request thì sai lệch không đáng kể; muốn chặt hơn phải "đặt trước"
    (reserve) chi phí ước tính trước khi gọi.
  • Redis lỗi → 503 (fail closed), cùng lý do như rate limiter.
"""
import time

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r, store_unavailable

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

_KEY_TTL_SECONDS = 2 * 24 * 3600


def _today_key() -> str:
    return "cost:" + time.strftime("%Y-%m-%d", time.gmtime())


def estimate_tokens(text: str) -> int:
    """Ước lượng thô ~4 ký tự / token (mock LLM không trả số token thật)."""
    return max(1, len(text) // 4)


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    try:
        spent = float(r.get(_today_key()) or 0.0)
    except redis.RedisError:
        raise store_unavailable() from None

    if spent >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Daily budget exceeded",
                "spent_usd": round(spent, 6),
                "budget_usd": settings.daily_budget_usd,
                "resets_at": "00:00 UTC",
            },
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = (input_tokens / 1000) * PRICE_INPUT_PER_1K + (output_tokens / 1000) * PRICE_OUTPUT_PER_1K
    key = _today_key()
    try:
        pipe = r.pipeline()
        pipe.incrbyfloat(key, cost)
        pipe.expire(key, _KEY_TTL_SECONDS)
        pipe.execute()
    except redis.RedisError:
        raise store_unavailable() from None
    return cost
