# Benchmark & Observability Report — Day 14

> CP7 đo agent develop trên máy local; CP8 đo stack trong thư mục `production/` bằng Docker Desktop trên cùng máy. Chưa benchmark Railway.
> Số liệu lấy từ report JSON/CSV hoặc Prometheus API đã lưu; mỗi phần ghi lệnh tạo/đọc kết quả.

**Họ tên:** Trần Duy Thanh
**Ngày chạy:** 26/11/2026
**Môi trường:** Windows 11 Home Single Language, 8 logical CPU, 7,7 GB RAM; Python 3.13.2 trong `.venv-1`. CP7: agent v1/v2 ở cổng 8001/8002, mock LLM nhỏ, `MOCK_ERROR_RATE=0`. CP8: Docker Desktop Engine 29.9.3, agent sau Nginx cổng 8080, mock LLM nhỏ; mặc định `MOCK_ERROR_RATE=0.01`, `MOCK_SLOW_RATE=0.03`. Chưa chạy benchmark trên Railway.

Thông tin OS/CPU/RAM lấy bằng `Get-CimInstance Win32_OperatingSystem` và `Get-CimInstance Win32_Processor | Select-Object -First 1`; RAM = `TotalVisibleMemorySize / 1MB`. Phiên bản Python do `configurePythonEnvironment` trả về.

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | ≤ 500 ms | Ngưỡng mặc định của `load_test.py`; đo trải nghiệm của ít nhất 95% request. |
| Error rate `/ask` | ≤ 2% | Ngưỡng mặc định của `load_test.py`; tỷ lệ phản hồi khác HTTP 200. |
| Accuracy trên golden dataset | ≥ 85%, không regression | Ngưỡng CI của Exercise 7.3; CP7 còn kiểm tra cuối với 100%. |

### 1.1 Metric của agent (Exercise 7.1)

Đã thêm histogram `agent_question_length_chars` trong [app.py](./06-lab-complete/benchmark-observability/develop/app.py), quan sát `len(body.question)` một lần mỗi request `/ask`. Lệnh kiểm tra trên agent v2 đang chạy:

```powershell
$body=@{question='Prometheus thu thập metrics như thế nào?'} | ConvertTo-Json -Compress
$body | curl.exe -sS -o NUL -w 'ask_http=%{http_code}' -X POST 'http://localhost:8002/ask' -H 'Content-Type: application/json' --data-binary '@-'
$m=curl.exe -sS 'http://localhost:8002/metrics'
$m | Select-String '^(http_requests_total\{method="POST",route="/ask"|agent_in_flight_requests |agent_question_length_chars_count |agent_question_length_chars_bucket\{le="50.0")' | ForEach-Object Line
```

Output snapshot: `ask_http=200`; Counter `http_requests_total{method="POST",route="/ask",status="200"} 24.0`; Gauge `agent_in_flight_requests 0.0`; Histogram `agent_question_length_chars_count 24.0` và bucket `le="50.0"` có 17 quan sát. Những số này là tổng từ lúc process v2 được khởi động lại và chạy eval, không phải chỉ từ request cuối. Dùng `route.path` làm label giữ số tổ hợp label hữu hạn; nếu dùng URL bất kỳ làm label, bot quét hàng nghìn URL lạ sẽ tạo rất nhiều time series và tăng dùng RAM Prometheus.

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4,00 | 202,5 | 233,4 | 1.714,8 | 0% | PASS ([JSON](./06-lab-complete/benchmark-observability/develop/reports/load_v2_c1.json)) |
| 10 | 35,87 | 202,1 | 463,7 | 1.707,1 | 0% | PASS ([JSON](./06-lab-complete/benchmark-observability/develop/reports/load_v2_c10.json)) |
| 50 | 95,69 | 215,6 | 554,1 | 1.729,0 | 0% | FAIL p95 ([JSON](./06-lab-complete/benchmark-observability/develop/reports/load_v2_c50.json)) |
| 100 | 50,95 | 672,1 | 3.749,7 | 4.066,5 | 0% | FAIL p95 ([JSON](./06-lab-complete/benchmark-observability/develop/reports/load_v2_c100.json)) |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

