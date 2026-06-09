"""文档处理 Celery 异步任务"""
import logging
import os

from django.conf import settings
from openai import APIStatusError
from backend.celery import app

from web.documents.loaders import get_loader
from web.documents.services import CustomEmbeddings, chunk_documents
from web.models.document import UserDocument, DocumentChunk

logger = logging.getLogger(__name__)


@app.task(max_retries=1)
def process_document_task(doc_id: int):
    """异步处理上传文档：加载 → 切分 → embedding → 写入 chunks"""
    try:
        doc = UserDocument.objects.get(id=doc_id)
        doc.status = 'processing'
        doc.save(update_fields=['status'])
        logger.info('文档处理开始, doc_id=%d, title=%s', doc_id, doc.title)

        # 拼接完整文件路径（file_url 存的是相对路径如 documents/xxx.pdf）
        full_path = os.path.join(settings.MEDIA_ROOT, doc.file_url)

        # 1. 选 loader → list[Document]（含 page_content + metadata）
        loader = get_loader(doc.file_type)
        documents = loader.load(full_path)

        # 2. 统一切分 → 保留 metadata
        chunks = chunk_documents(documents)

        # 3. 空内容检测
        if not chunks or all(not c.page_content.strip() for c in chunks):
            doc.status = 'failed'
            doc.error_message = '文档无可提取文字，可能是扫描件或空文件'
            doc.celery_task_id = ''
            doc.save(update_fields=['status', 'error_message', 'celery_task_id'])
            logger.warning('文档无文字, doc_id=%d', doc_id)
            return

        # 4. 批量 embedding
        embeddings = CustomEmbeddings(user_id=doc.owner_id)
        texts = [c.page_content for c in chunks]
        vectors = embeddings.embed_documents(texts)

        # 5. 批量写入 DocumentChunk
        objs = [
            DocumentChunk(
                content=c.page_content, embedding=v, document=doc,
                owner=doc.owner, chunk_index=i,
                # token_count 实际存字符数（近似），精确计数需 tiktoken
                token_count=len(c.page_content),
                metadata=c.metadata,
            )
            for i, (c, v) in enumerate(zip(chunks, vectors))
        ]
        DocumentChunk.objects.bulk_create(objs, batch_size=50)

        doc.status = 'completed'
        doc.chunks_count = len(objs)
        doc.celery_task_id = ''
        doc.save(update_fields=['status', 'chunks_count', 'celery_task_id'])
        logger.info('文档处理完成, doc_id=%d, chunks=%d', doc_id, len(objs))

    except UserDocument.DoesNotExist:
        logger.warning('文档已删除，跳过处理, doc_id=%d', doc_id)
        return
    except Exception as exc:
        logger.exception('文档处理失败, doc_id=%d', doc_id)
        # 尝试更新状态为 failed（不更新 celery_task_id）
        try:
            doc.status = 'failed'
            doc.error_message = str(exc)[:500]
            doc.save(update_fields=['status', 'error_message'])
        except Exception:
            pass
        # 4xx 永久故障不重试（429 除外），清空 task_id
        # 其余重试一次，保留 task_id 以支持重试期间撤销
        if isinstance(exc, APIStatusError) and \
               400 <= exc.status_code < 500 and exc.status_code != 429:
            try:
                doc.celery_task_id = ''
                doc.save(update_fields=['celery_task_id'])
            except Exception:
                pass
            return
        raise process_document_task.retry(exc=exc, countdown=10)
