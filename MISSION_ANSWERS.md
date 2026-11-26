# Day 14 Lab — Mission Answers

## CP0: Setup

- Repo: `git status --short --branch` → `## main...origin/main` (working tree sạch tại thời điểm kiểm tra). `git remote -v` → `origin` trỏ tới repo GitHub mang tên bài nộp K5-L3B.
- WSL2: `wsl --list --verbose` → `Ubuntu-24.04` đang Running, Version 2. `wsl -d Ubuntu-24.04 -- /usr/bin/python3 --version` → Python 3.12.3.
- Docker: `docker compose version` → v5.7.0. `docker info --format '{{.ServerVersion}}'` → 29.9.3. 
- `docker run --rm hello-world` cho output `Hello from Docker!` trong hội thoại.

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

Đọc [develop/app.py](./01-localhost-vs-production/develop/app.py):

1. `OPENAI_API_KEY` và chuỗi kết nối database chứa user/password được hardcode (dòng 17–18): dễ lộ khi đẩy code lên GitHub, khó thay đổi giữa môi trường.
2. `DEBUG` và `MAX_TOKENS` là hằng số trong code (dòng 21–22), không đọc từ environment.
3. Dùng `print()` cho log, còn in cả API key và toàn bộ câu hỏi/response (dòng 33–38): lộ secret và khó tổng hợp log.
4. Không có endpoint `/health` hay `/ready`: nền tảng không có cách kiểm tra sức khỏe và trạng thái sẵn sàng của agent.
5. `host="localhost"` (dòng 51) chỉ bind loopback, không nhận traffic bên ngoài container.
6. `port=8000` cố định (dòng 52), không dùng `PORT` do nền tảng cloud cấp.
7. `reload=True` cố định (dòng 53), bật chế độ phát triển khi triển khai.
8. Không có cơ chế xử lý vòng đời và tắt an toàn trong bản develop.

### Exercise 1.2: Chạy bản develop

Chạy trong `01-localhost-vs-production/develop/`:

```text
wsl -d Ubuntu-24.04 -- /tmp/day14-venv/bin/python app.py
curl.exe -i -X POST 'http://localhost:8000/ask?question=Hello'
```

Kết quả: `POST /ask` trả `HTTP/1.1 200 OK`, có trường `answer` từ mock LLM. Bản develop nhận `question` qua query string.

```text
curl.exe -i 'http://localhost:8000/health'
```

Kết quả: `HTTP/1.1 404 Not Found`, xác nhận thiếu health check. Output console của request `/ask` cũng có dòng `[DEBUG] Using key: ...`, xác nhận secret bị ghi vào log.

### Exercise 1.3: So sánh với bản production

| Feature | Develop | Production | Vì sao quan trọng? |
| --- | --- | --- | --- |
| Config | Key, host, port, debug hardcode trong `app.py` | [config.py](./01-localhost-vs-production/production/config.py) đọc environment | Cấu hình mỗi môi trường khác nhau mà không sửa code hoặc commit secret. |
| Health/readiness | Không có, `/health` trả 404 | `/health` và `/ready` trả 200 khi app sẵn sàng | Nền tảng và load balancer có tín hiệu để giám sát/định tuyến. |
| Logging | `print()`, lộ key | Có log sự kiện và không in key | Giảm rò rỉ secret, thuận lợi phân tích sự cố. |
| Shutdown | Không có logic vòng đời | Có FastAPI lifespan để cleanup | Tạo chỗ đóng tài nguyên khi dừng app. Tuy nhiên handler SIGTERM trong ví dụ không chuyển tiếp cho Uvicorn; không nên coi đây là bằng chứng đã xử lý graceful shutdown đúng. |
| Network | Bind `localhost:8000` | Bind host/port theo environment; host mặc định `0.0.0.0` | Container/cloud nhận được kết nối từ ngoài process. |
| Request | `question` trong query string | `question` trong JSON body | Cần gọi API theo đúng hợp đồng của từng bản. |

Chạy trong `01-localhost-vs-production/production/`:

```text
wsl -d Ubuntu-24.04 -- /tmp/day14-venv/bin/python app.py
curl.exe -sS -i 'http://localhost:8000/health'
curl.exe -sS -i 'http://localhost:8000/ready'
Invoke-RestMethod -Uri 'http://localhost:8000/ask' -Method Post -ContentType 'application/json' -Body (@{question='Hello'} | ConvertTo-Json -Compress) | ConvertTo-Json -Compress
```

Kết quả: `/health` trả 200, `/ready` trả 200; request `/ask` hợp lệ trả JSON có `question`, `answer`, `model` (server log ghi 200).