RPS tăng từ concurrency 1 đến 50 nhưng giảm ở 100; không tăng tuyến tính. Ở 100, p50 và p95 đều tăng mạnh, cho thấy mức tải này đã gây chờ đợi/chi phí điều phối ở hệ thống local. Chỉ từ các report này chưa xác định được nút thắt cụ thể là CPU, server hay client; CP8 sẽ đo thêm bằng dashboard và benchmark nhiều instance. Mỗi hàng có 300 request và dùng `MOCK_SLOW_RATE=0.03` mặc định.

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 219,7 | 455,8 | 514,8 |
| 0.03 (mặc định) | 257,4 | 492,8 | 1.693,0 |
| 0.1 | 360,1 | 1.697,4 | 1.731,9 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

Các hàng chạy cùng 300 request, concurrency 20 và `MOCK_ERROR_RATE=0`; nguồn lần lượt là [slow 0](./06-lab-complete/benchmark-observability/develop/reports/load_v2_slow_0.json), [slow 0.03](./06-lab-complete/benchmark-observability/develop/reports/load_v2_slow_0.03.json), [slow 0.1](./06-lab-complete/benchmark-observability/develop/reports/load_v2_slow_0.1.json). Khi slow rate tăng từ 0 lên 0,03, average chỉ tăng 37,7 ms nhưng p99 tăng 1.178,2 ms. Với 0,1, p95 vượt 500 ms dù average vẫn 360,1 ms. Vì vậy SLO theo average sẽ bỏ sót một nhóm người dùng phải chờ rất lâu; p95/p99 cho thấy phần đuôi phân bố.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Hai agent V1 và V2 chạy cùng [`app.py`](./06-lab-complete/benchmark-observability/develop/app.py), không có hai bộ mã riêng. Lệnh chạy đặt `AGENT_VERSION=v1` hoặc `AGENT_VERSION=v2` (xem bên dưới). Trong endpoint `/ask`, v1 bỏ bước tìm tài liệu và tạo câu trả lời mock mặc định; v2 gọi `search_knowledge_base()` để lấy ngữ cảnh từ [`utils/mock_llm.py`](./06-lab-complete/benchmark-observability/develop/utils/mock_llm.py) rồi mới tạo câu trả lời. Đây là mô phỏng RAG bằng so khớp từ khóa.

