from django.db import models


class RetrievalTrace(models.Model):
    """每次 RAG 检索命中的 chunk 记录，用于排查和评估 RAG 质量"""
    user = models.ForeignKey(
        'UserProfile', on_delete=models.CASCADE, db_index=True,
    )
    query = models.TextField()                          # 检索 query 文本
    document = models.ForeignKey(
        'UserDocument', on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    chunk_index = models.IntegerField()                 # 命中 chunk 在文档中的序号（0-based）
    distance = models.FloatField()                      # 余弦距离（pgvector <=> 返回值）
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', '-created_at']),   # 按用户查最近 trace
            models.Index(fields=['document']),              # 按文档查被引情况
        ]
