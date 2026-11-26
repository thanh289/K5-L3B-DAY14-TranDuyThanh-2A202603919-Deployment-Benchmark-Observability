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

### AI log

- Hỏi AI: đọc yêu cầu CP0–CP1, hỗ trợ chạy kiểm tra và soạn câu trả lời Part 1.
