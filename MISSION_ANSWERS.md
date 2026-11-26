# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

1. **AP-01 — Hardcoded credentials.** `01-localhost-vs-production/develop/app.py:15-18` đặt API key mẫu và URL database có thông tin đăng nhập trực tiếp trong source. Nếu dùng credential thật, người đọc repo hoặc lịch sử Git có thể lấy được chúng. Production đọc các key từ environment tại `production/config.py:26-32`; vẫn cần quản lý secret an toàn bên ngoài code.
2. **AP-02 — Logging sensitive information.** `develop/app.py:31-38` in cả câu hỏi và biến API key. Log có thể bị thu thập hoặc chia sẻ và làm lộ thông tin nhạy cảm. `production/app.py:110-122` ghi độ dài câu hỏi và response, không ghi key hay nội dung câu hỏi trong các event này. Không suy ra mọi log production đều hợp lệ hoặc an toàn.
3. **AP-03 — Missing health/readiness endpoints.** `develop/app.py:25-39` chỉ khai báo `/` và `/ask`; `develop/app.py:42-43` cũng nêu thiếu health check. Thiếu probe chuyên dụng làm platform khó kiểm tra trạng thái process và mức sẵn sàng. `production/app.py:135-161` có `/health` và `/ready`; readiness ở đây chỉ dựa vào cờ nội bộ, chưa kiểm tra dependency ngoài.
4. **AP-04 — Hardcoded host and port.** `develop/app.py:47-53` cố định host loopback và port 8000. Service có thể không nhận kết nối từ bên ngoài môi trường chạy hoặc không nghe port platform cấp. Production đọc `HOST` và `PORT` từ environment tại `production/config.py:16-19` và dùng chúng ở `production/app.py:192-198`.
5. **AP-05 — Auto reload always enabled.** `develop/app.py:49-53` đặt `reload=True`; file watcher có thể gây restart ngoài dự kiến trong môi trường vận hành. Production chỉ bật reload khi `DEBUG=true`, mặc định false: `production/config.py:19`, `production/app.py:192-198`.
6. **AP-06 — Hardcoded application configuration.** `develop/app.py:20-22` đặt cố định `DEBUG` và `MAX_TOKENS`, gây khó thay cấu hình giữa các môi trường. Hai biến này không thấy được dùng trong request handler develop, nên không kết luận chúng đã gây lỗi runtime. Production định nghĩa cấu hình tương ứng từ environment tại `production/config.py:19-29`.

Đường dẫn `develop/` và `production/` viết tắt ở trên đều thuộc `01-localhost-vs-production/`.

### Exercise 1.2: Development runtime testing

Người dùng chạy từ `01-localhost-vs-production/develop`:

```bash
../../.venv/bin/python app.py
```

Startup thực tế: Uvicorn lắng nghe `localhost:8000`; reloader PID 11079, server PID 11097; application startup hoàn tất.

| ID | Request | Expected | Actual | Response thực tế | Kết quả |
| --- | --- | --- | --- | --- | --- |
| TC-01 | `GET /` | 200 | 200 | `{"message":"Hello! Agent is running on my machine :)"}` | PASS |
| TC-02 | `POST /ask?question=Hello` | 200 | 200 | `{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}` | PASS |
| TC-03 | `POST /ask`, JSON `{"question":"Hello"}` | 422 | 422 | `{"detail":[{"type":"missing","loc":["query","question"],"msg":"Field required","input":null}]}` | PASS |
| TC-04 | `GET /health` | 404 | 404 | `{"detail":"Not Found"}` | PASS |
| TC-05 | `GET /ready` | 404 | 404 | `{"detail":"Not Found"}` | PASS |

Development HTTP tests: **5/5 PASS**. Người dùng đã dừng develop và xác nhận port 8000 không còn listener trước khi chạy production.

Theo `develop/app.py:30-31`, `question` là query parameter, tức nằm trên URL; JSON body là dữ liệu trong thân request và không thay thế tham số query bắt buộc này. Vì vậy TC-03 trả 422 cho input thiếu theo contract, còn 404 ở TC-04/05 cho biết các route đó không tồn tại ở develop. Cả hai bản gọi Mock LLM cục bộ; response có thể thay đổi do lựa chọn ngẫu nhiên (`develop/utils/mock_llm.py:21-32`).

### Exercise 1.3: Comparison table

Các nhận định trong bảng là phân tích **source**; kết quả thực tế được ghi riêng ở các test case bên dưới và tại Exercise 1.2.

