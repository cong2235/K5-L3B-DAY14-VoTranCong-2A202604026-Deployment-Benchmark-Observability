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

Lớp K5 deploy chính agent Part 6 (thư mục `06-lab-complete/`), không deploy app mẫu trong `03-cloud-deployment/` (xem `CHECKPOINTS.md`, CP6).

### Exercise 3.2: Deploy lên Render (nền tảng chính)

- **URL public:** https://ai-agent-hges.onrender.com
- **Nền tảng:** Render, Blueprint (`06-lab-complete/render.yaml`), gồm 2 service: `ai-agent` (web, Docker) và `agent-redis` (Key Value, gói free). `REDIS_URL` được nối tự động từ `agent-redis` bằng `fromService`, `AGENT_API_KEY` do Render sinh (`generateValue: true`), không ghi trong code hay trong git.
- **Kết quả kiểm tra trên URL public** (đo bằng `curl`; lệnh đầy đủ và biến môi trường xem `DEPLOYMENT.md`):

| Lệnh | Kết quả |
|---|---|
| `GET /health` | **200** `{"status":"ok",...,"environment":"production"}` |
| `GET /ready` | **200** `{"ready":true}` (nghĩa là agent nối được Redis trên Render) |
| `POST /ask` không có key | **401** |
| `POST /ask` key sai | **401** |
| `GET /docs` | **404** (đã tắt khi `ENVIRONMENT=production`) |
| `POST /ask` có `X-API-Key` đúng | _chưa kiểm tra, cần key trên dashboard Render_ |

- **Lần deploy đầu bị lỗi:** Blueprint sync đầu tiên tạo được `agent-redis` nhưng `ai-agent` báo "Failed deploy". Lúc đó `render.yaml` chưa có `rootDir`. Theo tài liệu Render, `dockerfilePath` được tính theo `rootDir` (mặc định là gốc repo), trong khi Dockerfile nằm trong `06-lab-complete/`. Tôi dự đoán đây là nguyên nhân (chưa xem log build để xác nhận). Sau khi thêm `rootDir: 06-lab-complete` và sync lại thì service deploy thành công.
- **Lưu ý gói free:** web service tự tắt sau 15 phút không có traffic và mất khoảng 1 phút để khởi động lại (lần gọi `/health` đầu tiên của tôi mất 11,9 giây). Free Key Value không lưu dữ liệu xuống đĩa, nên bộ đếm rate limit và chi phí về 0 mỗi lần Redis khởi động lại.

### Exercise 3.1: Railway

Chưa deploy lên Railway. Phần "nền tảng còn lại" được thay bằng bài so sánh cấu hình dưới đây (RUBRIC cho phép: "so sánh `railway.toml` với `render.yaml`").

### So sánh `railway.toml` và `render.yaml` (của agent Part 6)

| Khía cạnh | `railway.toml` | `render.yaml` | Vì sao khác |
|---|---|---|---|
| Kiểu build | `[build] builder = "DOCKERFILE"` | `runtime: docker` + `rootDir` + `dockerfilePath` | Cả hai đều build từ Dockerfile của mình, nên image giống hệt nhau trên cả hai nền tảng. Render cần `rootDir` vì file cấu hình nằm trong thư mục con |
| Health check | `healthcheckPath = "/health"`, `healthcheckTimeout = 30` | `healthCheckPath: /health` | Cùng ý tưởng: chờ `/health` trả 200 mới chuyển traffic sang bản mới. Khác tên khóa (`healthcheck…` và `healthCheck…`) |
| Restart | `restartPolicyType = "ON_FAILURE"`, `restartPolicyMaxRetries = 3` | Không khai báo (Render tự restart service lỗi) | Railway cho cấu hình chính sách restart ngay trong file |
| **Redis** | **Không khai báo được.** Phải thêm Redis trong dashboard rồi đặt `REDIS_URL` thành `${{Redis.REDIS_URL}}` | **Khai báo ngay trong file:** service `type: keyvalue` + `fromService … property: connectionString` | Khác biệt quan trọng nhất. Render là "infrastructure as code" cho cả dịch vụ phụ thuộc, Railway chỉ mô tả service của bạn. Với Render, Blueprint tự dựng toàn bộ stack; với Railway, một phần làm thủ công và dễ quên |
| Secret | Không có trong file; đặt bằng `railway variables set` hoặc dashboard | `AGENT_API_KEY` dùng `generateValue: true` (Render tự sinh); loại khác dùng `sync: false` | Cả hai đều không đưa secret vào git. Render sinh được key ngẫu nhiên ngay khi tạo, Railway thì bạn tự đặt |
| Cổng | Railway cấp biến `PORT` | Render cấp biến `PORT` | Cả hai dùng chung quy ước. `CMD` trong Dockerfile đọc `${PORT:-8000}` nên một Dockerfile chạy được cả hai nơi |
| Tạo dịch vụ | `railway up` từ CLI (đẩy trực tiếp code) | Tạo Blueprint từ repo GitHub, sau đó push là tự sync | Railway hướng CLI/đẩy code, Render hướng Git/khai báo |