Lưu ý khi thử: `curl.exe -sS -i -X POST 'http://localhost:8000/ask' -H 'Content-Type: application/json' -d '{"question":"Hello"}'` chạy từ PowerShell đã gửi body sai định dạng, nhận 500. Server log ghi `JSONDecodeError`. Sau đó dùng `Invoke-RestMethod` với `ConvertTo-Json` như trên để gửi JSON hợp lệ. Bản production mẫu chưa xử lý JSON lỗi thành phản hồi 4xx.

## Part 2: Docker

### Exercise 2.1: Dockerfile cơ bản

Đọc [Dockerfile develop](./02-docker/develop/Dockerfile):

1. Base image là `python:3.11`, bản Python đầy đủ.
2. Working directory trong container là `/app` (`WORKDIR /app`).
3. `COPY requirements.txt` đứng trước `COPY app.py` để Docker có thể tái dùng layer cài dependencies khi chỉ thay đổi source code. `pip install --no-cache-dir` không tắt Docker layer cache.
4. `CMD` cung cấp lệnh mặc định và có thể được thay bằng command sau tên image trong `docker run`. `ENTRYPOINT` chỉ định executable chính; command truyền vào `docker run` thường trở thành đối số cho executable đó. Dockerfile này dùng `CMD ["python", "app.py"]`.

### Exercise 2.2: Build và chạy container develop

Chạy từ gốc repo (build context là `.` vì Dockerfile dùng đường dẫn `COPY` tính từ gốc):

```text
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -d --name day14-cp2-develop -p 8000:8000 my-agent:develop
curl.exe -sS -i 'http://localhost:8000/health'
curl.exe -sS -i -X POST 'http://localhost:8000/ask?question=What%20is%20Docker%3F'
```

Kết quả đo: build thành công; `/health` trả HTTP 200 và JSON `{"status":"ok",...}`; `/ask` trả HTTP 200, câu trả lời mock về container. Bản develop của Part 2 nhận `question` qua query string. Dọn container bằng `docker stop day14-cp2-develop` rồi `docker rm day14-cp2-develop` để nhường cổng 8000.

### Exercise 2.3: Multi-stage và kích thước image

Đọc [Dockerfile production](./02-docker/production/Dockerfile): `builder` cài GCC, `libpq-dev` và Python packages; `runtime` bắt đầu từ `python:3.11-slim`, chỉ copy Python packages và source cần chạy, dùng non-root user. Các công cụ build trong stage `builder` không nằm trong image cuối.

Lệnh chạy từ gốc repo:

```text
docker build -f 02-docker/production/Dockerfile -t my-agent:advanced .
docker image inspect my-agent:develop my-agent:advanced --format '{{index .RepoTags 0}} {{.Size}}'
docker images my-agent
```

Số đo thực tế từ `docker image inspect`:

| Image | Byte | MB (10^6 byte) |
| --- | ---: | ---: |
| `my-agent:develop` | 1,667,784,038 | 1,667.78 |
| `my-agent:advanced` | 239,815,653 | 239.82 |

Image advanced nhỏ hơn **85.62%**: `(1,667,784,038 − 239,815,653) / 1,667,784,038 × 100`. Lệnh `docker images my-agent` hiển thị xấp xỉ `1.67GB` và `240MB`. Đây là kích thước image đo được trên máy này, không phải dung lượng tải qua mạng.

### Exercise 2.4: Docker Compose stack

Đọc [docker-compose.yml](./02-docker/production/docker-compose.yml) và [nginx.conf](./02-docker/production/nginx/nginx.conf). Thư mục `production/` cần file `.env.local`; đã tạo file trống bằng `New-Item -ItemType File -Path '.env.local'` (file này được `.gitignore` bỏ qua, không chứa secret).

```text
Client → Nginx (:80) → agent (:8000)
                         ├── REDIS_URL → redis (:6379)
                         └── QDRANT_URL → qdrant (:6333)
```

Compose tạo một network nội bộ và hai volume cho Redis, Qdrant. `agent` đợi Redis và Qdrant healthy trước khi start. `REDIS_URL` và `QDRANT_URL` được cấu hình trong Compose; [main.py](./02-docker/production/main.py) của ví dụ này chưa thực sự gọi hai service đó. Nginx nhận request bên ngoài qua cổng 80 và proxy tới agent; Compose hiện chạy một instance agent mặc định.

Chạy trong `02-docker/production/`:

```text
docker compose -p k5-day14-docker config --services
docker compose -p k5-day14-docker up -d --build
docker compose -p k5-day14-docker ps
curl.exe -sS -i 'http://localhost/health'
Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost/ask' -Method Post -ContentType 'application/json' -Body (@{question='Explain microservices'} | ConvertTo-Json -Compress) | Select-Object StatusCode,Content
docker compose -p k5-day14-docker down
```

