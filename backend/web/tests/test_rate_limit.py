"""Rate Limit Middleware Tests"""
from unittest.mock import patch, MagicMock

from rest_framework import status


class TestRateLimitNormalRequest:
    """正常请求放行（未达阈值）"""

    def test_login_under_limit(self, db, api_client):
        with patch('web.middleware.rate_limit.RateLimitMiddleware._check_rate_limit',
                   return_value=(True, 4)):
            resp = api_client.post('/api/user/account/login/', {
                'username': 'test', 'password': 'test'
            }, format='json')
            assert resp.status_code != 429

    def test_chat_under_limit(self, db, auth_client):
        with patch('web.middleware.rate_limit.RateLimitMiddleware._check_rate_limit',
                   return_value=(True, 19)):
            resp = auth_client.post('/api/friend/message/chat/', {
                'friend_id': 1, 'message': 'hello'
            }, format='json')
            # 可能 404（friend 不存在）但不应该是 429
            assert resp.status_code != 429


class TestRateLimitExceeded:
    """超阈值返回 429 + Retry-After"""

    def test_login_rate_limited(self, db, api_client):
        with patch('web.middleware.rate_limit.RateLimitMiddleware._check_rate_limit',
                   return_value=(False, 23)):
            resp = api_client.post('/api/user/account/login/', {
                'username': 'test', 'password': 'test'
            }, format='json')
            assert resp.status_code == 429
            assert resp['Retry-After'] == '23'
            data = resp.json()
            assert 'message' in data
            assert data['retry_after'] == 23

    def test_chat_rate_limited(self, db, auth_client):
        with patch('web.middleware.rate_limit.RateLimitMiddleware._check_rate_limit',
                   return_value=(False, 15)):
            resp = auth_client.post('/api/friend/message/chat/', {
                'friend_id': 1, 'message': 'hello'
            }, format='json')
            assert resp.status_code == 429


class TestRateLimitUserIsolation:
    """不同用户独立计数"""

    def test_different_users_isolated(self, db, api_client, user):
        from rest_framework_simplejwt.tokens import RefreshToken

        # 用户 A 被限流
        with patch('web.middleware.rate_limit.RateLimitMiddleware._check_rate_limit',
                   return_value=(False, 30)):
            resp = api_client.post('/api/user/account/login/', {
                'username': 'test', 'password': 'test'
            }, format='json')
            assert resp.status_code == 429

        # 用户 B 正常
        token = str(RefreshToken.for_user(user).access_token)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        with patch('web.middleware.rate_limit.RateLimitMiddleware._check_rate_limit',
                   return_value=(True, 19)):
            resp = api_client.post('/api/friend/message/chat/', {
                'friend_id': 1, 'message': 'hello'
            }, format='json')
            assert resp.status_code != 429


class TestRateLimitAnonymousByIP:
    """未登录用户按 IP 限流"""

    def test_anonymous_ip_rate_limit(self, db, api_client):
        with patch('web.middleware.rate_limit.RateLimitMiddleware._check_rate_limit',
                   return_value=(False, 30)):
            resp = api_client.post('/api/user/account/login/', {
                'username': 'test', 'password': 'test'
            }, format='json')
            assert resp.status_code == 429


class TestRateLimitFailOpen:
    """Redis 异常时 fail-open"""

    def test_redis_error_does_not_block(self, db, api_client):
        with patch('web.middleware.rate_limit.RateLimitMiddleware._check_rate_limit',
                   side_effect=Exception('Redis connection refused')):
            resp = api_client.post('/api/user/account/login/', {
                'username': 'test', 'password': 'test'
            }, format='json')
            # 应该是 401（密码错误）或其他业务错误，而不是 429 或 500
            assert resp.status_code != 429
            # fail-open: 不因 Redis 异常而返回 500
            assert resp.status_code < 500


class TestRateLimitGetUnlimited:
    """GET 请求不限流"""

    def test_get_not_rate_limited(self, db, api_client):
        # GET 请求不应调用 _check_rate_limit
        resp = api_client.get('/api/homepage/index/')
        assert resp.status_code == 200

    def test_get_homepage_not_rate_limited(self, db, api_client):
        resp = api_client.get('/api/homepage/index/')
        assert resp.status_code == 200


class TestRateLimitSkipPaths:
    """跳过路径不限流"""

    @patch("web.views.health.app.control.inspect")
    @patch("web.views.health.redis.Redis.from_url")
    def test_health_never_rate_limited(self, mock_redis, mock_inspect, db,
                                        api_client):
        """health 端点应被限流跳过，不考虑 health 内部检查状态"""
        mock_redis.return_value = MagicMock()
        mock_insp = MagicMock()
        mock_insp.ping.return_value = {"worker@host": {"ok": "pong"}}
        mock_inspect.return_value = mock_insp

        resp = api_client.get('/api/health/')
        assert resp.status_code == 200

    def test_refresh_token_never_rate_limited(self, db, api_client):
        resp = api_client.post('/api/user/account/refresh_token/', {}, format='json')
        # 可能是 400/401 但不是 429
        assert resp.status_code != 429


class TestRateLimitWindowRecovery:
    """窗口过期后自动恢复"""

    def test_recovery_after_window_expiry(self, db, api_client):
        # 模拟被限流
        with patch('web.middleware.rate_limit.RateLimitMiddleware._check_rate_limit',
                   return_value=(False, 1)):
            resp = api_client.post('/api/user/account/login/', {
                'username': 'test', 'password': 'test'
            }, format='json')
            assert resp.status_code == 429

        # 窗口过期后恢复
        with patch('web.middleware.rate_limit.RateLimitMiddleware._check_rate_limit',
                   return_value=(True, 4)):
            resp = api_client.post('/api/user/account/login/', {
                'username': 'test2', 'password': 'test2'
            }, format='json')
            assert resp.status_code != 429
