"""API Usage tracking model for cost governance"""
from django.db import models
from web.models.user import UserProfile


class APIUsage(models.Model):
    """记录每次 AI API 调用的用量和耗时。

    原始明细保留 API_USAGE_RETENTION_DAYS 天（默认 90），
    之后由 cleanup_usage_task 聚合到 APIUsageDaily 后删除。
    """
    API_TYPES = [
        ('llm', 'LLM 对话/摘要'),
        ('embedding', '文本向量化'),
        ('tts', '语音合成'),
        ('asr', '语音识别'),
    ]

    user = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE,
        null=True, blank=True,
        help_text='调用者（系统知识库处理时可为空）'
    )
    api_type = models.CharField(max_length=20, choices=API_TYPES)
    model_name = models.CharField(max_length=50)
    token_count = models.IntegerField(default=0)
    duration_ms = models.IntegerField(default=0)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['api_type', '-created_at']),
        ]


class APIUsageDaily(models.Model):
    """按天聚合的 API 用量摘要（永久保留）。

    每天凌晨由 Celery Beat 任务从 APIUsage 聚合写入。
    一条记录 = 一个用户一天一种 API 类型的汇总。
    注意: model_name 在聚合时被有意丢弃 — 日摘要仅按 api_type 汇总，同类型不同模型合并统计。
    """

    date = models.DateField()
    user = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE,
        null=True, blank=True,
    )
    api_type = models.CharField(max_length=20, choices=APIUsage.API_TYPES)
    total_tokens = models.IntegerField(default=0)
    call_count = models.IntegerField(default=0)
    total_duration_ms = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['date', 'user', 'api_type'],
                name='unique_daily_user_api',
                # PostgreSQL treats NULLs as distinct, so multiple user=NULL entries
                # for the same (date, api_type) will NOT conflict. This is the expected
                # behavior for system-level calls (knowledge base processing).
            ),
        ]
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['user', '-date']),
        ]

    def __str__(self):
        return (
            f'<APIUsageDaily date={self.date} user_id={self.user_id} '
            f'api_type={self.api_type} tokens={self.total_tokens} calls={self.call_count}>'
        )
