"""文本编码探测 — txt/md loader 共用"""
import logging

logger = logging.getLogger(__name__)


def read_with_encoding(file_path: str) -> str:
    """按优先级探测编码读取文件内容"""
    for enc in ['utf-8', 'gbk', 'gb2312', 'latin-1']:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise ValueError(f'无法识别文件编码: {file_path}')