Hai file mẫu trong `03-cloud-deployment/` cũng khác file của tôi: mẫu Railway dùng `builder = "NIXPACKS"` + `startCommand`, mẫu Render dùng `runtime: python` + `buildCommand`. Tôi chọn Docker cho cả hai để build giống hệt môi trường đã kiểm chứng bằng `check_production_ready.py`, và vì tiêu chí chấm yêu cầu image multi-stage chạy bằng user non-root.

### Exercise 3.3: Pipeline CI/CD của Cloud Run (chỉ đọc, không deploy)

Đọc `03-cloud-deployment/production-cloud-run/cloudbuild.yaml` và `service.yaml`:

- **Kích hoạt:** tự chạy khi push lên nhánh `main` (Cloud Build trigger), hoặc chạy tay bằng `gcloud builds submit`.
- **4 bước nối tiếp** (mỗi bước `waitFor` bước trước, nên một bước lỗi thì pipeline dừng): (1) **test**: cài dependencies và chạy `pytest tests/` trong container `python:3.11-slim`; (2) **build**: dựng Docker image, gắn hai tag `$COMMIT_SHA` và `latest`, dùng `--cache-from` để tận dụng layer cũ; (3) **push**: đẩy mọi tag lên Container Registry; (4) **deploy**: `gcloud run deploy` với image gắn đúng `$COMMIT_SHA` (không phải `latest`, để mỗi bản deploy truy ngược được về commit), vùng `asia-southeast1`, `--min-instances=1` (tránh cold start), `--max-instances=10`, secret lấy từ Secret Manager.
- **`service.yaml`** là bản khai báo (Knative) của chính service đó: scale 1–10 instance, mỗi instance nhận tối đa 80 request đồng thời, giới hạn CPU/RAM, `livenessProbe` gọi `/health`, `startupProbe` gọi `/ready`, secret qua `secretKeyRef`. Dùng với `gcloud run services replace`.
- **Hai điểm tôi thấy trong file:** (a) bước deploy chỉ gắn secret `OPENAI_API_KEY`, còn `service.yaml` gắn thêm `AGENT_API_KEY`, nên hai cách deploy cho ra cấu hình khác nhau; (b) bước test chạy `pytest tests/` nhưng thư mục ví dụ này không có `tests/`, nên pipeline sẽ lỗi ngay ở bước đầu nếu dùng nguyên văn.

## Part 4: API Security

### Exercise 4.1: API Key authentication (`04-api-gateway/develop/app.py`)

- **API key được check ở đâu?** Hàm `verify_api_key` (dòng 39–54), gắn vào endpoint bằng `Depends(verify_api_key)` (dòng 70). Key đúng lấy từ env `AGENT_API_KEY` (dòng 35), header đọc bằng `APIKeyHeader(name="X-API-Key")` (dòng 36). `/health` và `/` không có `Depends` nên công khai.
- **Sai key thì sao?** Thiếu header → **401** `Missing API key`. Có header nhưng sai → **403** `Invalid API key`.
- **Rotate key thế nào?** Key không nằm trong code, chỉ cần đổi biến môi trường `AGENT_API_KEY` trên nền tảng rồi restart/redeploy; không phải sửa code. (Hạn chế của bản demo: chỉ có **một** key nên đổi key là mọi client cũ hỏng ngay. Production thật nên cho phép nhiều key cùng lúc để đổi dần. Ngoài ra dòng 35 có giá trị mặc định `demo-key-change-in-production`, nếu quên đặt env thì chạy bằng key công khai đó, nên production phải bắt buộc đặt biến này.)

