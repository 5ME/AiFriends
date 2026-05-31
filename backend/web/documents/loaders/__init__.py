"""文档加载器 — 每种文件类型一个 loader，统一返回 list[Document]"""
from .base import AbstractLoader
from .txt_loader import TxtLoader
from .md_loader import MdLoader
from .pdf_loader import PdfLoader

__all__ = ['AbstractLoader', 'TxtLoader', 'MdLoader', 'PdfLoader']


def get_loader(file_type: str) -> AbstractLoader:
    """根据文件扩展名返回对应的 loader 实例（懒加载）"""
    loaders = {
        'txt': TxtLoader,
        'md': MdLoader,
        'pdf': PdfLoader,
    }
    loader_cls = loaders.get(file_type.lower())
    if loader_cls is None:
        raise ValueError(f'不支持的文件类型: {file_type}')
    return loader_cls()
