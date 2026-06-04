"""API Usage tracking model for cost governance"""
from django.db import models
from web.models.user import UserProfile


class APIUsage(models.Model):
    """记录每次 AI API 调用的用量和耗时。

    TODO: 数据积累 3-6 个月后评估清理策略（按时间分区 / 聚合到小时粒度 / 保留最近 N 天）
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
