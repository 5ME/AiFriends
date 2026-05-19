import logging
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from web.documents.utils.custom_embeddings import CustomEmbeddings
from web.models.document import DocumentChunk

logger = logging.getLogger(__name__)


def insert_documents():
    loader = TextLoader('./web/documents/Bailian_Overview.txt', encoding='utf-8')
    docs = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = text_splitter.split_documents(docs)
    logger.info('已切分成 %d 个片段', len(chunks))

    embeddings = CustomEmbeddings()

    # 先清空旧数据再插入，保证多次执行不会产生重复记录
    DocumentChunk.objects.all().delete()
    for chunk in chunks:
        emb = embeddings.embed_query(chunk.page_content)
        DocumentChunk.objects.create(content=chunk.page_content, embedding=emb)

    logger.info('已插入 %d 条向量记录', len(chunks))
