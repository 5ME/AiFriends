"""兼容旧 import 路径，实际逻辑已迁至 services/embeddings.py"""
from web.documents.services.embeddings import CustomEmbeddings  # noqa: F401
