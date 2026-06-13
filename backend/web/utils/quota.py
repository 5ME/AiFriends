"""User daily quota checking utility"""
from django.conf import settings
from django.utils import timezone

API_TYPE_TO_FIELD = {
    'llm':       'llm_tokens_used',
    'tts':       'tts_chars_used',
    'asr':       'asr_seconds_used',
    'embedding': 'embedding_tokens_used',
}

API_TYPE_TO_SETTING = {
    'llm':       'QUOTA_LLM_TOKENS_PER_DAY',
    'tts':       'QUOTA_TTS_CHARS_PER_DAY',
    'asr':       'QUOTA_ASR_SECONDS_PER_DAY',
    'embedding': 'QUOTA_EMBEDDING_TOKENS_PER_DAY',
}


def check_quota(user_id: int, api_type: str):
    """检查用户今日 API 配额是否超限。

    Args:
        user_id: UserProfile.id
        api_type: 'llm' | 'tts' | 'asr' | 'embedding'

    Returns:
        (allowed, current_usage, limit)
        - allowed: True 表示未超限
        - current_usage: 今日已用量
        - limit: 今日限额（0 表示该 API 被禁用）
    """
    from web.models.quota import UserQuota

    limit = getattr(settings, API_TYPE_TO_SETTING[api_type], 0)
    if limit == 0:
        return (False, 0, 0)

    field_name = API_TYPE_TO_FIELD[api_type]
    today = timezone.localdate()

    quota = UserQuota.objects.filter(user_id=user_id, date=today).first()
    current = getattr(quota, field_name, 0) if quota else 0

    return (current < limit, current, limit)
