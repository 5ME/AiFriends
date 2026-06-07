from unittest.mock import patch, MagicMock

from rest_framework import status


class TestHealthEndpoint:
    """GET /api/health/"""

    @patch("web.views.health.app.control.inspect")
    @patch("web.views.health.redis.Redis.from_url")
    def test_health_ok(self, mock_redis_from_url, mock_inspect, db, api_client):
        """全部组件正常 → 200 + 完整响应体"""
        mock_redis_client = MagicMock()
        mock_redis_from_url.return_value = mock_redis_client

        mock_insp = MagicMock()
        mock_insp.ping.return_value = {"worker@host": {"ok": "pong"}}
        mock_inspect.return_value = mock_insp

        resp = api_client.get("/api/health/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json() == {
            "status": "ok", "db": "ok", "redis": "ok", "celery": "ok"
        }

    @patch("web.views.health.app.control.inspect")
    @patch("web.views.health.redis.Redis.from_url")
    def test_health_has_request_id(self, mock_redis_from_url, mock_inspect, db,
                                    api_client):
        """X-Request-ID 头仍返回（测试环境需 mock Redis/Celery）"""
        mock_redis_client = MagicMock()
        mock_redis_from_url.return_value = mock_redis_client

        mock_insp = MagicMock()
        mock_insp.ping.return_value = {"worker@host": {"ok": "pong"}}
        mock_inspect.return_value = mock_insp

        resp = api_client.get("/api/health/")
        assert "X-Request-ID" in resp
        rid = resp["X-Request-ID"]
        assert len(rid) == 32
        assert all(c in "0123456789abcdef" for c in rid)

    @patch("web.views.health.app.control.inspect")
    @patch("web.views.health.redis.Redis.from_url")
    def test_health_db_error(self, mock_redis_from_url, mock_inspect, db,
                              api_client):
        """DB 故障 → 503 + db:error，其他组件仍 ok"""
        mock_redis_client = MagicMock()
        mock_redis_from_url.return_value = mock_redis_client

        mock_insp = MagicMock()
        mock_insp.ping.return_value = {"worker@host": {"ok": "pong"}}
        mock_inspect.return_value = mock_insp

        with patch("django.db.connections") as mock_connections:
            mock_db = MagicMock()
            mock_db.cursor.side_effect = Exception("DB connection failed")
            mock_connections.__getitem__.return_value = mock_db

            resp = api_client.get("/api/health/")
            assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            data = resp.json()
            assert data["db"] == "error"
            assert data["redis"] == "ok"
            assert data["celery"] == "ok"
            assert data["status"] == "degraded"

    @patch("web.views.health.app.control.inspect")
    def test_health_redis_error(self, mock_inspect, db, api_client):
        """Redis 故障 → 503 + redis:error，其他组件仍 ok"""
        mock_insp = MagicMock()
        mock_insp.ping.return_value = {"worker@host": {"ok": "pong"}}
        mock_inspect.return_value = mock_insp

        with patch("web.views.health.redis.Redis.from_url") as mock_redis:
            mock_client = MagicMock()
            mock_client.ping.side_effect = ConnectionError("Connection refused")
            mock_redis.return_value = mock_client

            resp = api_client.get("/api/health/")
            assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            data = resp.json()
            assert data["redis"] == "error"
            assert data["db"] == "ok"
            assert data["celery"] == "ok"
            assert data["status"] == "degraded"

    @patch("web.views.health.redis.Redis.from_url")
    def test_health_celery_error(self, mock_redis_from_url, db, api_client):
        """Celery 无 worker → 503 + celery:error，其他组件仍 ok"""
        mock_redis_client = MagicMock()
        mock_redis_from_url.return_value = mock_redis_client

        with patch("web.views.health.app.control.inspect") as mock_inspect:
            mock_insp = MagicMock()
            mock_insp.ping.return_value = None  # 无 worker 响应
            mock_inspect.return_value = mock_insp

            resp = api_client.get("/api/health/")
            assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            data = resp.json()
            assert data["celery"] == "error"
            assert data["db"] == "ok"
            assert data["redis"] == "ok"
            assert data["status"] == "degraded"

    @patch("web.views.health.app.control.inspect")
    def test_health_partial_degraded(self, mock_inspect, db, api_client):
        """仅 Redis 挂，DB + Celery 正常 → 503 + 仅 redis:error"""
        mock_insp = MagicMock()
        mock_insp.ping.return_value = {"worker@host": {"ok": "pong"}}
        mock_inspect.return_value = mock_insp

        with patch("web.views.health.redis.Redis.from_url") as mock_redis:
            mock_client = MagicMock()
            mock_client.ping.side_effect = ConnectionError("Connection refused")
            mock_redis.return_value = mock_client

            resp = api_client.get("/api/health/")
            assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            data = resp.json()
            assert data["redis"] == "error"
            assert data["db"] == "ok"
            assert data["celery"] == "ok"
            assert data["status"] == "degraded"
