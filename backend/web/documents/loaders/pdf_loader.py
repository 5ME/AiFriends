""".pdf 加载器 — 通过 PyMuPDF4LLM 转为 Markdown 后切分"""
import os

import pymupdf4llm
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .base import AbstractLoader


class PdfLoader(AbstractLoader):
    """加载 .pdf 文件：PyMuPDF4LLM 转 Markdown → 按长度切分"""

    def load(self, file_path: str) -> list[Document]:
        # PyMuPDF4LLM 一步将 PDF 转为 Markdown，按页分块
        chunks = pymupdf4llm.to_markdown(file_path, page_chunks=True)

        docs = []
        for chunk in chunks:
            docs.append(Document(
                page_content=chunk['text'],
                metadata={
                    'page_number': chunk['metadata']['page_number'],
                    'source': os.path.basename(file_path),
                }
            ))

        # 按长度切分
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500, chunk_overlap=50,
        )
        return text_splitter.split_documents(docs)
