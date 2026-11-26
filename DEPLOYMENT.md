# Deployment Information

## Public URL

https://ai-agent-hges.onrender.com

## Platform

Render (Blueprint `06-lab-complete/render.yaml`, gói free)

- `ai-agent`: web service, build từ `06-lab-complete/Dockerfile` (multi-stage, user non-root)
- `agent-redis`: Render Key Value (tương thích Redis), dùng cho rate limit và cost guard

Gói free: web service tự tắt sau 15 phút không có traffic và mất khoảng 1 phút để khởi động lại, nên **lần gọi đầu có thể chậm**. Key Value free không lưu dữ liệu xuống đĩa, bộ đếm rate limit và chi phí về 0 mỗi lần Redis khởi động lại.

## Test Commands

Đặt `BASE` là URL public và `AGENT_API_KEY` là key trên dashboard Render (service `ai-agent` → Environment). Mỗi lệnh chỉ in mã HTTP nên chụp ảnh được mà không lộ key.

```bash
BASE=https://ai-agent-hges.onrender.com
AGENT_API_KEY='<lấy từ dashboard Render>'

# 1. Health check (liveness)  → 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"

# 2. Readiness (nối được Redis) → 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"

# 3. Không có API key → 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -d '{"question":"Hello"}'

# 4. Có API key → 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
```

### Kết quả đã kiểm tra (2026-11-26)

| # | Lệnh | Mong đợi | Thực tế |
|---|---|---|---|
| 1 | `GET /health` | 200 | **200** |
| 2 | `GET /ready` | 200 | **200** |
| 3 | `POST /ask` không key | 401 | **401** |
| 3b | `POST /ask` key sai | 401 | **401** |
| 4 | `POST /ask` có key đúng | 200 | **200** (0,89 giây) |

Kiểm tra thêm: `GET /docs` trả 404 (tài liệu API bị tắt khi `ENVIRONMENT=production`).

## Environment Variables Set

Khai báo trong `06-lab-complete/render.yaml`, giá trị thật nằm trên Render, không nằm trong git.

| Biến | Nguồn giá trị |
|---|---|
| `ENVIRONMENT` | `production` (ghi trong `render.yaml`) |
| `AGENT_API_KEY` | Render tự sinh (`generateValue: true`); **secret, không ghi trong repo** |
| `REDIS_URL` | Nối tự động từ service `agent-redis` (`fromService`, `connectionString`) |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` | `10` |
| `PORT` | Render tự cấp; `CMD` trong Dockerfile đọc `${PORT:-8000}` |

## Screenshots

_Chưa có. Cần chụp và lưu vào `screenshots/`:_

- Dashboard Render: Blueprint đã sync thành công, 2 service
- Service `ai-agent` đang chạy (Live)
- Kết quả 4 lệnh test ở trên
