"""P1-A3 APIUsage 数据保留策略 — 聚合 + 清理测试"""
from datetime import timedelta

import pytest
from django.utils import timezone

from web.models.usage import APIUsage, APIUsageDaily


@pytest.mark.django_db
class TestAggregateUsage:
    """APIUsage → APIUsageDaily 聚合逻辑"""

    def test_aggregate_correctness(self, user_profile):
        """同一天同用户 3 llm + 2 tts → 各一行，sum/count 正确"""
        today = timezone.now()
        # 3 条 llm
        for i in range(3):
            APIUsage.objects.create(
                user=user_profile, api_type='llm', model_name='m1',
                token_count=100, duration_ms=1000, created_at=today,
            )
        # 2 条 tts
        for i in range(2):
            APIUsage.objects.create(
                user=user_profile, api_type='tts', model_name='m2',
                token_count=50, duration_ms=500, created_at=today,
            )

        target_date = timezone.localdate()
        from web.tasks.cleanup_usage import aggregate_usage
        aggregate_usage(target_date)

        llm_row = APIUsageDaily.objects.get(user=user_profile, api_type='llm')
        assert llm_row.total_tokens == 300
        assert llm_row.call_count == 3
        assert llm_row.total_duration_ms == 3000

        tts_row = APIUsageDaily.objects.get(user=user_profile, api_type='tts')
        assert tts_row.total_tokens == 100
        assert tts_row.call_count == 2
        assert tts_row.total_duration_ms == 1000

    def test_idempotent(self, user_profile):
        """同一天运行两次聚合 → 不报错，数据不变"""
        today = timezone.now()
        APIUsage.objects.create(
            user=user_profile, api_type='llm', model_name='m1',
            token_count=100, duration_ms=0, created_at=today,
        )

        target_date = timezone.localdate()
        from web.tasks.cleanup_usage import aggregate_usage
        aggregate_usage(target_date)
        aggregate_usage(target_date)  # 第二次运行

        row = APIUsageDaily.objects.get(user=user_profile, api_type='llm')
        assert row.total_tokens == 100
        assert row.call_count == 1

    def test_empty_dataset(self, db):
        """无数据时聚合不报错"""
        from web.tasks.cleanup_usage import aggregate_usage
        aggregate_usage(timezone.localdate())  # 不应抛异常
        assert APIUsageDaily.objects.count() == 0

    def test_user_isolation(self, user_profile, db):
        """用户 A 和用户 B 的 usage 独立汇总"""
        from django.contrib.auth.models import User
        from web.models.user import UserProfile
        today = timezone.now()

        # 用户 B
        user_b = User.objects.create_user(username="user_b")
        profile_b = UserProfile.objects.create(user=user_b)

        APIUsage.objects.create(
            user=user_profile, api_type='llm', model_name='m1',
            token_count=100, duration_ms=0, created_at=today,
        )
        APIUsage.objects.create(
            user=profile_b, api_type='llm', model_name='m1',
            token_count=200, duration_ms=0, created_at=today,
        )

        target_date = timezone.localdate()
        from web.tasks.cleanup_usage import aggregate_usage
        aggregate_usage(target_date)

        row_a = APIUsageDaily.objects.get(user=user_profile, api_type='llm')
        assert row_a.total_tokens == 100

        row_b = APIUsageDaily.objects.get(user=profile_b, api_type='llm')
        assert row_b.total_tokens == 200

    def test_system_user_null(self, db):
        """user=None 的 APIUsage 正常聚合（NULL 行不冲突）"""
        today = timezone.now()
        for i in range(3):
            APIUsage.objects.create(
                user=None, api_type='embedding', model_name='m1',
                token_count=100, duration_ms=0, created_at=today,
            )

        target_date = timezone.localdate()
        from web.tasks.cleanup_usage import aggregate_usage
        aggregate_usage(target_date)

        row = APIUsageDaily.objects.get(user=None, api_type='embedding')
        assert row.total_tokens == 300
        assert row.call_count == 3


@pytest.mark.django_db
class TestDeleteOldRecords:
    """90 天前 APIUsage 删除逻辑"""

    def test_retention_boundary(self, user_profile):
        """retention_days=90 → 91 天前删，89 天前保留"""
        from web.tasks.cleanup_usage import delete_old_records

        today = timezone.now()
        old_date = today - timedelta(days=91)
        recent_date = today - timedelta(days=89)

        # auto_now_add 会覆盖 created_at，先 create 再 update
        old_record = APIUsage.objects.create(
            user=user_profile, api_type='llm', model_name='m1',
            token_count=100, duration_ms=0,
        )
        APIUsage.objects.filter(pk=old_record.pk).update(created_at=old_date)

        recent_record = APIUsage.objects.create(
            user=user_profile, api_type='llm', model_name='m1',
            token_count=100, duration_ms=0,
        )
        APIUsage.objects.filter(pk=recent_record.pk).update(created_at=recent_date)

        # cutoff = today - 90days → 91 天前的被删，89 天前的保留
        cutoff = today.date() - timedelta(days=90)
        delete_old_records(cutoff)

        # 91 天前的应该被删除
        assert not APIUsage.objects.filter(pk=old_record.pk).exists()
        # 89 天前的应该保留
        assert APIUsage.objects.filter(pk=recent_record.pk).exists()