```
$ AGENT_API_KEY=secret-key-123 python app.py

$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

$ curl -i -X POST http://localhost:8000/ask -H "X-API-Key: wrong-key" -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 403 Forbidden
{"detail":"Invalid API key."}

$ curl -i -X POST http://localhost:8000/ask -H "X-API-Key: secret-key-123" -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 200 OK
{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

### Exercise 4.2: JWT authentication (`04-api-gateway/production/`)

**JWT flow** (`auth.py`): client gửi `POST /auth/token` với username/password → `authenticate_user` đối chiếu `DEMO_USERS` → `create_token` ký token HS256 bằng `JWT_SECRET`, trong payload có `sub` (user), `role`, `iat`, `exp` (hết hạn sau 60 phút) → client gửi lại `Authorization: Bearer <token>` ở mọi request → `verify_token` kiểm tra chữ ký và hạn rồi trả `{username, role}`. Server **không cần tra DB** mỗi request (stateless). Hết hạn → 401, token sai chữ ký → 403.

Dùng tài khoản `student` / `demo123` (đường dẫn `/auth/token`; `CODE_LAB.md` ghi `/token` và `admin/secret` là không đúng với code). Token đã che:

```
$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Explain JWT"}'
HTTP/1.1 401 Unauthorized
{"detail":"Authentication required. Include: Authorization: Bearer <token>"}

$ curl -i -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" -d '{"username":"student","password":"bad"}'
HTTP/1.1 401 Unauthorized
{"detail":"Invalid credentials"}

$ curl -i -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" -d '{"username":"student","password":"demo123"}'
HTTP/1.1 200 OK
{"access_token":"<TOKEN>","token_type":"bearer","expires_in_minutes":60,...}

$ curl -i -X POST http://localhost:8000/ask -H "Authorization: Bearer abc.def.ghi" -H "Content-Type: application/json" -d '{"question":"x"}'
HTTP/1.1 403 Forbidden
{"detail":"Invalid token."}

$ curl -i -X POST http://localhost:8000/ask -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" -d '{"question":"Explain JWT"}'
HTTP/1.1 200 OK
{"question":"Explain JWT","answer":"...","usage":{"requests_remaining":9,"budget_remaining_usd":1.6e-05}}
```

### Exercise 4.3: Rate limiting (`rate_limiter.py`)

- **Algorithm:** **Sliding window** (log of timestamps). Mỗi user có một `deque` chứa thời điểm các request; mỗi lần gọi thì bỏ timestamp cũ hơn `window_seconds`, nếu số còn lại `>= max_requests` thì trả 429 (dòng 110–137).
- **Limit:** `rate_limiter_user` = **10 request / 60 giây**; `rate_limiter_admin` = **100 request / 60 giây** (dòng 161–162).
- **Bypass cho admin:** không phải bypass hoàn toàn mà là *bậc cao hơn*: `app.py:141` chọn `rate_limiter_admin` khi `role == "admin"` (role nằm trong JWT). Tài khoản `teacher` (admin) gọi 15 lần liên tiếp đều 200 (giới hạn 100/phút).

Vòng lặp 15 request liên tiếp bằng token `student`:

```
 1..9   HTTP/1.1 200 OK
10..15  HTTP/1.1 429 Too Many Requests
        {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}

Header của response 429:
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795682101
retry-after: 59
```

429 bắt đầu từ request thứ **10** (không phải 11) vì trước vòng lặp tôi đã gọi 1 request bằng token hợp lệ ở Exercise 4.2, nên 1 trong 10 lượt đã dùng. `/me/usage` ghi nhận đúng `requests: 10`.

### Exercise 4.4: Cost guard

**Bản có sẵn (`cost_guard.py`)**, chạy trong bản production: mỗi lần `/ask`, `app.py` gọi `check_budget(user)` **trước** khi gọi LLM, rồi `record_usage(user, input_tokens, output_tokens)` **sau** khi gọi xong. Chi phí tính theo giá token (`$0.15/1M` input, `$0.60/1M` output của GPT-4o-mini). Có 3 lớp:

| Ngưỡng | Hành vi |
|---|---|
| ≥ 80% budget ngày của user | ghi log cảnh báo, vẫn cho gọi |
| ≥ **$1/ngày/user** | **402 Payment Required** |
| ≥ **$10/ngày toàn hệ thống** | **503** cho mọi user (chặn thảm họa chi phí) |

Tôi đã gọi trực tiếp module để kiểm chứng (vì với mock LLM không thể tiêu tới $1 bằng request thật):

```
sau 1 request nhỏ: 0.00021 USD, 0.0 %
check_budget: OK (còn budget)
sau khi tiêu nhiều: 1.65021 USD
check_budget -> 402 {'error': 'Daily budget exceeded', 'used_usd': 1.65021, 'budget_usd': 1.0, 'resets_at': 'midnight UTC'}
global budget  -> 503 Service temporarily unavailable due to budget limits. Try again tomorrow.
```

**Bản đề bài yêu cầu ($10/tháng/user, lưu trong Redis)** — cách làm của tôi:

```python
def check_budget(user_id: str, estimated_cost: float) -> bool:
    key = f"budget:{user_id}:{datetime.now():%Y-%m}"   # key theo tháng → tự "reset" đầu tháng
    current = float(r.get(key) or 0)
    if current + estimated_cost > 10:
        return False                                  # vượt → chặn
    r.incrbyfloat(key, estimated_cost)                # cộng dồn chi phí
    r.expire(key, 32 * 24 * 3600)                     # TTL 32 ngày → Redis tự dọn key tháng cũ
    return True
