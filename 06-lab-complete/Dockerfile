# ============================================================
# Production Dockerfile — multi-stage (tiêu chí 1)
#
#   builder : cài dependencies vào một virtualenv. Stage này bị bỏ đi sau khi build,
#             nên mọi thứ chỉ phục vụ việc build (cache pip, pip, công cụ biên dịch nếu có)
#             không nằm trong image cuối.
#   runtime : base slim + virtualenv đã cài sẵn + code. Chạy bằng user không phải root.
# ============================================================

# ──────────────────────────────────────────────────────────
# STAGE 1: builder
# ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Dùng virtualenv thay vì `pip install --user`: copy nguyên một thư mục sang stage sau,
# đường dẫn giống hệt nhau (/opt/venv) nên các script có shebang vẫn chạy đúng.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Chỉ copy requirements.txt trước: layer `pip install` chỉ build lại khi dependencies đổi,
# sửa code không làm mất cache (xem Exercise 2.1).
WORKDIR /build
COPY requirements.txt .
RUN pip install -r requirements.txt

# ──────────────────────────────────────────────────────────
# STAGE 2: runtime
# ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# User hệ thống, không có shell đăng nhập, không có home: nếu app bị khai thác thì kẻ tấn công
# không có quyền root trong container.
RUN groupadd --system --gid 10001 agent \
    && useradd --system --uid 10001 --gid agent --no-create-home --shell /usr/sbin/nologin agent

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=agent:agent app/ ./app/
COPY --chown=agent:agent utils/ ./utils/

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER agent

# Chỉ để tài liệu hoá. Cổng thật lấy từ biến PORT (Railway/Render tự cấp), mặc định 8000.
EXPOSE 8000

# Docker tự đánh dấu container unhealthy nếu /health không trả 200.
# urlopen ném exception với mã không phải 2xx, nên lệnh thoát khác 0 → healthcheck fail.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT', '8000'), timeout=3)"]

# `sh -c "exec ..."`: shell cần để thay ${PORT}, còn `exec` thay chính shell bằng uvicorn nên
# uvicorn là PID 1 và nhận SIGTERM trực tiếp khi `docker stop` (exit code 0, không bị SIGKILL).
# Không có `exec` thì SIGTERM đến sh, sh không chuyển tiếp, sau 10s Docker SIGKILL → exit 137.
# WEB_CONCURRENCY chỉnh được số worker (mặc định 2) mà không phải build lại image.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2}"]
