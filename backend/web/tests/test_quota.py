"""Tests for check_quota, record_api_usage quota update, and UserQuota model"""
import time
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone

from web.models.quota import UserQuota
from web.utils.quota import check_quota
from web.utils.usage import record_api_usage


@pytest.mark.django_db
class TestCheckQuota:
    """check_quota() 函数测试"""

    def test_under_limit_returns_allowed(self, user_profile):
        """配额未超 → allowed=True"""
        allowed, cur, limit = check_quota(user_profile.id, 'llm')
        assert allowed is True
        assert cur == 0
        assert limit == 10_000

    def test_over_limit_returns_denied(self, user_profile):
        """配额已超 → allowed=False"""
        today = timezone.localdate()
        UserQuota.objects.create(
            user=user_profile, date=today,
            llm_tokens_used=10_000,
        )
        allowed, cur, limit = check_quota(user_profile.id, 'llm')
        assert allowed is False
        assert cur == 10_000
        assert limit == 10_000

    def test_different_api_types_independent(self, user_profile):
        """不同 API 类型独立计数"""
        today = timezone.localdate()
        UserQuota.objects.create(
            user=user_profile, date=today,
            llm_tokens_used=10_000,  # LLM 已满
            tts_chars_used=0,
        )
        # LLM 超限
        assert check_quota(user_profile.id, 'llm')[0] is False
        # TTS 仍然可用
        assert check_quota(user_profile.id, 'tts')[0] is True

    def test_no_quota_row_means_zero(self, user_profile):
        """没有记录 → current=0"""
        allowed, cur, _ = check_quota(user_profile.id, 'embedding')
        assert allowed is True
        assert cur == 0

    def test_cross_day_isolation(self, user_profile):
        """跨天配额隔离"""
        today = timezone.localdate()
        UserQuota.objects.create(
            user=user_profile, date=today,
            llm_tokens_used=10_000,
        )
        # 今天超限
        assert check_quota(user_profile.id, 'llm')[0] is False
        # 模拟明天：新日期无记录 → 从 0 开始
        with patch.object(timezone, 'localdate', return_value=today + timedelta(days=1)):
            assert check_quota(user_profile.id, 'llm')[0] is True

    @override_settings(QUOTA_LLM_TOKENS_PER_DAY=0)
    def test_zero_limit_means_disabled(self, user_profile):
        """限额=0 → API 禁用"""
        allowed, cur, limit = check_quota(user_profile.id, 'llm')
        assert allowed is False
        assert limit == 0


@pytest.mark.django_db
class TestRecordApiUsageQuota:
    """record_api_usage 配额更新测试"""

    def test_updates_quota_on_first_call(self, user_profile):
        """首次调用创建配额行并递增"""
        record_api_usage(
            user_id=user_profile.id, api_type='llm',
            model_name='deepseek-v4-flash', token_count=500,
        )
        today = timezone.localdate()
        quota = UserQuota.objects.get(user=user_profile, date=today)
        assert quota.llm_tokens_used == 500

    def test_updates_quota_on_second_call(self, user_profile):
        """第二次调用原子递增"""
        today = timezone.localdate()
        UserQuota.objects.create(
            user=user_profile, date=today, llm_tokens_used=300,
        )
        record_api_usage(
            user_id=user_profile.id, api_type='llm',
            model_name='deepseek-v4-flash', token_count=200,
        )
        quota = UserQuota.objects.get(user=user_profile, date=today)
        assert quota.llm_tokens_used == 500

    def test_update_quota_false_skips_quota(self, user_profile):
        """update_quota=False → APIUsage 写入但配额不更新"""
        record_api_usage(
            user_id=user_profile.id, api_type='llm',
            model_name='deepseek-v4-flash', token_count=500,
            update_quota=False,
        )
        assert not UserQuota.objects.filter(user=user_profile).exists()

    def test_user_none_skips_quota(self):
        """user_id=None → 跳过配额更新"""
        record_api_usage(
            user_id=None, api_type='llm',
            model_name='deepseek-v4-flash', token_count=500,
        )
        assert not UserQuota.objects.exists()

    def test_asr_converts_samples_to_seconds(self, user_profile):
        """ASR 采样点 → 秒转换"""
        record_api_usage(
            user_id=user_profile.id, api_type='asr',
            model_name='gummy-realtime-v1',
            token_count=16000 * 3,  # 3 秒的采样点
        )
        today = timezone.localdate()
        quota = UserQuota.objects.get(user=user_profile, date=today)
        assert quota.asr_seconds_used == 3

    def test_asr_minimum_one_second(self, user_profile):
        """ASR 不足 1 秒按 1 秒计"""
        record_api_usage(
            user_id=user_profile.id, api_type='asr',
            model_name='gummy-realtime-v1',
            token_count=100,  # < 16000 采样点
        )
        quota = UserQuota.objects.get(user=user_profile, date=timezone.localdate())
        assert quota.asr_seconds_used == 1

    def test_different_users_isolated(self, user_profile):
        """不同用户配额隔离"""
        from django.contrib.auth.models import User
        other_user = User.objects.create_user(username='quota_test_other')
        from web.models.user import UserProfile
        other_profile = UserProfile.objects.create(user=other_user)

        record_api_usage(
            user_id=user_profile.id, api_type='llm',
            model_name='deepseek-v4-flash', token_count=100,
        )
        record_api_usage(
            user_id=other_profile.id, api_type='llm',
            model_name='deepseek-v4-flash', token_count=200,
        )
        assert UserQuota.objects.get(user=user_profile).llm_tokens_used == 100
        assert UserQuota.objects.get(user=other_profile).llm_tokens_used == 200

    def test_quota_deduct_uses_given_value(self, user_profile):
        """quota_deduct 参数 → 配额扣除传入值而非 token_count"""
        record_api_usage(
            user_id=user_profile.id, api_type='llm',
            model_name='deepseek-v4-flash',
            token_count=500,      # API 记录完整值
            quota_deduct=200,     # 配额只扣 200（模拟 overhead 扣除后）
        )
        today = timezone.localdate()
        quota = UserQuota.objects.get(user=user_profile, date=today)
        assert quota.llm_tokens_used == 200

    def test_quota_deduct_none_uses_token_count(self, user_profile):
        """quota_deduct=None → 配额默认使用 token_count"""
        record_api_usage(
            user_id=user_profile.id, api_type='llm',
            model_name='deepseek-v4-flash',
            token_count=300,
            # quota_deduct 不传
        )
        quota = UserQuota.objects.get(user=user_profile, date=timezone.localdate())
        assert quota.llm_tokens_used == 300


@pytest.mark.django_db
class TestUserQuotaModel:
    """UserQuota 模型测试"""

    def test_unique_user_date(self, user_profile):
        """同一用户同一天不能有两行"""
        today = timezone.localdate()
        UserQuota.objects.create(user=user_profile, date=today)
        with pytest.raises(Exception):
            UserQuota.objects.create(user=user_profile, date=today)

    def test_defaults_are_zero(self, user_profile):
        """新建记录的 consumed 字段默认为 0"""
        today = timezone.localdate()
        quota = UserQuota.objects.create(user=user_profile, date=today)
        assert quota.llm_tokens_used == 0
        assert quota.tts_chars_used == 0
        assert quota.asr_seconds_used == 0
        assert quota.embedding_tokens_used == 0