```

- **Reset đầu tháng:** nhúng `YYYY-MM` vào tên key, sang tháng mới là key mới bắt đầu từ 0; TTL 32 ngày xóa key cũ, không cần job reset.
- **Vì sao Redis chứ không phải RAM:** bản có sẵn lưu trong dict trong process, nên restart là mất số liệu và chạy nhiều instance thì mỗi instance đếm riêng (user gọi qua 3 instance được tiêu gấp 3 lần budget). Redis là nguồn chung duy nhất.
- **Lưu ý:** đoạn trên là bản mẫu của đề, tôi chưa chạy nó với Redis thật (sẽ làm trong Part 6). Nó có lỗi race condition: `get` rồi `incrbyfloat` không nguyên tử, hai request đồng thời có thể cùng qua kiểm tra. Cách sửa: `INCRBYFLOAT` trước rồi so sánh kết quả trả về (vượt thì trừ lại), hoặc dùng Lua script.

**Cần hiểu — vì sao cần cả rate limit và cost guard:** rate limit bảo vệ *tốc độ* (chặn lạm dụng, DoS), nhưng 10 request/phút kéo dài cả tháng với prompt rất dài vẫn có thể tốn rất nhiều tiền. Cost guard bảo vệ *tiền* (chặn theo tổng chi phí), nhưng không chặn được một đợt request dồn dập làm sập server trước khi chi phí kịp tăng. Hai lớp bù cho nhau.

**Hạn chế chung của code mẫu:** `RateLimiter` và `CostGuard` đều lưu trong RAM của một process, nên không dùng được khi scale nhiều instance (xem Part 5); bản Part 6 phải chuyển sang Redis.

## Part 5: Scaling & Reliability

### Exercise 5.1: Health checks (`05-scaling-reliability/develop/app.py`)

Hai endpoint đã được cài sẵn trong `develop/app.py` (dòng 104–168); tôi đọc, chạy và kiểm chứng chứ không viết lại.

| Endpoint | Câu hỏi nó trả lời | Trả gì | Ai dùng |
|---|---|---|---|
| `GET /health` (liveness) | "Process còn sống không?" | 200 + `status`, `uptime_seconds`, `version`, kiểm tra bộ nhớ (psutil) | Platform: **non-200 hoặc timeout → restart container** |
| `GET /ready` (readiness) | "Sẵn sàng nhận traffic chưa?" | 200 khi `_is_ready=True`, **503** khi đang khởi động hoặc đang shutdown | Load balancer: quyết định **có route traffic vào instance này không** (không restart) |

```
$ curl -i http://localhost:8000/health
HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":4.0,"version":"1.0.0",...,"checks":{"memory":{"status":"ok","used_percent":44.5}}}

$ curl -i http://localhost:8000/ready
HTTP/1.1 200 OK
{"ready":true,"in_flight_requests":1}
```

**Vì sao tách làm hai:** instance đang khởi động hoặc mất kết nối Redis thì *chưa nên nhận traffic* (`/ready` = 503) nhưng *không cần restart* (`/health` = 200). Gộp làm một thì platform sẽ restart liên tục một container chỉ đang chờ dependency.

Quan sát nhỏ: `in_flight_requests` báo `1` dù không có request nào khác, vì middleware `track_requests` đếm cả chính request `/ready` đang gọi.

### Exercise 5.2: Graceful shutdown

Cơ chế đã có trong code: `lifespan` (dòng 54–66) đặt `_is_ready=False` rồi chờ `_in_flight_requests` về 0 (tối đa 30 giây), và `uvicorn.run(..., timeout_graceful_shutdown=30)`. Để thấy tác dụng, tôi dùng bản develop (mock LLM trễ 3 giây/request), gửi một request rồi bắn `SIGTERM` sau 1 giây, đối chứng với `SIGKILL`:

```
# SIGTERM khi request đang chạy
gửi SIGTERM tới pid 3231 lúc request đang chạy...
request MỚI ngay sau SIGTERM:  http=000  (không kết nối được: đã ngừng nhận)
request ĐANG CHẠY DỞ:          {"answer":"..."}  [curl] http=200 time=2.876s   ← vẫn hoàn thành

