from django.db import models
from pgvector.django import VectorField


class DocumentChunk(models.Model):
    content = models.TextField()
    embedding = VectorField(dimensions=1024)
    created_at = models.DateTimeField(auto_now_add=True)
