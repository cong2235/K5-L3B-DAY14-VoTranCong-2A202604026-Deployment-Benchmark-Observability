"""
API Key authentication (tiêu chí 6).

Yêu cầu:
  • Client gửi header  X-API-Key: <key>
  • Key phải trùng biến môi trường AGENT_API_KEY
  • Thiếu hoặc sai key → HTTP 401 (không phải 403 hay 422)

Quyết định thiết kế:
  • auto_error=False: nếu để mặc định, FastAPI tự trả 403 khi thiếu header. Ta cần 401 theo
    hợp đồng, nên tự raise.
  • Thiếu key và sai key đều 401 với cùng một thông báo: không cho kẻ tấn công biết key
    "gần đúng" hay không. (Bản demo ở Part 4 trả 403 cho key sai; ở đây theo hợp đồng của Part 6.)
  • secrets.compare_digest: so sánh thời gian hằng, tránh lộ key qua chênh lệch thời gian
    phản hồi (timing attack). So sánh bằng `==` dừng ở ký tự sai đầu tiên.
  • Server chưa cấu hình AGENT_API_KEY → từ chối tất cả (fail closed), không có key mặc định.
"""
import secrets

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(_api_key_header)) -> str:
    """Dependency cho FastAPI — dùng trong /ask: Depends(verify_api_key)."""
    expected = settings.agent_api_key
    valid = (
        bool(api_key)
        and bool(expected)
        and secrets.compare_digest(api_key.encode(), expected.encode())
    )
    if not valid:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Include header: X-API-Key: <key>",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key
