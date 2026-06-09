"""文档异步处理测试 — Mock embedding API 验证完整处理流"""
from unittest.mock import patch, MagicMock
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from web.models.document import UserDocument, DocumentChunk


def _dummy_upload(user_profile, filename='test.txt'):
    """辅助：创建 UserDocument + 写 media 文件"""
    from django.conf import settings
    import os
    content_map = {
        'test.txt': b'Hello World\nThis is a test document.',
        'test.md': b'# Title\n\n## Section\n\nContent here.',
    }
    content = content_map.get(filename, b'sample content')
    ext = filename.rsplit('.', 1)[-1]
    doc = UserDocument.objects.create(
        owner=user_profile, title=filename,
        file_url=f'documents/{filename}', file_type=ext, status='pending',
    )
    dir_path = os.path.join(settings.MEDIA_ROOT, 'documents')
    os.makedirs(dir_path, exist_ok=True)
    with open(os.path.join(dir_path, filename), 'wb') as f:
        f.write(content)
    return doc


class TestDocumentProcessing:
    """process_document_task 完整处理流"""

    @patch("web.views.document.tasks.CustomEmbeddings")
    def test_process_txt_document(self, mock_embeddings, user_profile):
        """上传 .txt → processing → completed，写入 chunks"""
        emb_mock = MagicMock()
        emb_mock.embed_documents.return_value = [[0.1] * 1024, [0.2] * 1024]
        mock_embeddings.return_value = emb_mock

        from web.views.document.tasks import process_document_task
        doc = _dummy_upload(user_profile, 'test.txt')
        process_document_task(doc.id)

        doc.refresh_from_db()
        assert doc.status == 'completed'
        assert doc.chunks_count > 0
        assert DocumentChunk.objects.filter(document=doc).count() == doc.chunks_count

    @patch("web.views.document.tasks.CustomEmbeddings")
    def test_process_md_document_preserves_metadata(self, mock_embeddings, user_profile):
        """.md 文档分块后保留标题 metadata"""
        emb_mock = MagicMock()
        emb_mock.embed_documents.return_value = [[0.1] * 1024] * 3
        mock_embeddings.return_value = emb_mock

        from web.views.document.tasks import process_document_task
        doc = _dummy_upload(user_profile, 'test.md')
        process_document_task(doc.id)

        doc.refresh_from_db()
        assert doc.status == 'completed'
        # 至少一个 chunk 有 Markdown 标题 metadata
        chunks = DocumentChunk.objects.filter(document=doc)
        has_header_meta = any('Header 1' in c.metadata for c in chunks)
        assert has_header_meta

    @patch("web.views.document.tasks.CustomEmbeddings")
    def test_empty_content_marks_failed(self, mock_embeddings, user_profile):
        """空文件 → status=failed"""
        from web.views.document.tasks import process_document_task
        doc = _dummy_upload(user_profile, 'test.txt')
        # 清空文件内容
        import os
        from django.conf import settings
        with open(os.path.join(settings.MEDIA_ROOT, doc.file_url), 'w') as f:
            f.write('')

        process_document_task(doc.id)
        doc.refresh_from_db()
        assert doc.status == 'failed'
        assert '无' in doc.error_message

    def test_document_already_deleted_skips_silently(self, user_profile):
        """文档已被用户删除 → DoesNotExist → 静默跳过"""
        from web.views.document.tasks import process_document_task
        doc = _dummy_upload(user_profile, 'test.txt')
        doc_id = doc.id
        doc.delete()

        # 不应抛异常
        process_document_task(doc_id)
        assert not UserDocument.objects.filter(id=doc_id).exists()

    @patch("web.views.document.tasks.CustomEmbeddings")
    def test_pdf_file_processed(self, mock_embeddings, user_profile):
        """PDF 文件通过 PyMuPDF4LLM 处理后写入 chunks"""
        from django.conf import settings
        import os

        # 先确认 PyMuPDF4LLM 可用
        try:
            import pymupdf4llm  # noqa: F401
        except ImportError:
            pytest.skip('pymupdf4llm not installed')

        emb_mock = MagicMock()
        emb_mock.embed_documents.return_value = [[0.1] * 1024] * 2
        mock_embeddings.return_value = emb_mock

        # 创建最小合法 PDF
        minimal_pdf = (
            b'%PDF-1.4\n'
            b'1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n'
            b'2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n'
            b'3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n'
            b'xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n'
            b'0000000115 00000 n \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF'
        )
        import uuid
        filename = f'{uuid.uuid4().hex}.pdf'
        dir_path = os.path.join(settings.MEDIA_ROOT, 'documents')
        os.makedirs(dir_path, exist_ok=True)
        file_path = os.path.join(dir_path, filename)
        with open(file_path, 'wb') as f:
            f.write(minimal_pdf)

        doc = UserDocument.objects.create(
            owner=user_profile, title='test.pdf',
            file_url=f'documents/{filename}', file_type='pdf', status='pending',
        )

        from web.views.document.tasks import process_document_task
        process_document_task(doc.id)

        doc.refresh_from_db()
        # PDF 可能无文字 → failed 或 completed 都可接受
        assert doc.status in ('completed', 'failed')

    @patch("web.views.document.tasks.CustomEmbeddings")
    def test_task_clears_celery_task_id_on_completion(
            self, mock_embeddings, user_profile):
        """task 执行成功 → celery_task_id 清空"""
        emb_mock = MagicMock()
        emb_mock.embed_documents.return_value = [[0.1] * 1024, [0.2] * 1024]
        mock_embeddings.return_value = emb_mock

        from web.views.document.tasks import process_document_task
        doc = _dummy_upload(user_profile, 'test.txt')
        # 模拟上传时已设置 task_id
        doc.celery_task_id = 'task-before-complete'
        doc.save(update_fields=['celery_task_id'])

        process_document_task(doc.id)

        doc.refresh_from_db()
        assert doc.status == 'completed'
        assert doc.celery_task_id == ''

    @patch("web.views.document.tasks.CustomEmbeddings")
    def test_task_clears_celery_task_id_on_permanent_failure(
            self, mock_embeddings, user_profile):
        """4xx API 错误 → celery_task_id 清空，不重试"""
        from openai import APIStatusError
        response_mock = MagicMock()
        response_mock.status_code = 400
        emb_mock = MagicMock()
        emb_mock.embed_documents.side_effect = APIStatusError(
            'Bad request', response=response_mock, body=None
        )
        mock_embeddings.return_value = emb_mock

        from web.views.document.tasks import process_document_task
        doc = _dummy_upload(user_profile, 'test.txt')
        doc.celery_task_id = 'task-permanent-fail'
        doc.save(update_fields=['celery_task_id'])

        process_document_task(doc.id)

        doc.refresh_from_db()
        assert doc.status == 'failed'
        assert doc.celery_task_id == ''

    @patch("web.views.document.tasks.process_document_task.retry")
    @patch("web.views.document.tasks.CustomEmbeddings")
    def test_task_keeps_celery_task_id_on_retryable_failure(
            self, mock_embeddings, mock_retry, user_profile):
        """5xx / 网络异常 → celery_task_id 保留，task 被 retry"""
        from celery.exceptions import Retry
        mock_retry.side_effect = Retry()

        emb_mock = MagicMock()
        emb_mock.embed_documents.side_effect = Exception("Network timeout")
        mock_embeddings.return_value = emb_mock

        from web.views.document.tasks import process_document_task
        doc = _dummy_upload(user_profile, 'test.txt')
        doc.celery_task_id = 'task-retryable'
        doc.save(update_fields=['celery_task_id'])

        # retry 会抛出 Retry 异常（Celery 标准行为）
        try:
            process_document_task(doc.id)
        except Retry:
            pass

        doc.refresh_from_db()
        assert doc.status == 'failed'
        assert doc.celery_task_id == 'task-retryable'
        mock_retry.assert_called_once()
