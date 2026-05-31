"""系统知识库批量导入 — 使用 loader + chunker 消除重复代码"""
import logging

from web.documents.loaders import get_loader
from web.documents.services import CustomEmbeddings, chunk_documents
from web.models.document import DocumentChunk, UserDocument

logger = logging.getLogger(__name__)


def _insert_with_loader(title: str, file_path: str, file_type: str):
    """通用导入逻辑：get_or_create → load → chunk → embed → bulk_create"""
    loader = get_loader(file_type)
    documents = loader.load(file_path)
    chunks = chunk_documents(documents)

    sys_doc, _ = UserDocument.objects.get_or_create(
        title=title,
        defaults={'status': 'completed'}
    )
    DocumentChunk.objects.filter(document=sys_doc).delete()

    embeddings = CustomEmbeddings()
    texts = [c.page_content for c in chunks]
    vectors = embeddings.embed_documents(texts)

    objs = [
        DocumentChunk(
            content=c.page_content, embedding=v,
            document=sys_doc, chunk_index=i,
            # token_count 实际存字符数（近似），非精确 token 数
            token_count=len(c.page_content),
            metadata=c.metadata,
        )
        for i, (c, v) in enumerate(zip(chunks, vectors))
    ]
    DocumentChunk.objects.bulk_create(objs, batch_size=50)

    sys_doc.chunks_count = len(objs)
    sys_doc.save()
    logger.info('已插入 %d 条向量记录 → %s', len(objs), title)


def insert_documents():
    _insert_with_loader('百炼平台概述',
                        './web/documents/raw/Bailian_Overview.txt', 'txt')


def insert_markdown_documents():
    _insert_with_loader('百炼平台概述 Markdown',
                        './web/documents/raw/Bailian_Overview.md', 'md')
