import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
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
        mock_embeddings.embed_documents.side_effect = \
            lambda texts: [[0.0] * 1024 for _ in texts]
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
        # 验证至少调用过一次（4 个文档各 1 次，第二次执行 hash 匹配不再调）
        assert mock_embeddings.embed_documents.call_count >= 1

    @patch("web.documents.utils.insert_documents.CustomEmbeddings")
    def test_insert_markdown_documents_idempotent(self, mock_embeddings_class, db):
        from web.documents.utils.insert_documents import insert_markdown_documents
        from web.models.document import UserDocument, DocumentChunk

        mock_embeddings = MagicMock()
        mock_embeddings.embed_documents.side_effect = \
            lambda texts: [[0.0] * 1024 for _ in texts]
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
        # 验证至少调用过一次
        assert mock_embeddings.embed_documents.call_count >= 1

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
            mock_embeddings.embed_documents.side_effect = \
                lambda texts: [[0.0] * 1024 for _ in texts]
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
        # 验证 content_hash 已设置
        own_chunks = DocumentChunk.objects.filter(document__title='百炼平台概述')
        for c in own_chunks:
            assert c.content_hash != ''
            assert len(c.content_hash) == 64

    @patch("web.documents.utils.insert_documents.CustomEmbeddings")
    def test_repeat_insert_skips_embedding(self, mock_embeddings_class, db):
        """重复导入且内容不变 → 不调用 embedding API"""
        from web.documents.utils.insert_documents import insert_documents

        mock_embeddings = MagicMock()
        mock_embeddings.embed_documents.side_effect = \
            lambda texts: [[0.0] * 1024 for _ in texts]
        mock_embeddings_class.return_value = mock_embeddings

        insert_documents()
        # 重置 mock，第二次执行
        mock_embeddings.embed_documents.reset_mock()
        insert_documents()

        # 第二次执行不应调用 embedding
        mock_embeddings.embed_documents.assert_not_called()

    @patch("web.documents.utils.insert_documents.CustomEmbeddings")
    def test_new_document_is_imported(self, mock_embeddings_class, db):
        """新增 raw 文件的文档 → 正常导入"""
        from web.documents.utils.insert_documents import insert_documents
        from web.models.document import DocumentChunk

        mock_embeddings = MagicMock()
        mock_embeddings.embed_documents.side_effect = \
            lambda texts: [[0.0] * 1024 for _ in texts]
        mock_embeddings_class.return_value = mock_embeddings

        insert_documents()

        # 新增的 claude-prompting-best-practices.md 应被导入
        count = DocumentChunk.objects.filter(
            document__title='Claude Prompting Best Practices'
        ).count()
        assert count > 0

        # coding-plan-overview.md 也应被导入
        count2 = DocumentChunk.objects.filter(
            document__title='Coding Plan Overview'
        ).count()
        assert count2 > 0

    @patch("web.documents.utils.insert_documents.CustomEmbeddings")
    def test_extra_chunks_are_removed(self, mock_embeddings_class, db):
        """旧 chunks 中有新文件不存在的 index → 被删除"""
        from web.documents.utils.insert_documents import insert_documents
        from web.models.document import UserDocument, DocumentChunk

        # 手动创建多余的旧 chunk（index=99 不在新文件中）
        sys_doc, _ = UserDocument.objects.get_or_create(
            title='百炼平台概述', defaults={'status': 'completed'}
        )
        DocumentChunk.objects.create(
            content='extra chunk', embedding=[0.0] * 1024,
            document=sys_doc, chunk_index=99,
            content_hash='abc123',
        )
        assert DocumentChunk.objects.filter(
            document=sys_doc, chunk_index=99
        ).exists()

        mock_embeddings = MagicMock()
        mock_embeddings.embed_documents.side_effect = \
            lambda texts: [[0.0] * 1024 for _ in texts]
        mock_embeddings_class.return_value = mock_embeddings

        insert_documents()

        # 多余的 chunk_index=99 应被删除
        assert not DocumentChunk.objects.filter(
            document=sys_doc, chunk_index=99
        ).exists()

    @patch("web.documents.utils.insert_documents.CustomEmbeddings")
    def test_historical_empty_hash_triggers_reembed(self, mock_embeddings_class, db):
        """content_hash='' 的历史数据 → 触发重新 embedding"""
        from web.documents.utils.insert_documents import insert_documents
        from web.models.document import UserDocument, DocumentChunk

        # 手动创建旧格式数据（content_hash=''）
        sys_doc, _ = UserDocument.objects.get_or_create(
            title='百炼平台概述', defaults={'status': 'completed'}
        )
        DocumentChunk.objects.create(
            content='stale content', embedding=[0.0] * 1024,
            document=sys_doc, chunk_index=0,
            content_hash='',  # 旧数据无 hash
        )

        mock_embeddings = MagicMock()
        mock_embeddings.embed_documents.side_effect = \
            lambda texts: [[0.1] * 1024 for _ in texts]
        mock_embeddings_class.return_value = mock_embeddings

        insert_documents()

        # 旧 chunk 应被替换，hash 应更新为非空
        chunks = DocumentChunk.objects.filter(document=sys_doc)
        for c in chunks:
            assert c.content_hash != ''
            assert len(c.content_hash) == 64