| Feature | Develop | Production | Why Important? |
|---|---|---|---|
| Configuration | Giá trị đặt trong `develop/app.py:20-22`. | `production/config.py:14-29` đọc environment. | Cấu hình theo môi trường không cần sửa source; hai biến mẫu develop không thấy được dùng trong handler. |
| Secret management | Key và thông tin kết nối mẫu nằm trong source: `develop/app.py:15-18`. | Key đọc từ environment: `production/config.py:26-32`. | Tránh đưa credential thật vào code và lịch sử Git; đọc env không tự bảo đảm xác thực API. |
| Logging | `print` câu hỏi và key: `develop/app.py:31-38`. | Log event gồm độ dài và client IP: `production/app.py:27-32,110-122`. | Hạn chế lộ nội dung; formatter có dạng JSON nhưng không thể khẳng định mọi dòng là JSON hợp lệ. |
| Network binding | `localhost:8000` cố định: `develop/app.py:47-53`. | Host/port từ config, mặc định `0.0.0.0:8000`: `production/config.py:17-18`, `production/app.py:192-197`. | Giúp service nhận kết nối và dùng port do môi trường cấp. |
| Auto reload | Luôn bật khi chạy file: `develop/app.py:49-53`. | Theo `DEBUG`, mặc định tắt: `production/config.py:19`, `production/app.py:198`. | Tránh tự restart do thay đổi file khi vận hành. |
| Request contract | `POST /ask` nhận query, response chứa `answer`: `develop/app.py:29-39`. | `POST /ask` đọc JSON và trả `question`, `answer`, `model`: `production/app.py:102-128`. | Client cần gửi đúng định dạng; contract sai dẫn tới lỗi thay vì kết quả mong đợi. |
| Health check | Không khai báo `/health`: `develop/app.py:25-43`. | `GET /health`: `production/app.py:135-149`. | Probe giúp theo dõi process còn đáp ứng. |
| Readiness check | Không khai báo `/ready`: `develop/app.py:25-43`. | `GET /ready` dựa trên cờ lifecycle: `production/app.py:35-36,152-161`. | Giúp quyết định route traffic; cờ nội bộ chưa chứng minh dependency ngoài sẵn sàng. |
| Metrics | Không khai báo `/metrics`: `develop/app.py:25-43`. | `GET /metrics` trả JSON uptime, environment, version: `production/app.py:164-173`. | Cung cấp thông tin quan sát cơ bản; response không phải Prometheus exposition format. |
| Lifecycle management | Không có lifespan do ứng dụng khai báo: `develop/app.py:13-54`. | Có lifespan startup/shutdown và handler SIGTERM: `production/app.py:39-67,180-189`. | Cho phép chuẩn bị và dọn dẹp tài nguyên; hành vi graceful đầy đủ cần kiểm thử riêng. |

#### Production startup và HTTP evidence

Người dùng quan sát warning `OPENAI_API_KEY not set — using mock LLM`, `Started server process [12757]`, `Waiting for application startup.`, `Application startup complete.` và Uvicorn lắng nghe `http://0.0.0.0:8000`. Không quan sát thấy reloader process.

| ID | Request | Expected | Actual | Response thực tế | Kết quả |
| --- | --- | --- | --- | --- | --- |
| TC-06 | `GET /` | 200 | 200 | `{"app":"AI Agent","version":"1.0.0","environment":"development","status":"running"}` | PASS |
| TC-07 | `POST /ask`, JSON `{"question":"Hello"}` | 200 | 200 | `{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","model":"gpt-4o-mini"}` | PASS |
| TC-08 | `POST /ask`, JSON `{}` | 422 | 422 | `{"detail":"question field is required"}` | PASS |
| TC-09 | `GET /health` | 200 | 200 | `{"status":"ok","uptime_seconds":35.9,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T07:34:35.024017+00:00"}` | PASS |
| TC-10 | `GET /ready` | 200 | 200 | `{"ready":true}` | PASS |
| TC-11 | `GET /metrics` | 200 | 200 | `{"uptime_seconds":35.9,"environment":"development","version":"1.0.0"}` | PASS |

Production HTTP tests: **6/6 PASS**.

#### Production shutdown evidence

Người dùng nhấn Ctrl+C. Log ghi `Shutting down`, `Waiting for application shutdown.`, `Application shutdown complete.` và `Finished server process [12757]`. Sau đó xuất hiện traceback gồm `asyncio.exceptions.CancelledError` và `KeyboardInterrupt`. Hai lần kiểm tra `ss -ltnp | grep ':8000'` đều không có output.

| Hạng mục | Kết quả |
| --- | --- |
| Application shutdown lifecycle | PASS |
| Server termination và giải phóng port 8000 | PASS |
| Shutdown không có exception | WARNING: có traceback sau log shutdown |
| Exit code | Chưa xác minh |
| Graceful shutdown bằng SIGTERM | Chưa kiểm thử |
| Hoàn tất request đang xử lý khi shutdown | Chưa kiểm thử |
| Nguyên nhân traceback | Chưa xác minh |

Các bằng chứng trên chưa chứng minh graceful shutdown toàn diện.

### Part 1 — Test summary

- Development: **5/5 PASS**; Production: **6/6 PASS**.
- Tổng: **11/11 HTTP tests PASS**, tương đương **100% trong phạm vi các test đã thực hiện**.

### Limitations

- Chưa cloud deployment; cả hai phiên bản sử dụng Mock LLM. Nhãn `gpt-4o-mini` trong response không chứng minh OpenAI API đã được gọi.
- Source bản production chạy với runtime environment `development`; endpoint `/ask` của Part 1 chưa xác thực API key.
- Readiness chưa kiểm tra external dependencies; metrics chưa ở Prometheus exposition format.
- Shutdown lifecycle và port release PASS; exception-free shutdown WARNING. Exit code, SIGTERM, hoàn tất request đang xử lý và nguyên nhân traceback chưa được xác minh.

## AI log

- **Đã hỏi:** hỗ trợ phân tích yêu cầu, thiết kế checkpoint và test cases, review kết quả và bổ sung báo cáo Part 1 theo bằng chứng có sẵn.
- **Đã nhận:** ChatGPT hỗ trợ phân tích yêu cầu, thiết kế checkpoint và test cases, review kết quả; Codex phân tích source code và hỗ trợ viết báo cáo.
- **Tự thực hiện và kiểm tra:** người dùng trực tiếp chạy server, curl, kiểm tra shutdown, port và Git status, rồi cung cấp các kết quả runtime. Không khẳng định người dùng đã xác minh độc lập mọi nhận định phân tích source trong báo cáo này.
- **Revision:** review lần đầu phát hiện `MISSION_ANSWERS.md` thiếu Exercise 1.1–1.3 và Development evidence; Codex được yêu cầu bổ sung dựa trên bằng chứng thực tế. Người dùng cần review nội dung revision này.
