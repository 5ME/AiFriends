"""系统知识库批量导入 — hash 对比增量更新"""
import hashlib
import logging

from web.documents.loaders import get_loader
from web.documents.services import CustomEmbeddings, chunk_documents
from web.models.document import DocumentChunk, UserDocument

logger = logging.getLogger(__name__)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _insert_with_loader(title: str, file_path: str, file_type: str):
    """增量导入：只 embed 新增/变更的 chunk，内容不变的原地保留"""
    # 1. load + chunk
    loader = get_loader(file_type)
    new_chunks = chunk_documents(loader.load(file_path))

    # 2. get_or_create 系统文档
    sys_doc, _ = UserDocument.objects.get_or_create(
        title=title,
        defaults={'status': 'completed'}
    )

    # 3. 查询已有 chunks，按 chunk_index 索引
    old_chunks = {
        c.chunk_index: c
        for c in DocumentChunk.objects.filter(document=sys_doc)
    }
    old_indexes = set(old_chunks.keys())
    new_indexes = set(range(len(new_chunks)))

    # 4. 分类：需要 embedding 的 chunk
    to_embed = []

    for i, chunk in enumerate(new_chunks):
        new_hash = _sha256(chunk.page_content)
        old = old_chunks.get(i)
        if old and old.content_hash == new_hash:
            continue          # hash 匹配 → 保留不动
        to_embed.append((chunk, i, new_hash))

    to_remove = old_indexes - new_indexes

    # 5. 批量删除需要替换的旧 chunks
    replace_indexes = {i for _, i, _ in to_embed} & old_indexes
    if replace_indexes:
        DocumentChunk.objects.filter(
            document=sys_doc, chunk_index__in=list(replace_indexes)
        ).delete()

    # 6. 批量 embedding + 批量插入
    changed = False
    if to_embed:
        texts = [c.page_content for c, _, _ in to_embed]
        vectors = CustomEmbeddings(user_id=None).embed_documents(texts)
        objs = [
            DocumentChunk(
                content=chunk.page_content, embedding=vector,
                document=sys_doc, chunk_index=i,
                content_hash=new_hash,
                token_count=len(chunk.page_content),
                metadata=chunk.metadata,
            )
            for (chunk, i, new_hash), vector in zip(to_embed, vectors)
        ]
        DocumentChunk.objects.bulk_create(objs, batch_size=50)
        changed = True

    # 7. 删除多余的旧 chunks
    if to_remove:
        DocumentChunk.objects.filter(
            document=sys_doc, chunk_index__in=list(to_remove)
        ).delete()
        changed = True

    # 8. 仅在变更时更新 doc 元信息
    if changed:
        sys_doc.chunks_count = DocumentChunk.objects.filter(
            document=sys_doc
        ).count()
        sys_doc.save(update_fields=['chunks_count'])

    logger.info('已更新 %d 条向量记录 → %s', sys_doc.chunks_count, title)


def insert_documents():
    _insert_with_loader('百炼平台概述',
                        './web/documents/raw/Bailian_Overview.txt', 'txt')
    _insert_with_loader('百炼平台概述 Markdown',
                        './web/documents/raw/Bailian_Overview.md', 'md')
    _insert_with_loader('Claude Prompting Best Practices',
                        './web/documents/raw/claude-prompting-best-practices.md', 'md')
    _insert_with_loader('Coding Plan Overview',
                        './web/documents/raw/coding-plan-overview.md', 'md')


def insert_markdown_documents():
    _insert_with_loader('百炼平台概述 Markdown',
                        './web/documents/raw/Bailian_Overview.md', 'md')
