"""API usage recording utility"""
import logging

from web.utils.quota import API_TYPE_TO_FIELD

logger = logging.getLogger(__name__)


def record_api_usage(*, user_id, api_type, model_name,
                     token_count=0, duration_ms=0,
                     success=True, error_message='',
                     update_quota=True,
                     quota_deduct=None):
    """记录 AI API 调用用量 + 更新用户每日配额。

    update_quota=False 用于系统功能（如 Memory Agent），
    用量仍写入 APIUsage 但跳过配额更新。
    quota_deduct 用于扣除 LLM 系统 overhead（不传则默认 = token_count）。
    """
    try:
        from web.models.usage import APIUsage
        APIUsage.objects.create(
            user_id=user_id,
            api_type=api_type,
            model_name=model_name,
            token_count=token_count,
            duration_ms=duration_ms,
            success=success,
            error_message=error_message,
        )
    except Exception:
        logger.exception('APIUsage 写入失败: user=%s, type=%s', user_id, api_type)
        return

    if not (update_quota and user_id is not None):
        return

    try:
        deduct = quota_deduct if quota_deduct is not None else token_count
        _update_quota(user_id, api_type, deduct)
    except Exception:
        logger.exception('UserQuota 更新失败: user=%s, type=%s', user_id, api_type)


def _update_quota(user_id, api_type, deduct):
    from django.db.models import F
    from django.utils import timezone
    from web.models.quota import UserQuota

    quota_value = _quota_value(api_type, deduct)
    field_name = API_TYPE_TO_FIELD[api_type]

    quota, _ = UserQuota.objects.get_or_create(
        user_id=user_id,
        date=timezone.localdate(),
        defaults={
            'llm_tokens_used': 0,
            'tts_chars_used': 0,
            'asr_seconds_used': 0,
            'embedding_tokens_used': 0,
        },
    )
    UserQuota.objects.filter(pk=quota.pk).update(
        **{field_name: F(field_name) + quota_value}
    )


def _quota_value(api_type, token_count):
    """ASR 配额值转换：采样点 → 秒"""
    if api_type == 'asr':
        return max(token_count // 16000, 1)
    return token_count
