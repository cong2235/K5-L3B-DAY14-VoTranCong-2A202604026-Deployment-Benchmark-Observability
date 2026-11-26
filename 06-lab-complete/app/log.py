"""
Structured logging (tiêu chí 10): mỗi dòng log của app là đúng 1 JSON object.

Dùng một logger riêng tên "agent", có handler và formatter riêng, và không lan lên root logger
(propagate=False). Nhờ vậy:
  • log của uvicorn giữ nguyên định dạng của nó, không bị trộn vào;
  • không phụ thuộc thứ tự import. Lỗi ở Part 1 xảy ra vì `logging.basicConfig()` bị vô hiệu
    khi có module khác đã log trước, ở đây ta gắn handler trực tiếp nên không bị.

Cách dùng:  log_event("request", path="/ask", status=200, ms=12.3)
"""
import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "lvl": record.levelname,
            "event": record.getMessage(),
        }
        payload.update(getattr(record, "fields", {}))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # default=str: field lạ (datetime, Decimal...) không làm vỡ dòng log
        return json.dumps(payload, ensure_ascii=False, default=str)


def _build_logger() -> logging.Logger:
    lg = logging.getLogger("agent")
    if not lg.handlers:  # tránh gắn handler hai lần nếu module bị import lại
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        lg.addHandler(handler)
    lg.setLevel(logging.INFO)
    lg.propagate = False
    return lg


logger = _build_logger()


def log_event(event: str, level: int = logging.INFO, **fields) -> None:
    """Ghi một sự kiện. KHÔNG truyền secret (API key, nội dung câu hỏi) vào fields."""
    logger.log(level, event, extra={"fields": fields})