V2 sau sửa giữ nguyên `AGENT_VERSION=v2`, thêm hai mục về Kubernetes HPA và JWT vào `KNOWLEDGE_BASE` trong [`utils/mock_llm.py`](./06-lab-complete/benchmark-observability/develop/utils/mock_llm.py), khởi động lại agent v2 và chạy lại eval. 

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4,35% (1/23) | 91,30% (21/23) | 100% (23/23) |
| Avg tokens / câu | 56,9 | 108,7 | 113,7 |
| Tổng cost (USD) | 0,000401 | 0,000756 | 0,000790 |
| Cost / câu đúng (USD) | 0,00040095 | 0,00003599 | 0,00003436 |
| Quality gate | FAIL (80%) | PASS (80%; 0 regression) | PASS (100%; 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm tài liệu JWT vào `KNOWLEDGE_BASE`, nêu token có chữ ký và thời điểm hết hạn. |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm tài liệu Kubernetes HPA vào `KNOWLEDGE_BASE`, nêu ba loại chỉ số. |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

Nguồn: [eval v1](./06-lab-complete/benchmark-observability/develop/reports/eval_v1.json), [eval v2](./06-lab-complete/benchmark-observability/develop/reports/eval_v2.json), [eval v2 sau sửa](./06-lab-complete/benchmark-observability/develop/reports/eval_v2_fixed.json). v2 dùng nhiều token hơn vì có retrieval, tổng chi phí 23 câu cũng cao hơn v1. Tuy nhiên chi phí **mỗi câu đúng** giảm mạnh vì độ chính xác tăng từ 1/23 lên 21/23 rồi 23/23. p95 từ eval cuối là 1.566,4 ms do một câu bị mock làm chậm; 23 mẫu quá ít để dùng làm kết luận hiệu năng. Bảng load test 300 request phản ánh latency tốt hơn. Các giá trị cost chỉ là chi phí **mock**, không phải hóa đơn cloud/LLM thật.

### Lệnh tạo metric CP7

Tất cả lệnh dưới đây chạy trong `06-lab-complete/benchmark-observability/develop/` bằng PowerShell. `PYTHONIOENCODING` bảo đảm script in Unicode trên Windows; eval còn được sửa để ghi/đọc JSON bằng UTF-8.

```powershell
$py = 'D:\VinUni-AI20k\Day 14\K5-L3B-DAY14-TranDuyThanh-2A202603919-Deployment-Benchmark-Observability\.venv-1\Scripts\python.exe'
$env:PYTHONIOENCODING = 'utf-8'
$env:MOCK_ERROR_RATE = '0'
$env:AGENT_VERSION = 'v1'; $env:PORT = '8001'
$v1 = Start-Process -FilePath $py -ArgumentList 'app.py' -WorkingDirectory (Resolve-Path '.').Path -PassThru -WindowStyle Hidden
$env:AGENT_VERSION = 'v2'; $env:PORT = '8002'
$v2 = Start-Process -FilePath $py -ArgumentList 'app.py' -WorkingDirectory (Resolve-Path '.').Path -PassThru -WindowStyle Hidden
```

V2 chạy với `MOCK_SLOW_RATE` mặc định `0.03` khi đo concurrency. Lệnh từng mức (mỗi lệnh ghi đúng file JSON của hàng tương ứng):

```powershell
foreach ($c in 1,10,50,100) {
  & $py load_test.py --url http://localhost:8002 --requests 300 --concurrency $c --out "reports/load_v2_c$c.json"
  "EXIT concurrency=$c code=$LASTEXITCODE"
}
```

Để so slow rate, đã dừng/bật lại v2 cho mỗi giá trị `MOCK_SLOW_RATE=0`, `0.03`, `0.1`, rồi chạy (PID của process v2 lần đầu là `7932`, các lần sau lấy từ `Start-Process`):

```powershell
$lastPid = 7932
foreach ($rate in @('0','0.03','0.1')) {
  Stop-Process -Id $lastPid
  Start-Sleep -Milliseconds 600
  $env:MOCK_SLOW_RATE = $rate
  $p = Start-Process -FilePath $py -ArgumentList 'app.py' -WorkingDirectory (Resolve-Path '.').Path -PassThru -WindowStyle Hidden
  $lastPid = $p.Id
  Start-Sleep -Seconds 2
  & $py load_test.py --url http://localhost:8002 --requests 300 --concurrency 20 --out "reports/load_v2_slow_$rate.json"
  "EXIT slow_rate=$rate code=$LASTEXITCODE"
}
```

Lệnh eval thực tế, trước và sau khi sửa knowledge base và khởi động lại v2:

```powershell
& $py eval/run_eval.py --url http://localhost:8001 --out reports/eval_v1.json
& $py eval/run_eval.py --url http://localhost:8002 --out reports/eval_v2.json --baseline reports/eval_v1.json
& $py eval/run_eval.py --url http://localhost:8002 --min-accuracy 1.0 --baseline reports/eval_v2.json --out reports/eval_v2_fixed.json
```

Script trả exit code 1 khi không đạt SLO/quality gate. Vì vậy các lần load concurrency 50, 100 và slow rate 0,1 có JSON hợp lệ dù exit code 1; eval v1 cũng có JSON hợp lệ nhưng quality gate FAIL. [Job CI](./.github/workflows/eval.yml) chạy v2 trên pull request, đặt lỗi mock bằng 0, chờ `/health`, rồi chạy eval với `--min-accuracy 0.85 --baseline reports/eval_v2.json`. Exit code 1 của eval làm job fail; khi bật branch protection yêu cầu job này, PR không thể merge nếu gate không đạt.

---

## 4. Observability stack (production)

Đây là stack Docker Compose trong [production/](./06-lab-complete/benchmark-observability/production/), **không phải số liệu từ Railway**. Dockerfile ban đầu chép package vào sai thư mục home làm agent restart với `ModuleNotFoundError: uvicorn`; đã sửa [Dockerfile](./06-lab-complete/benchmark-observability/production/Dockerfile) sang `/app/.local`, build lại, rồi `/health` trả 200. Hai mục HPA/JWT cũng được đồng bộ sang [knowledge base production](./06-lab-complete/benchmark-observability/production/utils/mock_llm.py).

### 4.1 Screenshot

- [x] [Grafana dashboard khi có tải](./screenshots/grafana-dashboard.png): Traffic, Error rate, Latency p95, Saturation, Instances và Cost.
- [x] [Jaeger trace chậm](./screenshots/jaeger-slow-trace.png): trace `fb4d8233e3ce7277a0306a088f78e723`.
- [x] [Jaeger trace lỗi](./screenshots/jaeger-error-trace.png): trace `9b98675447761742b875038a3ae2f45a`, span LLM có event `exception` với lỗi upstream 503.
- [x] [Prometheus Alerts](./screenshots/prometheus-alert-firing.png): cả `AgentHighErrorRate` và `AgentHighLatencyP95` cùng **firing**.

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` | ~90,7 giây | Error rate: 20,07% tại mốc kiểm tra |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` | ~151,4 giây | Latency p95: 1.903,7 ms tại mốc kiểm tra |
| C | `LLM_MODEL=mock-llm-large` | Chưa thực hiện | — | — |
| D | `docker pause` 1 instance | Chưa thực hiện | — | — |
| E | `AGENT_VERSION=v1` | Chưa thực hiện | — | — |

Hai thay đổi A và B được áp dụng **cùng lúc** trong lúc Locust tạo 30 users. Mốc bắt đầu tính thời gian là **08:23:21 UTC**, khi lệnh `docker compose up` áp dụng cấu hình xong. Poll Prometheus mỗi 5 giây: A được quan sát firing lúc **08:24:51 UTC**, B lúc **08:25:52 UTC**. Sai số thời gian quan sát khoảng 5 giây cộng thời gian lệnh Compose chạy. [Timeline](./benchmark-results/alert_timeline.csv), [trạng thái firing tại 08:25:55 UTC](./benchmark-results/alerts_firing.json) và [metric Prometheus](./benchmark-results/fault_metrics.json) lưu bằng chứng. Trước khi tạo fault, test `promtool` cho alert rules báo `SUCCESS`.

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?** Chạy eval định kỳ/canary với golden dataset và đặt quality gate cho accuracy cùng regression. Các metric hạ tầng không biết câu trả lời có đúng hay không; CP7 đã cho thấy v1 chỉ đúng 1/23 câu trong khi v2 sau sửa đúng 23/23.

### 4.3 Debug bằng trace

Trace chậm được chọn từ các dòng `llm_call` có `llm_ms` lớn nhất trong log agent đã quan sát:

- `trace_id`: `fb4d8233e3ce7277a0306a088f78e723`.
- Tổng thời gian: **1.725,3 ms** theo log `http_request` (Jaeger làm tròn thành 1,7 s).
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small`, **1.698,7 ms**, khoảng **98,5%** tổng thời gian; `agent.retrieve_context` khoảng 20,4 ms.
- Trace lỗi `9b98675447761742b875038a3ae2f45a` trả 503; Jaeger ghi `exception.message=Upstream LLM error: 503 Service Unavailable (mock)`.
- Dòng log JSON có cùng `trace_id`:

```json
{"ts": "2026-11-26T08:01:08.287763+00:00", "level": "INFO", "service": "observable-agent", "instance": "23764d6f4f67", "event": "llm_call", "trace_id": "fb4d8233e3ce7277a0306a088f78e723", "span_id": "630628f4a957b454", "request_id": "78295a207467", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1698.7}
{"ts": "2026-11-26T08:01:08.288579+00:00", "level": "INFO", "service": "observable-agent", "instance": "23764d6f4f67", "event": "http_request", "trace_id": "fb4d8233e3ce7277a0306a088f78e723", "span_id": "630628f4a957b454", "request_id": "78295a207467", "method": "POST", "route": "/ask", "status": 200, "ms": 1725.3}
{"ts": "2026-11-26T08:00:50.039701+00:00", "level": "INFO", "service": "observable-agent", "instance": "23764d6f4f67", "event": "llm_error", "trace_id": "9b98675447761742b875038a3ae2f45a", "span_id": "c545c10af1aa9131", "request_id": "5810105afa2b", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

Các dòng trên được chép từ log gốc; lệnh tra log:

```powershell
docker compose -p k5-day14-observability logs --no-log-prefix agent 2>$null |
  Select-String 'fb4d8233e3ce7277a0306a088f78e723|9b98675447761742b875038a3ae2f45a' |
  Select-Object -First 8 | ForEach-Object { $_.Line }
[math]::Round(1698.7 / 1725.3 * 100, 1)  # 98,5% thời gian của request
```

### 4.4 Lệnh chạy và truy vấn CP8

Chạy trong `06-lab-complete/benchmark-observability/production/` bằng PowerShell:

```powershell
docker info --format '{{.ServerVersion}}'
docker run --rm -v "${PWD}/prometheus:/p" --entrypoint promtool prom/prometheus:v3.16.0 test rules /p/alert_rules_test.yml
docker compose -p k5-day14-observability up -d --build --scale agent=1
docker compose -p k5-day14-observability ps --format 'table {{.Service}}\t{{.Name}}\t{{.State}}'
curl.exe --noproxy '*' -sS -o NUL -w '%{http_code}\n' http://127.0.0.1:8080/health
```

Khi quan sát alert, tạo `.env` từ `.env.example` với `MOCK_ERROR_RATE=0.2` và `MOCK_SLOW_RATE=0.3`, rồi chạy:

```powershell
docker compose -p k5-day14-observability run --rm --no-deps locust -f /mnt/locust/locustfile.py --host http://nginx --headless -u 30 -r 5 -t 4m --csv /mnt/results/alerts_ab
docker compose -p k5-day14-observability up -d --scale agent=3
curl.exe --noproxy '*' -sS http://127.0.0.1:9090/api/v1/alerts
```

Lệnh đã dùng để truy vấn các metric tại 08:25:55 UTC và ghi [fault_metrics.json](./benchmark-results/fault_metrics.json):

```powershell
$t = [DateTimeOffset]::Parse('2026-11-26T08:25:55Z').ToUnixTimeSeconds()
$exprs = @{
  error_rate = 'sum(rate(http_requests_total{job="agent",route="/ask",status=~"5.."}[1m])) / sum(rate(http_requests_total{job="agent",route="/ask"}[1m]))'
  p95_seconds = 'histogram_quantile(0.95,sum by(le)(rate(http_request_duration_seconds_bucket{job="agent",route="/ask"}[1m])))'
}
$out = [ordered]@{timestamp_utc='2026-11-26T08:25:55Z'}
foreach ($k in $exprs.Keys) {
  $q = [uri]::EscapeDataString($exprs[$k])
  $j = curl.exe --noproxy '*' -sS "http://127.0.0.1:9090/api/v1/query?query=$q&time=$t" | ConvertFrom-Json
  $out[$k] = [ordered]@{query=$exprs[$k]; value=$j.data.result[0].value[1]}
}
$out | ConvertTo-Json -Depth 5
```

Kiểm chứng hai alert cùng firing tại cùng mốc:

```powershell
$t = [DateTimeOffset]::Parse('2026-11-26T08:25:55Z').ToUnixTimeSeconds()
$q = [uri]::EscapeDataString('ALERTS{alertstate="firing"}')
curl.exe --noproxy '*' -sS -o benchmark-results/alerts_firing.json "http://127.0.0.1:9090/api/v1/query?query=$q&time=$t"
Import-Csv benchmark-results/alert_timeline.csv | Where-Object state -eq 'firing' | Select-Object alert,seconds_since_change
```

Sau khi chụp ảnh và lưu kết quả, đã xóa `.env` fault injection và chạy lại `docker compose -p k5-day14-observability up -d --scale agent=3` để về cấu hình mặc định.

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 58,48 | 200 | 640 | 1.700 | 73/6.975 (1,05%) |
| 3 | 57,12 | 200 | 1.300 | 1.900 | 61/6.785 (0,90%) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

Không trong phép đo này: p95 tăng từ 640 lên 1.300 ms, còn RPS gần như không đổi. Ba agent có mặt và Prometheus scrape được cả ba target (`up{job="agent"}=1`); các instance đều nhận request. Trace chậm cho thấy mock LLM chiếm gần hết thời gian của một request, nhưng **chưa đủ bằng chứng để khẳng định** đây là nút thắt duy nhất khiến lần đo 3 instance chậm hơn. Cả ba container và Locust dùng chung máy 8 logical CPU/7,7 GB RAM, nên tranh chấp tài nguyên và biến động của mock slow cũng có thể ảnh hưởng. Cần lặp lại nhiều lượt và đo CPU/memory theo container để kết luận.

Nguồn: [CSV 1 instance](./benchmark-results/scale_1_stats.csv), [CSV 3 instance](./benchmark-results/scale_3_stats.csv). RPS/p50/p95/p99 dùng riêng dòng `POST,/ask`, không dùng dòng `Aggregated` có cả `/health`. Lệnh tạo CSV (100 users, ramp 10/s, 2 phút mỗi lượt):

```powershell
docker compose -p k5-day14-observability up -d --scale agent=1
docker compose -p k5-day14-observability run --rm --no-deps locust -f /mnt/locust/locustfile.py --host http://nginx --headless -u 100 -r 10 -t 2m --csv /mnt/results/scale_1
docker compose -p k5-day14-observability up -d --scale agent=3
docker compose -p k5-day14-observability run --rm --no-deps locust -f /mnt/locust/locustfile.py --host http://nginx --headless -u 100 -r 10 -t 2m --csv /mnt/results/scale_3
Import-Csv benchmark-results/scale_1_stats.csv | Where-Object Name -eq '/ask'
Import-Csv benchmark-results/scale_3_stats.csv | Where-Object Name -eq '/ask'
[math]::Round(73 / 6975 * 100, 2)  # failure rate 1 instance: 1,05%
[math]::Round(61 / 6785 * 100, 2)  # failure rate 3 instance: 0,90%
```

`--no-deps` là cần thiết: lượt thử đầu dùng `docker compose run locust` đã tự bật `agent-2` theo `replicas: 2` và bị hủy, sau đó đo lại đúng 1 instance. Locust kết thúc exit code 1 khi mock trả 503; các request lỗi đã được tính trong cột Failures.

---

## 6. Kết luận

1. Chỉ tăng số instance không bảo đảm p95 tốt hơn; cần kiểm tra phân bố tải và tài nguyên chia sẻ.
2. Golden Signals chỉ ra có vấn đề, còn trace và log cùng `trace_id` xác định bước chậm/lỗi cụ thể.
3. Alert có thời gian `for` giúp lọc spike ngắn; lỗi chất lượng trả lời cần eval riêng, vì có thể không tạo lỗi HTTP.

Nếu đưa agent lên production thật, nên thêm metric/error alert ở Nginx (502/504), CPU và memory mỗi container, tỷ lệ retrieval miss, cùng alert cho accuracy/regression từ eval định kỳ.
