from rest_framework import status


class TestHealthEndpoint:
    """GET /api/health/"""

    def test_health_ok(self, db, api_client):
        resp = api_client.get("/api/health/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json() == {"status": "ok", "db": "ok"}

    def test_health_has_request_id(self, db, api_client):
        resp = api_client.get("/api/health/")
        assert "X-Request-ID" in resp
        rid = resp["X-Request-ID"]
        assert len(rid) == 32
        assert all(c in "0123456789abcdef" for c in rid)
