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

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)

1. **Base image:** `python:3.11` (dòng 8), bản Python đầy đủ. Đo được **1.62 GB** trên máy này (`docker images python`).
2. **Working directory:** `/app` (dòng 11, `WORKDIR /app`). Các lệnh `COPY`, `RUN`, `CMD` phía sau đều tính từ thư mục này.
3. **Vì sao `COPY requirements.txt` trước:** Docker cache theo từng layer, và một layer bị làm mất cache thì mọi layer sau nó cũng build lại. `requirements.txt` ít khi đổi còn code đổi liên tục. Đặt `requirements.txt` + `pip install` trước thì khi chỉ sửa code, Docker dùng lại layer đã cài thư viện và chỉ chạy lại bước `COPY app.py`. Nếu `COPY . .` đứng trước, mỗi lần sửa một dòng code lại phải `pip install` từ đầu.
4. **CMD vs ENTRYPOINT:** `CMD` là lệnh mặc định, bị thay hoàn toàn nếu truyền lệnh khác khi `docker run` (ví dụ `docker run image bash`). `ENTRYPOINT` là chương trình cố định của container; tham số truyền sau tên image được nối vào cuối chứ không thay thế. Hay dùng cùng nhau: `ENTRYPOINT` là chương trình, `CMD` là tham số mặc định.

### Exercise 2.2: Build và run bản develop

Build từ gốc repo vì Dockerfile `COPY` theo đường dẫn tính từ gốc:

```
$ docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
$ docker run -d -p 8000:8000 my-agent:develop
$ curl -i -X POST "http://localhost:8000/ask?question=What%20is%20Docker%3F"
HTTP/1.1 200 OK
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
$ curl http://localhost:8000/health
{"status":"ok","uptime_seconds":4.5,"container":true}
$ docker exec <container> whoami
root
```

Container develop chạy bằng **root** (không có `USER`), đây là điểm kém an toàn so với bản production.

### Exercise 2.3: Multi-stage build và so sánh kích thước

Đọc `02-docker/production/Dockerfile`:

- **Stage 1 (`builder`, `python:3.11-slim`):** cài `gcc`, `libpq-dev` (công cụ biên dịch), rồi `pip install --user -r requirements.txt` vào `/root/.local`. Stage này chỉ để *build*, không bao giờ được deploy.
- **Stage 2 (`runtime`, `python:3.11-slim`):** tạo user không phải root (`appuser`), chỉ `COPY --from=builder /root/.local` (các thư viện đã cài) và code, thêm `HEALTHCHECK`, chạy `uvicorn` với 2 workers.
- **Vì sao nhỏ hơn:** (1) base `slim` thay vì bản đầy đủ; (2) `gcc`, `libpq-dev`, cache apt, cache pip nằm trong stage builder và bị bỏ đi, image cuối không chứa chúng; (3) chỉ copy phần cần để chạy.

```
$ docker build -f 02-docker/production/Dockerfile -t my-agent:advanced .
$ docker images | grep my-agent
my-agent:advanced     240MB
my-agent:develop      1.67GB
```

| Image | Kích thước (`docker images`) |
|---|---|
| Develop (`python:3.11`, single-stage) | **1.67 GB** (≈ 1670 MB) |
| Production (`python:3.11-slim`, multi-stage) | **240 MB** |
| Chênh lệch | giảm ≈ **1430 MB, tức ≈ 86%** (production chỉ bằng ~14% develop) |

Số trên là số tôi đo trên máy này bằng `docker images`, không chép từ README. Image production đạt mục tiêu `< 500 MB` của đề.

Chạy thử bản production:

```
$ docker run -d -p 8000:8000 my-agent:advanced
$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"What is Docker?"}'
HTTP/1.1 200 OK
$ curl http://localhost:8000/ready
{"ready":true}
$ docker exec <container> whoami
appuser
$ docker inspect <container> --format '{{.State.Health.Status}}'
healthy
```

