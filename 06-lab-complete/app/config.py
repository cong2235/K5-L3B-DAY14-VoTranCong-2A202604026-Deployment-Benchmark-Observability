"""
Config — 12-Factor: mọi cấu hình đọc từ biến môi trường (tiêu chí 9).

Nguyên tắc:
  • Không có secret nào nằm trong code. AGENT_API_KEY mặc định là chuỗi rỗng, nghĩa là
    "chưa cấu hình" và khi đó MỌI request vào /ask bị từ chối (xem auth.py), chứ không
    rơi về một key mặc định ai cũng biết.
  • Giá trị sai (vd RATE_LIMIT_PER_MINUTE=abc) làm app dừng ngay lúc khởi động với thông báo
    rõ ràng, thay vì chạy sai âm thầm (fail fast).
  • REDIS_URL luôn có giá trị hợp lệ. Việc kết nối KHÔNG xảy ra ở đây (xem redis_client.py).
"""
import os
from dataclasses import dataclass, field


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"Biến môi trường {name}={raw!r} phải là số nguyên") from None


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"Biến môi trường {name}={raw!r} phải là số") from None


@dataclass(frozen=True)
class Settings:
    # default_factory: đọc env lúc tạo object, không phải lúc định nghĩa class
    port: int = field(default_factory=lambda: _env_int("PORT", 8000))
    environment: str = field(default_factory=lambda: _env_str("ENVIRONMENT", "development"))
    agent_api_key: str = field(default_factory=lambda: _env_str("AGENT_API_KEY", ""))
    redis_url: str = field(default_factory=lambda: _env_str("REDIS_URL", "redis://localhost:6379/0"))
    rate_limit_per_minute: int = field(default_factory=lambda: _env_int("RATE_LIMIT_PER_MINUTE", 10))
    daily_budget_usd: float = field(default_factory=lambda: _env_float("DAILY_BUDGET_USD", 1.0))
    app_version: str = field(default_factory=lambda: _env_str("APP_VERSION", "1.0.0"))

    def validate(self) -> "Settings":
        if self.rate_limit_per_minute < 1:
            raise ValueError("RATE_LIMIT_PER_MINUTE phải >= 1")
        if self.daily_budget_usd < 0:
            raise ValueError("DAILY_BUDGET_USD phải >= 0")
        if self.environment == "production" and not self.agent_api_key:
            raise ValueError("AGENT_API_KEY phải được đặt khi ENVIRONMENT=production")
        return self


settings = Settings().validate()
