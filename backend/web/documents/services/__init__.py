"""文档处理服务层"""
from .embeddings import CustomEmbeddings
from .chunker import chunk_documents

__all__ = ['CustomEmbeddings', 'chunk_documents']
