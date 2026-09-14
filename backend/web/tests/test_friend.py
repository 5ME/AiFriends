import pytest
from rest_framework import status

from web.models.friend import Friend, Message


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

    def test_get_list_last_message_preview(self, auth_client, friend):
        """最后一条消息的 output 作为预览 + isoformat 时间戳"""
        Message.objects.create(friend=friend, user_message="你好", output="第一句回复")
        last = Message.objects.create(friend=friend, user_message="在吗", output="第二句回复")

        resp = auth_client.get("/api/friend/get_list/")
        item = resp.json()["friends"][0]
        assert item["last_message"] == "第二句回复"
        assert item["last_message_at"] == last.created_at.isoformat()

    def test_get_list_last_message_falls_back_to_user_message(self, auth_client, friend):
        """output 为空/全空白（流中断/模型空回复）→ 回退 user_message"""
        Message.objects.create(friend=friend, user_message="只有我说了话", output="")

        resp = auth_client.get("/api/friend/get_list/")
        assert resp.json()["friends"][0]["last_message"] == "只有我说了话"

        # 空白字符不算内容：仍应回退到用户消息
        Message.objects.create(friend=friend, user_message="我又说了一句", output="\n\n  ")
        resp = auth_client.get("/api/friend/get_list/")
        assert resp.json()["friends"][0]["last_message"] == "我又说了一句"

    def test_get_list_last_message_empty_without_message(self, auth_client, friend):
        """无消息的好友 → 预览空串 + 时间 null（前端据此显示占位文案）"""
        resp = auth_client.get("/api/friend/get_list/")
        item = resp.json()["friends"][0]
        assert item["last_message"] == ""
        assert item["last_message_at"] is None

    def test_get_list_last_message_truncated_and_normalized(self, auth_client, friend):
        """长文本截断到 60 字符；换行/连续空白归一化（防 20×5000 字符 payload）"""
        Message.objects.create(
            friend=friend, user_message="x", output="第一行\n\n第二行   " + "a" * 100
        )

        resp = auth_client.get("/api/friend/get_list/")
        preview = resp.json()["friends"][0]["last_message"]
        assert len(preview) == 60
        assert preview.startswith("第一行 第二行 a")
        assert "\n" not in preview


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


class TestGetHistory:
    """GET /api/friend/message/get_history/"""

    def test_get_history_returns_created_at_and_citations(self, auth_client, friend):
        """每条消息含 created_at ISO 时间与 citations 字段（Q3/Q4 后端批次）"""
        from web.models.friend import Message

        citations = [
            {'index': 1, 'title': '测试文档.pdf', 'chunk_index': 3, 'content': '引用正文'},
        ]
        msg_with_citations = Message.objects.create(
            friend=friend,
            user_message='你好',
            output='你好呀',
            citations=citations,
        )
        msg_without_citations = Message.objects.create(
            friend=friend,
            user_message='第二条',
            output='回复',
        )

        resp = auth_client.get(
            "/api/friend/message/get_history/",
            {"friend_id": friend.id},
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["message"] == "success"
        assert len(data["messages"]) == 2

        # 按 -id 排序：最新（无 citations）在前
        newest = data["messages"][0]
        oldest = data["messages"][1]
        assert newest["id"] == msg_without_citations.id
        assert newest["created_at"] == msg_without_citations.created_at.isoformat()
        assert newest["citations"] == []

        assert oldest["id"] == msg_with_citations.id
        assert oldest["created_at"] == msg_with_citations.created_at.isoformat()
        assert oldest["citations"] == citations
