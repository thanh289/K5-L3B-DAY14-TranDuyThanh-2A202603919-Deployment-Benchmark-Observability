# Benchmark & Observability Report — Day 14

> CP7 đã đo trên máy local. Các mục observability và scaling production thuộc CP8, chưa đo.
> Mọi con số dưới đây lấy từ các report JSON đã lưu, không ước lượng.

**Họ tên:** Trần Duy Thanh
**Ngày chạy:** 26/11/2026
**Môi trường:** Windows 11 Home Single Language, 8 logical CPU, 7,7 GB RAM; Python 3.13.2 trong `.venv-1`. Agent v1/v2 chạy local ở cổng 8001/8002; mock LLM nhỏ, `MOCK_ERROR_RATE=0` để tách lỗi ngẫu nhiên khỏi phép đo latency. Chưa chạy benchmark trên Railway.

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

### 4.1 Screenshot

- [ ] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals)
- [ ] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian)
- [ ] Một trace lỗi trong Jaeger (có event `exception`)
- [ ] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing**

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | | | |
| B | `MOCK_SLOW_RATE=0.3` | | | |
| C | `LLM_MODEL=mock-llm-large` | | | |
| D | `docker pause` 1 instance | | | |
| E | `AGENT_VERSION=v1` | | | |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

...

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: ...
- Tổng thời gian: ... ms
- Span chiếm nhiều thời gian nhất: ... (... ms, ...%)
- Dòng log tương ứng (grep theo `trace_id`):

```json

```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | | | | | |
| 3 | | | | | |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

...

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. ...
  2. ...
  3. ...
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

...
