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

- **4.1 Screenshot** — Pending CP8.
- **4.2 Thí nghiệm phá hệ thống** — Pending CP8.
- **4.3 Debug bằng trace** — Pending CP8.

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Pending CP8.

---

## 6. Kết luận

1. Route template và histogram bucket cố định giới hạn cardinality trong khi vẫn đo được phân bố.
2. p95 và p99 giúp thấy độ trễ của nhóm request mà giá trị trung bình dễ che khuất.
3. Golden dataset, baseline và exit code giúp phát hiện lỗi nội dung ngay cả khi HTTP thành công.

Nếu lên production, có thể theo dõi tỷ lệ câu trả lời đạt trên một bộ câu hỏi tổng hợp định kỳ và cảnh báo khi tỷ lệ này xuống dưới ngưỡng đã thống nhất.
