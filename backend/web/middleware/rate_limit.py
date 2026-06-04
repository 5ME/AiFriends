import logging
import time
import uuid

import redis
from django.conf import settings
from django.http import JsonResponse

logger = logging.getLogger(__name__)

# Sliding Window Log 限流 Lua 脚本
# KEYS[1]: ratelimit key
# ARGV[1]: current timestamp (ms)
# ARGV[2]: window size (ms)
# ARGV[3]: max requests
# ARGV[4]: unique member id (f"{now}:{uuid.uuid4().hex[:8]}")
_LUA_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)

if count < limit then
    redis.call('ZADD', key, now, member)
    redis.call('EXPIRE', key, math.ceil(window / 1000) + 1)
    return {1, limit - count - 1}
else
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = math.ceil((tonumber(oldest[2]) + window - now) / 1000)
    if retry_after < 1 then retry_after = 1 end
    return {0, retry_after}
end
"""


class RateLimitMiddleware:
    """Sliding Window Log 限流中间件。

    按用户（登录）或 IP（匿名）对写请求做频率限制。
    Redis 不可用时 fail-open，不阻断请求。
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._redis = None
        self._lua = None

    @property
    def redis_client(self):
        if self._redis is None:
            redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/1')
            self._redis = redis.Redis.from_url(redis_url, decode_responses=False)
            self._lua = self._redis.register_script(_LUA_SCRIPT)
        return self._redis

    def __call__(self, request):
        # 1. 跳过不需要限流的路径
        if self._should_skip(request.path):
            return self.get_response(request)

        # 2. 只限制写操作，GET/HEAD/OPTIONS 不限
        if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
            return self.get_response(request)

        # 3. 匹配限流规则
        rule = self._match_rule(request.path, request.method)
        if rule is None:
            return self.get_response(request)

        # 4. 构建 Redis key
        key = self._build_key(request, rule['scope'])

        # 5. 执行限流检查（fail-open）
        try:
            allowed, value = self._check_rate_limit(key, rule)
        except Exception:
            logger.exception('Redis 限流检查失败，跳过限流（fail-open）')
            return self.get_response(request)

        if allowed:
            return self.get_response(request)

        # 6. 返回 429
        return JsonResponse(
            {
                'message': f'请求过于频繁，请 {value} 秒后再试',
                'retry_after': value,
            },
            status=429,
            headers={'Retry-After': str(value)},
        )

    def _should_skip(self, path):
        skip_paths = getattr(settings, 'RATE_LIMIT_SKIP_PATHS', [
            '/api/health/',
            '/api/user/account/refresh_token/',
            '/static/',
            '/media/',
            '/admin/',
        ])
        return any(path.startswith(p) for p in skip_paths)

    def _match_rule(self, path, method):
        rules = getattr(settings, 'RATE_LIMIT_RULES', {})
        for scope, (url_prefix, methods, max_req, window) in rules.items():
            if path.startswith(url_prefix) and method in methods:
                return {
                    'scope': scope,
                    'max_req': max_req,
                    'window_sec': window,
                }
        return None

    def _build_key(self, request, scope):
        if hasattr(request, 'user') and request.user.is_authenticated:
            identifier = f'user:{request.user.id}'
        else:
            xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
            ip = xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR', 'unknown')
            identifier = f'ip:{ip}'
        return f'ratelimit:{identifier}:{scope}'

    def _check_rate_limit(self, key, rule):
        now_ms = int(time.time() * 1000)
        window_ms = rule['window_sec'] * 1000
        member = f'{now_ms}:{uuid.uuid4().hex[:8]}'
        result = self._lua(
            keys=[key],
            args=[now_ms, window_ms, rule['max_req'], member],
        )
        allowed = bool(result[0])
        value = int(result[1])
        return allowed, value
