# Deployment Information — CP6

## Public URL

https://vinuni-day14-production.up.railway.app

## Platform

- Railway project: `VinUni Day14`, environment: `production`.
- Agent: service `VinUni Day14`, deployed from `06-lab-complete/` with its `Dockerfile` and `railway.toml`.
- Redis: service `Redis` in the same project; status `Online` when checked.
- The agent's `/health` is the Railway deployment healthcheck. `/ready` checks Redis.

## Environment variables

- `REDIS_URL=${{Redis.REDIS_URL}}` (Railway reference to the Redis service).
- `AGENT_API_KEY` (random key, set in Railway through stdin; value omitted).
- `ENVIRONMENT=production`.
- `PORT` is supplied by Railway; the Dockerfile starts Uvicorn on that port.

The key is also stored locally in `06-lab-complete/.env` for testing. Git ignores this file; never copy its value into screenshots or commits.

The Railway CLI warned that `railway.toml` (Config as Code) is deprecated and that existing files keep working until 2026-12-01. The lab currently requires this file; migrate the deployment configuration if this service must be redeployed after that date.

## Commands run and results

Commands below were run in `06-lab-complete/` using PowerShell. The initial `railway up` and its `Deploy complete` output were reported by the student; the remaining commands and outputs were checked locally.

| Command | Observed result |
| --- | --- |
| `railway status` | Project `VinUni Day14`, environment `production`, agent `Online`; initially no Redis. |
| `railway add --database redis` then `railway status` | Redis service `Online`. |
| `railway variable set 'REDIS_URL=${{Redis.REDIS_URL}}' 'ENVIRONMENT=production' --service 'VinUni Day14' --skip-deploys` | Set `REDIS_URL`, `ENVIRONMENT`. |
| `railway variable set AGENT_API_KEY --stdin --service 'VinUni Day14'` | Set `AGENT_API_KEY`; the key was generated locally and piped through stdin. |
| `railway domain --service 'VinUni Day14'` | Created `https://vinuni-day14-production.up.railway.app`. |
| `railway domain status 084b2455-bb3e-4805-9b71-8e5a5a12a1bd --service 'VinUni Day14'` | Domain sync status `ACTIVE`. |
| `railway status` | Agent and Redis both `Online`; agent public URL displayed. |

The 32-byte random API key was generated and saved without printing it:

```powershell
$bytes = New-Object byte[] 32; $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create(); $rng.GetBytes($bytes); $rng.Dispose(); $agentKey = [System.BitConverter]::ToString($bytes).Replace('-','').ToLowerInvariant(); Set-Content -LiteralPath '.env' -Value "AGENT_API_KEY=$agentKey" -Encoding ascii -NoNewline; $agentKey | railway variable set AGENT_API_KEY --stdin --service 'VinUni Day14'
```

HTTP checks (the commands print only status codes):

```powershell
$baseUrl = 'https://vinuni-day14-production.up.railway.app'; $body = @{question='Hello'} | ConvertTo-Json -Compress; $apiKey = (Get-Content -LiteralPath '.env' -Raw).Substring('AGENT_API_KEY='.Length)
"health=$(curl.exe -sS -o NUL -w '%{http_code}' "$baseUrl/health")"
"ready=$(curl.exe -sS -o NUL -w '%{http_code}' "$baseUrl/ready")"
"ask_without_key=$($body | curl.exe -sS -o NUL -w '%{http_code}' -X POST "$baseUrl/ask" -H 'Content-Type: application/json' --data-binary '@-')"
"ask_with_key=$($body | curl.exe -sS -o NUL -w '%{http_code}' -X POST "$baseUrl/ask" -H 'Content-Type: application/json' -H "X-API-Key: $apiKey" --data-binary '@-')"
```

Observed output:

```text
health=200
ready=200
ask_without_key=401
ask_with_key=200
```

## Screenshots

- [Railway dashboard](./screenshots/dashboard.png): shows the agent and Redis Online
- [Railway running](./screenshots/running.png): capture the agent's **Deployments** tab with `ACTIVE`, `Deployment successful`, and the public domain visible.
- [Railway test](./screenshots/test.png): capture PowerShell after running the four HTTP check commands above, showing `200`, `200`, `401`, `200` without displaying the API key.
