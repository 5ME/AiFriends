"""Liveness / Readiness 探测端点测试（P1-D2）。

- /api/health/live/  存活：不查依赖，恒 200（容器存活探测）
- /api/health/ready/ 就绪：查 DB + Redis，不查 Celery（是否接流量）
- /api/health/       深度聚合（DB+Redis+Celery）由 test_health.py 覆盖
"""
from unittest.mock import patch, MagicMock

from rest_framework import status


class TestLiveness:
    """GET /api/health/live/ — 进程存活，不查任何依赖。"""

    def test_liveness_ok(self, api_client):
        """不依赖 DB/Redis/Celery，恒 200。"""
        resp = api_client.get("/api/health/live/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json() == {"status": "ok"}


class TestReadiness:
    """GET /api/health/ready/ — 查 DB + Redis（不查 Celery）。"""

    @patch("web.views.health.redis.Redis.from_url")
    def test_readiness_ok(self, mock_redis_from_url, db, api_client):
        """DB + Redis 正常 → 200。未 mock Celery 仍 200、响应也不含 celery 键
        —— 证明 readiness 不查 Celery（D2 关键设计决策）。"""
        mock_redis_from_url.return_value = MagicMock()
        resp = api_client.get("/api/health/ready/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json() == {"status": "ok", "db": "ok", "redis": "ok"}

    @patch("web.views.health.redis.Redis.from_url")
    def test_readiness_db_error(self, mock_redis_from_url, db, api_client):
        """DB 故障 → 503 + db:error。"""
        mock_redis_from_url.return_value = MagicMock()
        with patch("django.db.connections") as mock_connections:
            mock_db = MagicMock()
            mock_db.cursor.side_effect = Exception("DB connection failed")
            mock_connections.__getitem__.return_value = mock_db
            resp = api_client.get("/api/health/ready/")
        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["db"] == "error"
        assert data["redis"] == "ok"

    def test_readiness_redis_error(self, db, api_client):
        """Redis 故障 → 503 + redis:error，db 仍 ok。"""
        with patch("web.views.health.redis.Redis.from_url") as mock_redis:
            mock_client = MagicMock()
            mock_client.ping.side_effect = ConnectionError("Connection refused")
            mock_redis.return_value = mock_client
            resp = api_client.get("/api/health/ready/")
        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["redis"] == "error"
        assert data["db"] == "ok"