log server:
INFO: Shutting down
INFO: 127.0.0.1 - "POST /ask?question=LongTask HTTP/1.1" 200 OK
INFO: Waiting for application shutdown.
INFO  🔄 Graceful shutdown initiated...
INFO  ✅ Shutdown complete

# SIGKILL (đối chứng)
[curl] http=000 exit=52      ← "Empty reply from server": request bị cắt ngang, client không nhận gì
```

**Kết luận:** với SIGTERM, server ngừng nhận kết nối mới, **để request đang chạy xong (200 sau 2,88 giây)**, rồi mới chạy phần dọn dẹp và thoát. SIGKILL thì không thể bắt được nên request mất hẳn. Platform luôn gửi SIGTERM trước, rồi SIGKILL sau một thời gian chờ nên code phải xử lý SIGTERM.

Hai điều tôi quan sát được từ log, khác với phần mô tả trong comment của code:
- Phần *chờ request* thực tế do **uvicorn** làm (nó đợi các kết nối đang mở rồi mới gọi `lifespan` shutdown). Lúc vòng lặp chờ trong `lifespan` chạy thì `in_flight` đã bằng 0 nên nó không phải chờ gì. Vòng lặp đó là lớp phòng thủ dự phòng, không phải thứ tạo ra hành vi graceful trong thử nghiệm này.
- Sau khi `SIGTERM`, request mới bị **từ chối kết nối** (`http=000`) chứ không nhận 503 từ `/ready`, vì uvicorn đóng cổng lắng nghe ngay. Với load balancer, kết quả vẫn là "không gửi traffic vào instance này nữa".

### Exercise 5.3: Stateless design (`05-scaling-reliability/production/app.py`)

**Anti-pattern** là lưu state (history hội thoại) trong RAM của process. Khi chạy nhiều instance, mỗi instance có RAM riêng. `production/app.py` lưu session trong Redis (`save_session`/`load_session`, key `session:<id>`, TTL 1 giờ, giữ tối đa 20 message), nên instance nào cũng đọc được.

Để chứng minh vấn đề, tôi chạy 2 instance **không có Redis** (app tự rơi về dict trong RAM) ở cổng 8001 và 8002:

```
instance A: POST /chat {"question":"My name is Alice"}  → session_id=9b29a2bc-...
instance A: GET /chat/9b29a2bc-.../history              → có messages
instance B: GET /chat/9b29a2bc-.../history              → HTTP/1.1 404 Not Found
            {"detail":"Session 9b29a2bc-... not found or expired"}
