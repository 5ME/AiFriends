import logging
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter

from web.documents.utils.custom_embeddings import CustomEmbeddings
from web.models.document import DocumentChunk, UserDocument

logger = logging.getLogger(__name__)


def insert_documents():
    loader = TextLoader('./web/documents/Bailian_Overview.txt', encoding='utf-8')
    docs = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = text_splitter.split_documents(docs)
    logger.info('已切分成 %d 个片段', len(chunks))

    embeddings = CustomEmbeddings()

    # 使用 UserDocument 管理文档，保证多次执行不会产生重复记录
    sys_doc, _ = UserDocument.objects.get_or_create(
        title='百炼平台概述',
        defaults={'status': 'completed'}
    )
    DocumentChunk.objects.filter(document=sys_doc).delete()
    for i, chunk in enumerate(chunks):
        emb = embeddings.embed_query(chunk.page_content)
        DocumentChunk.objects.create(
            content=chunk.page_content, embedding=emb,
            document=sys_doc, owner=None, chunk_index=i,
        )
    sys_doc.chunks_count = len(chunks)
    sys_doc.save()

    logger.info('已插入 %d 条向量记录', len(chunks))

def insert_markdown_documents():
    loader = TextLoader('./web/documents/Bailian_Overview.md', encoding='utf-8')
    docs = loader.load()

    # 2. 先按标题切分
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]
    md_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=False
    )
    # docs 是 List[Document]
    md_chunks = []
    for doc in docs:
        md_chunks.extend(md_splitter.split_text(doc.page_content))

    # 3. 再按长度切分
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50
    )
    final_chunks = text_splitter.split_documents(md_chunks)

    embeddings = CustomEmbeddings()

    # 使用 UserDocument 管理文档，保证多次执行不会产生重复记录
    sys_doc, _ = UserDocument.objects.get_or_create(
        title='百炼平台概述 Markdown',
        defaults={'status': 'completed'}
    )
    DocumentChunk.objects.filter(document=sys_doc).delete()
    for i, chunk in enumerate(final_chunks):
        emb = embeddings.embed_query(chunk.page_content)
        DocumentChunk.objects.create(
            content=chunk.page_content, embedding=emb,
            document=sys_doc, owner=None, chunk_index=i,
        )
    sys_doc.chunks_count = len(final_chunks)
    sys_doc.save()

    logger.info('已插入 %d 条向量记录', len(final_chunks))