### Exercise 2.4: Docker Compose stack

Compose project `k5-day14-docker` (`docker compose -p k5-day14-docker up -d --build`). 4 service đều lên, `agent`, `redis`, `qdrant` ở trạng thái `healthy`:

```
agent    running  healthy  8000/tcp          (chỉ mạng nội bộ)
nginx    running           0.0.0.0:80->80, 443->443
qdrant   running  healthy  6333-6334/tcp     (chỉ mạng nội bộ)
redis    running  healthy  6379/tcp          (chỉ mạng nội bộ)
```

**Sơ đồ kiến trúc:**

```
                 Internet / Client
                        │  :80 / :443   (cổng duy nhất mở ra host)
                        ▼
              ┌───────────────────┐
              │      nginx        │  reverse proxy + load balancer
              │  rate limit 10r/s │  security headers, 429 khi vượt
              └─────────┬─────────┘
   ═════════════════════╪═══════ mạng nội bộ `internal` (bridge) ═══════
                        │ upstream agent:8000
                        ▼
              ┌───────────────────┐
              │   agent (FastAPI) │  uvicorn, user appuser, /health
              └────┬─────────┬────┘
        REDIS_URL  │         │  QDRANT_URL
   redis://redis:6379/0      │  http://qdrant:6333
                   ▼         ▼
             ┌─────────┐  ┌──────────┐
             │  redis  │  │  qdrant  │   volumes: redis_data, qdrant_data
             │ session │  │  vector  │   (dữ liệu giữ lại khi restart)
             │ + rate  │  │    DB    │
             └─────────┘  └──────────┘
```

**Giao tiếp giữa các service:** tất cả nằm trong mạng bridge `internal`, gọi nhau bằng *tên service* (DNS của Compose): nginx → `agent:8000`, agent → `redis:6379` và `qdrant:6333`. `depends_on` + `condition: service_healthy` bắt agent chờ Redis và Qdrant healthy rồi mới khởi động. Chỉ nginx publish cổng ra host; `agent`, `redis`, `qdrant` không thể truy cập trực tiếp từ ngoài.

**Kết quả test qua Nginx (cổng 80):**

```
$ curl -i http://localhost/health
HTTP/1.1 200 OK
Server: nginx                      ← version bị ẩn (server_tokens off)
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
{"status":"ok","uptime_seconds":32.2,"version":"2.0.0",...}

$ curl -i -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question":"Explain microservices"}'
HTTP/1.1 200 OK
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}

$ curl -m 3 http://localhost:8000/health     # gọi thẳng agent, bỏ qua nginx
http=000  (không kết nối được, đúng thiết kế)
$ docker compose -p k5-day14-docker exec redis redis-cli ping
PONG
```

Khi bắn nhanh 40 request liên tiếp bằng vòng lặp `curl` thì cả 40 đều trả 200, không có 429. Lý do: Nginx cho 10 req/giây và `burst=20`, mà `curl` chạy tuần tự chậm hơn mức đó, nên chưa chạm giới hạn. Tôi không kết luận rate limit "đã hoạt động" từ thí nghiệm này.

Dọn stack: `docker compose -p k5-day14-docker down`.

**Cách debug container (checkpoint 2):** `docker logs <container>` (hoặc `docker compose -p ... logs agent`) xem log; `docker exec -it <container> sh` vào trong; `docker inspect --format '{{.State.Health.Status}}'` xem trạng thái healthcheck.

**Ghi chú môi trường:** lúc build lần đầu Docker Hub trả `429 Too Many Requests` (giới hạn pull ẩn danh). Tôi lấy `python:3.11` và `python:3.11-slim` từ `mirror.gcr.io` (bản sao công khai của Docker Hub do Google chạy) rồi gắn lại tag cùng tên, nên Dockerfile không phải sửa.

## Part 3: Cloud Deployment

_(chưa làm)_

## Part 4: API Security

_(chưa làm)_

## Part 5: Scaling & Reliability

_(chưa làm)_