```

Cùng một session mà sang instance B là mất sạch, đúng như đề mô tả ("Alice" ở instance 1, instance 2 không biết). Với Redis (mục 5.4–5.5) thì không bị.

**Rủi ro thiết kế nên biết:** nếu Redis lỗi lúc khởi động thì app *im lặng rơi về RAM* (`USE_REDIS=False`) và `/ready` vẫn trả 200. Một instance cấu hình sai Redis sẽ trông khỏe mạnh nhưng lại hỏng state khi scale. Production thật nên fail fast (không khởi động) thay vì fallback.

### Exercise 5.4: Load balancing

```
$ docker compose -p k5-day14-scaling up -d --build --scale agent=3
k5-day14-scaling-agent-1   running  healthy
k5-day14-scaling-agent-2   running  healthy
k5-day14-scaling-agent-3   running  healthy
k5-day14-scaling-nginx-1   running          0.0.0.0:8080->80/tcp
k5-day14-scaling-redis-1   running  healthy
```

Gửi 12 request (mỗi request một session mới) qua Nginx (`:8080/chat`), đếm theo `served_by`:

```
4 instance-02bb10 redis
4 instance-6d45f6 redis
4 instance-a086f7 redis
```

Chia đều 4/4/4, tức round-robin. **Cơ chế:** Docker DNS trả về cả 3 IP cho tên `agent`, Nginx đưa cả 3 vào `upstream agent_cluster` rồi xoay vòng. Chú ý: `upstream` dạng tĩnh chỉ phân giải tên **một lần lúc Nginx khởi động**; nếu scale thêm instance sau đó thì phải reload Nginx (tôi chưa kiểm chứng điểm này, chỉ suy ra từ cấu hình).

**Khi một instance chết:** tôi `docker kill` `agent-1` rồi gửi 9 request tiếp theo trong **cùng session**:

```
200 200 200 200 200 200 200 200 200
```

9/9 thành công, không request nào lỗi. Lý do là `proxy_next_upstream error timeout http_503` + `proxy_next_upstream_tries 3` trong `nginx.conf`: khi Nginx thử `agent-1` và gặp lỗi kết nối thì tự chuyển sang instance khác trong cùng request, client không thấy lỗi. Log của 2 instance còn lại nhận 11 + 11 request `POST /chat`.

(Tôi chưa kiểm chứng việc `agent-1` có được Docker tự bật lại hay không: 7 giây sau khi kill, `docker compose ps` mới liệt kê 2 instance.)

### Exercise 5.5: Test stateless

`python test_stateless.py` gửi 5 câu trong **cùng một session**, rồi đọc history:

```
Session ID: 4b1bfc28-2214-49b7-ab51-0357abad1b13
Request 1: [instance-02bb10]   Request 4: [instance-02bb10]
Request 2: [instance-6d45f6]   Request 5: [instance-6d45f6]
Request 3: [instance-a086f7]
Instances used: {'instance-a086f7', 'instance-02bb10', 'instance-6d45f6'}
✅ All requests served despite different instances!
--- Conversation History ---
Total messages: 10      (5 user + 5 assistant, đủ và đúng thứ tự)
✅ Session history preserved across all instances via Redis!
```

**Giải thích:** 5 request của một hội thoại đi qua cả 3 instance khác nhau (round-robin), nhưng history vẫn đủ 10 message vì tất cả instance cùng đọc/ghi một chỗ là Redis. Instance không giữ gì trong RAM nên bị thay thế hay chết bất kỳ lúc nào cũng không mất hội thoại. Thử nghiệm kill ở 5.4 xác nhận thêm: sau khi mất `agent-1`, history của session vẫn còn nguyên (`messages = 20`, tin nhắn đầu là "My name is Alice").

Xong thì dọn: `docker compose -p k5-day14-scaling down`.

**Cần hiểu (CP4):**
- *Liveness khác readiness:* liveness (`/health`) trả lời "có cần restart không", readiness (`/ready`) trả lời "có nên gửi traffic vào không".
- *State trong RAM hỏng khi chạy nhiều instance:* mỗi instance có bộ nhớ riêng, request kế tiếp có thể rơi vào instance khác (xem 404 ở Ex 5.3). Phải đưa state ra ngoài (Redis).

## Part 6: Final Project (`06-lab-complete/`)

### Kết quả chấm

`python check_production_ready.py` (bản đầy đủ, có Docker, chạy trong WSL2 Ubuntu, Python 3.12, `os.name == posix`):

```
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

Số đo từ chính lần chạy này: image `< 500 MB` đạt với **63 MB** (số script đọc từ `docker image inspect`, là kích thước nén); `docker images` hiển thị **286 MB** cho image build bằng compose (số trên đĩa). Hai số đo cùng một image theo hai cách tính khác nhau, đều dưới 500 MB. `docker stop` tắt trong **0,9 giây** (script) / **2,6 giây** (đo tay), exit code **0**.

Script chỉ *đọc* `docker-compose.yml` chứ không chạy nó, nên tôi tự chạy `docker compose up` rồi kiểm tra: `/health` 200, `/ready` 200, không key → 401, key sai → 401, 12 request liên tiếp với `RATE_LIMIT_PER_MINUTE=10` cho `200×10` rồi `429×2` kèm `Retry-After: 59`; trong Redis chỉ có khóa đã băm `rl:57c8…` (không lộ API key) và `cost:2026-11-26`; PID 1 trong container là `uvicorn`; tiến trình chạy bằng user `agent` (không phải root); không có file `.env` bên trong image; không dòng log nào chứa API key; mọi dòng log của app là JSON.

### Các quyết định thiết kế và lý do

