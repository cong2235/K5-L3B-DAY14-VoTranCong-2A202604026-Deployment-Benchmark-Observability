"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

Yêu cầu:
  • Đọc REDIS_URL từ config
  • App vẫn phải KHỞI ĐỘNG ĐƯỢC khi Redis chưa sẵn sàng (đừng ping Redis lúc import)
  • redis_healthy() dùng cho GET /ready: Redis không kết nối được → False

Quyết định thiết kế:
  • redis.from_url() chỉ tạo connection pool, KHÔNG mở kết nối. Kết nối thật chỉ xảy ra ở lần
    gọi lệnh đầu tiên. Vì vậy import module này không bao giờ làm app sập khi Redis chưa lên,
    còn /health vẫn trả 200 (liveness không phụ thuộc Redis).
  • socket_connect_timeout / socket_timeout ngắn: khi Redis chết, /ready phải trả 503 nhanh
    thay vì treo hàng chục giây (platform sẽ coi probe là timeout).
"""
import redis
from fastapi import HTTPException

from app.config import settings

r = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=2,
    health_check_interval=30,
)


def store_unavailable() -> HTTPException:
    """
    Lỗi trả về khi cần Redis mà Redis không dùng được: 503, KHÔNG cho request đi tiếp.

    Vì sao chặn (fail closed) mà không bỏ qua (fail open)? Rate limit và cost guard là hai lớp
    bảo vệ tiền và tài nguyên. Nếu Redis chết mà ta cho qua, kẻ tấn công chỉ cần làm Redis
    chết (hoặc chờ nó chết) là gọi LLM không giới hạn. Chặn tạm thời an toàn hơn.
    """
    return HTTPException(
        status_code=503,
        detail="Service temporarily unavailable (state store unreachable). Retry shortly.",
        headers={"Retry-After": "5"},
    )


def redis_healthy() -> bool:
    """True nếu PING được Redis. Mọi lỗi kết nối → False (không raise)."""
    try:
        return bool(r.ping())
    except redis.RedisError:
        return False
