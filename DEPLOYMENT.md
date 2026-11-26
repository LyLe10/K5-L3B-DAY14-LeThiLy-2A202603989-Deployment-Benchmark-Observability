# Deployment Information

## Public URL

https://day14-agent-tzgb.onrender.com

## Platform

Render Free · Blueprint `day14-production` · Web service `day14-agent` · Key Value service `day14-agent-kv`.

Commit `b8f27a8` có trạng thái **Live** theo kết quả triển khai thực tế. Blueprint triển khai agent Part 6 từ [06-lab-complete/render.yaml](06-lab-complete/render.yaml). Railway bị chặn bởi giới hạn tạo tài nguyên của gói miễn phí, nên chưa có deployment Railway.

| Thành phần | Cấu hình trong Blueprint |
| --- | --- |
| Web service | Docker, gói `free`, region `singapore`, `rootDir: 06-lab-complete`, `dockerfilePath: ./Dockerfile`, `dockerContext: .`, `healthCheckPath: /health` |
| Key Value | Gói `free`, region `singapore`, `ipAllowList: []` (không cho phép truy cập từ IP bên ngoài), `maxmemoryPolicy: noeviction` |

## Environment Variables Set

| Biến | Cách cấu hình |
| --- | --- |
| `REDIS_URL` | Blueprint lấy `connectionString` từ `day14-agent-kv` qua `fromService`. |
| `AGENT_API_KEY` | Render sinh giá trị bằng `generateValue: true`. |
| `ENVIRONMENT` | `production`. |
| `RATE_LIMIT_PER_MINUTE` | `10`. |
| `DAILY_BUDGET_USD` | `1`. |
| `MONTHLY_BUDGET_USD` | `10`. |
| `PORT` | Dockerfile dùng cổng do nền tảng cấp, mặc định `8000` khi biến vắng mặt. Blueprint không đặt giá trị riêng. |
| `LOG_LEVEL` | Mẫu checklist liệt kê biến này. Blueprint hiện tại không khai báo. |

## Test Commands

Bốn lệnh theo CP6, chỉ in mã HTTP. Lệnh cuối dùng biến `AGENT_API_KEY` đã có trong môi trường shell.

```bash
BASE='https://day14-agent-tzgb.onrender.com'
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"What is deployment?"}'
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: ${AGENT_API_KEY:?}" -d '{"question":"What is deployment?"}'
```

## Kết quả public API

Kết quả kiểm thử đạt 4/4 PASS ngày 2026-11-26. Lượt xác nhận trong ảnh bắt đầu lúc **18:17:52 GMT+7** và cũng đạt **4/4 PASS**.

| Ca test | Request | HTTP thực tế | Kết quả |
| --- | --- | --- | --- |
| TC01 | `GET /health` | 200 | `{"status":"ok"}` |
| TC02 | `GET /ready` | 200 | `{"status":"ready"}` |
| TC03 | `POST /ask` thiếu API key | 401 | Request bị từ chối. |
| TC04 | `POST /ask` có API key hợp lệ | 200 | Deployment là quá trình đưa code từ máy bạn lên server để người khác dùng được. |

## Checker chính thức

Lệnh kiểm tra production readiness đầy đủ, từ thư mục `06-lab-complete/`.

```bash
python check_production_ready.py --public-url https://day14-agent-tzgb.onrender.com
```

| Hạng mục | Kết quả kiểm thử |
| --- | --- |
| Tổng kết | **12/12 tiêu chí, 44/44 checks passed, exit code 0** |
| Docker build và image | 7 giây, 273 MB theo checker |
| Docker graceful shutdown | Exit code 0 trong 1,6 giây |
| Structured logging | 12 dòng JSON hợp lệ |
| Public health check | PASS |
| Rate limit local | PASS, trạng thái còn sau khi restart agent |
| Redis mất kết nối ở local | `/ready` trả 503, `/health` vẫn trả 200 |
| Cost guard local | HTTP 402 |
| SIGTERM khi đang xử lý request ở local | Request trả HTTP 200, process thoát với exit code 0 |

## Giới hạn xác minh

- Render Free có thể gặp hiện tượng cold start sau một khoảng thời gian không hoạt động, làm tăng độ trễ của request đầu tiên.
- Chưa đánh giá khả năng duy trì trạng thái Redis trên môi trường cloud sau khi dịch vụ Redis khởi động lại.
- Production Readiness Checker xác minh runtime local, Docker và endpoint `GET /health` trên public URL. Các endpoint public còn lại được kiểm thử trực tiếp trên Render bằng `curl`, với kết quả 4/4 test case đạt yêu cầu.

## Screenshots

- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png) — một ảnh terminal chứa URL public, response body và mã HTTP thực tế của cả bốn ca.
