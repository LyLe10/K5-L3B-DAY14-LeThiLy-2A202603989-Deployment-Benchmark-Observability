# Benchmark & Observability Report — Day 14

**Họ tên** Lê Thị Ly

**Ngày chạy** 26/11/2026 (GMT+7)

**Môi trường** WSL2 Linux 5.15.167.4, 8 CPU logic, 7.7 GiB RAM, Python 3.12.3 trong `.venv`. Các phiên bản dependency đã ghim được cài từ `develop/requirements.txt`. `pip check` báo không có dependency lỗi.

**Phạm vi CP7** Hai agent local dùng `mock-llm-small`. Theo tiêu chí K5, lưu JSON một lần tại [reports/](reports/) theo cấu trúc nộp bài của SUBMISSION.md. Chạy đủ ba slow rate theo CHECKPOINTS.md, bao gồm mốc 0.03 bên cạnh hai mốc 0 và 0.1 của CODE_LAB.md. CSV Locust và ảnh observability thuộc CP8.

---

## 1. SLO của agent

| SLI | SLO / quality gate | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | ≤ 500 ms | Ngưỡng mặc định của `load_test.py`, giới hạn thời gian chờ ở percentile 95. |
| Error rate `/ask` | ≤ 2% | Ngưỡng mặc định của `load_test.py`, áp dụng cho mọi kết quả khác HTTP 200. |
| Accuracy trên golden dataset | ≥ 85% trong CI | Ngưỡng Exercise 7.3. Nghiệm thu CP7 yêu cầu 100% và 0 regression so với v2 ban đầu. |

### 1.1 Exercise 7.1 — Metrics

Gửi `POST /ask` với câu “Prometheus thu thập metrics như thế nào?” tới v1 trên cổng 8001 và v2 trên cổng 8002. Cả hai trả HTTP 200, có `usage` và `request_id` trong JSON. Giá trị `request_id` trùng header `X-Request-ID`, lần lượt là `6ac7425e95b5` và `ed28745eccf3`. Hai lượt scrape `GET /metrics` trước và sau đều trả HTTP 200 trên mỗi agent.

- **Counter** `http_requests_total` đếm request theo method, route template và status.
- **Gauge** `agent_in_flight_requests` tăng khi bắt đầu xử lý và giảm khi kết thúc. Lúc scrape sau request, giá trị là 0.
- **Histogram** `agent_question_length_chars` ghi độ dài câu hỏi đã qua validation trước khi gọi mock LLM. Với câu 40 ký tự, `_count` tăng 1, `_sum` tăng 40, bucket tích lũy `le="20.0"` giữ nguyên và `le="50.0"` tăng 1 trên cả hai agent.

Trích output thực tế của `/metrics` sau khi gọi API và hai URL thử nghiệm trả 404.

```text
# Agent v1
http_requests_total{method="POST",route="/ask",status="200"} 1.0
http_requests_total{method="GET",route="unmatched",status="404"} 2.0
agent_question_length_chars_bucket{le="20.0"} 0.0
agent_question_length_chars_bucket{le="50.0"} 1.0
agent_question_length_chars_count 1.0
agent_question_length_chars_sum 40.0
agent_in_flight_requests 0.0
agent_info{model="mock-llm-small",version="v1"} 1.0
# Agent v2
http_requests_total{method="POST",route="/ask",status="200"} 1.0
http_requests_total{method="GET",route="unmatched",status="404"} 2.0
agent_question_length_chars_bucket{le="20.0"} 0.0
agent_question_length_chars_bucket{le="50.0"} 1.0
agent_question_length_chars_count 1.0
agent_question_length_chars_sum 40.0
agent_in_flight_requests 0.0
agent_info{model="mock-llm-small",version="v2"} 1.0
```

Mỗi tổ hợp nhãn tạo một time series. Dùng path thực làm `route` sẽ khiến mỗi URL lạ sinh thêm series cho Counter và nhiều series bucket, count, sum cho Histogram. Điều đó làm tăng RAM, dung lượng lưu trữ và chi phí truy vấn. Trong kiểm thử, `/cp7-metrics-example-a` và `/cp7-metrics-example-b` cùng nằm trong `route="unmatched"`, với Counter 404 bằng 2. Histogram độ dài dùng bucket cố định để giới hạn số series.

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

