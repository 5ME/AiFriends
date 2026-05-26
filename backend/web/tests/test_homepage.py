from rest_framework import status
from web.models.character import Character
from web.models.user import UserProfile


class TestHomepageIndex:
    """GET /api/homepage/index/"""

    def test_list_returns_characters(self, api_client, character):
        resp = api_client.get("/api/homepage/index/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["message"] == "success"
        assert len(data["characters"]) >= 1
        assert any(c["name"] == "Test Character" for c in data["characters"])

    def test_list_pagination(self, api_client, user, voice):
        """items_count=0 → max 20"""
        author = UserProfile.objects.get(user=user)
        for i in range(25):
            Character.objects.create(
                author=author, name=f"Char {i}", voice=voice,
            )
        resp = api_client.get("/api/homepage/index/?items_count=0")
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.json()["characters"]) == 20

        # 翻页
        resp2 = api_client.get("/api/homepage/index/?items_count=20")
        assert len(resp2.json()["characters"]) >= 5

    def test_search_by_name(self, api_client, character):
        resp = api_client.get("/api/homepage/index/?search_text=Test")
        assert resp.status_code == status.HTTP_200_OK
        names = [c["name"] for c in resp.json()["characters"]]
        assert "Test Character" in names

    def test_search_by_introduction(self, api_client, character):
        resp = api_client.get(
            "/api/homepage/index/?search_text=" + character.introduction[:5]
        )
        assert resp.status_code == status.HTTP_200_OK

    def test_search_empty_text(self, api_client, character):
        resp = api_client.get("/api/homepage/index/?search_text=")
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.json()["characters"]) >= 1
