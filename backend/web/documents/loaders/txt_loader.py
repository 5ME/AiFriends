"""纯文本 .txt 加载器"""
from langchain_core.documents import Document

from .base import AbstractLoader
from .encoding import read_with_encoding


class TxtLoader(AbstractLoader):
    """加载 .txt 文件，自动探测编码。

    注：使用自定义 read_with_encoding() 而非直接调用 TextLoader。
    原因：TextLoader 默认假定 UTF-8，GBK/gb2312 编码的中文 txt
    会抛 UnicodeDecodeError。我们对中文用户场景需要多编码探测。
    """

    def load(self, file_path: str) -> list[Document]:
        content = read_with_encoding(file_path)
        return [Document(page_content=content, metadata={'source': file_path})]
