import pytest
from django.contrib.auth.models import User
from rest_framework import status

from web.models.user import UserProfile


class TestLogin:
    """POST /api/user/account/login/"""

    def test_login_success(self, api_client, user):
        """正确凭据 → 200 + access_token + refresh cookie"""
        user.set_password("testpass123")
        user.save()
        resp = api_client.post(
            "/api/user/account/login/",
            {"username": "testuser", "password": "testpass123"},
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "access_token" in data
        assert data["username"] == "testuser"
        assert resp.cookies.get("refresh_token") is not None

    def test_login_wrong_password(self, api_client, user):
        """错误密码 → 401"""
        user.set_password("testpass123")
        user.save()
        resp = api_client.post(
            "/api/user/account/login/",
            {"username": "testuser", "password": "wrongpass"},
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_empty_username(self, api_client):
        """空用户名 → 400"""
        resp = api_client.post(
            "/api/user/account/login/",
            {"username": "", "password": "testpass123"},
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_empty_password(self, api_client):
        """空密码 → 400"""
        resp = api_client.post(
            "/api/user/account/login/",
            {"username": "testuser", "password": ""},
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


class TestRegister:
    """POST /api/user/account/register/"""

    def test_register_success(self, api_client, db):
        """新用户 → 200 + User + UserProfile 均已创建"""
        resp = api_client.post(
            "/api/user/account/register/",
            {"username": "newuser", "password": "newpass123"},
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "access_token" in data
        assert data["username"] == "newuser"
        assert resp.cookies.get("refresh_token") is not None
        assert User.objects.filter(username="newuser").exists()
        assert UserProfile.objects.filter(user__username="newuser").exists()

    def test_register_duplicate_username(self, api_client, user):
        """重复用户名 → 409"""
        resp = api_client.post(
            "/api/user/account/register/",
            {"username": "testuser", "password": "newpass123"},
        )
        assert resp.status_code == status.HTTP_409_CONFLICT

    def test_register_empty_fields(self, api_client):
        """空字段 → 400"""
        resp = api_client.post(
            "/api/user/account/register/",
            {"username": "", "password": ""},
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


class TestRefreshToken:
    """POST /api/user/account/refresh_token/"""

    def test_refresh_success(self, auth_client):
        """有效 refresh cookie → 200 + 新 access_token"""
        resp = auth_client.post("/api/user/account/refresh_token/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "access_token" in data

    def test_refresh_missing_cookie(self, api_client):
        """无 refresh cookie → 401"""
        resp = api_client.post("/api/user/account/refresh_token/")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_refresh_expired_token(self, api_client):
        """过期 refresh_token → 401"""
        api_client.cookies["refresh_token"] = "invalid_expired_token"
        resp = api_client.post("/api/user/account/refresh_token/")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


class TestLogout:
    """POST /api/user/account/logout/"""

    def test_logout_success(self, auth_client):
        """已认证 → 200 + refresh cookie 已清除"""
        resp = auth_client.post("/api/user/account/logout/")
        assert resp.status_code == status.HTTP_200_OK
        # delete_cookie sets cookie to empty string
        assert resp.cookies.get("refresh_token").value == ""


class TestGetUserInfo:
    """GET /api/user/account/get_user_info/"""

    def test_get_user_info(self, auth_client, user):
        """已认证 → 200 + 返回用户数据"""
        resp = auth_client.get("/api/user/account/get_user_info/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["username"] == "testuser"
        assert "user_id" in data
        assert "photo" in data
        assert "profile" in data