class TestDocumentUpload:
    """POST /api/document/upload/ 上传校验"""

    def test_upload_requires_auth(self, api_client):
        """未登录 → 401"""
        file = SimpleUploadedFile('test.txt', b'hello', content_type='text/plain')
        resp = api_client.post('/api/document/upload/', {'file': file})
        assert resp.status_code == 401

    def test_upload_no_file_returns_400(self, auth_client):
        """不传 file → 400"""
        resp = auth_client.post('/api/document/upload/', {})
        assert resp.status_code == 400
        assert '请选择文件' in resp.data['message']

    def test_upload_empty_file_returns_400(self, auth_client):
        """空文件 → 400"""
        file = SimpleUploadedFile('test.txt', b'', content_type='text/plain')
        resp = auth_client.post('/api/document/upload/', {'file': file})
        assert resp.status_code == 400

    def test_upload_oversized_file_returns_400(self, auth_client):
        """超大文件 → 400"""
        content = b'x' * (10 * 1024 * 1024 + 1)  # 10MB + 1B
        file = SimpleUploadedFile('big.txt', content, content_type='text/plain')
        resp = auth_client.post('/api/document/upload/', {'file': file})
        assert resp.status_code == 400

    def test_upload_bad_extension_returns_400(self, auth_client):
        """不支持的文件类型 → 400"""
        file = SimpleUploadedFile('test.exe', b'test', content_type='application/octet-stream')
        resp = auth_client.post('/api/document/upload/', {'file': file})
        assert resp.status_code == 400

    def test_upload_magic_bytes_mismatch_returns_400(self, auth_client):
        """文件头魔数与扩展名不匹配 → 400（.exe 伪装 .pdf）"""
        file = SimpleUploadedFile('fake.pdf', b'MZ\x90\x00test',
                                  content_type='application/pdf')
        resp = auth_client.post('/api/document/upload/', {'file': file})
        assert resp.status_code == 400

    @patch("web.views.document.upload.process_document_task.delay")
    def test_upload_txt_success(self, mock_delay, auth_client, user_profile):
        """正常上传 .txt"""
        mock_delay.return_value.id = 'test-task-id'
        file = SimpleUploadedFile('hello.txt', b'Hello World',
                                  content_type='text/plain')
        resp = auth_client.post('/api/document/upload/', {'file': file})
        assert resp.status_code == 201
        assert resp.data['status'] == 'pending'
        # 验证 UserDocument 已创建
        from web.models.document import UserDocument
        doc = UserDocument.objects.get(id=resp.data['id'])
        assert doc.owner == user_profile
        assert doc.file_type == 'txt'
        assert doc.title == 'hello.txt'
        # 验证 Celery 任务已被触发
        mock_delay.assert_called_once_with(doc.id)

    @patch("web.views.document.upload.process_document_task.delay")
    def test_upload_enqueue_failure(self, mock_delay, auth_client):
        """delay() 抛异常 → doc 标记 failed，返回 500"""
        mock_delay.side_effect = Exception("Broker connection error")
        file = SimpleUploadedFile('test.txt', b'Hello', content_type='text/plain')
        resp = auth_client.post('/api/document/upload/', {'file': file})
        assert resp.status_code == 500
        assert '处理启动失败' in resp.data['message']
        doc = UserDocument.objects.latest('id')
        assert doc.status == 'failed'
        assert '任务投递失败' in doc.error_message

    @patch("web.views.document.upload.process_document_task.delay")
    def test_upload_saves_celery_task_id(self, mock_delay, auth_client):
        """正常上传 → celery_task_id 非空"""
        mock_result = MagicMock()
        mock_result.id = 'test-task-uuid-123'
        mock_delay.return_value = mock_result
        file = SimpleUploadedFile('hello.txt', b'Hello World',
                                  content_type='text/plain')
        resp = auth_client.post('/api/document/upload/', {'file': file})
        assert resp.status_code == 201
        doc = UserDocument.objects.get(id=resp.data['id'])
        assert doc.celery_task_id == 'test-task-uuid-123'


