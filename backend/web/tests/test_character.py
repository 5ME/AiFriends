import pytest
from io import BytesIO
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status

from web.models.character import Character


def _make_test_image(name="test.jpg"):
    """创建 1x1 白色 JPEG 的内存文件"""
    img = Image.new("RGB", (1, 1), color="white")
    buf = BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/jpeg")


class TestCreate:
    """POST /api/create/character/create/"""

    def test_create_success(self, auth_client, voice, user_profile):
        """有效数据 → 200 + Character 已创建"""
        resp = auth_client.post(
            "/api/create/character/create/",
            {
                "name": "My Character",
                "introduction": "A friendly AI",
                "system_prompt": "You are a friendly AI character.",
                "voice_id": voice.id,
                "photo": _make_test_image("photo.jpg"),
                "background_image": _make_test_image("bg.jpg"),
            },
        )
        assert resp.status_code == status.HTTP_200_OK
        assert Character.objects.filter(name="My Character").exists()

    def test_create_no_auth(self, api_client, voice):
        """无 token → 401"""
        resp = api_client.post(
            "/api/create/character/create/",
            {"name": "X", "introduction": "X", "system_prompt": "X", "voice_id": voice.id},
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_empty_name(self, auth_client, voice):
        """空 name → 400"""
        resp = auth_client.post(
            "/api/create/character/create/",
            {
                "name": "",
                "introduction": "Test",
                "system_prompt": "Test",
                "voice_id": voice.id,
                "photo": _make_test_image("photo.jpg"),
                "background_image": _make_test_image("bg.jpg"),
            },
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_empty_introduction(self, auth_client, voice):
        """空 introduction → 400"""
        resp = auth_client.post(
            "/api/create/character/create/",
            {
                "name": "Test",
                "introduction": "",
                "system_prompt": "Test",
                "voice_id": voice.id,
                "photo": _make_test_image("photo.jpg"),
                "background_image": _make_test_image("bg.jpg"),
            },
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_empty_system_prompt(self, auth_client, voice):
        """空 system_prompt → 400"""
        resp = auth_client.post(
            "/api/create/character/create/",
            {
                "name": "Test",
                "introduction": "Test",
                "system_prompt": "",
                "voice_id": voice.id,
                "photo": _make_test_image("photo.jpg"),
                "background_image": _make_test_image("bg.jpg"),
            },
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


class TestGetSingle:
    """GET /api/create/character/get_single/"""

    def test_get_single_own(self, auth_client, character):
        """查看自己的 → 200"""
        resp = auth_client.get(
            "/api/create/character/get_single/",
            {"character_id": character.id},
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["character"]["name"] == "Test Character"

    def test_get_single_other_author(self, other_auth_client, character):
        """查看别人的 → 404"""
        resp = other_auth_client.get(
            "/api/create/character/get_single/",
            {"character_id": character.id},
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND


class TestUpdate:
    """POST /api/create/character/update/"""

    def test_update_success(self, auth_client, character, voice):
        """自己的角色 → 200 + 字段已更新"""
        resp = auth_client.post(
            "/api/create/character/update/",
            {
                "character_id": character.id,
                "name": "Updated Name",
                "introduction": "Updated intro",
                "system_prompt": "Updated system prompt",
                "voice_id": voice.id,
            },
        )
        assert resp.status_code == status.HTTP_200_OK
        character.refresh_from_db()
        assert character.name == "Updated Name"
        assert character.introduction == "Updated intro"
        assert character.system_prompt == "Updated system prompt"

    def test_update_not_author(self, other_auth_client, character, voice):
        """非作者编辑 → 404"""
        resp = other_auth_client.post(
            "/api/create/character/update/",
            {
                "character_id": character.id,
                "name": "Hacked",
                "introduction": "Hacked profile",
                "system_prompt": "Hacked system prompt",
                "voice_id": voice.id,
            },
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND


class TestDelete:
    """POST /api/create/character/remove/"""

    def test_delete_success(self, auth_client, character):
        """自己的角色 → 200 + 角色已从 DB 消失"""
        resp = auth_client.post(
            "/api/create/character/remove/",
            {"character_id": character.id},
        )
        assert resp.status_code == status.HTTP_200_OK
        assert not Character.objects.filter(id=character.id).exists()

    def test_delete_not_author(self, other_auth_client, character):
        """非作者删除 → 404"""
        resp = other_auth_client.post(
            "/api/create/character/remove/",
            {"character_id": character.id},
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND


class TestGetList:
    """GET /api/create/character/get_list/"""

    def test_get_list(self, api_client, user, character):
        """公开接口 → 200 + characters 数组"""
        resp = api_client.get(
            "/api/create/character/get_list/",
            {"user_id": user.id, "items_count": 0},
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["message"] == "success"
        assert len(data["characters"]) >= 1