Kết quả: `config --services` in `qdrant`, `redis`, `agent`, `nginx`. `ps` cho thấy cả bốn container đang chạy; agent, Redis, Qdrant healthy. Qua Nginx, `/health` trả HTTP 200 và `/ask` với JSON hợp lệ trả HTTP 200. Đã dừng stack bằng cùng project name `k5-day14-docker`.

## Part 3: Cloud Deployment (CP6)

### Exercise 3.1: Railway

Agent trong [06-lab-complete/](./06-lab-complete/) đã được deploy lên Railway project `VinUni Day14`, môi trường `production`. URL public: **https://vinuni-day14-production.up.railway.app**. Service agent và Redis cùng project đều `Online`; `REDIS_URL` của agent tham chiếu `${{Redis.REDIS_URL}}`, `AGENT_API_KEY` được đặt bằng biến môi trường, không ghi giá trị vào bài.

```powershell
railway status
railway add --database redis
railway status
railway variable set 'REDIS_URL=${{Redis.REDIS_URL}}' 'ENVIRONMENT=production' --service 'VinUni Day14' --skip-deploys
railway variable set AGENT_API_KEY --stdin --service 'VinUni Day14'
railway domain --service 'VinUni Day14'
railway domain status 084b2455-bb3e-4805-9b71-8e5a5a12a1bd --service 'VinUni Day14'
railway status
```

Kết quả: `railway status` sau khi cấu hình cho thấy agent và Redis đều `Online`; `railway domain status` cho `ACTIVE`. API key được tạo ngẫu nhiên 32 byte, lưu trong file `.env` cục bộ đã được Git bỏ qua và truyền qua stdin; lệnh tạo chi tiết có trong [DEPLOYMENT.md](./DEPLOYMENT.md). Railway tự cấp `PORT`; Dockerfile lắng nghe `0.0.0.0` trên cổng đó.

Kiểm tra HTTP bằng PowerShell trong `06-lab-complete/`; lệnh chỉ in mã trạng thái và không in key:

```powershell
$baseUrl = 'https://vinuni-day14-production.up.railway.app'; $body = @{question='Hello'} | ConvertTo-Json -Compress; $apiKey = (Get-Content -LiteralPath '.env' -Raw).Substring('AGENT_API_KEY='.Length)
"health=$(curl.exe -sS -o NUL -w '%{http_code}' "$baseUrl/health")"
"ready=$(curl.exe -sS -o NUL -w '%{http_code}' "$baseUrl/ready")"
"ask_without_key=$($body | curl.exe -sS -o NUL -w '%{http_code}' -X POST "$baseUrl/ask" -H 'Content-Type: application/json' --data-binary '@-')"
"ask_with_key=$($body | curl.exe -sS -o NUL -w '%{http_code}' -X POST "$baseUrl/ask" -H 'Content-Type: application/json' -H "X-API-Key: $apiKey" --data-binary '@-')"
```

Output thực tế: `health=200`, `ready=200`, `ask_without_key=401`, `ask_with_key=200`. JSON gửi qua stdin để tránh lỗi escape trong PowerShell. [DEPLOYMENT.md](./DEPLOYMENT.md) ghi toàn bộ thông tin và lệnh; ảnh chụp dashboard, service và kết quả test cần lưu trong [screenshot](./screenshots).

### Exercise 3.2: So sánh Railway và Render

[railway.toml](./06-lab-complete/railway.toml) hiện cấu hình build bằng Dockerfile và healthcheck `/health`; Redis và secrets được tạo/đặt riêng trong Railway, không khai báo trong file này. [render.yaml](./06-lab-complete/render.yaml) hiện chỉ là TODO, nên chưa thể dùng trực tiếp để deploy bản Part 6 lên Render. Mẫu [render.yaml](./03-cloud-deployment/render/render.yaml) cho thấy Render Blueprint có thể khai báo web service, Redis, build/start command, healthcheck, vùng triển khai và biến môi trường trong một file. Nếu chọn Render cho Part 6, cần viết Blueprint phù hợp cấu trúc `06-lab-complete/` và nối `REDIS_URL` với Redis của Render. Sự khác biệt thực tế trong bài này là cấu hình Railway ngắn hơn nhưng phần Redis và secrets phải thiết lập thêm trên platform; Blueprint Render có thể mô tả nhiều service cùng lúc.

### Exercise 3.3: Đọc pipeline Cloud Run