class TestDocumentRemove:
    """POST /api/document/remove/ 删除文档"""

    def test_remove_requires_auth(self, api_client):
        """未登录 → 401"""
        resp = api_client.post('/api/document/remove/', {'id': 1})
        assert resp.status_code == 401

    def test_remove_own_document(self, auth_client, user_profile):
        """删除自己的文档 → 200，级联删除 chunks"""
        from web.models.document import UserDocument, DocumentChunk
        doc = UserDocument.objects.create(title='to-delete', owner=user_profile,
                                          status='completed')
        DocumentChunk.objects.create(content='chunk', embedding=[0.0] * 1024,
                                     document=doc, chunk_index=0)
        resp = auth_client.post('/api/document/remove/', {'id': doc.id})
        assert resp.status_code == 200
        assert not UserDocument.objects.filter(id=doc.id).exists()
        assert not DocumentChunk.objects.filter(document_id=doc.id).exists()

    def test_remove_other_user_document(self, auth_client, other_user):
        """不能删除别人的文档 → 404"""
        from web.models.document import UserDocument
        doc = UserDocument.objects.create(
            title='theirs', owner=other_user.userprofile, status='completed')
        resp = auth_client.post('/api/document/remove/', {'id': doc.id})
        assert resp.status_code == 404

    def test_remove_nonexistent_returns_404(self, auth_client):
        """删除不存在的文档 → 404"""
        resp = auth_client.post('/api/document/remove/', {'id': 99999})
        assert resp.status_code == 404

    @patch("web.views.document.remove.app.control.revoke")
    def test_delete_pending_doc_revokes_task(self, mock_revoke, auth_client,
                                              user_profile):
        """删除 pending 文档 → revoke 被调用"""
        doc = UserDocument.objects.create(
            title='pending-doc', owner=user_profile, status='pending',
            celery_task_id='task-pending-123',
        )
        resp = auth_client.post('/api/document/remove/', {'id': doc.id})
        assert resp.status_code == 200
        mock_revoke.assert_called_once_with('task-pending-123')
        assert not UserDocument.objects.filter(id=doc.id).exists()

    @patch("web.views.document.remove.app.control.revoke")
    def test_delete_processing_doc_revokes_task(self, mock_revoke, auth_client,
                                                 user_profile):
        """删除 processing 文档 → revoke 被调用"""
        doc = UserDocument.objects.create(
            title='processing-doc', owner=user_profile, status='processing',
            celery_task_id='task-processing-456',
        )
        resp = auth_client.post('/api/document/remove/', {'id': doc.id})
        assert resp.status_code == 200
        mock_revoke.assert_called_once_with('task-processing-456')
        assert not UserDocument.objects.filter(id=doc.id).exists()

    @patch("web.views.document.remove.app.control.revoke")
    def test_delete_completed_doc_skips_revoke(self, mock_revoke, auth_client,
                                                user_profile):
        """删除 completed 文档（task_id 为空）→ revoke 不调用"""
        doc = UserDocument.objects.create(
            title='completed-doc', owner=user_profile, status='completed',
            celery_task_id='',
        )
        resp = auth_client.post('/api/document/remove/', {'id': doc.id})
        assert resp.status_code == 200
        mock_revoke.assert_not_called()
        assert not UserDocument.objects.filter(id=doc.id).exists()

    @patch("web.views.document.remove.app.control.revoke")
    def test_delete_during_retry_revokes_task(self, mock_revoke, auth_client,
                                               user_profile):
        """task 失败重试中（status=failed + task_id 非空）→ revoke 被调用"""
        doc = UserDocument.objects.create(
            title='retrying-doc', owner=user_profile, status='failed',
            celery_task_id='task-retrying-123',
        )
        resp = auth_client.post('/api/document/remove/', {'id': doc.id})
        assert resp.status_code == 200
        mock_revoke.assert_called_once_with('task-retrying-123')
        assert not UserDocument.objects.filter(id=doc.id).exists()

    @patch("web.views.document.remove.app.control.revoke")
    def test_revoke_failure_does_not_block_delete(self, mock_revoke, auth_client,
                                                   user_profile):
        """revoke 抛异常 → 删除仍成功"""
        mock_revoke.side_effect = Exception("Revoke failed")
        doc = UserDocument.objects.create(
            title='revoke-fail-doc', owner=user_profile, status='pending',
            celery_task_id='task-revoke-fail',
        )
        resp = auth_client.post('/api/document/remove/', {'id': doc.id})
        assert resp.status_code == 200
        assert not UserDocument.objects.filter(id=doc.id).exists()


class TestDocumentList:
    """GET /api/document/list/ 文档列表"""

    def test_list_requires_auth(self, api_client):
        """未登录 → 401"""
        resp = api_client.get('/api/document/list/')
        assert resp.status_code == 401

    def test_list_empty(self, auth_client):
        """无文档时返回空列表"""
        resp = auth_client.get('/api/document/list/')
        assert resp.status_code == 200
        assert resp.data['documents'] == []

    def test_list_only_own_documents(self, auth_client, user_profile, other_user):
        """只能看到自己的文档"""
        from web.models.document import UserDocument
        UserDocument.objects.create(title='mine', owner=user_profile,
                                    status='completed')
        UserDocument.objects.create(title='theirs', owner=other_user.userprofile,
                                    status='completed')
        resp = auth_client.get('/api/document/list/')
        assert resp.status_code == 200
        assert len(resp.data['documents']) == 1
        assert resp.data['documents'][0]['title'] == 'mine'

    def test_list_ordered_by_created_desc(self, auth_client, user_profile):
        """按创建时间倒序"""
        from web.models.document import UserDocument
        d1 = UserDocument.objects.create(title='older', owner=user_profile,
                                          status='completed')
        d2 = UserDocument.objects.create(title='newer', owner=user_profile,
                                          status='completed')
        resp = auth_client.get('/api/document/list/')
        titles = [d['title'] for d in resp.data['documents']]
        assert titles == ['newer', 'older']  # DESC
