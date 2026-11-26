"""
Production AI Agent — Part 6 Final Project

Chạy:  uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
Chấm:  python check_production_ready.py
"""
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, estimate_tokens, record_cost
from app.log import log_event
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import ask as llm_ask

START_TIME = time.time()
_accepting = False  # False khi đang khởi động hoặc đang tắt → /ready trả 503


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Vòng đời app (tiêu chí 11 — Graceful shutdown).

    Ta KHÔNG tự đăng ký signal handler cho SIGTERM. Uvicorn đã bắt SIGTERM và làm đúng thứ tự:
    đóng cổng lắng nghe (ngừng nhận kết nối mới) → chờ request đang chạy xong → chạy phần dưới
    `yield` này → thoát với exit code 0. Tự viết handler mà quên gọi lại handler cũ của uvicorn
    sẽ làm process không bao giờ tắt (docker stop phải chờ rồi SIGKILL, exit 137).
    Phần việc của ta chỉ là dọn dẹp tài nguyên mình sở hữu: đóng connection pool Redis.
    """
    global _accepting
    log_event("startup", env=settings.environment, port=settings.port, version=settings.app_version)
    if settings.environment != "production" and not settings.agent_api_key:
        log_event("config_warning", level=logging.WARNING,
                  msg="AGENT_API_KEY chua duoc dat: moi request /ask se bi tu choi (401)")
    _accepting = True

    yield

    _accepting = False
    log_event("shutdown_begin")
    try:
        r.close()
    except Exception as e:  # dọn dẹp không được làm hỏng quá trình tắt
        log_event("shutdown_error", level=logging.WARNING, error=type(e).__name__)
    log_event("shutdown_complete")


app = FastAPI(
    title="Production AI Agent",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)


@app.middleware("http")
async def access_log(request: Request, call_next):
    """Mỗi request một dòng log JSON: path, status, thời gian. Không log header/body (có thể chứa key)."""
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        # /health bị platform gọi liên tục (vài giây một lần): bỏ qua cho đỡ nhiễu
        if request.url.path != "/health":
            log_event("request", method=request.method, path=request.url.path, status=status,
                      ms=round((time.perf_counter() - started) * 1000, 1))


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


@app.get("/health")
def health():
    """
    Liveness: "process còn sống không?" Luôn 200 khi process chạy được.
    Cố ý KHÔNG kiểm tra Redis: nếu Redis chết mà /health trả lỗi, platform sẽ restart agent
    liên tục dù restart không sửa được gì (Redis mới là thứ hỏng).
    """
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "version": settings.app_version,
        "environment": settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready")
def ready():
    """
    Readiness: "có nên gửi traffic vào instance này không?"
    503 khi đang khởi động/đang tắt hoặc Redis không kết nối được: lúc đó /ask chắc chắn lỗi
    (rate limit và cost guard cần Redis), nên load balancer nên tạm bỏ instance này.
    """
    if not _accepting:
        return JSONResponse(status_code=503, content={"ready": False, "reason": "starting or shutting down"})
    if not redis_healthy():
        return JSONResponse(status_code=503, content={"ready": False, "reason": "redis unreachable"})
    return {"ready": True}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    """
    Thứ tự các lớp bảo vệ là có chủ đích, từ rẻ đến đắt và từ ngoài vào trong:
      1. Xác thực (Depends, chạy trước thân hàm): kẻ lạ bị chặn trước khi đụng Redis,
         nên không thể làm đầy bộ đếm rate limit của người khác.
      2. Rate limit: chặn spam theo tốc độ.
      3. Cost guard: chặn theo tổng tiền, TRƯỚC khi gọi LLM để request bị từ chối không tốn tiền.
      4. Gọi LLM → ghi nhận chi phí thật.
    """
    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)

    cost = record_cost(estimate_tokens(body.question), estimate_tokens(answer))
    log_event("ask", question_chars=len(body.question), answer_chars=len(answer), cost_usd=round(cost, 8))
    return {"question": body.question, "answer": answer}