[cloudbuild.yaml](./03-cloud-deployment/production-cloud-run/cloudbuild.yaml) mô tả chuỗi `test → build Docker image → push image → deploy Cloud Run`; bước sau chờ bước trước thành công. Image được gắn tag `$COMMIT_SHA` và `latest`, rồi Cloud Run deploy tag theo commit để xác định phiên bản. [service.yaml](./03-cloud-deployment/production-cloud-run/service.yaml) mô tả cổng, CPU/RAM, giới hạn scale, health probes và secret lấy từ Secret Manager. Đây là phân tích file mẫu, chưa chạy Cloud Run; muốn deploy agent Part 6 cần điều chỉnh image và kết nối Redis cho cấu trúc ứng dụng này.

## Part 4: API Gateway & Security (CP3)

### Exercise 4.1: API key

Đọc [develop/app.py](./04-api-gateway/develop/app.py): `APIKeyHeader` lấy header `X-API-Key`; dependency `verify_api_key` kiểm tra key trước khi `/ask` xử lý câu hỏi. Thiếu key trả 401; key sai trả 403 theo code. Để rotate key, đổi biến môi trường `AGENT_API_KEY` và khởi động lại process; khi cần chuyển đổi không gián đoạn, cần bổ sung cơ chế chấp nhận đồng thời key cũ và mới trong thời gian ngắn. Ví dụ develop vẫn in key ra console nên không dùng cách này để giữ secret trong production.

Lệnh chạy trong `04-api-gateway/develop/` (venv WSL tạo ở `/tmp/day14-venv`; đã cài dependencies bằng lệnh ở mục 4.2):

```powershell
wsl -d Ubuntu-24.04 -- env AGENT_API_KEY=secret-key-123 /tmp/day14-venv/bin/python app.py
```

Lệnh kiểm tra từ gốc repo; truyền JSON qua stdin để tránh lỗi quoting của PowerShell:

```powershell
$json = @{question='hello'} | ConvertTo-Json -Compress
$json | curl.exe -sS -i -X POST 'http://localhost:8000/ask' -H 'Content-Type: application/json' --data-binary '@-'
$json | curl.exe -sS -i -X POST 'http://localhost:8000/ask' -H 'Content-Type: application/json' -H 'X-API-Key: secret-key-123' --data-binary '@-'
```

Output HTTP thực tế (lược header `date`, `server`, `content-length`):

```http
HTTP/1.1 401 Unauthorized
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

HTTP/1.1 200 OK
content-type: application/json

{"question":"hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

### Exercise 4.2: JWT

Đọc [auth.py](./04-api-gateway/production/auth.py) và [app.py](./04-api-gateway/production/app.py): `POST /auth/token` xác thực user mẫu `student/demo123`, tạo JWT HS256 có `sub`, `role`, `iat`, `exp` và hạn 60 phút. Request tới `/ask` gửi `Authorization: Bearer <token>`; dependency kiểm tra chữ ký và hạn dùng. Không có token trả 401; token không hợp lệ trả 403 theo code. Chỉ dùng credentials mẫu của lab; `JWT_SECRET` mặc định trong code phải đổi bằng biến môi trường nếu triển khai thật.

Lệnh chuẩn bị đã chạy (lệnh cài packages chạy trong `04-api-gateway/production/`):

```powershell
wsl -d Ubuntu-24.04 -- /usr/bin/python3 -m venv /tmp/day14-venv
wsl -d Ubuntu-24.04 -- /tmp/day14-venv/bin/python -m pip install -r requirements.txt
wsl -d Ubuntu-24.04 -- /tmp/day14-venv/bin/python app.py
```

Lệnh kiểm tra dưới đây chạy trong **một** PowerShell process; `$token` chỉ giữ trong bộ nhớ, không in JWT ra file/output. Đồng thời đây là phép thử rate limit của Exercise 4.3:

```powershell
$askJson = @{question='what is docker?'} | ConvertTo-Json -Compress
$askJson | curl.exe -sS -i -X POST 'http://localhost:8000/ask' -H 'Content-Type: application/json' --data-binary '@-'
$loginJson = @{username='student';password='demo123'} | ConvertTo-Json -Compress
$login = $loginJson | curl.exe -sS -X POST 'http://localhost:8000/auth/token' -H 'Content-Type: application/json' --data-binary '@-' | ConvertFrom-Json
"token_type=$($login.token_type); expires_in_minutes=$($login.expires_in_minutes); access_token=[REDACTED]"
$token = $login.access_token
1..12 | ForEach-Object {
  $i = $_
  $resp = $askJson | curl.exe -sS -i -X POST 'http://localhost:8000/ask' -H 'Content-Type: application/json' -H "Authorization: Bearer $token" --data-binary '@-'
  if ($i -eq 1 -or $i -eq 11) { "--- request $i ---"; $resp } else { "request $i : $($resp[0])" }
}
```

Output của lệnh, lược các header không liên quan và che token:

```http
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer
content-type: application/json

