import io

import pytest
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from model_bakery import baker
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from web.models.user import UserProfile
from web.models.character import Character, Voice
from web.models.friend import Friend


def _dummy_image(name="test.png"):
    """Create a 1x1 pixel PNG SimpleUploadedFile for ImageField fixtures."""
    img = Image.new("RGB", (1, 1), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


@pytest.fixture
def api_client():
    """未认证的 DRF APIClient"""
    return APIClient()


@pytest.fixture
def user(db):
    """创建 Django User + 关联 UserProfile"""
    u = baker.make(User, username="testuser")
    baker.make(UserProfile, user=u)
    return u


@pytest.fixture
def auth_client(user):
    """已认证的 APIClient — 附带 Bearer token + refresh cookie"""
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    client.cookies["refresh_token"] = str(refresh)
    return client


@pytest.fixture
def user_profile(user):
    """已存在的 UserProfile"""
    return UserProfile.objects.get(user=user)


@pytest.fixture
def voice(db):
    """测试音色"""
    return baker.make(Voice, name="Test Voice", voice_id="test_voice_001")


@pytest.fixture
def character(user_profile, voice):
    """测试角色（属于 auth_client 的用户）"""
    photo = _dummy_image("photo.png")
    bg = _dummy_image("bg.png")
    return baker.make(
        Character,
        author=user_profile,
        name="Test Character",
        voice=voice,
        photo=photo,
        background_image=bg,
    )


@pytest.fixture
def friend(user_profile, character):
    """测试好友关系"""
    return baker.make(
        Friend,
        user_profile=user_profile,
        character=character,
    )


@pytest.fixture
def other_user(db):
    """另一个用户 — 用于权限测试"""
    u = baker.make(User, username="otheruser")
    baker.make(UserProfile, user=u)
    return u


@pytest.fixture
def other_auth_client(other_user):
    """另一个用户的已认证 client"""
    client = APIClient()
    refresh = RefreshToken.for_user(other_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    client.cookies["refresh_token"] = str(refresh)
    return client
