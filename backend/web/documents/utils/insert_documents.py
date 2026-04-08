import lancedb
from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import LanceDB
from langchain_text_splitters import RecursiveCharacterTextSplitter

from web.documents.utils.custom_embeddings import CustomEmbeddings


def insert_documents():
    # 加载文件
    loader = TextLoader('./web/documents/Bailian_Overview.txt', encoding='utf-8')
    docs = loader.load()

    # 切分文件
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = text_splitter.split_documents(docs)
    print(f'已切分成 {len(chunks)} 个片段')

    # 自定义向量化类
    embeddings = CustomEmbeddings()

    # 插入向量数据库
    db_connection = lancedb.connect('./web/documents/lancedb_storage')
    lance_db = LanceDB.from_documents(
        connection=db_connection,
        documents=chunks,
        embedding=embeddings,
        table_name='my_knowledge_base',
        mode='overwrite',
    )
    print(f'{type(lance_db)}')
    print(f'已插入 {lance_db._table.count_rows()} 行数据')
