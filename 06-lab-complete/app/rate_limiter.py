"""
Rate limiting (tiêu chí 7).

Yêu cầu:
  • Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request trong 60 giây (sliding window)
  • Vượt giới hạn → HTTP 429, nên kèm header Retry-After
  • State lưu trong Redis để mọi worker / instance dùng chung và vẫn còn sau khi
    restart agent (script chấm sẽ restart agent để kiểm tra)
"""


import hashlib
import uuid

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import r


_WINDOW_SCRIPT = """
local now = redis.call('TIME')
local ms = now[1] * 1000 + math.floor(now[2] / 1000)
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ms - 60000)
local count = redis.call('ZCARD', KEYS[1])
if count >= tonumber(ARGV[1]) then
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  return {0, math.max(1, math.ceil((oldest[2] + 60000 - ms) / 1000))}
end
redis.call('ZADD', KEYS[1], ms, ARGV[2])
redis.call('EXPIRE', KEYS[1], 61)
return {1, 0}
"""


def check_rate_limit(key: str) -> None:
    if settings.rate_limit_per_minute < 1:
        raise HTTPException(status_code=503, detail="Rate limit is misconfigured")
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    try:
        allowed, retry_after = r.eval(
            _WINDOW_SCRIPT, 1, f"rate:{key_hash}", settings.rate_limit_per_minute, uuid.uuid4().hex
        )
    except RedisError:
        raise HTTPException(status_code=503, detail="Rate limiter unavailable") from None
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded", headers={"Retry-After": str(retry_after)})