Mỗi lượt đo 300 request tới v2 trước sửa knowledge base, sau một request warm-up được script loại khỏi phép đo. RPS và error rate lấy trên toàn bộ 300 request. Latency lấy trên các response HTTP 200. Mock error rate cấu hình 0.01 cho mọi lượt load.

### 2.1 Concurrency vs latency (agent v2)

Cố định `MOCK_SLOW_RATE=0.03`. JSON tương ứng mang tên `load_v2_c1.json`, `load_v2_c10.json`, `load_v2_c50.json` và `load_v2_c100.json`.

| Concurrency | RPS | avg (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO | Exit code |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 4.13 | 243.3 | 187.7 | 220.7 | 1708.6 | 1.00% | PASS | 0 |
| 10 | 35.98 | 246.5 | 192.4 | 225.6 | 1703.5 | 0.33% | PASS | 0 |
| 50 | 96.0 | 288.9 | 208.1 | 504.9 | 1726.4 | 0.00% | FAIL (p95) | 1 |
| 100 | 48.02 | 1393.9 | 923.4 | 4151.3 | 4618.9 | 1.67% | FAIL (p95) | 1 |

Async I/O cho phép chồng lấp thời gian chờ mock LLM, nhưng throughput tăng dưới tuyến tính. Từ concurrency 1 đến 100, RPS chỉ tăng 11.6 lần và giảm từ 96.0 ở c50 xuống 48.02 ở c100. c50 vượt ngưỡng p95 với 504.9 ms, còn c100 có cả p50 923.4 ms và p95 4151.3 ms. Độ trễ ở c100 tăng trên cả phần giữa của phân bố, phù hợp với hiện tượng tranh chấp tài nguyên khi tải cao. Với một batch hữu hạn, worker hoàn thành nhanh dần hết việc trong khi một số request chậm kéo dài thời gian kết thúc. Chi phí client, socket, event loop và logging cũng giới hạn mức tăng throughput. Phép đo end-to-end với một lượt mỗi cấu hình chưa đủ để xác định nút thắt hay giới hạn công suất.

### 2.2 Tail latency

Khởi động lại v2 cho từng cấu hình, giữ concurrency 20. JSON tương ứng là `load_v2_slow_0.json`, `load_v2_slow_0.03.json` và `load_v2_slow_0.1.json`.

| MOCK_SLOW_RATE | RPS | avg (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO | Exit code |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 96.66 | 201.3 | 202.1 | 239.7 | 255.6 | 1.33% | PASS | 0 |
| 0.03 | 63.95 | 234.6 | 195.0 | 231.7 | 1714.7 | 1.00% | PASS | 0 |
| 0.1 | 46.32 | 366.5 | 194.0 | 1701.3 | 1733.5 | 1.67% | FAIL (p95) | 1 |

Từ slow rate 0 đến 0.03, trung bình đổi từ 201.3 lên 234.6 ms và p99 từ 255.6 lên 1714.7 ms. Một nhóm nhỏ chịu thêm độ trễ lớn chỉ đóng góp theo tỷ trọng của nhóm vào trung bình, nhưng có thể chi phối p99. Ở 0.1, p95 lên 1701.3 ms vì nhóm chậm chiếm phần lớn hơn trong mẫu. SLO dùng p95 để theo dõi trải nghiệm của đa số, còn p99 cho thấy mức chờ ở đuôi. Ngưỡng SLO được giữ như script. Mỗi cấu hình là một lượt đo local có jitter và lỗi ngẫu nhiên.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Dùng golden dataset và grader gốc với pass threshold 0.6 cho từng câu. Tắt lỗi mock ngẫu nhiên bằng `MOCK_ERROR_RATE=0` khi đo chất lượng câu trả lời. Các JSON lần lượt là `eval_v1.json`, `eval_v2.json` và `eval_v2_fixed.json`. Baseline của v2 là v1, baseline của v2 fixed là v2 trước sửa.

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
| --- | --- | --- | --- |
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.0 | 109.0 | 115.0 |
| Tổng cost (USD) | 0.000402 | 0.000760 | 0.000802 |
| Cost / câu đúng (USD) | 0.00040215 | 0.00003619 | 0.00003488 |
| Eval p50 / p95 (ms) | 159.2 / 189.5 | 185.4 / 1552.0 | 195.9 / 1526.6 |
| Quality gate | FAIL (≥ 80%) | PASS (≥ 80%) | PASS (≥ 100%) |
| Regression so với baseline | — | 0 | 0 |

Cả hai câu sai ban đầu thiếu ba keyword và có score 0. Retrieval chưa có mục phù hợp nên mock trả lời chung chung.

| ID | Câu trả lời trước sửa | Keyword bị thiếu | Thay đổi |
| --- | --- | --- | --- |
| security-02 | “Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.” | token, hết hạn, chữ ký | Thêm mục JWT mô tả token có chữ ký, thời hạn và cách xác minh, đối chiếu với API key. |
| scaling-03 | “Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.” | cpu, memory, custom metrics | Thêm mục Kubernetes HPA mô tả autoscaling theo CPU, memory và custom metrics. |

Retrieval cho v2 thêm ngữ cảnh và cải thiện số câu đúng. So với v1, v2 fixed dùng nhiều token hơn mỗi câu và có tổng chi phí mô phỏng cao hơn, nhưng chi phí trên mỗi câu đúng giảm. p50 của v2 cao hơn v1 trong lượt này, phù hợp với chi phí bước retrieval và prompt dài hơn. Với 23 mẫu ngẫu nhiên, p95 có thể biến động mạnh.

### 3.1 Quality gate

Workflow [.github/workflows/eval.yml](.github/workflows/eval.yml) chạy trên pull request, chờ agent v2 sẵn sàng rồi gọi `python eval/run_eval.py --url http://localhost:8002 --min-accuracy 0.85`. Exit code 1 làm job fail. Muốn gate chặn merge, cần đặt job `eval` là required status check trên GitHub.

- Local v2 fixed với lệnh trên đạt 23/23, exit 0. Cùng ngưỡng 85% với v1 trên cổng 8001 trả exit 1 (1/23).
- Local v2 fixed với `--min-accuracy 1.0 --baseline` trỏ tới `eval_v2.json` đạt 23/23, 0 regression, exit 0.
- Trạng thái GitHub Actions chưa được xác minh. Các kết quả trên lấy từ lệnh local.

---

## 4. Observability stack (production)

CP8 chạy ngày 26/11/2026 trên Docker Desktop/WSL2, với 8 CPU và 7,69 GiB RAM mà Docker báo cáo. Project là `k5-day14-observability`. Mỗi Agent có một Uvicorn worker, giới hạn 0,5 CPU và 256 MiB RAM. Toàn bộ request dùng mock LLM nội bộ.

Agent ban đầu thoát với `ModuleNotFoundError: No module named 'uvicorn'`. Dockerfile production của observability đặt `PYTHONUSERBASE=/home/agent/.local` để Python tìm package tại nơi stage runtime nhận dependency từ builder. Agent chạy với user `agent`.

| Service | Địa chỉ | Kiểm tra |
| --- | --- | --- |
| Agent | `http://agent:8000` trong mạng Compose | Target scrape trực tiếp `/metrics` |
| Nginx | `http://localhost:8080` | `/health` và `/ready` trả HTTP 200 |
| Grafana | [Day 14 — AI Agent Overview](http://localhost:3000/d/day14-agent-overview/day-14-e28094-ai-agent-overview) | Dashboard provision sẵn và truy vấn Prometheus qua datasource |
| Prometheus | [Targets](http://localhost:9090/targets), [Alerts](http://localhost:9090/alerts) | `/-/ready` trả HTTP 200 |
| Jaeger | [Jaeger UI](http://localhost:16686), OTLP HTTP cổng 4318 | `/api/v3/services` có `observable-agent` |
| Locust | [Locust UI](http://localhost:8089) | UI trả HTTP 200, headless xuất CSV |

`GET http://localhost:8080/metrics` trả **HTTP 404** với trang HTML `404 Not Found` của Nginx. Block `location = /metrics` trả 404 trực tiếp để giữ dữ liệu vận hành trong mạng Compose. Prometheus tìm IP Agent qua Docker DNS và scrape /metrics trực tiếp từng replica.

### 4.1 Exercise 7.4 — Golden Signals và ảnh bàn giao

Locust UI chạy với 30 user, spawn 5 user/s và host nội bộ `http://nginx`. Sau 80 giây, API Locust báo `running`, 30 user, 1.440 lượt `/ask` với 21 failures và 146 lượt `/health` với 0 failures. Bảng dưới lấy từ Prometheus lúc **19:55:40 GMT+7**, trước chaos. Các panel dùng cửa sổ 1 phút, trừ cost như ghi trong bảng.

| Golden Signal | Số đo |
| --- | --- |
| Latency | p50 **175,44 ms**, p95 **293,65 ms**, p99 **1.830,25 ms**, avg **233,87 ms** |
| Traffic | **18,17 req/s** ở `POST /ask` |
| Errors | **1,13%** HTTP 5xx ở `POST /ask` |
| Saturation | **4** request in-flight ở thời điểm đo, trung bình **4,17** và đỉnh **7** qua các mẫu scrape trong 1 phút |

Hai target Agent đều `UP`, cùng target tự giám sát của Prometheus. Nginx chia tải gần đều giữa `172.20.0.6:8000` (8,97 req/s, 49,38%) và `172.20.0.8:8000` (9,20 req/s, 50,62%).

p95 cao hơn avg **59,78 ms**. p99 trên 1,8 giây cho thấy một nhóm nhỏ request có độ trễ cao hơn đáng kể. p95 và p99 trên dashboard là nội suy theo bucket Prometheus. Các percentile trong CSV ở mục 5 đo end-to-end bằng Locust.

`Tokens/s` đo **1.334,86 input** và **713,05 output**. Input chứa system prompt, câu hỏi và ngữ cảnh retrieval của v2, còn output chỉ chứa câu trả lời. Token của mock được ước lượng theo độ dài chuỗi, và hai counter token chỉ cộng khi LLM thành công. Panel cost 1 giờ ghi **0,538 USD** mô phỏng. Burn rate là **4,90 USD/giờ** theo cửa sổ 5 phút, có chứa tải 100 user từ hai lượt benchmark trước và có thể cộng cả series replica vừa rời stack. Đây là ước tính dựa trên counter và bảng giá mock.

Tại mốc bàn giao 19:59:54 GMT+7, Grafana qua datasource Prometheus đọc 15,40 req/s, 18,13% lỗi 5xx, p95 1.890,94 ms và 16 request in-flight. Hai replica Agent đều healthy. Locust giữ 30 user với cấu hình chaos B tại mốc này. Ảnh Grafana được chụp sau đó trong chaos B, hiển thị 14,9 req/s, 18,96% lỗi, p95 1,89 s và 8 request in-flight. Bảng Golden Signals phía trên là baseline đo trước khi bật chaos.

Học viên đã trực tiếp kiểm tra giao diện và lưu đủ bốn ảnh CP8 trong thư mục `screenshots/` ở gốc repo.

- [grafana-dashboard.png](screenshots/grafana-dashboard.png) — Dashboard có tải trong chaos B, hiện Traffic, Error rate, Latency p95 và Saturation.
- [jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png) — Trace `POST /ask` trả HTTP 200 với tổng thời lượng hiển thị 2,5 s. Chi tiết span `chat mock-llm-small` đang mở và hiển thị 2,4 s theo cách làm tròn của giao diện. Thời lượng chính xác và log JSON có cùng trace ID được ghi ở mục 4.3.
- [jaeger-error-trace.png](screenshots/jaeger-error-trace.png) — Error trace, mở span `chat mock-llm-small` và event `exception`.
- [prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png) — Trang Alerts, hiện đồng thời `AgentHighErrorRate` và `AgentHighLatencyP95` ở trạng thái firing.

### 4.2 Exercise 7.6 — Alerting và chaos

`promtool test rules` chạy trong `prom/prometheus:v3.16.0` với file `/p/alert_rules_test.yml` và trả `SUCCESS`.

| Rule | Điều kiện | `for` |
| --- | --- | --- |
| `AgentHighErrorRate` | Tỷ lệ HTTP 5xx của `/ask` trong 1 phút > 5% | 1 phút |
| `AgentHighLatencyP95` | p95 `/ask` từ histogram trong 1 phút > 1 giây | 2 phút |
| `AgentInstanceDown` | Target agent có `up == 0` | 30 giây |
| `LLMCostBurnRateHigh` | Tốc độ chi phí 5 phút quy đổi > 2 USD/giờ | 2 phút |

Prometheus scrape và đánh giá rule mỗi 5 giây. Các rule vận hành dùng ngưỡng riêng trong bảng. Ngưỡng benchmark SLO ở mục 1 là 500 ms và 2%. Bộ unit test gốc kiểm tra error rate và instance down. Latency p95 được kiểm tra bằng traffic và fault injection trong thí nghiệm B.

Locust giữ 30 user trong cả hai thí nghiệm. Thời điểm bắt đầu là lúc chạy Compose để áp dụng cấu hình. Thời điểm firing lấy từ mẫu `ALERTS{alertstate="firing"}` đầu tiên của Prometheus sau mốc bắt đầu. Các thời điểm dưới đây dùng GMT+7 ngày 26/11/2026.

| Thí nghiệm | Bắt đầu | Pending | Firing | Phát hiện |
| --- | --- | --- | --- | --- |
| A — `MOCK_ERROR_RATE=0.2` | 19:55:48.630 | 19:56:12.401 | 19:57:12.401 | **83,771 giây** |
| B — `MOCK_SLOW_RATE=0.3`, giữ error rate 0.2 | 19:57:19.352 | 19:57:47.401 | 19:59:47.401 | **148,048 giây** |

- **A — `AgentHighErrorRate`**. Mock LLM trả lỗi upstream được Agent ánh xạ thành HTTP 503. Panel Error rate phản ánh tỷ lệ 5xx của `/ask` trong một phút. Tại lần xác minh firing của A, Prometheus ghi **18,56%**.
- **B — `AgentHighLatencyP95`**. Tăng tỷ lệ request chịu thêm 1.500 ms. Panel Latency p95 tăng qua 1 giây. Giữ error rate 20% để hai điều kiện cùng được duy trì sau khi B firing.
- **Cost trong benchmark**. `LLMCostBurnRateHigh` đã firing trước thí nghiệm A khi cửa sổ 5 phút còn chứa tải benchmark. Việc này xuất phát từ số token trên mỗi giây và bảng giá mock. Cost alert trở lại inactive trước mốc bàn giao. Thí nghiệm C với model lớn và thí nghiệm D với pause instance không được thực hiện.

Tại 19:59:54 GMT+7, API Alerts xác nhận đồng thời `AgentHighErrorRate` firing (18,42%) và `AgentHighLatencyP95` firing (1.887,63 ms). Giá trị alert lấy từ lần đánh giá rule gần nhất, còn panel Grafana truy vấn tức thời.

Quality regression khi chuyển sang v1 cần eval như mục 6. HTTP status, latency, tình trạng scrape và chi phí chỉ mô tả vận hành. V1 mất retrieval, có thể trả câu chung chung với HTTP 200 và thậm chí dùng ít token hơn. Kết quả CP7 xác nhận regression nội dung bằng 23 câu golden.
### 4.3 Exercise 7.5 — Debug bằng trace

Jaeger nhận span của service `observable-agent` từ OpenTelemetry. Image 2.23.0 trả HTTP 404 cho route cũ `/api/services`. Tôi truy vấn trace qua API v3. [Tài liệu API Jaeger](https://www.jaegertracing.io/docs/2.dev/architecture/apis/).

**Slow trace** `7f8c3f05cdd257099c3ef7492970d8be`. Đây là trace HTTP 200 có root span dài nhất trong kết quả tìm kiếm với thời lượng tối thiểu 1,5 giây trong cửa sổ 30 user trước chaos. [Mở slow trace](http://localhost:16686/trace/7f8c3f05cdd257099c3ef7492970d8be).

| Span | Duration theo Jaeger |
| --- | ---: |
| `POST /ask` | 2.454,274 ms |
| `agent.run` | 2.452,209 ms |
| `agent.retrieve_context` | 24,592 ms |
| `chat mock-llm-small` | **2.427,357 ms** |

Span `chat mock-llm-small` chiếm **98,90%** tổng thời gian Jaeger. Span cha bao gồm thời gian của span con. Log `http_request` cùng `trace_id` và root `span_id` ghi HTTP 200 với 1.713,3 ms theo đồng hồ monotonic của ứng dụng. Trace dùng chênh lệch timestamp của span. Hai phép đo khác nhau ở request này và nguyên nhân chênh lệch chưa được cô lập.

```json
{"ts": "2026-11-26T12:54:42.942164+00:00", "level": "INFO", "service": "observable-agent", "instance": "c3f5b477f534", "event": "http_request", "trace_id": "7f8c3f05cdd257099c3ef7492970d8be", "span_id": "b4b1d78dab0119b2", "request_id": "33094b10c139", "method": "POST", "route": "/ask", "status": 200, "ms": 1713.3}
```

**Error trace** `461bf4b676527f9197994a4b17f9d030`. Tìm ID từ log `llm_error` trong thí nghiệm A rồi truy vấn Jaeger bằng ID đó. Root `POST /ask` dài **124,155 ms** và có trạng thái Error. `agent.run` dài **120,412 ms** và `agent.retrieve_context` dài **26,369 ms**. Span `chat mock-llm-small` dài **93,381 ms**, ID `44cbbf29558bc574`, có event `exception` với type `utils.mock_llm.LLMError` và message `Upstream LLM error: 503 Service Unavailable (mock)`. `span_id` trong log khớp root `13ccbe3b4bac489d`. [Mở error trace](http://localhost:16686/trace/461bf4b676527f9197994a4b17f9d030).

```json
{"ts": "2026-11-26T12:56:05.492843+00:00", "level": "INFO", "service": "observable-agent", "instance": "fe99db7ca9cf", "event": "llm_error", "trace_id": "461bf4b676527f9197994a4b17f9d030", "span_id": "13ccbe3b4bac489d", "request_id": "889087d75c08", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Hai lượt dùng cùng Locust 2.47.0, Nginx, tập câu hỏi, lịch chờ 0,5–2 giây, 100 user, spawn 10 user/s và 2 phút mỗi lượt. Agent v2 dùng `mock-llm-small`, `MOCK_LATENCY_MS=120`, `MOCK_SLOW_RATE=0.03` và `MOCK_ERROR_RATE=0.01`. Chờ Prometheus thấy đủ replica trước mỗi lượt. Dùng `docker compose run --no-deps --rm locust` để không thay đổi replica của dịch vụ phụ thuộc. Một lượt khởi động ban đầu bị loại vì Compose tự bật replica thứ hai khi chạy Locust kèm dependencies.

| Replicas | Dòng CSV | Requests | RPS | Avg (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Failures | Error rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `POST /ask` | 6.868 | 56,95 | 308,89 | 210 | 930 | 1.700 | 67 | 0,98% |
| 3 | `POST /ask` | 7.192 | 59,03 | 248,32 | 200 | 380 | 1.700 | 84 | 1,17% |
| 1 | `Aggregated` | 7.507 | 62,25 | 286,64 | 210 | 880 | 1.700 | 67 | 0,89% |
| 3 | `Aggregated` | 7.848 | 64,42 | 228,26 | 190 | 340 | 1.700 | 84 | 1,07% |

Các số đọc trực tiếp từ CSV do Locust xuất, làm tròn khi trình bày. Error rate = Failure Count / Request Count. Trong cả hai lượt, mọi failure đều là HTTP 503 ở `/ask` và `/health` có 0 failure. Lượt scale 1 vượt SLO p95 500 ms, lượt scale 3 đạt cả p95 và error rate theo ngưỡng ở mục 1. Cả hai lượt có mã thoát 1 của Locust vì có request thất bại. [CSV scale 1](benchmark-results/scale_1_stats.csv) · [CSV scale 3](benchmark-results/scale_3_stats.csv).

Throughput `/ask` tăng 3,65% trong khi p95 giảm 59,14%. p50 giảm nhẹ và p99 giữ ở 1.700 ms. Kết quả phù hợp với giảm độ trễ khi nhiều request chia qua ba worker độc lập, trong khi nhóm request rơi vào nhánh mock chậm vẫn chịu thêm 1.500 ms. Với 100 user có thời gian chờ giữa các request, đây là phép đo tải đóng. Kết quả throughput không cho biết công suất cực đại của mỗi cấu hình.

Prometheus xác nhận trong phút đo cuối có 1 target Agent `UP` ở scale 1 và 3 target `UP` ở scale 3. Tại **19:51:30 GMT+7**, scale 1 ghi 58,35 req/s trên `172.20.0.6:8000`. Tại **19:54:00 GMT+7**, scale 3 ghi 20,51, 20,24 và 20,46 req/s trên `172.20.0.6:8000`, `172.20.0.8:8000` và `172.20.0.9:8000`, tương ứng khoảng 33,51%, 33,07% và 33,43%. p95 histogram của LLM tại hai mốc lần lượt là 198,49 ms và 198,06 ms. Độ trễ mock p95 gần như giữ nguyên khi p95 HTTP giảm, phù hợp với giảm thời gian chờ xử lý quanh LLM. Phép đo này không cô lập riêng ảnh hưởng của CPU quota, logging và hàng đợi máy client.

---

## 6. Kết luận

1. Route template và histogram bucket cố định giới hạn cardinality trong khi vẫn đo được phân bố.
2. p95 và p99 giúp thấy độ trễ của nhóm request mà giá trị trung bình dễ che khuất.
3. Golden dataset, baseline và exit code giúp phát hiện lỗi nội dung ngay cả khi HTTP thành công.

Nếu lên production, có thể theo dõi tỷ lệ câu trả lời đạt trên một bộ câu hỏi tổng hợp định kỳ và cảnh báo khi tỷ lệ này xuống dưới ngưỡng đã thống nhất.

### Giới hạn kiểm thử CP8

- Mỗi cấu hình scaling có một lượt đo 2 phút trên cùng máy Docker. Locust, Agent, Nginx và telemetry chia sẻ tài nguyên. Jitter, lỗi ngẫu nhiên, thời gian ramp-up và việc dùng tập câu hỏi nhỏ ảnh hưởng kết quả.
- `/ask` trên dashboard đếm lỗi 5xx tại Agent. Locust đo toàn bộ lỗi nhìn thấy từ client qua Nginx và cả độ trễ mạng, proxy, xử lý response. Gauge in-flight là số mẫu tại các thời điểm scrape, nên đỉnh quan sát được có thể thấp hơn đỉnh thực.
- Token, cost và fault injection là hành vi mock. CP8 dùng stack observability production tại local. CP7 đo chất lượng trên agent develop, còn CP8 báo hành vi vận hành của Agent production và không chạy lại eval trong stack đó.
- Bằng chứng dashboard và trace phụ thuộc stack đang chạy. Jaeger dùng bộ nhớ của container. Hai lượt benchmark lấy cùng 100 user theo checkpoint nhưng không ghim seed của câu hỏi hoặc độ trễ.

### Câu hỏi thảo luận Part 7

1. Một câu trả lời sai vẫn có thể trả HTTP 200 trong giới hạn latency và cost. Theo dõi accuracy theo phiên bản bằng eval định kỳ trên golden dataset, chạy quality gate trước khi merge hoặc rollout, rồi dùng canary, phản hồi người dùng và đánh giá mẫu câu trả lời thật để phát hiện regression sau deploy. Kết quả CP7 đo được 1/23 câu đúng ở v1 và 23/23 ở v2 sau khi sửa KB. Bốn rule vận hành không đọc nội dung câu trả lời.
2. Pull cho phép Prometheus đặt lịch scrape, tự tìm target và phát hiện scrape lỗi qua `up`. Khi Cloud Run scale về 0 hoặc instance tồn tại ngắn hơn chu kỳ scrape, Prometheus có thể bỏ lỡ dữ liệu. Có thể dùng metrics do nền tảng cung cấp, kiểm tra từ bên ngoài hoặc gửi số liệu qua OpenTelemetry Collector phù hợp với vòng đời instance.
3. Thêm `user_id` với 100.000 giá trị tạo tới 100.000 series chỉ riêng cho mỗi tổ hợp method, route và status có đủ người dùng. RAM, lưu trữ và chi phí truy vấn đều tăng. Giữ ID người dùng trong log hoặc trace có kiểm soát truy cập.
4. Trace mọi request làm tăng chi phí xuất, truyền, lập chỉ mục và lưu span. Lấy mẫu 10% giảm khối lượng nhưng có thể bỏ sót request chậm hoặc lỗi hiếm. Tail sampling có thể ưu tiên các trace lỗi và chậm nếu collector đủ tài nguyên để chờ các span.
5. Với `for: 0s`, spike ngắn hoặc ít request cũng có thể làm alert firing ngay ở lần đánh giá tiếp theo. Với `for: 30m`, sự cố kéo dài bị báo chậm và sự cố ngắt quãng có thể liên tục đặt lại thời gian chờ. Ngưỡng 1 phút của bài cân bằng hai rủi ro đó.