| Phần | Quyết định | Vì sao |
|---|---|---|
| `config.py` | Đọc env bằng `default_factory`, sai kiểu thì dừng ngay khi khởi động. `AGENT_API_KEY` mặc định rỗng; `ENVIRONMENT=production` mà thiếu key thì không khởi động | Fail fast, không chạy sai âm thầm. Không có key mặc định ai cũng biết (bản demo Part 4 có `demo-key-change-in-production`, là điểm yếu) |
| `auth.py` | `auto_error=False` + tự `raise 401`; so key bằng `secrets.compare_digest`; thiếu key và sai key trả cùng một thông báo; chưa cấu hình key → từ chối tất cả | Hợp đồng đòi 401 (mặc định FastAPI trả 403 khi thiếu header). `compare_digest` chống timing attack |
| `redis_client.py` | `redis.from_url` (lazy, không ping lúc import) + timeout 1s/2s | App phải khởi động được khi Redis chưa lên; `/ready` phải trả 503 nhanh chứ không treo |
| `rate_limiter.py` | Sliding window bằng Redis sorted set, toàn bộ trong **một Lua script**; thời gian lấy từ lệnh `TIME` của Redis; khóa dùng hash SHA-256 của API key | Gợi ý của đề (`ZREMRANGEBYSCORE → ZCARD → ZADD` là các lệnh riêng) không nguyên tử: với `--workers 2` hai worker có thể cùng đọc 9/10 rồi cùng thêm thành 11/10. Lua loại bỏ race này. Một đồng hồ duy nhất (Redis) tránh lệch giờ giữa các instance |
| `cost_guard.py` | Bộ đếm USD theo ngày UTC (`cost:YYYY-MM-DD`) bằng `INCRBYFLOAT`, TTL 2 ngày; `check_budget` trước khi gọi LLM, `record_cost` sau | Sang ngày mới là khóa mới nên không cần job reset. Kiểm tra trước để request bị từ chối không tốn tiền |
| Khi Redis chết | `/ask` trả **503** (fail closed), `/ready` trả 503, `/health` vẫn 200 | Rate limit và cost guard là hai lớp bảo vệ tiền. Nếu "fail open" thì chỉ cần làm Redis chết là gọi LLM không giới hạn. `/health` không phụ thuộc Redis để platform không restart agent liên tục vì lỗi của Redis |
| Thứ tự trong `/ask` | auth → rate limit → cost guard → LLM → ghi chi phí | Từ rẻ đến đắt: kẻ chưa xác thực bị chặn trước khi chạm Redis nên không làm đầy bộ đếm của người khác |
| Logging (`log.py`) | Logger riêng `agent` với handler JSON, `propagate=False`; chỉ log độ dài câu hỏi, không log nội dung/key | Sửa đúng lỗi ở Part 1 (`basicConfig` bị vô hiệu vì module khác log trước). Không trộn với log uvicorn |
| Graceful shutdown | **Không** đăng ký signal handler; dùng `lifespan` để đóng pool Redis | Uvicorn đã xử lý SIGTERM đúng thứ tự (đóng cổng → chờ request → chạy lifespan → exit 0). Tự viết handler mà không gọi lại handler cũ của uvicorn sẽ làm process không bao giờ tắt |
| Dockerfile | Multi-stage; builder tạo `/opt/venv`, runtime chỉ copy venv + code; user hệ thống `agent` (uid 10001); `HEALTHCHECK` bằng `urllib`; `CMD ["sh","-c","exec uvicorn ... --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2}"]` | `exec` làm uvicorn thành PID 1 để nhận SIGTERM (thiếu thì `docker stop` đợi 10s rồi SIGKILL, exit 137). Không cài `gcc` vì mọi dependency đều có wheel dựng sẵn |
| `docker-compose.yml` | `env_file` với `required: false`; `REDIS_URL` và `PORT` đặt cứng trong `environment`; Redis có healthcheck, `appendonly`, `maxmemory 64mb`, không đặt eviction, không publish cổng 6379 | `environment` ưu tiên hơn `env_file` nên `.env` (trỏ `localhost`) không phá được kết nối nội bộ. Không eviction: bộ nhớ đầy thì ghi lỗi → agent 503, thay vì âm thầm xoá bộ đếm của rate limit/cost guard |
| `.dockerignore` | Loại `.env`, `.env.*` (giữ `!.env.example`), `__pycache__`, `venv`, `.git`, `*.md`, `benchmark-observability/` | Secret không bao giờ vào image; build context nhỏ |
| `railway.toml` / `render.yaml` | Viết cả hai. Railway: `builder = "DOCKERFILE"`, `healthcheckPath`. Render: khai báo luôn Redis (`type: keyvalue`), nối `REDIS_URL` bằng `fromService`, `AGENT_API_KEY` dùng `generateValue: true` | Dùng cho phần so sánh hai nền tảng ở Part 3 (làm ở CP6). Khác biệt chính: Render khai báo được Redis ngay trong file, Railway thì phải thêm Redis trong dashboard |