{"detail":"Authentication required. Include: Authorization: Bearer <token>"}
token_type=bearer; expires_in_minutes=60; access_token=[REDACTED]

--- request 1 ---
HTTP/1.1 200 OK
content-type: application/json

{"question":"what is docker?","answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}

request 2–10: HTTP/1.1 200 OK

--- request 11 ---
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
retry-after: 59
content-type: application/json

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
request 12: HTTP/1.1 429 Too Many Requests
```

### Exercise 4.3: Rate limiting

[rate_limiter.py](./04-api-gateway/production/rate_limiter.py) lưu timestamp từng request trong `deque` của mỗi user, loại timestamp cũ hơn 60 giây rồi đếm số còn lại: đây là **sliding window log** theo cách code thực hiện (docstring gọi là counter). User thường được 10 request/60 giây, admin được 100 request/60 giây; admin có quota cao hơn, không được bypass vô hạn. Sau 10 request của `student`, request thứ 11 nhận 429 với `Retry-After: 59`, đúng như output trên. Bộ đếm nằm trong RAM nên không dùng chung được giữa nhiều instance và mất khi restart; cần Redis/shared store cho triển khai nhiều replica.

### Exercise 4.4: Cost guard

[cost_guard.py](./04-api-gateway/production/cost_guard.py) đếm input/output token và tính chi phí theo giá mẫu. Bản chạy hiện tại giữ budget **$1/user/ngày**, **$10/toàn hệ thống/ngày** trong RAM; cảnh báo ở 80%, kiểm tra trước khi gọi LLM, trả 402 khi user hết tiền hoặc 503 khi hết budget chung. Sang ngày mới, record per-user được tạo lại. Rate limit hạn chế **tốc độ** gọi, cost guard hạn chế **chi phí**; cần cả hai vì mỗi request có thể tốn lượng token khác nhau.

Đề Exercise 4.4 còn nêu thiết kế $10/user/tháng với Redis. Cách làm: dùng key `budget:{user_id}:{YYYY-MM}`, kiểm tra `spent + estimated_cost <= 10` trước khi gọi LLM, reserve chi phí bằng thao tác Redis nguyên tử (Lua script hoặc transaction), rồi đối soát theo token thực tế; đặt TTL đến đầu tháng sau để reset. Phải xử lý đồng thời nhiều request để không vượt budget. Bản mẫu hiện tại chỉ kiểm tra chi phí **đã phát sinh**, sau đó mới ghi chi phí request mới nên một request có thể làm vượt ngưỡng. Ngoài ra trường `usage.budget_remaining_usd` trong `/ask` hiện chứa `usage.total_cost_usd` (chi phí đã dùng), không phải số còn lại; xem `/me/usage` nếu cần số còn lại đúng.

## Part 5: Scaling & Reliability (CP4)

### Exercise 5.1: Health và readiness

Đọc [develop/app.py](./05-scaling-reliability/develop/app.py): `/health` là liveness, báo process còn hoạt động; `/ready` là readiness, chỉ nhận traffic sau khi khởi động xong và trả 503 khi `_is_ready=False`. Trong bản production, `/ready` còn thử `Redis PING` nếu đã kết nối Redis lúc startup. Liveness không nên phụ thuộc Redis để tránh restart process khỏe khi chỉ Redis gặp sự cố; readiness có thể trả 503 để ngừng nhận traffic.

Lệnh chuẩn bị và chạy trong `05-scaling-reliability/develop/` (venv đặt trong WSL):

```powershell
wsl -d Ubuntu-24.04 -- /usr/bin/python3 -m venv /tmp/day14-venv
wsl -d Ubuntu-24.04 -- /tmp/day14-venv/bin/python -m pip install -r requirements.txt --quiet
wsl -d Ubuntu-24.04 -- /tmp/day14-venv/bin/python app.py
```

Lệnh kiểm tra từ gốc repo:

```powershell
curl.exe -sS -i 'http://localhost:8000/health'
curl.exe -sS -i 'http://localhost:8000/ready'
curl.exe -sS -i -X POST 'http://localhost:8000/ask?question=hello'
```

Kết quả: cả ba trả `HTTP/1.1 200 OK`. `/health` trả `status=ok`, `uptime_seconds=20.9`, `version=1.0.0`, `checks.memory.used_percent=10.9` tại thời điểm gọi; `/ready` trả `{"ready":true,"in_flight_requests":1}`; `/ask` trả câu trả lời mock. Các giá trị uptime và memory chỉ là snapshot của lần thử này.

### Exercise 5.2: Graceful shutdown

Code đặt `_is_ready=False` trong lifespan shutdown rồi chờ `_in_flight_requests` về 0, tối đa 30 giây. Tôi kiểm tra bằng hai request đồng thời và SIGTERM tới PID `402` (PID lấy từ log lúc khởi động):

```powershell
$job1 = Start-Job -ScriptBlock { curl.exe -sS -o NUL -w 'A HTTP %{http_code}' -X POST 'http://localhost:8000/ask?question=hello' }
$job2 = Start-Job -ScriptBlock { curl.exe -sS -o NUL -w 'B HTTP %{http_code}' -X POST 'http://localhost:8000/ask?question=docker' }
Start-Sleep -Milliseconds 500
wsl -d Ubuntu-24.04 -- kill -TERM 402
$job1,$job2 | Wait-Job | Receive-Job
$job1,$job2 | Remove-Job
```

Kết quả thực tế: A nhận `HTTP 200`, B nhận `HTTP 000` và `curl: (52) Empty reply from server`. Log server có `Shutting down`, `Graceful shutdown initiated`, `Shutdown complete`, nhưng **không chứng minh được cả hai request đều hoàn thành**. Một nguyên nhân có thể là endpoint `async def` gọi `time.sleep(3)` đồng bộ trong [mock_llm.py](./05-scaling-reliability/develop/utils/mock_llm.py), chặn event loop; request thứ hai chưa xử lý xong khi server tắt. Cần dùng I/O bất đồng bộ hoặc đưa tác vụ đồng bộ sang thread và kiểm lại dưới tải trước khi coi đây là graceful shutdown đạt yêu cầu.

### Exercise 5.3–5.5: Redis, load balancing, stateless

Đọc [production/app.py](./05-scaling-reliability/production/app.py), [docker-compose.yml](./05-scaling-reliability/production/docker-compose.yml) và [nginx.conf](./05-scaling-reliability/production/nginx.conf): client vào Nginx cổng `8080`; Nginx chuyển tới 3 agent; các agent dùng chung Redis để lưu `session:{session_id}` với TTL 3600 giây. Nếu lưu history trong RAM, request sau đi tới instance khác sẽ không thấy lượt trước. Bản ví dụ có fallback sang RAM khi Redis không kết nối được lúc startup, nên chỉ kết luận stateless khi response báo `storage=redis`.

Lệnh chạy trong `05-scaling-reliability/production/` (file `.env.local` rỗng, không có secret):

```powershell
New-Item -ItemType File -Path '.env.local' | Select-Object Name,Length
docker compose -p k5-day14-scaling config --services
docker compose -p k5-day14-scaling up -d --build --scale agent=3
docker compose -p k5-day14-scaling ps
```

Kết quả: `config --services` cho `redis`, `agent`, `nginx`. `ps` cho thấy **3 agent healthy**, **Redis healthy** và Nginx mở `0.0.0.0:8080->80/tcp`. Kiểm tra qua Nginx:

```powershell
curl.exe -sS -i 'http://localhost:8080/health'
curl.exe -sS -i 'http://localhost:8080/ready'
```

Cả hai trả HTTP 200; `/health` báo `storage=redis`, `redis_connected=true`. Hai response có `X-Served-By` khác nhau (`172.19.0.4:8000` và `172.19.0.5:8000`), cho thấy traffic qua các backend khác nhau.

Lệnh test chạy trong `05-scaling-reliability/production/`:

```powershell
wsl -d Ubuntu-24.04 -- /usr/bin/python3 test_stateless.py
```

Output thực tế: 5 request cùng session `7f13dcd9-aa98-437b-b015-fe5b794457d9` lần lượt được phục vụ bởi `instance-59944c`, `instance-65ead4`, `instance-4b28ca`, `instance-59944c`, `instance-65ead4`. `Instances used` có đủ 3 ID; endpoint history trả **10 messages**, gồm 5 câu hỏi và 5 câu trả lời. Script chỉ kiểm tra session qua nhiều instance; nó **không tự tắt một instance**.

Tôi thử thêm sau khi dừng agent 1. Lệnh `docker stop` chạy từ gốc repo; các lệnh còn lại cũng chạy từ gốc repo:

```powershell
docker stop k5-day14-scaling-agent-1
$json = @{question='Continue after one agent stopped'; session_id='7f13dcd9-aa98-437b-b015-fe5b794457d9'} | ConvertTo-Json -Compress
$json | curl.exe -sS -i -X POST 'http://localhost:8080/chat' -H 'Content-Type: application/json' --data-binary '@-'
curl.exe -sS -i 'http://localhost:8080/chat/7f13dcd9-aa98-437b-b015-fe5b794457d9/history'
```

Request mới trả HTTP 200 với `served_by=instance-65ead4`, `storage=redis`; header `X-Served-By: 172.19.0.3:8000, 172.19.0.4:8000` cho thấy Nginx đã retry qua backend khác. History trả HTTP 200 và **12 messages** (6 cặp user/assistant), chứng minh session còn sau khi một agent dừng. Request này có độ trễ đáng kể lúc retry, nên khả năng chịu lỗi không đồng nghĩa phản hồi ngay. Một lỗi nhỏ ở bản mẫu: response này ghi `turn=7` mặc dù đó là câu hỏi thứ 6, do [chat](./05-scaling-reliability/production/app.py) cộng thêm 1 sau khi đã append câu hỏi vào history.

Đã dọn stack bằng lệnh chạy trong `05-scaling-reliability/production/`:

```powershell
docker compose -p k5-day14-scaling down
```

## Part 6: Final Project (CP5)

Đã hoàn thiện [06-lab-complete/](./06-lab-complete/): config từ environment, API key, health/readiness, rate limit trong Redis, daily cost guard, JSON log, graceful shutdown, Dockerfile multi-stage chạy non-root, Compose agent + Redis, `.dockerignore` và Railway config. `render.yaml` là phương án thay thế chưa cấu hình; CP5 chọn Railway config. `/health` độc lập với Redis, còn `/ready` trả 503 nếu Redis không kết nối được.

### Lệnh chấm và số liệu

Lệnh kiểm tra bản khung ban đầu, chạy trong `06-lab-complete/`:

```powershell
wsl -d Ubuntu-24.04 -- /usr/bin/python3 check_production_ready.py --static-only
```

Output ban đầu: `0/12`, `5/24 checks passed`. Sau khi sửa, lệnh kiểm tra tĩnh (ẩn Docker CLI Windows khỏi `PATH` để checker dùng bộ đọc Compose của Python):

```powershell
wsl -d Ubuntu-24.04 -- bash -lc 'PATH=/usr/bin:/bin /usr/bin/python3 check_production_ready.py --static-only'
```

Output: `26/26 checks passed`; các mục runtime/Docker vẫn chưa được kiểm tra trong chế độ này.

Ubuntu hiện chưa bật Docker Desktop WSL integration. Lệnh `wsl -d Ubuntu-24.04 -- bash -lc 'command -v docker; docker version --format "{{.Server.Version}}"'` báo không có Docker CLI trong distro. Để script chấm chạy bằng Python Linux (kiểm được SIGTERM) và dùng Docker Desktop Windows, tôi tạo helper tạm `/tmp/day14-bin/docker`, đổi `/mnt/...` và build context `.` sang đường dẫn Windows bằng `wslpath -w`, rồi gọi `/mnt/c/Users/dell/AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe`. Helper chỉ nằm trong `/tmp`, không commit vào repo. Lệnh `wsl -d Ubuntu-24.04 -- sleep 3600` giữ distro chạy để `/tmp` không bị reset trong lúc kiểm tra.

Các lệnh chuẩn bị chạy trong `06-lab-complete/`:

```powershell
wsl -d Ubuntu-24.04 -- /usr/bin/python3 -m venv /tmp/day14-venv
wsl -d Ubuntu-24.04 -- /tmp/day14-venv/bin/python -m pip install -r requirements.txt --quiet
wsl -d Ubuntu-24.04 -- /tmp/day14-bin/docker info --format '{{.ServerVersion}}'
```

Lệnh cuối trả Docker server `29.9.3`. Helper được tạo bằng PowerShell: `$bridge` chứa shell script bên dưới, sau đó chạy `$bridge = $bridge.Replace("`r`n", "`n") + "`n"`, `$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($bridge))`, `wsl -d Ubuntu-24.04 -- bash -c "echo $encoded | base64 -d > /tmp/day14-bin/docker"` và `wsl -d Ubuntu-24.04 -- chmod +x /tmp/day14-bin/docker`.

```bash
#!/usr/bin/env bash
args=()
for arg in "$@"; do
  if [[ "$arg" == /mnt/* ]]; then
    args+=("$(wslpath -w "$arg")")
  elif [[ "$arg" == "." ]]; then
    args+=("$(wslpath -w "$PWD")")
  else
    args+=("$arg")
  fi
done
exec /mnt/c/Users/dell/AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe "${args[@]}"
```

**Lệnh chấm đầy đủ**, chạy trong `06-lab-complete/`:

```powershell
wsl -d Ubuntu-24.04 -- env PATH=/tmp/day14-bin:/usr/bin:/bin /tmp/day14-venv/bin/python check_production_ready.py
```

Output: **`PASS 12/12 — PRODUCTION READY!`**, **`41/41 checks passed`**. Image được checker đo **238 MB** (script tính byte / 1024²), build trong **18 giây**. Checker đặt `RATE_LIMIT_PER_MINUTE=5` và thấy 429 sau **5** request thành công; sau restart vẫn 429. Thiếu/sai key trả 401, key đúng 200; `/ready` trả 503 khi Redis mất kết nối trong khi `/health` vẫn 200; budget rất nhỏ trả 402 ở request đầu; **12** dòng log app là JSON hợp lệ. SIGTERM lúc có request giữ request 200 và process exit code 0; `docker stop` exit code 0 trong **0,9 giây**. Mọi số liệu trong đoạn này đều từ lệnh checker đầy đủ trên.

Phần `📋 Checklist Deliverable` từ output:

```text
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
```

Kiểm tra Compose trực tiếp trong `06-lab-complete/` với key mẫu chỉ dùng local:

```powershell
$env:AGENT_API_KEY = 'lab-cp5-key'
try {
  docker compose -p k5-day14-final up -d --build --wait
  docker compose -p k5-day14-final ps
  curl.exe -sS -i 'http://localhost:8000/health'
  curl.exe -sS -i 'http://localhost:8000/ready'
  $json = @{question='What is deployment?'} | ConvertTo-Json -Compress
  $json | curl.exe -sS -i -X POST 'http://localhost:8000/ask' -H 'Content-Type: application/json' -H 'X-API-Key: lab-cp5-key' --data-binary '@-'
} finally {
  docker compose -p k5-day14-final down
  Remove-Item Env:AGENT_API_KEY
}
```

Output: agent và Redis đều healthy; cả ba endpoint trả HTTP 200. `/ask` trả `cost_usd=2.01e-05` cho câu hỏi mẫu. Stack đã được dọn bằng `down`.

Giới hạn cần nhớ: cost guard mẫu kiểm tra số tiền đã dùng trước request rồi mới ghi chi phí sau khi trả lời, nên nhiều request đồng thời vẫn có thể vượt nhẹ ngân sách. `PASS 12/12` xác nhận hợp đồng chấm của lab; cloud deployment và cấu hình Redis/secret trên nền tảng sẽ thực hiện ở CP6.

## Part 7: Benchmark & Observability — CP7

Đã chạy benchmark **local** cho agent develop v1/v2 và điền [BENCHMARK_REPORT.md](./BENCHMARK_REPORT.md). Report ghi môi trường, ngưỡng SLO, bảng 4 mức concurrency, 3 mức `MOCK_SLOW_RATE`, eval v1/v2/v2 sau sửa, lệnh chính xác tạo từng file JSON, giải thích p95/p99 và cost trên mỗi câu đúng. Mười file kết quả ở [develop/reports/](./06-lab-complete/benchmark-observability/develop/reports/) và job [eval.yml](./.github/workflows/eval.yml). Lệnh cuối `eval/run_eval.py --url http://localhost:8002 --min-accuracy 1.0 --baseline reports/eval_v2.json --out reports/eval_v2_fixed.json` trả exit code 0, `23/23`, không regression; chi tiết lệnh chạy và các lần SLO FAIL có trong báo cáo. CP8 (Grafana, Jaeger, Prometheus alerts, Locust scaling) chưa đo.

## AI log

- CP0–CP1: AI hỗ trợ đọc yêu cầu, so sánh hai bản agent, chạy kiểm tra và soạn câu trả lời Part 1. Đã đối chiếu code, mã HTTP và server log.
- CP2: AI hỗ trợ đọc Dockerfile/Compose, ghi câu trả lời Part 2.
- CP3: AI hỗ trợ đọc luồng xác thực và giới hạn, ghi lại lệnh cùng HTTP response thực tế, và giải thích cost guard.
- CP4: AI hỗ trợ đọc health/readiness và Redis/Nginx, kiểm tra stateless sau khi dừng một agent.
- CP5: AI hỗ trợ hoàn thiện agent Part 6, chạy checker tĩnh và đầy đủ trong WSL2, kiểm tra Compose và ghi lại lệnh cùng số liệu thực tế.
- CP6: AI thêm Redis và biến môi trường Railway, tạo domain.
- CP7: AI sửa hai entry knowledge base, viết quality gate CI.
