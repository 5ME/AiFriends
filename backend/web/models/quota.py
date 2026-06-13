"""User daily API quota model"""
from django.db import models
from web.models.user import UserProfile


class UserQuota(models.Model):
    """用户每日 API 配额消耗记录。

    同一用户同一天只有一行 — unique_together('user', 'date') 保证。
    四种 API 独立计数，互不影响。
    """
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    date = models.DateField()

    llm_tokens_used = models.IntegerField(default=0)
    tts_chars_used = models.IntegerField(default=0)
    asr_seconds_used = models.IntegerField(default=0)
    embedding_tokens_used = models.IntegerField(default=0)

    class Meta:
        unique_together = ('user', 'date')
