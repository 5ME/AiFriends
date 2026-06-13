"""GET /api/admin/usage/summary/ — 聚合摘要接口测试"""
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from web.models.usage import APIUsage


def _admin_client():
    """创建 admin 用户并返回已认证 client"""
    admin, _ = User.objects.get_or_create(
        username="admin", defaults={"is_staff": True},
    )
    client = APIClient()
    refresh = RefreshToken.for_user(admin)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


class TestUsageSummary:
    """GET /api/admin/usage/summary/"""

    def test_requires_admin(self, auth_client):
        """非 admin → 403"""
        resp = auth_client.get("/api/admin/usage/summary/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_aggregation(self, user_profile):
        """按 api_type 聚合 token_count 和 call_count"""
        APIUsage.objects.create(
            user=user_profile, api_type='llm', model_name='m1',
            token_count=100, duration_ms=1000, created_at=timezone.now(),
        )
        APIUsage.objects.create(
            user=user_profile, api_type='llm', model_name='m1',
            token_count=50, duration_ms=500, created_at=timezone.now(),
        )
        APIUsage.objects.create(
            user=user_profile, api_type='tts', model_name='m2',
            token_count=200, duration_ms=3000, created_at=timezone.now(),
        )

        resp = _admin_client().get("/api/admin/usage/summary/?days=1")
        assert resp.status_code == 200

        rows = resp.json()['summary']
        llm_rows = [r for r in rows if r['api_type'] == 'llm']
        assert len(llm_rows) == 1
        assert llm_rows[0]['total_tokens'] == 150
        assert llm_rows[0]['call_count'] == 2

        tts_rows = [r for r in rows if r['api_type'] == 'tts']
        assert tts_rows[0]['total_tokens'] == 200
        assert tts_rows[0]['call_count'] == 1

    def test_user_id_filter(self, user_profile):
        """user_id 过滤只返回指定用户"""
        APIUsage.objects.create(
            user=user_profile, api_type='llm', model_name='m1',
            token_count=100, duration_ms=0, created_at=timezone.now(),
        )
        other = User.objects.create_user(username="other")
        from web.models.user import UserProfile
        other_profile = UserProfile.objects.create(user=other)
        APIUsage.objects.create(
            user=other_profile, api_type='llm', model_name='m1',
            token_count=200, duration_ms=0, created_at=timezone.now(),
        )

        resp = _admin_client().get(
            f"/api/admin/usage/summary/?days=1&user_id={user_profile.id}"
        )
        assert resp.status_code == 200
        assert all(r['user_id'] == user_profile.id for r in resp.json()['summary'])

    def test_days_range(self, db):
        """只返回指定天数内的记录"""
        from datetime import timedelta
        old_date = timezone.now() - timedelta(days=30)

        # auto_now_add 会覆盖 created_at，先用 create 再用 update 设回旧日期
        old_record = APIUsage.objects.create(
            user=None, api_type='llm', model_name='m1',
            token_count=100, duration_ms=0,
        )
        APIUsage.objects.filter(pk=old_record.pk).update(created_at=old_date)

        APIUsage.objects.create(
            user=None, api_type='llm', model_name='m1',
            token_count=200, duration_ms=0,
        )

        # days=7: 只有今天的
        resp = _admin_client().get("/api/admin/usage/summary/?days=7")
        rows = resp.json()['summary']
        assert len(rows) == 1, f"Expected 1 row, got {len(rows)}: {rows}"
        assert rows[0]['total_tokens'] == 200

        # days=60: 两条都有
        resp = _admin_client().get("/api/admin/usage/summary/?days=60")
        assert len(resp.json()['summary']) == 2

    def test_filters_in_response(self, db):
        """响应包含 filters 元数据"""
        resp = _admin_client().get("/api/admin/usage/summary/?days=3")
        assert resp.json()['filters'] == {'days': 3, 'user_id': None}
