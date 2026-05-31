"""Loader 抽象基类"""
from abc import ABC, abstractmethod
from langchain_core.documents import Document


class AbstractLoader(ABC):
    """所有文档加载器的基类。子类只需实现 load(file_path) -> list[Document]。"""

    @abstractmethod
    def load(self, file_path: str) -> list[Document]:
        """加载文件，返回 LangChain Document 列表"""
        ...