### Hạn chế đã biết

- **Cost guard là bộ đếm toàn cục**, không tách theo API key (hợp đồng chỉ yêu cầu tổng chi phí). Script chấm chạy nhiều pha trên cùng một Redis tạm nên chi phí tích luỹ từ các pha trước, và pha cost guard báo 402 ngay ở request đầu (`402 ở request thứ 1`). Kết quả đúng với thiết kế, nhưng cho thấy bộ đếm dùng chung.
- **Kiểm tra trước, ghi nhận sau** nên N request đồng thời sát ngưỡng có thể vượt budget cỡ N × chi phí một request (~1e-5 USD). Muốn chặt hơn phải "đặt trước" chi phí ước tính.
- **Ước lượng token thô** (~4 ký tự/token) vì mock LLM không trả số token thật.
- **Base image `python:3.11-slim`**: trình phân tích của IDE báo image có 5 lỗ hổng mức cao (CVE của gói Debian trong base image). Chưa xử lý; production thật nên ghim digest và quét định kỳ.
- **Chưa deploy lên cloud và chưa chạy 4 lệnh tự kiểm của CP6** (`/health`, `/ready`, `/ask` không key, `/ask` có key trên URL public). Phần này làm ở CP6.

## AI log

Theo `RULES.md` mục 1, ghi lại việc dùng AI. **Toàn bộ nội dung bài này, gồm code Part 6 và các câu trả lời Part 1–5, do Claude Code (Anthropic, mô hình Claude Sonnet 5.5) thực hiện theo yêu cầu của tôi** trong một phiên làm việc. Tôi ghi rõ điều này để Lab Coach biết; tôi sẽ đọc lại và phải giải thích được từng đoạn code trong `06-lab-complete/app/` khi được hỏi.

| Việc | Tôi yêu cầu | AI làm / cho tôi | Kiểm tra bằng cách nào |
|---|---|---|---|
| Môi trường | Cài sẵn môi trường lab | Tạo venv trong WSL2 Ubuntu, cài requirements; xử lý lỗi DNS của WSL (apt treo) và Docker Hub trả 429 (lấy base image từ `mirror.gcr.io` rồi gắn lại tag) | `pip check` sạch, `os.name == posix`, build image thành công |
| Part 1–2 | Làm CP1, CP2 | Đọc code, chạy bản develop/production, build hai image, dựng stack compose, ghi kết quả | Số MB lấy từ `docker images` trên máy tôi; kiểm tra cả `whoami` và healthcheck chứ không chỉ `curl` |
| Part 4 | Làm CP3 | Chạy các trường hợp 401/403/200/429, kiểm tra cost guard bằng cách gọi trực tiếp module | Output `curl -i` thật; chỉ ra lệch giữa `CODE_LAB.md` và code thật (`/auth/token`, `student/demo123`); nói rõ đoạn Redis $10/tháng của đề **chưa được chạy** |
| Part 5 | Làm CP4 | Chạy health/shutdown/stateless, dựng 3 instance sau Nginx, `docker kill` một instance giữa chừng | SIGTERM so với SIGKILL; 404 khi không có Redis so với đủ history khi có Redis; 9/9 request thành công sau khi kill |
| Part 6 | Làm CP5, kèm giải thích logic | Đọc toàn bộ `check_production_ready.py` trước khi viết code, rồi viết `app/*.py`, `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.env.example`, `railway.toml`, `render.yaml`. Lần chạy đầy đủ đầu tiên đạt 12/12 | `check_production_ready.py` báo `PASS 12/12`; tự chạy `docker compose up` rồi kiểm tra rate limit, khóa Redis đã băm, PID 1, user, `docker stop`. Chạy chế độ `--skip-docker` trước để tách lỗi code với lỗi Docker |

**Những chỗ AI làm khác gợi ý của đề, và lý do** (để tôi giải thích được): dùng Lua script thay cho các lệnh Redis rời; `compare_digest` thay cho `==`; fail closed khi Redis chết; không tự đăng ký handler SIGTERM; logger riêng thay vì `basicConfig`. Chi tiết trong bảng quyết định thiết kế ở trên.

**Điều AI chưa làm:** deploy lên Railway hoặc Render (cần tài khoản của tôi), chạy Part 7 Bước 2, chụp ảnh màn hình.
