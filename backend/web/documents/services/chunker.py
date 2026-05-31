"""统一切分策略 — 所有 loader 的输出都经过这里二次切分"""
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_documents(documents: list[Document]) -> list[Document]:
    """对 loader 返回的文档列表进行二次长度切分（兜底）。

    每个 loader 内部已经做了初步切分（MdLoader 按标题、PdfLoader 按页），
    此函数确保单个 chunk 不会超过 chunk_size，同时保留原始 metadata。
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500, chunk_overlap=50,
    )
    return text_splitter.split_documents(documents)
