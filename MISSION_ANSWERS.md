# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

Phân tích `01-localhost-vs-production/develop/app.py`:

1. **API key hardcode** (dòng 17): `OPENAI_API_KEY = "sk-hardcoded-..."`. Push lên GitHub là lộ key ngay, và nằm vĩnh viễn trong lịch sử git.
2. **Mật khẩu database hardcode** (dòng 18): `DATABASE_URL = "postgresql://admin:password123@localhost..."`. Cùng lỗi trên, lại còn gắn cứng `localhost`, nên không đổi được giữa các môi trường.
3. **Không có config management** (dòng 21–22): `DEBUG = True`, `MAX_TOKENS = 500` ghi cứng. Muốn đổi phải sửa code và deploy lại.
4. **`print()` thay cho logging** (dòng 33, 36, 38): không có level, không có timestamp, không có cấu trúc để log aggregator parse.
5. **Log ra secret** (dòng 34): `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")`. Đã kiểm chứng: log của server in nguyên `sk-hardcoded-fake-key-never-do-this`.
6. **Không có health check** (dòng 42–43): không có `/health` hay `/ready`. Gọi `GET /health` trả **404**, nên platform không biết khi nào agent chết để restart.
7. **Port cố định** (dòng 53): `port=8000`. Railway/Render inject `PORT` qua env var nên app không nghe đúng cổng.
8. **Bind `localhost`** (dòng 51): chỉ nhận kết nối từ chính máy đó. Trong container hoặc trên cloud, request từ ngoài không vào được (cần `0.0.0.0`).
9. **`reload=True`** (dòng 53): chế độ auto-reload dành cho dev, tốn tài nguyên và không an toàn trên production.
10. **Không xử lý shutdown**: không có lifespan hay handler SIGTERM, nên request đang chạy bị cắt đột ngột khi platform dừng container.

### Exercise 1.2: Kết quả chạy bản develop

Chạy `python app.py` trong WSL (Python 3.12). App nhận `question` qua **query string**, không nhận JSON:

```
$ curl -i -X POST "http://localhost:8000/ask?question=Hello"
HTTP/1.1 200 OK
server: uvicorn
content-type: application/json

{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

Gửi JSON như trong `CODE_LAB.md` thì lỗi:

```
$ curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
http=422
$ curl http://localhost:8000/health
http=404
```

**Quan sát:** app chạy được, nhưng chưa production-ready. Server log in ra `[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this` (lộ secret), và không có `/health` (404).

### Exercise 1.3: Comparison table

Chạy bản production (`cp .env.example .env`, `python app.py`):

```
$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 200 OK
{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","model":"gpt-4o-mini"}

$ curl http://localhost:8000/health
{"status":"ok","uptime_seconds":5.3,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T08:16:37.917651+00:00"}

$ curl http://localhost:8000/ready
{"ready":true}
```

Khi gửi SIGTERM, log ghi `Shutting down` → `Waiting for application shutdown` → `Application shutdown complete`: server tắt có trình tự, không bị kill đột ngột.

| Feature | Develop | Production | Tại sao quan trọng? |
|---------|---------|------------|---------------------|
| Config | Hardcode trong code (`app.py:17-22`) | Env vars qua `config.py` (`Settings`, dòng 14–46), có `validate()` fail-fast | Secret không vào git; cùng một image chạy được ở dev/staging/prod chỉ bằng đổi biến môi trường. |
| Secrets | `sk-...` và password DB nằm trong code, bị `print` ra log | `OPENAI_API_KEY`, `AGENT_API_KEY` đọc từ env; chỉ log `question_length`, không log nội dung nhạy cảm (`app.py:111-115`) | Lộ key = mất tiền và mất dữ liệu; log thường được nhiều người đọc. |
| Port / Host | `localhost:8000` cố định (`app.py:51-52`) | `HOST=0.0.0.0`, `PORT` từ env (`config.py:17-18`) | Cloud inject `PORT`; trong container phải bind `0.0.0.0` mới nhận được kết nối từ ngoài. |
| Health check | Không có (`/health` → 404) | `GET /health` (liveness) và `GET /ready` (readiness, 503 khi chưa sẵn sàng) (`app.py:135-161`) | Platform dùng `/health` để restart container chết, load balancer dùng `/ready` để quyết định có route traffic vào không. |
| Logging | `print()` | `logging` có level, kèm payload JSON (`app.py:28-32`, `111-122`) | Parse được bằng Datadog/Loki, lọc theo level, không log secret. |
| Shutdown | Đột ngột, không handler | `lifespan` shutdown + handler SIGTERM (`app.py:39-67`, `180-189`) | Request đang xử lý được hoàn thành, không mất dữ liệu khi deploy hay scale. |
| Debug / Reload | `reload=True` luôn bật | `reload=settings.debug`, mặc định `DEBUG=false` (`app.py:198`) | Reload chỉ dành cho dev; bật trên production gây tốn tài nguyên và rủi ro. |
| CORS | Không cấu hình | `allowed_origins` từ env (`app.py:77-82`) | Giới hạn trang web nào được gọi API từ trình duyệt. |

**Tự kiểm tra (CP1):** anti-pattern ở `develop/app.py:17` (key hardcode) đã được bản production sửa bằng `config.py:27` (`os.getenv("OPENAI_API_KEY", "")`).

**Cần hiểu:**
- *Hardcode secret nguy hiểm vì:* code thường được push lên git; key lộ thì bất kỳ ai đọc repo cũng dùng được, và xóa commit sau đó không đủ vì lịch sử vẫn còn.
- *Cần health check:* để platform tự phát hiện và restart agent chết, và để load balancer không gửi traffic vào instance chưa sẵn sàng.
- *Cần graceful shutdown:* để request đang chạy được xử lý xong trước khi container bị dừng.

> Lưu ý khi chạy thật: log của bản production **không ra JSON như thiết kế**. `config.py` gọi `logging.warning(...)` lúc import (`validate()`), việc này tự cấu hình root logger trước, nên `logging.basicConfig(...)` trong `app.py:28` không còn hiệu lực. Kết quả là dòng cảnh báo ra dạng `WARNING:root:OPENAI_API_KEY not set...` và các dòng `logger.info(json.dumps(...))` của app không xuất hiện (mức mặc định là WARNING). Cách sửa: thêm `force=True` vào `basicConfig` hoặc cấu hình logging trước khi import `config`.

## Part 2: Docker

_(chưa làm)_

## Part 3: Cloud Deployment

_(chưa làm)_

## Part 4: API Security

_(chưa làm)_

## Part 5: Scaling & Reliability

_(chưa làm)_
