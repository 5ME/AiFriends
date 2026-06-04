"""API usage recording utility"""
import logging

logger = logging.getLogger(__name__)


def record_api_usage(*, user_id, api_type, model_name,
                     token_count=0, duration_ms=0,
                     success=True, error_message=''):
    """记录 AI API 调用用量。写入失败不抛异常。"""
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
