"""
Rate limiting (tiêu chí 7).

Yêu cầu:
  • Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request trong 60 giây (sliding window)
  • Vượt giới hạn → HTTP 429, nên kèm header Retry-After
  • State lưu trong Redis để mọi worker / instance dùng chung và vẫn còn sau khi
    restart agent (script chấm sẽ restart agent để kiểm tra)

Thiết kế:
  • Sliding window log bằng Redis sorted set: mỗi request là một phần tử, score = thời điểm (ms).
    Đếm số phần tử trong 60 giây gần nhất. Chính xác hơn "fixed window" (tránh dồn gấp đôi
    request quanh ranh giới phút).
  • Toàn bộ "xóa cũ → đếm → thêm" chạy trong MỘT Lua script, nên nguyên tử trong Redis. Nếu làm
    thành 3 lệnh riêng như gợi ý ZREMRANGEBYSCORE → ZCARD → ZADD, hai worker (chạy --workers 2)
    có thể cùng đọc "9/10" rồi cùng thêm, thành 11/10. Lua loại bỏ race này.
  • Thời gian lấy từ lệnh TIME của Redis chứ không phải đồng hồ của app: nhiều instance có thể
    lệch đồng hồ nhau, còn Redis chỉ có một đồng hồ.
  • Khóa Redis dùng hash của API key, không để key nguyên văn trong Redis (KEYS, MONITOR, dump).
"""
import hashlib
import uuid

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r, store_unavailable

WINDOW_SECONDS = 60

# Trả {1, còn_lại} nếu cho qua, {0, giây_chờ} nếu vượt giới hạn.
_SLIDING_WINDOW = r.register_script(
    """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local window = tonumber(ARGV[1]) * 1000
local limit = tonumber(ARGV[2])

redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, now - window)
local count = redis.call('ZCARD', KEYS[1])

if count >= limit then
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  local retry = math.ceil((tonumber(oldest[2]) + window - now) / 1000)
  if retry < 1 then retry = 1 end
  return {0, retry}
end

redis.call('ZADD', KEYS[1], now, ARGV[3])
redis.call('PEXPIRE', KEYS[1], window)
return {1, limit - count - 1}
"""
)


def check_rate_limit(key: str) -> None:
    """Gọi sau khi xác thực. Vượt giới hạn → 429 kèm Retry-After; Redis lỗi → 503."""
    limit = settings.rate_limit_per_minute
    redis_key = "rl:" + hashlib.sha256(key.encode()).hexdigest()[:24]
    # member phải duy nhất, nếu không hai request cùng mili-giây sẽ bị coi là một
    member = uuid.uuid4().hex
    try:
        allowed, value = _SLIDING_WINDOW(keys=[redis_key], args=[WINDOW_SECONDS, limit, member])
    except redis.RedisError:
        raise store_unavailable() from None

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "limit": limit,
                "window_seconds": WINDOW_SECONDS,
                "retry_after_seconds": value,
            },
            headers={
                "Retry-After": str(value),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
            },
        )
