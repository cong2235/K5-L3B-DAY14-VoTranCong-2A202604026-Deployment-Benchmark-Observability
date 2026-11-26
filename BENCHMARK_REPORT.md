# Benchmark & Observability Report — Day 14

> Mọi con số trong file này lấy từ các file JSON trong `reports/` (do `load_test.py` và `run_eval.py` ghi ra bằng `--out`), không ước lượng.
> **Trạng thái:** mục 1–3 (CP7, benchmark local) đã làm. Mục 4–6 (CP8, observability stack và scaling) **chưa làm**.

**Họ tên:** Võ Trần Công (MSSV 2A202604026)
**Ngày chạy:** 2026-11-26
**Môi trường:** Windows 11, chạy trong WSL2 Ubuntu 24.04 (WSL thấy 12 CPU logic, 3603 MB RAM), Python 3.12.3. Agent (cổng 8001/8002) và công cụ tạo tải `load_test.py` **chạy trên cùng một máy**, nên số đo bị ảnh hưởng bởi việc hai bên tranh CPU với nhau và với các tiến trình khác của máy.

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Mặc định của `load_test.py`. Latency nền của agent là khoảng 190–230 ms (p95 khi không tải: 221–224 ms), nên 500 ms cho dư địa khoảng 2,2 lần cho tải và jitter mà người dùng vẫn thấy phản hồi gần như tức thì. |
| Error rate `/ask` | < 2 % | Mặc định của `load_test.py`. Mock LLM cố ý trả lỗi 503 ngẫu nhiên ở mức 1 % (`MOCK_ERROR_RATE`), nên 2 % là mức "gấp đôi nền", đủ để phân biệt nhiễu với sự cố thật. |
| Accuracy trên golden dataset | ≥ 80 % (gate mặc định) và 100 % sau khi sửa KB | 80 % là `--min-accuracy` mặc định của `run_eval.py`. Với 23 câu, mỗi câu sai làm accuracy tụt khoảng 4,3 điểm %, nên sau khi sửa tôi nâng gate lên 100 % để chặn mọi regression. |

Ghi chú: `load_test.py` coi SLO là `p95 ≤ 500 ms` và `error ≤ 2,0 %` (bao gồm dấu bằng).

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

Mỗi mức chạy 300 request vào agent v2 (cổng 8002), sau một lượt khởi động nóng 30 request không lưu. File: `reports/load_v2_c{1,10,50,100}.json`.

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4,40 | 195,2 | 223,7 | 1695,2 | 0,33 % (1/300) | ✅ PASS |
| 10 | 40,55 | 193,9 | 221,9 | 1680,9 | 1,33 % (4/300) | ✅ PASS |
| 50 | 95,04 | 206,7 | 463,3 | 1699,0 | 1,00 % (3/300) | ✅ PASS |
| 100 | 65,68 | 509,2 | 3322,8 | 3466,4 | 2,00 % (6/300) | ❌ FAIL (p95) |

**Nhận xét:** RPS **không** tăng tuyến tính theo concurrency, và còn **giảm** ở mức 100.

- Quy luật tham chiếu là RPS ≈ concurrency / latency trung bình. Ở concurrency 1: 1 / 0,2277 s ≈ 4,39, khớp với 4,40 đo được. Ở concurrency 10: 10 / 0,2379 s ≈ 42,0, gần với 40,55 (96 %). Ở 50 và 100 thì lệch xa: lý thuyết 178 và 90,5, đo được 95,04 và 65,68 (53 % và 73 %).
- Từ concurrency 10 lên 50, RPS chỉ tăng 2,3 lần trong khi tải tăng 5 lần, và p95 đã từ 222 ms lên 463 ms, sát ngưỡng 500 ms. Ở 100, p50 tăng gấp đôi (509 ms) và p95 vọt lên 3,3 giây: request phải **xếp hàng**, tức hệ thống đã bão hòa.
- **Chưa kết luận được nút thắt nằm ở đâu.** Agent (một process Python) và công cụ tạo tải chạy cùng máy, nên không tách được "server chậm" khỏi "client tạo tải không kịp". Ngoài ra mỗi lần chạy chỉ kéo dài 3–5 giây ở các mức cao (xem `duration_s` trong JSON: 3,16 giây ở 50 và 4,57 giây ở 100), mà chỉ một request chậm bất thường (khoảng 1,7 giây) đã chiếm một phần lớn thời gian chạy, nên RPS ở các mức cao bị kéo thấp xuống một phần do hiệu ứng "đuôi" của lần chạy ngắn, không chỉ do bão hòa. Muốn kết luận chắc cần chạy dài hơn (`--duration 30`) và tách máy tạo tải.
- Error rate dao động 0,33–2,00 % **không có xu hướng theo concurrency**: đó là lỗi 503 do mock LLM bơm ngẫu nhiên ở mức 1 %. Với 300 mẫu, độ lệch chuẩn khoảng 0,57 điểm %, nên 2,00 % ở mức 100 không có ý nghĩa thống kê. Mức 100 FAIL vì **p95**, không vì error rate.

