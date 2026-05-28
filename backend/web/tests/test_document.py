import pytest
from unittest.mock import patch, MagicMock
from web.models.document import UserDocument, DocumentChunk


class TestUserDocument:
    """UserDocument 模型基本操作"""

    def test_create_system_document(self, db):
        """owner=null 表示系统文档"""
        doc = UserDocument.objects.create(title='测试文档')
        assert doc.owner is None
        assert doc.status == 'completed'

    def test_create_user_document(self, user_profile):
        """owner 指向用户"""
        doc = UserDocument.objects.create(title='我的文档', owner=user_profile)
        assert doc.owner == user_profile

    def test_get_or_create_idempotent(self, db):
        """重复调用不产生重复记录"""
        doc1, created1 = UserDocument.objects.get_or_create(
            title='幂等测试', defaults={'status': 'completed'}
        )
        assert created1 is True

        doc2, created2 = UserDocument.objects.get_or_create(
            title='幂等测试', defaults={'status': 'completed'}
        )
        assert created2 is False
        assert doc1.id == doc2.id
        assert UserDocument.objects.filter(title='幂等测试').count() == 1


class TestDocumentChunkMetadata:
    """DocumentChunk 新字段"""

    def test_chunk_belongs_to_document(self, db):
        """document FK 关联文档"""
        doc = UserDocument.objects.create(title='测试')
        chunk = DocumentChunk.objects.create(
            content='hello', embedding=[0.0] * 1024, document=doc, chunk_index=0
        )
        assert chunk.document == doc
        assert chunk.chunk_index == 0

    def test_chunk_belongs_to_user(self, user_profile):
        """owner FK 关联用户"""
        chunk = DocumentChunk.objects.create(
            content='我的内容', embedding=[0.0] * 1024,
            owner=user_profile, chunk_index=0,
        )
        assert chunk.owner == user_profile

    def test_chunk_metadata_json(self, db):
        """metadata JSON 字段可存储扩展信息"""
        chunk = DocumentChunk.objects.create(
            content='test', embedding=[0.0] * 1024,
            metadata={'header': '第一章', 'source_page': 5},
        )
        chunk.refresh_from_db()
        assert chunk.metadata['header'] == '第一章'


class TestOwnerFiltering:
    """owner 过滤查询验证"""

    def test_global_chunks_have_null_owner(self, db):
        """全局知识库 chunks owner 为 null"""
        chunk = DocumentChunk.objects.create(
            content='global', embedding=[0.0] * 1024,
        )
        assert chunk.owner is None

    def test_filter_by_owner(self, user_profile):
        """按 owner 过滤个人 chunks"""
        DocumentChunk.objects.create(
            content='user chunk', embedding=[0.1] * 1024,
            owner=user_profile,
        )
        DocumentChunk.objects.create(
            content='global chunk', embedding=[0.2] * 1024,
            owner=None,
        )
        user_chunks = DocumentChunk.objects.filter(owner=user_profile)
        globals_ = DocumentChunk.objects.filter(owner__isnull=True)
        assert user_chunks.count() == 1
        assert globals_.count() == 1

    def test_mixed_recall(self, user_profile):
        """owner IS NULL OR owner = user_id 同时召回全局和个人"""
        DocumentChunk.objects.create(
            content='user', embedding=[0.3] * 1024, owner=user_profile
        )
        DocumentChunk.objects.create(
            content='global', embedding=[0.4] * 1024, owner=None
        )
        from django.db.models import Q
        mixed = DocumentChunk.objects.filter(
            Q(owner__isnull=True) | Q(owner=user_profile)
        )
        assert mixed.count() == 2


class TestInsertDocuments:
    """insert_documents 幂等性和隔离性"""

    @patch("web.documents.utils.insert_documents.CustomEmbeddings")
    def test_insert_documents_idempotent(self, mock_embeddings_class, db):
        from web.documents.utils.insert_documents import insert_documents
        from web.models.document import UserDocument, DocumentChunk

        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.0] * 1024
        mock_embeddings_class.return_value = mock_embeddings

        insert_documents()
        chunk_count_1 = DocumentChunk.objects.filter(
            document__title='百炼平台概述'
        ).count()
        assert chunk_count_1 > 0

        insert_documents()
        chunk_count_2 = DocumentChunk.objects.filter(
            document__title='百炼平台概述'
        ).count()
        assert chunk_count_2 == chunk_count_1
        assert UserDocument.objects.filter(title='百炼平台概述').count() == 1

    @patch("web.documents.utils.insert_documents.CustomEmbeddings")
    def test_insert_markdown_documents_idempotent(self, mock_embeddings_class, db):
        from web.documents.utils.insert_documents import insert_markdown_documents
        from web.models.document import UserDocument, DocumentChunk

        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.0] * 1024
        mock_embeddings_class.return_value = mock_embeddings

        insert_markdown_documents()
        count_1 = DocumentChunk.objects.filter(
            document__title='百炼平台概述 Markdown'
        ).count()
        assert count_1 > 0

        insert_markdown_documents()
        count_2 = DocumentChunk.objects.filter(
            document__title='百炼平台概述 Markdown'
        ).count()
        assert count_2 == count_1

    def test_delete_only_own_chunks(self, db):
        """insert_documents 只删自己文档的 chunks"""
        from web.documents.utils.insert_documents import insert_documents
        from web.models.document import UserDocument, DocumentChunk

        other_doc = UserDocument.objects.create(title='other', status='completed')
        DocumentChunk.objects.create(
            content='keep me', embedding=[0.0] * 1024,
            document=other_doc,
        )

        with patch("web.documents.utils.insert_documents.CustomEmbeddings") as mock_class:
            mock_embeddings = MagicMock()
            mock_embeddings.embed_query.return_value = [0.0] * 1024
            mock_class.return_value = mock_embeddings

            insert_documents()

        own_count = DocumentChunk.objects.filter(
            document__title='百炼平台概述'
        ).count()
        assert own_count > 0

        other_count = DocumentChunk.objects.filter(
            document=other_doc
        ).count()
        assert other_count == 1
        assert DocumentChunk.objects.get(document=other_doc).content == 'keep me'
