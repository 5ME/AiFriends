from django.db import models
from pgvector.django import VectorField


class UserDocument(models.Model):
    """用户上传的文档 / 系统知识库文档"""
    owner = models.ForeignKey(
        'UserProfile', on_delete=models.CASCADE, null=True, blank=True,
        db_index=True,
    )
    title = models.CharField(max_length=200)
    file_url = models.CharField(max_length=500, blank=True, default='')
    file_type = models.CharField(max_length=20, blank=True, default='')
    status = models.CharField(
        max_length=20,
        choices=[('pending', 'pending'), ('processing', 'processing'),
                 ('completed', 'completed'), ('failed', 'failed')],
        default='completed',
    )
    error_message = models.TextField(blank=True, default='')
    chunks_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        owner_name = self.owner.user.username if self.owner else 'system'
        return f'{self.title} - {owner_name}'


class DocumentChunk(models.Model):
    content = models.TextField()
    embedding = VectorField(dimensions=1024)
    document = models.ForeignKey(
        UserDocument, on_delete=models.CASCADE, null=True, blank=True,
    )
    owner = models.ForeignKey(
        'UserProfile', on_delete=models.CASCADE, null=True, blank=True,
    )
    chunk_index = models.IntegerField(default=0)
    token_count = models.IntegerField(default=0)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['owner']),
            models.Index(fields=['document']),
        ]

    def __str__(self):
        doc = f'Doc {self.document_id}' if self.document_id else 'no document'
        return f'Chunk {self.chunk_index} of {doc}'
