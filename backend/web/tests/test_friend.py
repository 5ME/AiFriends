import pytest
from rest_framework import status

from web.models.friend import Friend


class TestGetOrCreate:
    """POST /api/friend/get_or_create/"""

    def test_get_or_create_new(self, auth_client, character):
        """首次添加 → 200 + Friend 已创建"""
        resp = auth_client.post(
            "/api/friend/get_or_create/",
            {"character_id": character.id},
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["message"] == "success"
        assert data["friend"]["id"] is not None
        assert Friend.objects.count() == 1

    def test_get_or_create_duplicate(self, auth_client, character):
        """重复添加 → 200 + 返回已有（不重复创建）"""
        auth_client.post("/api/friend/get_or_create/", {"character_id": character.id})
        resp = auth_client.post("/api/friend/get_or_create/", {"character_id": character.id})
        assert resp.status_code == status.HTTP_200_OK
        assert Friend.objects.count() == 1

    def test_get_or_create_missing_character_id(self, auth_client):
        """无 character_id → 400"""
        resp = auth_client.post("/api/friend/get_or_create/", {})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_or_create_character_not_found(self, auth_client):
        """角色不存在 → 404"""
        resp = auth_client.post(
            "/api/friend/get_or_create/",
            {"character_id": 99999},
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_get_or_create_requires_auth(self, api_client, character):
        """无 token → 401"""
        resp = api_client.post(
            "/api/friend/get_or_create/",
            {"character_id": character.id},
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


class TestRemove:
    """POST /api/friend/remove/"""

    def test_remove_success(self, auth_client, friend):
        """删除自己的好友 → 200 + Friend 已从 DB 消失"""
        resp = auth_client.post("/api/friend/remove/", {"friend_id": friend.id})
        assert resp.status_code == status.HTTP_200_OK
        assert not Friend.objects.filter(id=friend.id).exists()

    def test_remove_other_users_friend(self, auth_client, other_user, character):
        """删除别人的好友 → 200（filter 按 user 过滤找不到记录，delete 无操作）"""
        from web.models.user import UserProfile
        other_profile = UserProfile.objects.get(user=other_user)
        other_friend = Friend.objects.create(
            user_profile=other_profile, character=character
        )
        resp = auth_client.post("/api/friend/remove/", {"friend_id": other_friend.id})
        # 按 user_profile__user 过滤 → 找不到 → delete() 无操作 → 返回 200
        assert resp.status_code == status.HTTP_200_OK
        # 确认别人的好友记录依然存在（未被误删）
        assert Friend.objects.filter(id=other_friend.id).exists()


class TestGetList:
    """GET /api/friend/get_list/"""

    def test_get_list(self, auth_client, friend):
        """已认证 → 200 + friends 数组 + 按 last_active 排序"""
        resp = auth_client.get("/api/friend/get_list/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["message"] == "success"
        assert len(data["friends"]) >= 1
        assert data["friends"][0]["id"] == friend.id


class TestIsFriend:
    """GET /api/friend/is_friend/"""

    def test_is_friend_true(self, auth_client, friend):
        """已是好友 → is_friend: true + friend_id"""
        resp = auth_client.get(
            "/api/friend/is_friend/", {"character_id": friend.character.id}
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["is_friend"] is True
        assert data["friend_id"] == friend.id

    def test_is_friend_false(self, auth_client, character):
        """不是好友 → is_friend: false + friend_id: null"""
        resp = auth_client.get(
            "/api/friend/is_friend/", {"character_id": character.id}
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["is_friend"] is False
        assert data["friend_id"] is None


class TestGetCount:
    """GET /api/friend/get_count/"""

    def test_get_count(self, auth_client, friend):
        """返回正确好友数"""
        resp = auth_client.get(
            "/api/friend/get_count/", {"character_id": friend.character.id}
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["friend_count"] == 1
