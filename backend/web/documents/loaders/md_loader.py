""".md Markdown 加载器 — 按标题层级 + 长度切分"""
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from .base import AbstractLoader
from .encoding import read_with_encoding


class MdLoader(AbstractLoader):
    """加载 .md 文件：先按 Markdown 标题切分，再按长度切分"""

    def load(self, file_path: str) -> list[Document]:
        content = read_with_encoding(file_path)
        doc = Document(page_content=content, metadata={'source': file_path})

        # 先按 Markdown 标题层级切分
        md_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "Header 1"),
                ("##", "Header 2"),
                ("###", "Header 3"),
            ],
            strip_headers=False,
        )
        # split_text 返回 List[Document]，每个带标题层级 metadata
        md_chunks = md_splitter.split_text(doc.page_content)
        # 将原始 doc 的 metadata（如 source）合并到每个 chunk
        for chunk in md_chunks:
            chunk.metadata.update({k: v for k, v in doc.metadata.items()
                                   if k not in chunk.metadata})

        # 再按长度切分
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500, chunk_overlap=50,
        )
        return text_splitter.split_documents(md_chunks)