### 2.2 Tail latency

Mỗi mức chạy 300 request, concurrency 20, khởi động lại agent v2 với `MOCK_SLOW_RATE` tương ứng. File: `reports/load_v2_slow_{0,0.03,0.1}.json`.

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) | SLO |
|---|---|---|---|---|
| 0 | 193,1 | 221,1 | 233,3 | ✅ PASS |
| 0.03 (mặc định) | 236,4 | 225,5 | 1690,3 | ✅ PASS |
| 0.1 | 323,8 | 1686,9 | 1717,1 | ❌ FAIL (p95) |

**Nhận xét:**

- Chỉ số **nhạy nhất** là p99, và nó đổi trước p95. Khi tỉ lệ request chậm là 3 %, p99 nhảy từ 233 ms lên 1690 ms (gấp 7 lần) trong khi p95 gần như không đổi (221 → 225 ms). Lý do: p95 là ngưỡng mà 95 % request nhanh hơn, nên nó chỉ bị kéo lên khi phần request chậm **vượt 5 %**. Ở mức 3 % chưa vượt nên p95 vẫn "đẹp", còn p99 (ngưỡng 1 %) đã thấy hết. Ở mức 10 %, phần chậm vượt cả 5 % nên p95 cũng vọt lên 1687 ms và SLO FAIL.
- **Vì sao không đặt SLO theo average:** ở mức 0,03, avg chỉ là 236 ms, thấp hơn ngưỡng 500 ms rất nhiều, nên một SLO theo trung bình sẽ báo "ổn", trong khi cứ khoảng 33 người thì 1 người phải chờ gần 1,7 giây. Average che giấu đúng nhóm người dùng đang trải nghiệm tệ nhất. Ở mức 0,1, avg (324 ms) vẫn dưới 500 ms dù p95 đã vi phạm SLO rõ rệt.
- Lưu ý khi đọc cột RPS trong JSON: RPS giảm từ 100,6 (slow=0) xuống 50,4 (slow=0.1) vì mỗi request chậm giữ một "slot" concurrency lâu hơn, không phải vì server yếu đi.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Golden dataset 23 câu (`eval/golden_dataset.jsonl`), một câu đúng khi câu trả lời chứa ≥ 60 % keyword mong đợi. File: `reports/eval_v1.json`, `eval_v2.json`, `eval_v2_fixed.json`.

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4,3 % (1/23) | 91,3 % (21/23) | 100 % (23/23) |
| Avg tokens / câu | 57,9 | 109,3 | 115,5 |
| Tổng cost (USD) | 0,000415 | 0,000764 | 0,000807 |
| Cost / câu đúng (USD) | 0,00041475 | 0,00003639 | 0,00003507 |
| Latency p95 trong eval (ms) | 195,3 | 218,1 | 218,3 |
| Quality gate | FAIL (gate 80 %) | PASS (gate 80 %) | PASS (gate 100 %, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` ("JWT khác gì API key trong xác thực?") | `token`, `hết hạn`, `chữ ký` | Thêm vào `KNOWLEDGE_BASE` (`develop/utils/mock_llm.py`) một tài liệu kích hoạt bởi `jwt`, `api key`, `xác thực`, nội dung nói JWT là token tự chứa, có chữ ký và thời gian hết hạn, còn API key là chuỗi cố định không tự hết hạn |
| `scaling-03` ("Kubernetes HPA scale dựa trên những chỉ số nào?") | `cpu`, `memory`, `custom metrics` | Thêm tài liệu kích hoạt bởi `kubernetes`, `hpa`, `autoscal`, nội dung nói HPA scale theo CPU, memory hoặc custom metrics |

Cả hai câu đều trả về câu trả lời mặc định chung chung ("Đây là câu trả lời từ AI agent (mock)...") vì không có tài liệu nào trong KB khớp, tức là retrieval không tìm thấy gì chứ không phải LLM trả lời sai. **Cách kiểm tra regression:** retrieval chọn tài liệu có nhiều từ khoá khớp nhất (`top_k=1`), nên một mục mới có thể "giành" câu hỏi của mục cũ. Trước khi thêm, tôi đã quét dataset và xác nhận chỉ đúng hai câu mục tiêu chứa các từ khoá mới. Kết quả: 2 câu được cải thiện, **0 regression**.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- v2 tốn nhiều hơn: avg token gấp 1,89 lần (57,9 → 109,3), tổng cost gấp 1,84 lần, p95 chậm hơn 22,8 ms (+11,7 %). Đổi lại accuracy tăng từ 4,3 % lên 91,3 %.
- Tính theo **cost trên mỗi câu đúng**, v2 rẻ hơn v1 khoảng 11,4 lần (0,00041475 so với 0,00003639 USD). v1 rẻ hơn mỗi câu nhưng gần như toàn trả lời sai, nên mỗi câu đúng đắt hơn nhiều. Đây là lý do "cost / câu đúng" là chỉ số công bằng hơn "cost / câu" khi so hai phiên bản.
- Sau khi sửa KB, tài liệu dài thêm làm avg token tăng nhẹ (109,3 → 115,5) và cost tăng 0,000043 USD, còn p95 gần như không đổi (+0,2 ms).
- **Giới hạn của kết quả này:** eval chấm bằng việc câu trả lời có chứa keyword, và tôi sửa KB để chứa đúng keyword mà dataset mong đợi. Đạt 100 % trên 23 câu **không** chứng minh agent trả lời đúng các câu chưa thấy. Đây là hình thức "học theo đề" (teaching to the test) mà bài tập yêu cầu để luyện quy trình, không phải bằng chứng về chất lượng thật. Trong thực tế cần dataset đủ lớn, tách riêng tập kiểm tra, và chấm bằng độ tương đồng ngữ nghĩa hoặc LLM-as-judge. Ngoài ra 23 câu là mẫu quá nhỏ để đo latency, phần đó phải dựa vào load test ở mục 2.

### 3.1 Dùng exit code của `run_eval.py` để chặn merge (Exercise 7.3, bước 4–5)

`run_eval.py` thoát với mã **1** khi quality gate FAIL (accuracy thấp hơn `--min-accuracy` hoặc có regression so với `--baseline`), mã **0** khi PASS. Đã kiểm chứng trên máy:

| Lệnh | Exit code |
|---|---|
| Eval v2 sau khi sửa, `--min-accuracy 1.0 --baseline reports/eval_v2.json` | **0** (PASS) |
| Eval v1 (không baseline, gate 80 %) | **1** (accuracy 4,3 %) |
| Eval v1 với `--baseline reports/eval_v2.json` | **1** (FAIL, 20 câu regression, accuracy -87,0 điểm %) |

Vì mọi hệ thống CI đều coi mã thoát khác 0 là bước lỗi, chỉ cần chạy lệnh này trong một job và đặt job đó là **required status check** thì PR làm giảm chất lượng sẽ không merge được:

```yaml
# .github/workflows/eval-gate.yml (minh hoạ, chưa chạy trên GitHub Actions)
name: eval-gate
on: pull_request
jobs:
  eval:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: 06-lab-complete/benchmark-observability/develop
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt
      - name: Start agent v2
        run: |
          AGENT_VERSION=v2 PORT=8002 nohup python app.py > agent.log 2>&1 &
          for i in $(seq 1 30); do curl -sf localhost:8002/health && break; sleep 1; done
      - name: Quality gate (fails the job if accuracy < 100% or any regression)
        run: python eval/run_eval.py --url http://localhost:8002 --min-accuracy 1.0 --baseline reports/eval_v2_fixed.json
```

Cần bật *Settings → Branches → Branch protection → Require status checks* và chọn job `eval` thì PR mới bị chặn thật. Baseline (`reports/eval_v2_fixed.json`) phải được commit và cập nhật mỗi khi chấp nhận một mức chất lượng mới. Tôi chỉ kiểm chứng exit code ở máy local; file workflow trên chưa được chạy trong GitHub Actions.

---

## 4. Observability stack (production)

_Chưa làm. Thuộc CP8 (Part 7 Bước 2, Exercise 7.4–7.7): ảnh Grafana, trace chậm và trace lỗi trong Jaeger, alert firing, thí nghiệm A–E, debug bằng trace._

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

_Chưa làm. Thuộc CP8: Locust headless với 1 và 3 instance, file `benchmark-results/scale_1_stats.csv` và `scale_3_stats.csv`._

---

## 6. Kết luận

_Chưa làm, sẽ viết sau khi hoàn thành CP8._
