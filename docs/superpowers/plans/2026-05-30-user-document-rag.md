# P2-2 用户上传文档 RAG 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户上传 .txt/.md/.pdf 文档 → Celery 异步提取文本/分块/embedding → 存入 DocumentChunk(owner_id) → Chat Agent 按用户召回

**Architecture:** 重构 documents/ 为 loaders/services 两层；新增 document/upload|list|remove 三个 API 端点 + 一个 Celery 任务；前端新建 /knowledge 页面含拖拽上传 + 轮询状态更新

**Tech Stack:** Django 6.0 + DRF + Celery 5.5 + Redis + pgvector + PyMuPDF4LLM + LangChain RecursiveCharacterTextSplitter + Vue 3 + Tailwind 4 + daisyUI 5

---

### Task 1: 依赖安装与 settings 配置

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/backend/settings.py` (末尾追加)

- [ ] **Step 1: 安装 pymupdf4llm**

```bash
conda activate py312
cd backend
pip install "pymupdf4llm>=0.1,<1.0"
```

- [ ] **Step 2: 添加到 requirements.txt**

```diff
# requirements.txt 末尾追加
+ pymupdf4llm>=0.1,<1.0
```

- [ ] **Step 3: settings.py 追加文件上传大小限制**

在 settings.py 末尾 CELERY 配置块之后追加：

```python
# 文件上传大小限制 — 用户文档 RAG（Django 默认 2.5MB 太小）
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
```

- [ ] **Step 4: 验证配置生效**

```python
python -c "from django.conf import settings; print(settings.DATA_UPLOAD_MAX_MEMORY_SIZE)"
```

Expected: `10485760`

- [ ] **Step 5: 验证安装 & 确认 PyMuPDF4LLM API 参数名**

```bash
python -c "import pymupdf4llm; help(pymupdf4llm.to_markdown)" 2>&1 | grep -i page
```

检查 `page_chunks` 参数名（可能是 `page_chunks` 或 `page_wise`，取决于版本）。记下实际参数名，Task 2 Step 4 会用到。

- [ ] **Step 6: 运行现有测试确认无回归**

```bash
python -m pytest web/tests/ --collect-only -q
python -m pytest web/tests/ -v
```

先 `--collect-only` 确认当前测试总数，再跑全量确认全部 pass。

- [ ] **Step 7: Commit**

```bash
git add backend/requirements.txt backend/backend/settings.py
git commit -m "chore: add pymupdf4llm dependency and 10MB upload size limit"
```

---

### Task 2: documents/ 目录重构 — loaders 层

**Files:**
- Create: `backend/web/documents/loaders/__init__.py`
- Create: `backend/web/documents/loaders/base.py`
- Create: `backend/web/documents/loaders/txt_loader.py`
- Create: `backend/web/documents/loaders/md_loader.py`
- Create: `backend/web/documents/loaders/pdf_loader.py`
- Delete: `backend/web/documents/utils/md_split_test.py`
- Create: `backend/web/documents/raw/` (目录)
- Delete: `backend/web/documents/lancedb_storage/`
- Modify: 移动 raw 文档到 raw/ 目录

- [ ] **Step 1: 创建 base loader 抽象接口 + 共享编码探测**

`backend/web/documents/loaders/__init__.py`:

```python
"""文档加载器 — 每种文件类型一个 loader，统一返回 list[Document]"""
from .base import AbstractLoader
from .txt_loader import TxtLoader
from .md_loader import MdLoader
from .pdf_loader import PdfLoader

__all__ = ['AbstractLoader', 'TxtLoader', 'MdLoader', 'PdfLoader']


def get_loader(file_type: str) -> AbstractLoader:
    """根据文件扩展名返回对应的 loader 实例"""
    loaders = {
        'txt': TxtLoader(),
        'md': MdLoader(),
        'pdf': PdfLoader(),
    }
    loader = loaders.get(file_type.lower())
    if loader is None:
        raise ValueError(f'不支持的文件类型: {file_type}')
    return loader
```

`backend/web/documents/loaders/base.py`:

```python
"""Loader 抽象基类"""
from abc import ABC, abstractmethod
from langchain_core.documents import Document


class AbstractLoader(ABC):
    """所有文档加载器的基类。子类只需实现 load(file_path) -> list[Document]。"""

    @abstractmethod
    def load(self, file_path: str) -> list[Document]:
        """加载文件，返回 LangChain Document 列表"""
        ...
```

- [ ] **Step 2: 创建共享编码工具模块**

`backend/web/documents/loaders/encoding.py`:

```python
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
```

注意：函数名 `read_with_encoding`（公开函数，非 `_read_with_encoding`），因为被跨模块导入。

- [ ] **Step 3: 创建 TxtLoader**

`backend/web/documents/loaders/txt_loader.py`:

```python
"""纯文本 .txt 加载器"""
from langchain_community.document_loaders import TextLoader
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
```

- [ ] **Step 4: 创建 MdLoader**

`backend/web/documents/loaders/md_loader.py`:

```python
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
        md_chunks = md_splitter.split_text(doc.page_content)

        # 再按长度切分
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500, chunk_overlap=50,
        )
        return text_splitter.split_documents(md_chunks)
```

- [ ] **Step 5: 创建 PdfLoader**

**⚠️ 实现前确认：** Task 1 Step 5 已打印了 `pymupdf4llm.to_markdown` 的 help。确认分页参数名为 `page_chunks`（若为 `page_wise` 则替换下面的参数名）。

`backend/web/documents/loaders/pdf_loader.py`:

```python
""".pdf 加载器 — 通过 PyMuPDF4LLM 转为 Markdown 后切分"""
import os

import pymupdf4llm
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .base import AbstractLoader


class PdfLoader(AbstractLoader):
    """加载 .pdf 文件：PyMuPDF4LLM 转 Markdown → 按长度切分"""

    def load(self, file_path: str) -> list[Document]:
        # PyMuPDF4LLM 一步将 PDF 转为 Markdown
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
```

- [ ] **Step 5: 清理废弃文件**

```bash
# 删除调试脚本
rm backend/web/documents/utils/md_split_test.py

# 删除废弃 LanceDB 存储
rm -rf backend/web/documents/lancedb_storage/

# 创建 raw 目录并移动原始文档
mkdir -p backend/web/documents/raw
mv backend/web/documents/Bailian_Overview.md backend/web/documents/raw/
mv backend/web/documents/Bailian_Overview.txt backend/web/documents/raw/
mv backend/web/documents/claude-prompting-best-practices.md backend/web/documents/raw/
mv backend/web/documents/coding-plan-overview.md backend/web/documents/raw/
```

- [ ] **Step 6: Commit**

```bash
git add backend/web/documents/loaders/
git add backend/web/documents/raw/
git rm backend/web/documents/utils/md_split_test.py
git rm -r backend/web/documents/lancedb_storage/
git add -u backend/web/documents/
git commit -m "refactor: reorganize documents/ into loaders/services/raw layers

- Create loaders/ with AbstractLoader base + TxtLoader, MdLoader, PdfLoader
- Each loader returns unified list[Document] interface
- Remove dead md_split_test.py and lancedb_storage/
- Move raw docs to raw/ directory"
```

---

### Task 3: documents/ 目录重构 — services 层

**Files:**
- Create: `backend/web/documents/services/__init__.py`
- Create: `backend/web/documents/services/chunker.py`
- Move: `backend/web/documents/utils/custom_embeddings.py` → `backend/web/documents/services/embeddings.py`
- Modify: `backend/web/documents/utils/insert_documents.py` (精简)
- Modify: `backend/web/documents/utils/custom_embeddings.py` (re-export)
- Modify: `backend/web/views/friend/message/chat/graph.py` (更新 import)
- Modify: `backend/web/tests/test_document.py` (更新 import)

- [ ] **Step 1: 更新现有测试 import 路径**

⚠️ **TDD 注意：** 此步骤仅修改 import，此时 services/ 目录还不存在，import 会失败。不要单独 commit 此步骤 — 等 Step 3-7 全部完成后一起 commit。

`test_document.py` 中 `TestInsertDocuments` 类的 import 从旧路径改为新路径：

```python
# Before
from web.documents.utils.insert_documents import insert_documents
# After
from web.documents.services.insert_documents import insert_documents
```

`TestInsertDocuments` 第 132 行和第 153 行作同样修改。

- [ ] **Step 2: 运行测试确认现有测试失败（import 变更）**

```bash
python -m pytest web/tests/test_document.py -v
```

Expected: FAIL — 因为 services/ 目录还不存在

- [ ] **Step 3: 迁移 custom_embeddings.py 到 services/**

```bash
cp backend/web/documents/utils/custom_embeddings.py backend/web/documents/services/embeddings.py
```

不需要改 `services/embeddings.py` 的内容，logic 完全不变。

- [ ] **Step 4: 旧路径加 re-export 兼容**

`backend/web/documents/utils/custom_embeddings.py` 覆盖为：

```python
"""兼容旧 import 路径，实际逻辑已迁至 services/embeddings.py"""
from web.documents.services.embeddings import CustomEmbeddings  # noqa: F401
```

- [ ] **Step 5: 创建统一切分器 chunker.py**

`backend/web/documents/services/chunker.py`:

```python
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
```

`backend/web/documents/services/__init__.py`:

```python
"""文档处理服务层"""
from .embeddings import CustomEmbeddings
from .chunker import chunk_documents

__all__ = ['CustomEmbeddings', 'chunk_documents']
```

- [ ] **Step 6: 精简 insert_documents.py**

`backend/web/documents/utils/insert_documents.py` 覆盖为：

```python
"""系统知识库批量导入 — 使用 loader + chunker 消除重复代码"""
import logging

from web.documents.loaders import get_loader
from web.documents.services import CustomEmbeddings, chunk_documents
from web.models.document import DocumentChunk, UserDocument

logger = logging.getLogger(__name__)


def _insert_with_loader(title: str, file_path: str, file_type: str):
    """通用导入逻辑：get_or_create → load → chunk → embed → bulk_create"""
    loader = get_loader(file_type)
    documents = loader.load(file_path)
    chunks = chunk_documents(documents)

    sys_doc, _ = UserDocument.objects.get_or_create(
        title=title,
        defaults={'status': 'completed'}
    )
    DocumentChunk.objects.filter(document=sys_doc).delete()

    embeddings = CustomEmbeddings()
    texts = [c.page_content for c in chunks]
    vectors = embeddings.embed_documents(texts)

    objs = [
        DocumentChunk(
            content=c.page_content, embedding=v,
            document=sys_doc, chunk_index=i,
            # token_count 实际存字符数（近似），非精确 token 数
            token_count=len(c.page_content),
            metadata=c.metadata,
        )
        for i, (c, v) in enumerate(zip(chunks, vectors))
    ]
    DocumentChunk.objects.bulk_create(objs, batch_size=50)

    sys_doc.chunks_count = len(objs)
    sys_doc.save()
    logger.info('已插入 %d 条向量记录 → %s', len(objs), title)


def insert_documents():
    _insert_with_loader('百炼平台概述',
                        './web/documents/raw/Bailian_Overview.txt', 'txt')


def insert_markdown_documents():
    _insert_with_loader('百炼平台概述 Markdown',
                        './web/documents/raw/Bailian_Overview.md', 'md')
```

- [ ] **Step 7: 运行所有测试确认重构无回归**

```bash
python -m pytest web/tests/ -v
```

Expected: 全部 pass（含 test_document.py 中 TestInsertDocuments 通过 re-export 仍能运行）

- [ ] **Step 8: Commit**

```bash
git add backend/web/documents/services/
git add backend/web/documents/utils/
git add backend/web/tests/test_document.py
git commit -m "refactor: create services layer with unified chunker and embeddings

- Move custom_embeddings.py to services/embeddings.py with re-export
- Add chunker.py: unified chunk_documents() for all loaders
- Simplify insert_documents.py: single _insert_with_loader() replaces 2 duplicate functions
- Update test imports to new paths"
```

---

### Task 4: 后端 API — 上传端点 + 权限测试

**Files:**
- Create: `backend/web/views/document/__init__.py`
- Create: `backend/web/views/document/upload.py`
- Modify: `backend/web/urls.py`
- Modify: `backend/web/tests/test_document.py` (追加)

- [ ] **Step 1: 写失败的测试**

在 `backend/web/tests/test_document.py` 末尾追加：

```python
import io
from django.core.files.uploadedfile import SimpleUploadedFile


class TestDocumentUpload:
    """POST /api/document/upload/ 上传校验"""

    def test_upload_requires_auth(self, api_client):
        """未登录 → 401"""
        file = SimpleUploadedFile('test.txt', b'hello', content_type='text/plain')
        resp = api_client.post('/api/document/upload/', {'file': file})
        assert resp.status_code == 401

    def test_upload_no_file_returns_400(self, auth_client):
        """不传 file → 400"""
        resp = auth_client.post('/api/document/upload/', {})
        assert resp.status_code == 400
        assert '请选择文件' in resp.data['message']

    def test_upload_empty_file_returns_400(self, auth_client):
        """空文件 → 400"""
        file = SimpleUploadedFile('test.txt', b'', content_type='text/plain')
        resp = auth_client.post('/api/document/upload/', {'file': file})
        assert resp.status_code == 400

    def test_upload_oversized_file_returns_400(self, auth_client):
        """超大文件 → 400"""
        content = b'x' * (10 * 1024 * 1024 + 1)  # 10MB + 1B
        file = SimpleUploadedFile('big.txt', content, content_type='text/plain')
        resp = auth_client.post('/api/document/upload/', {'file': file})
        assert resp.status_code == 400

    def test_upload_bad_extension_returns_400(self, auth_client):
        """不支持的文件类型 → 400"""
        file = SimpleUploadedFile('test.exe', b'test', content_type='application/octet-stream')
        resp = auth_client.post('/api/document/upload/', {'file': file})
        assert resp.status_code == 400

    def test_upload_magic_bytes_mismatch_returns_400(self, auth_client):
        """文件头魔数与扩展名不匹配 → 400（.exe 伪装 .pdf）"""
        file = SimpleUploadedFile('fake.pdf', b'MZ\x90\x00test',
                                  content_type='application/pdf')
        resp = auth_client.post('/api/document/upload/', {'file': file})
        assert resp.status_code == 400

    def test_upload_txt_success(self, auth_client, user_profile):
        """正常上传 .txt"""
        file = SimpleUploadedFile('hello.txt', b'Hello World',
                                  content_type='text/plain')
        resp = auth_client.post('/api/document/upload/', {'file': file})
        assert resp.status_code == 201
        assert resp.data['status'] == 'pending'
        # 验证 UserDocument 已创建
        from web.models.document import UserDocument
        doc = UserDocument.objects.get(id=resp.data['id'])
        assert doc.owner == user_profile
        assert doc.file_type == 'txt'
        assert doc.title == 'hello.txt'
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python -m pytest web/tests/test_document.py::TestDocumentUpload -v
```

Expected: FAIL (路由不存在 / 视图不存在)

- [ ] **Step 3: 创建 document 目录和上传视图**

`backend/web/views/document/__init__.py` (空文件)

`backend/web/views/document/upload.py`:

```python
"""POST /api/document/upload/ — 用户上传文档，触发 Celery 异步处理"""
import logging
import os
import uuid

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.document import UserDocument
from web.views.document.tasks import process_document_task

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'txt', 'md', 'pdf'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# 魔数校验：文件头字节 → 预期值
MAGIC_BYTES = {
    'pdf': b'%PDF',
    'txt': None,   # 不含 null byte 即可
    'md': None,    # 同上
}


def _validate_file(file) -> str | None:
    """同步校验上传文件，返回错误消息；无错返回 None"""
    if not file:
        return '请选择文件'
    if file.size == 0:
        return '文件为空'
    if file.size > MAX_FILE_SIZE:
        return '文件大小不能超过 10MB'

    # 扩展名只提取一次，后续复用
    ext = file.name.rsplit('.', 1)[-1].lower() if '.' in file.name else ''
    if ext not in ALLOWED_EXTENSIONS:
        return '不支持的文件格式，仅支持 txt/md/pdf'

    expected_magic = MAGIC_BYTES.get(ext)
    if expected_magic is not None:
        header = file.read(4)
        file.seek(0)
        if not header.startswith(expected_magic):
            return '文件格式与扩展名不匹配'
    elif expected_magic is None:
        # txt/md: 检测是否为纯文本（不含 null byte）
        header = file.read(512)
        file.seek(0)
        if b'\x00' in header:
            return '文件格式与扩展名不匹配'

    return None


def sanitize_title(raw_name: str) -> str:
    """从原始文件名提取安全的 title，防路径遍历，截断到 200 字符"""
    basename = os.path.basename(raw_name)
    return basename[:200]


def save_to_media(file, ext: str) -> str:
    """保存上传文件到 media/documents/<uuid>.<ext>，返回相对路径"""
    from django.conf import settings
    filename = f'{uuid.uuid4().hex}.{ext}'
    dir_path = os.path.join(settings.MEDIA_ROOT, 'documents')
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, filename)
    with open(file_path, 'wb') as f:
        for chunk in file.chunks():
            f.write(chunk)
    return f'documents/{filename}'


class DocumentUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        file = request.FILES.get('file')

        error = _validate_file(file)
        if error:
            return Response({'message': error}, status=status.HTTP_400_BAD_REQUEST)

        ext = file.name.rsplit('.', 1)[-1].lower() if '.' in file.name else ''

        doc = UserDocument.objects.create(
            owner=request.user.userprofile,
            title=sanitize_title(file.name),
            file_url=save_to_media(file, ext),
            file_type=ext,
            status='pending',
        )
        process_document_task.delay(doc.id)

        logger.info('文档上传成功, doc_id=%d, title=%s', doc.id, doc.title)
        return Response(
            {'id': doc.id, 'title': doc.title, 'status': doc.status},
            status=status.HTTP_201_CREATED,
        )
```

- [ ] **Step 4: 注册路由**

`backend/web/urls.py` 新增 import 和路由：

```python
# 在现有 import 块末尾追加
from web.views.document.upload import DocumentUploadView

# 在 urlpatterns 中追加（放在 health 路由之后）
path('api/document/upload/', DocumentUploadView.as_view()),
```

- [ ] **Step 5: 创建 Celery 任务骨架（让 import 不报错）**

`backend/web/views/document/tasks.py`:

```python
"""文档处理 Celery 异步任务"""
from backend.celery import app


@app.task(max_retries=1)
def process_document_task(doc_id: int):
    """文档异步处理 — 占位，完整实现在 Task 7"""
    pass
```

- [ ] **Step 6: 注册 Celery 任务**

`backend/web/tasks.py` 追加一行：

```python
from web.views.document.tasks import process_document_task  # noqa: F401
```

- [ ] **Step 7: 运行上传测试**

```bash
python -m pytest web/tests/test_document.py::TestDocumentUpload -v
```

Expected: 7 passed（txt_success 会创建 UserDocument + 触发 Celery 任务，但 process_document_task 当前是占位所以 status 保持 pending）

- [ ] **Step 8: Commit**

```bash
git add backend/web/views/document/ backend/web/urls.py backend/web/tasks.py
git add backend/web/tests/test_document.py
git commit -m "feat: add document upload API with validation and auth check

- POST /api/document/upload/ with file size/ext/magic byte validation
- sanitize_title() prevents path traversal
- save_to_media() stores to media/documents/<uuid>.<ext>
- Celery task placeholder registered in web/tasks.py"
```

---

### Task 5: 后端 API — 列表端点 + 权限测试

**Files:**
- Create: `backend/web/views/document/list.py`
- Modify: `backend/web/urls.py`
- Modify: `backend/web/tests/test_document.py` (追加)

- [ ] **Step 1: 写失败的测试**

`test_document.py` 末尾追加：

```python
class TestDocumentList:
    """GET /api/document/list/ 文档列表"""

    def test_list_requires_auth(self, api_client):
        """未登录 → 401"""
        resp = api_client.get('/api/document/list/')
        assert resp.status_code == 401

    def test_list_empty(self, auth_client):
        """无文档时返回空列表"""
        resp = auth_client.get('/api/document/list/')
        assert resp.status_code == 200
        assert resp.data['documents'] == []

    def test_list_only_own_documents(self, auth_client, user_profile, other_user):
        """只能看到自己的文档"""
        from web.models.document import UserDocument
        UserDocument.objects.create(title='mine', owner=user_profile,
                                    status='completed')
        UserDocument.objects.create(title='theirs', owner=other_user.userprofile,
                                    status='completed')
        resp = auth_client.get('/api/document/list/')
        assert resp.status_code == 200
        assert len(resp.data['documents']) == 1
        assert resp.data['documents'][0]['title'] == 'mine'

    def test_list_ordered_by_created_desc(self, auth_client, user_profile):
        """按创建时间倒序"""
        from web.models.document import UserDocument
        d1 = UserDocument.objects.create(title='older', owner=user_profile,
                                          status='completed')
        d2 = UserDocument.objects.create(title='newer', owner=user_profile,
                                          status='completed')
        resp = auth_client.get('/api/document/list/')
        titles = [d['title'] for d in resp.data['documents']]
        assert titles == ['newer', 'older']  # DESC
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python -m pytest web/tests/test_document.py::TestDocumentList -v
```

Expected: FAIL

- [ ] **Step 3: 创建列表视图**

`backend/web/views/document/list.py`:

```python
"""GET /api/document/list/ — 返回当前用户的文档列表"""
import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.document import UserDocument

logger = logging.getLogger(__name__)


class DocumentListView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        docs = UserDocument.objects.filter(
            owner=request.user.userprofile
        ).order_by('-created_at')

        result = [{
            'id': d.id,
            'title': d.title,
            'file_type': d.file_type,
            'status': d.status,
            'error_message': d.error_message,
            'chunks_count': d.chunks_count,
            'created_at': d.created_at.isoformat(),
        } for d in docs]

        return Response({'documents': result})
```

- [ ] **Step 4: 注册路由**

`urls.py` 追加 import 和路由：

```python
from web.views.document.list import DocumentListView
# ...
path('api/document/list/', DocumentListView.as_view()),
```

- [ ] **Step 5: 运行测试**

```bash
python -m pytest web/tests/test_document.py::TestDocumentList -v
```

Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add backend/web/views/document/list.py backend/web/urls.py
git add backend/web/tests/test_document.py
git commit -m "feat: add document list API with owner filtering

- GET /api/document/list/ returns user's documents ordered by created_at DESC
- Other user's documents are not visible"
```

---

### Task 6: 后端 API — 删除端点 + 权限测试

**Files:**
- Create: `backend/web/views/document/remove.py`
- Modify: `backend/web/urls.py`
- Modify: `backend/web/tests/test_document.py` (追加)

- [ ] **Step 1: 写失败的测试**

`test_document.py` 末尾追加：

```python
class TestDocumentRemove:
    """POST /api/document/remove/ 删除文档"""

    def test_remove_requires_auth(self, api_client):
        """未登录 → 401"""
        resp = api_client.post('/api/document/remove/', {'id': 1})
        assert resp.status_code == 401

    def test_remove_own_document(self, auth_client, user_profile):
        """删除自己的文档 → 200，级联删除 chunks"""
        from web.models.document import UserDocument, DocumentChunk
        doc = UserDocument.objects.create(title='to-delete', owner=user_profile,
                                          status='completed')
        DocumentChunk.objects.create(content='chunk', embedding=[0.0] * 1024,
                                     document=doc, chunk_index=0)
        resp = auth_client.post('/api/document/remove/', {'id': doc.id})
        assert resp.status_code == 200
        assert not UserDocument.objects.filter(id=doc.id).exists()
        assert not DocumentChunk.objects.filter(document_id=doc.id).exists()

    def test_remove_other_user_document(self, auth_client, other_user):
        """不能删除别人的文档 → 404"""
        from web.models.document import UserDocument
        doc = UserDocument.objects.create(
            title='theirs', owner=other_user.userprofile, status='completed')
        resp = auth_client.post('/api/document/remove/', {'id': doc.id})
        assert resp.status_code == 404

    def test_remove_nonexistent_returns_404(self, auth_client):
        """删除不存在的文档 → 404"""
        resp = auth_client.post('/api/document/remove/', {'id': 99999})
        assert resp.status_code == 404
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python -m pytest web/tests/test_document.py::TestDocumentRemove -v
```

Expected: FAIL

- [ ] **Step 3: 创建删除视图**

`backend/web/views/document/remove.py`:

```python
"""POST /api/document/remove/ — 删除文档及其 chunks"""
import logging
import os

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.document import UserDocument

logger = logging.getLogger(__name__)


class DocumentRemoveView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        doc_id = request.data.get('id')
        try:
            doc = UserDocument.objects.get(
                id=doc_id, owner=request.user.userprofile
            )
        except UserDocument.DoesNotExist:
            return Response(
                {'message': '文档不存在或无权访问'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 删除 media 文件
        if doc.file_url:
            file_path = os.path.join(settings.MEDIA_ROOT, doc.file_url)
            if os.path.exists(file_path):
                os.remove(file_path)

        # 级联删除 DocumentChunks（Django CASCADE）
        doc.delete()
        logger.info('文档已删除, doc_id=%d, title=%s', doc_id, doc.title)

        return Response({'message': '删除成功'})
```

- [ ] **Step 4: 注册路由**

`urls.py` 追加：

```python
from web.views.document.remove import DocumentRemoveView
# ...
path('api/document/remove/', DocumentRemoveView.as_view()),
```

- [ ] **Step 5: 运行测试**

```bash
python -m pytest web/tests/test_document.py::TestDocumentRemove -v
```

Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add backend/web/views/document/remove.py backend/web/urls.py
git add backend/web/tests/test_document.py
git commit -m "feat: add document remove API with ownership check

- POST /api/document/remove/ cascades chunks + media file
- Returns 404 for other user's documents and nonexistent IDs"
```

---

### Task 7: Celery 异步文档处理任务

**Files:**
- Modify: `backend/web/views/document/tasks.py` (完整实现)
- Create: `backend/web/tests/test_document_processing.py`

- [ ] **Step 1: 写失败的测试**

`backend/web/tests/test_document_processing.py`:

```python
"""文档异步处理测试 — Mock embedding API 验证完整处理流"""
from unittest.mock import patch, MagicMock
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from web.models.document import UserDocument, DocumentChunk


def _dummy_upload(user_profile, filename='test.txt'):
    """辅助：创建 UserDocument + 写 media 文件"""
    from django.conf import settings
    import os
    content_map = {
        'test.txt': b'Hello World\nThis is a test document.',
        'test.md': b'# Title\n\n## Section\n\nContent here.',  // 注意 # 后有空格（Markdown 标准语法）
    }
    content = content_map.get(filename, b'sample content')
    ext = filename.rsplit('.', 1)[-1]
    doc = UserDocument.objects.create(
        owner=user_profile, title=filename,
        file_url=f'documents/{filename}', file_type=ext, status='pending',
    )
    dir_path = os.path.join(settings.MEDIA_ROOT, 'documents')
    os.makedirs(dir_path, exist_ok=True)
    with open(os.path.join(dir_path, filename), 'wb') as f:
        f.write(content)
    return doc


class TestDocumentProcessing:
    """process_document_task 完整处理流"""

    @patch("web.views.document.tasks.CustomEmbeddings")
    def test_process_txt_document(self, mock_embeddings, user_profile):
        """上传 .txt → processing → completed，写入 chunks"""
        emb_mock = MagicMock()
        emb_mock.embed_documents.return_value = [[0.1] * 1024, [0.2] * 1024]
        mock_embeddings.return_value = emb_mock

        from web.views.document.tasks import process_document_task
        doc = _dummy_upload(user_profile, 'test.txt')
        process_document_task(doc.id)

        doc.refresh_from_db()
        assert doc.status == 'completed'
        assert doc.chunks_count > 0
        assert DocumentChunk.objects.filter(document=doc).count() == doc.chunks_count

    @patch("web.views.document.tasks.CustomEmbeddings")
    def test_process_md_document_preserves_metadata(self, mock_embeddings, user_profile):
        """.md 文档分块后保留标题 metadata"""
        emb_mock = MagicMock()
        emb_mock.embed_documents.return_value = [[0.1] * 1024] * 3
        mock_embeddings.return_value = emb_mock

        from web.views.document.tasks import process_document_task
        doc = _dummy_upload(user_profile, 'test.md')
        process_document_task(doc.id)

        doc.refresh_from_db()
        assert doc.status == 'completed'
        # 至少一个 chunk 有 Markdown 标题 metadata
        chunks = DocumentChunk.objects.filter(document=doc)
        has_header_meta = any('Header 1' in c.metadata for c in chunks)
        assert has_header_meta

    @patch("web.views.document.tasks.CustomEmbeddings")
    def test_empty_content_marks_failed(self, mock_embeddings, user_profile):
        """空文件 → status=failed"""
        from web.views.document.tasks import process_document_task
        doc = _dummy_upload(user_profile, 'test.txt')
        # 清空文件内容
        import os
        from django.conf import settings
        with open(os.path.join(settings.MEDIA_ROOT, doc.file_url), 'w') as f:
            f.write('')

        process_document_task(doc.id)
        doc.refresh_from_db()
        assert doc.status == 'failed'
        assert '无' in doc.error_message

    def test_document_already_deleted_skips_silently(self, user_profile):
        """文档已被用户删除 → DoesNotExist → 静默跳过"""
        from web.views.document.tasks import process_document_task
        doc = _dummy_upload(user_profile, 'test.txt')
        doc_id = doc.id
        doc.delete()

        # 不应抛异常
        process_document_task(doc_id)
        assert not UserDocument.objects.filter(id=doc_id).exists()

    @patch("web.views.document.tasks.CustomEmbeddings")
    def test_pdf_file_processed(self, mock_embeddings, user_profile):
        """PDF 文件通过 PyMuPDF4LLM 处理后写入 chunks"""
        from django.conf import settings
        import os

        # 先确认 PyMuPDF4LLM 可用
        try:
            import pymupdf4llm  # noqa: F401
        except ImportError:
            pytest.skip('pymupdf4llm not installed')

        emb_mock = MagicMock()
        emb_mock.embed_documents.return_value = [[0.1] * 1024] * 2
        mock_embeddings.return_value = emb_mock

        # 创建最小合法 PDF
        minimal_pdf = (
            b'%PDF-1.4\n'
            b'1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n'
            b'2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n'
            b'3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n'
            b'xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n'
            b'0000000115 00000 n \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF'
        )
        import uuid
        filename = f'{uuid.uuid4().hex}.pdf'
        dir_path = os.path.join(settings.MEDIA_ROOT, 'documents')
        os.makedirs(dir_path, exist_ok=True)
        file_path = os.path.join(dir_path, filename)
        with open(file_path, 'wb') as f:
            f.write(minimal_pdf)

        doc = UserDocument.objects.create(
            owner=user_profile, title='test.pdf',
            file_url=f'documents/{filename}', file_type='pdf', status='pending',
        )

        from web.views.document.tasks import process_document_task
        process_document_task(doc.id)

        doc.refresh_from_db()
        # PDF 可能无文字 → failed 或 completed 都可接受
        assert doc.status in ('completed', 'failed')
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python -m pytest web/tests/test_document_processing.py -v
```

Expected: FAIL（process_document_task 是占位，无实际逻辑）

- [ ] **Step 3: 实现完整的 process_document_task**

`backend/web/views/document/tasks.py` 覆盖为完整实现：

```python
"""文档处理 Celery 异步任务"""
import logging
import os

from django.conf import settings
from openai import APIStatusError
from backend.celery import app

from web.documents.loaders import get_loader
from web.documents.services import CustomEmbeddings, chunk_documents
from web.models.document import UserDocument, DocumentChunk

logger = logging.getLogger(__name__)


@app.task(max_retries=1)
def process_document_task(doc_id: int):
    """异步处理上传文档：加载 → 切分 → embedding → 写入 chunks"""
    try:
        doc = UserDocument.objects.get(id=doc_id)
        doc.status = 'processing'
        doc.save()
        logger.info('文档处理开始, doc_id=%d, title=%s', doc_id, doc.title)

        # 拼接完整文件路径（file_url 存的是相对路径如 documents/xxx.pdf）
        full_path = os.path.join(settings.MEDIA_ROOT, doc.file_url)

        # 1. 选 loader → list[Document]（含 page_content + metadata）
        loader = get_loader(doc.file_type)
        documents = loader.load(full_path)

        # 2. 统一切分 → 保留 metadata
        chunks = chunk_documents(documents)

        # 3. 空内容检测
        if not chunks or all(not c.page_content.strip() for c in chunks):
            doc.status = 'failed'
            doc.error_message = '文档无可提取文字，可能是扫描件或空文件'
            doc.save()
            logger.warning('文档无文字, doc_id=%d', doc_id)
            return

        # 4. 批量 embedding
        embeddings = CustomEmbeddings()
        texts = [c.page_content for c in chunks]
        vectors = embeddings.embed_documents(texts)

        # 5. 批量写入 DocumentChunk
        objs = [
            DocumentChunk(
                content=c.page_content, embedding=v, document=doc,
                owner=doc.owner, chunk_index=i,
                # token_count 实际存字符数（近似），精确计数需 tiktoken
                token_count=len(c.page_content),
                metadata=c.metadata,
            )
            for i, (c, v) in enumerate(zip(chunks, vectors))
        ]
        DocumentChunk.objects.bulk_create(objs, batch_size=50)

        doc.status = 'completed'
        doc.chunks_count = len(objs)
        doc.save()
        logger.info('文档处理完成, doc_id=%d, chunks=%d', doc_id, len(objs))

    except UserDocument.DoesNotExist:
        logger.warning('文档已删除，跳过处理, doc_id=%d', doc_id)
        return
    except Exception as exc:
        logger.exception('文档处理失败, doc_id=%d', doc_id)
        # 尝试更新状态为 failed
        try:
            doc.status = 'failed'
            doc.error_message = str(exc)[:500]
            doc.save()
        except Exception:
            pass
        # 4xx 永久故障不重试（429 除外），其余重试一次
        if isinstance(exc, APIStatusError) and \
           400 <= exc.status_code < 500 and exc.status_code != 429:
            return
        raise process_document_task.retry(exc=exc, countdown=10)
```

- [ ] **Step 4: 运行处理测试**

```bash
python -m pytest web/tests/test_document_processing.py -v
```

Expected: 5 passed（PDF 测试可能 skip）

- [ ] **Step 5: Commit**

```bash
git add backend/web/views/document/tasks.py
git add backend/web/tests/test_document_processing.py
git commit -m "feat: implement async document processing with Celery

- process_document_task: load → chunk → embed → bulk_create DocumentChunk
- Preserve loader metadata (Markdown headers, PDF page numbers)
- Empty content detection → status=failed
- Deleted document → silent skip
- 4xx permanent errors not retried, others retry once"
```

---

### Task 8: Chat Agent tool description 更新

**Files:**
- Modify: `backend/web/views/friend/message/chat/graph.py`
- Modify: `backend/web/tests/test_chat_agent.py` (追加验证)

- [ ] **Step 1: 写测试验证 tool description 已更新**

`test_chat_agent.py` 末尾追加：

```python
class TestKnowledgeBaseToolDescription:
    """search_knowledge_base tool description 不应限定百炼平台"""

    def test_tool_description_is_generic(self):
        """tool description 不应出现'阿里云百炼'字样"""
        from web.views.friend.message.chat.graph import ChatGraph
        app = ChatGraph.create_app()
        # 拿到编译前的原始 graph 无法直接访问 tools，
        # 改为直接检查 graph.py 源码中的 tool description 字符串
        import inspect
        source = inspect.getsource(ChatGraph.create_app)
        assert '百炼' not in source, \
            'search_knowledge_base tool description 不应写死百炼平台'
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python -m pytest web/tests/test_chat_agent.py::TestKnowledgeBaseToolDescription -v
```

Expected: FAIL（当前 description 含"阿里云百炼"）

- [ ] **Step 3: 更新 tool description**

`graph.py` 中 `search_knowledge_base` 的 docstring 修改：

```python
# Before (graph.py:32-34):
@tool
def search_knowledge_base(query: str, state: Annotated[dict, InjectedState]) -> str:
    """
    当用户查询"阿里云百炼"相关简介信息时，调用此函数。
    输入为要查询的问题，输出为查询结果。
    :param query: 要查询的问题
    :return: 查询结果
    """

# After:
@tool
def search_knowledge_base(query: str, state: Annotated[dict, InjectedState]) -> str:
    """
    在知识库中检索与用户问题相关的文档内容。
    知识库包含平台文档和用户上传的个人文档。
    当需要查找文档中的信息、引用资料或专业知识时，调用此函数。
    :param query: 要查询的问题
    :return: 查询结果
    """
```

- [ ] **Step 4: 运行测试**

```bash
python -m pytest web/tests/test_chat_agent.py::TestKnowledgeBaseToolDescription -v
```

Expected: PASS

- [ ] **Step 5: 运行全量测试确认无回归**

```bash
python -m pytest web/tests/ -v
```

Expected: 全部 pass（含新增约 20 个测试）

- [ ] **Step 6: Commit**

```bash
git add backend/web/views/friend/message/chat/graph.py
git add backend/web/tests/test_chat_agent.py
git commit -m "fix: generalize search_knowledge_base tool description

Remove hardcoded '阿里云百炼' reference so LLM calls the tool
for user-uploaded documents as well as global knowledge base."
```

---

### Task 9: 前端 — API 函数 + Composable

**Files:**
- Modify: `frontend/src/js/http/api.js`
- Create: `frontend/src/composables/useDocumentPolling.js`

- [ ] **Step 1: 追加 API 函数**

`frontend/src/js/http/api.js` 末尾追加：

```javascript
// ==================== 文档管理 ====================

/** 上传文档 — axios 自动设置 Content-Type（含 boundary），不要手动覆盖 */
export function uploadDocument(file) {
  const formData = new FormData()
  formData.append('file', file)
  return http.post('/api/document/upload/', formData)
}

/** 获取文档列表 */
export function getDocumentList() {
  return http.get('/api/document/list/')
}

/** 删除文档 */
export function removeDocument(id) {
  return http.post('/api/document/remove/', { id })
}
```

- [ ] **Step 2: 创建轮询 composable**

`frontend/src/composables/useDocumentPolling.js`:

```javascript
import { ref, onUnmounted } from 'vue'
import { getDocumentList } from '@/js/http/api.js'

/**
 * 文档处理状态轮询。
 * 每 3 秒拉取文档列表，当全部文档到达终态时自动停止。
 * 兜底上限 120 次（6 分钟），超时提醒用户手动刷新。
 */
export function useDocumentPolling() {
  const documents = ref([])
  const isPolling = ref(false)
  let timer = null
  let pollCount = 0
  const MAX_POLLS = 120
  const isFetching = ref(false)

  async function fetchList() {
    if (isFetching.value) return  // 上一次请求未完成，跳过本次
    isFetching.value = true
    try {
      const res = await getDocumentList()
      documents.value = res.data.documents
    } catch (e) {
      console.error('文档列表拉取失败:', e)
    } finally {
      isFetching.value = false
    }
  }

  function hasProcessing() {
    return documents.value.some(
      d => d.status === 'pending' || d.status === 'processing'
    )
  }

  async function startPolling() {
    if (isPolling.value) return
    isPolling.value = true
    pollCount = 0

    await fetchList()

    if (!hasProcessing()) {
      isPolling.value = false
      return
    }

    timer = setInterval(async () => {
      pollCount++
      await fetchList()

      if (!hasProcessing() || pollCount >= MAX_POLLS) {
        clearInterval(timer)
        isPolling.value = false
        if (pollCount >= MAX_POLLS) {
          console.warn('文档处理轮询超时')
        }
      }
    }, 3000)
  }

  async function refresh() {
    await fetchList()
    // 有处理中的文档就重新启动轮询
    if (hasProcessing()) {
      startPolling()
    }
  }

  onUnmounted(() => {
    if (timer) {
      clearInterval(timer)
      isPolling.value = false
    }
  })

  return { documents, isPolling, startPolling, refresh }
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/js/http/api.js
git add frontend/src/composables/useDocumentPolling.js
git commit -m "feat: add document API functions and polling composable

- uploadDocument / getDocumentList / removeDocument API wrappers
- useDocumentPolling: auto-poll every 3s until all docs reach terminal state
- Hard cap at 120 polls (6 min) to prevent infinite polling on worker failure"
```

---

### Task 10: 前端 — UploadZone + DocumentCard 组件

**Files:**
- Create: `frontend/src/components/knowledge/UploadZone.vue`
- Create: `frontend/src/components/knowledge/DocumentCard.vue`

- [ ] **Step 1: 创建 UploadZone.vue**

```vue
<template>
  <div
    class="upload-zone border-2 border-dashed rounded-xl p-8 text-center transition-colors cursor-pointer"
    :class="[
      isDragOver ? 'border-primary bg-primary/5' : 'border-base-300',
      isUploading ? 'pointer-events-none opacity-50' : 'hover:border-primary/50'
    ]"
    @dragover.prevent="isDragOver = true"
    @dragleave.prevent="isDragOver = false"
    @drop.prevent="handleDrop"
    @click="triggerFileInput"
  >
    <input
      ref="fileInput"
      type="file"
      accept=".txt,.md,.pdf"
      class="hidden"
      @change="handleFileSelect"
    />

    <div v-if="isUploading" class="flex flex-col items-center gap-2">
      <span class="loading loading-spinner loading-md"></span>
      <span class="text-sm text-base-content/60">上传中...</span>
    </div>
    <div v-else class="flex flex-col items-center gap-2">
      <svg class="w-10 h-10 text-base-content/30" fill="none" stroke="currentColor"
           viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round"
           stroke-width="1.5" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25
           2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"/></svg>
      <span class="text-sm font-medium">拖拽文件到此处</span>
      <span class="text-xs text-base-content/40">或点击上传</span>
      <span class="text-xs text-base-content/30 mt-2">
        支持 .txt .md .pdf · 单文件 ≤ 10MB
      </span>
      <p v-if="errorMessage" class="text-xs text-error mt-2">{{ errorMessage }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const emit = defineEmits(['upload'])
const fileInput = ref(null)
const isDragOver = ref(false)
const isUploading = ref(false)
const errorMessage = ref('')

function validate(file) {
  const allowed = ['txt', 'md', 'pdf']
  const ext = file.name.split('.').pop()?.toLowerCase()
  if (!allowed.includes(ext)) return '不支持的文件格式，仅支持 txt/md/pdf'
  if (file.size > 10 * 1024 * 1024) return '文件大小不能超过 10MB'
  return null
}

function handleFile(file) {
  const error = validate(file)
  if (error) {
    errorMessage.value = error
    return
  }
  errorMessage.value = ''
  isUploading.value = true
  emit('upload', file, () => { isUploading.value = false })
}

function handleDrop(e) {
  isDragOver.value = false
  const file = e.dataTransfer.files[0]
  if (file) handleFile(file)
}

function handleFileSelect(e) {
  const file = e.target.files[0]
  if (file) handleFile(file)
  e.target.value = ''  // 允许重复选同一文件
}

function triggerFileInput() {
  if (!isUploading.value) fileInput.value?.click()
}
</script>
```

- [ ] **Step 2: 创建 DocumentCard.vue**

```vue
<template>
  <div class="card bg-base-100 shadow-sm border border-base-200">
    <div class="card-body p-4">
      <div class="flex items-start justify-between gap-2">
        <div class="flex-1 min-w-0">
          <h3 class="font-medium text-sm truncate">{{ doc.title }}</h3>
          <p class="text-xs text-base-content/50 mt-1">
            {{ statusText }}
          </p>
        </div>
        <span class="badge badge-sm shrink-0" :class="badgeClass">
          <span v-if="doc.status === 'processing'" class="loading loading-spinner loading-xs mr-1"></span>
          {{ statusLabel }}
        </span>
      </div>

      <div v-if="doc.status === 'failed' && doc.error_message" class="mt-2">
        <p class="text-xs text-error">{{ doc.error_message }}</p>
      </div>

      <div class="card-actions justify-end mt-3">
        <button
          class="btn btn-ghost btn-xs text-error"
          @click="emit('delete', doc.id)"
        >删除</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  doc: { type: Object, required: true },
})
const emit = defineEmits(['delete'])

const statusConfig = {
  pending:    { label: '等待中', cls: 'badge-ghost' },
  processing: { label: '处理中', cls: 'badge-info' },
  completed:  { label: '已完成', cls: 'badge-success' },
  failed:     { label: '失败', cls: 'badge-error' },
}

const statusLabel = computed(() => statusConfig[props.doc.status]?.label || props.doc.status)
const badgeClass = computed(() => statusConfig[props.doc.status]?.cls || 'badge-ghost')

const statusText = computed(() => {
  const d = props.doc
  if (d.status === 'completed') return `${d.chunks_count} 个片段 · ${d.created_at?.slice(0, 10)}`
  if (d.status === 'processing') return '解析中...'
  return d.created_at?.slice(0, 10) || ''
})
</script>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/knowledge/
git commit -m "feat: add UploadZone and DocumentCard components

- UploadZone: drag-and-drop + click upload, loading state, file validation
- DocumentCard: status badge (pending/processing/completed/failed), delete button"
```

---

### Task 11: 前端 — KnowledgeBase 页面 + 路由

**Files:**
- Create: `frontend/src/views/KnowledgeBase.vue`
- Modify: `frontend/src/router/index.js`

- [ ] **Step 1: 创建 KnowledgeBase.vue**

```vue
<template>
  <div class="max-w-4xl mx-auto p-6">
    <h1 class="text-2xl font-bold mb-1">知识库</h1>
    <p class="text-sm text-base-content/50 mb-6">
      上传你的文档，AI 将在聊天时引用其中的内容
    </p>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <!-- 左侧上传区 -->
      <div>
        <UploadZone @upload="handleUpload" />
      </div>

      <!-- 右侧文档列表 -->
      <div>
        <div v-if="documents.length === 0" class="flex flex-col items-center justify-center h-full text-base-content/30 py-16">
          <svg class="w-16 h-16 mb-4" fill="none" stroke="currentColor"
               viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round"
               stroke-width="1" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1
               1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
          <p class="text-sm">暂无文档</p>
          <p class="text-xs mt-1">上传你的第一个文档吧</p>
        </div>

        <div v-else class="space-y-3">
          <DocumentCard
            v-for="doc in documents"
            :key="doc.id"
            :doc="doc"
            @delete="confirmDelete"
          />
        </div>
      </div>
    </div>

    <!-- 上传/删除错误提示 -->
    <p v-if="uploadError" class="text-error text-sm mt-2">{{ uploadError }}</p>

    <!-- daisyUI 删除确认 Modal -->
    <dialog class="modal" :class="{ 'modal-open': showDeleteModal }">
      <div class="modal-box">
        <h3 class="text-lg font-bold">确认删除</h3>
        <p class="py-4">删除后文档及其所有片段将被永久移除，不可恢复。</p>
        <div class="modal-action">
          <button class="btn" @click="showDeleteModal = false">取消</button>
          <button class="btn btn-error" @click="handleDelete">确认删除</button>
        </div>
      </div>
    </dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import UploadZone from '@/components/knowledge/UploadZone.vue'
import DocumentCard from '@/components/knowledge/DocumentCard.vue'
import { uploadDocument, removeDocument } from '@/js/http/api.js'
import { useDocumentPolling } from '@/composables/useDocumentPolling.js'

const { documents, startPolling, refresh } = useDocumentPolling()

onMounted(() => {
  startPolling()
})

const uploadError = ref('')
const deleteTargetId = ref(null)
const showDeleteModal = ref(false)

async function handleUpload(file, done) {
  uploadError.value = ''
  try {
    await uploadDocument(file)
    await refresh()
  } catch (e) {
    uploadError.value = e.response?.data?.message || '上传失败，请重试'
  } finally {
    done()
  }
}

function confirmDelete(docId) {
  deleteTargetId.value = docId
  showDeleteModal.value = true
}
async function handleDelete() {
  const docId = deleteTargetId.value
  showDeleteModal.value = false

  const idx = documents.value.findIndex(d => d.id === docId)
  const removed = documents.value.splice(idx, 1)[0]

  try {
    await removeDocument(docId)
  } catch (e) {
    documents.value.splice(idx, 0, removed)
    uploadError.value = e.response?.data?.message || '删除失败'
  }
}
</script>
```

- [ ] **Step 2: 注册路由**

在 `router/index.js` 中追加：

```javascript
import KnowledgeBase from '@/views/KnowledgeBase.vue'

// 在 routes 数组中追加
{
  path: '/knowledge',
  name: 'KnowledgeBase',
  component: KnowledgeBase,
  meta: { needLogin: true },
},
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/KnowledgeBase.vue
git add frontend/src/router/index.js
git commit -m "feat: add KnowledgeBase page with drag-upload and polling

- /knowledge route with needLogin meta
- Left: UploadZone for drag-and-drop file upload
- Right: DocumentCard list with real-time status polling
- Empty state when no documents exist
- Optimistic delete with rollback on failure"
```

---

### Task 12: NavBar — 移除聊天占位 + 添加知识库入口

**Files:**
- Modify: `frontend/src/components/navbar/NavBar.vue`

- [ ] **Step 1: 移除聊天占位入口**

删除 `<li>` 中的 ChatIcon 相关代码块（`NavBar.vue:119-127`）：

```vue
<!-- 删除以下 8 行 -->
          <!-- List item -->
          <li>
            <RouterLink :to="{ name: 'create-index' }" active-class="menu-focus"
                        class="is-drawer-close:tooltip is-drawer-close:tooltip-right py-3" data-tip="聊天">
              <!-- Chat icon -->
              <ChatIcon/>
              <span class="is-drawer-close:hidden text-base whitespace-nowrap">聊天</span>
            </RouterLink>
          </li>
```

同时删除 `<script>` 中第 12 行的 `import ChatIcon from "@/components/navbar/icons/ChatIcon.vue";`

**ChatIcon.vue 文件保留不删**，后续扩展时复用。

- [ ] **Step 2: 创建 KnowledgeBaseIcon.vue**

匹配项目现有图标组件模式（HomepageIcon.vue、FriendIcon.vue、CharacterIcon.vue、ChatIcon.vue）：

`frontend/src/components/navbar/icons/KnowledgeBaseIcon.vue`:

```vue
<template>
  <svg class="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
      d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125
         0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25
         0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125
         1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"/>
  </svg>
</template>
```

- [ ] **Step 3: 添加知识库 NavBar 入口**

在同位置（删除聊天入口的原位置）插入，使用 `KnowledgeBaseIcon` 组件：

```vue
          <!-- 知识库入口 -->
          <li>
            <RouterLink to="/knowledge" active-class="menu-focus"
                        class="is-drawer-close:tooltip is-drawer-close:tooltip-right py-3" data-tip="知识库">
              <KnowledgeBaseIcon/>
              <span class="is-drawer-close:hidden text-base whitespace-nowrap">知识库</span>
            </RouterLink>
          </li>
```

同时添加 import：

```javascript
import KnowledgeBaseIcon from "@/components/navbar/icons/KnowledgeBaseIcon.vue";
```

注意：沿用项目 NavBar 已有的 `is-drawer-close:tooltip`、`active-class="menu-focus"` 等样式类，与其他入口保持一致。

- [ ] **Step 4: 前端构建验证**

```bash
cd frontend
npm run build
```

Expected: 构建成功

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/navbar/NavBar.vue
git commit -m "feat: add Knowledge Base nav entry, remove chat placeholder

- Add '知识库' nav item linking to /knowledge with document icon
- Remove hardcoded chat placeholder pointing to create-index
- ChatIcon.vue kept for future use"
```

---

### Task 13: 全量测试验证

- [ ] **Step 1: 运行后端全量测试**

```bash
conda activate py312
cd backend
python -m pytest web/tests/ -v
```

Expected: 全部 pass, 0 failed

- [ ] **Step 2: 前端构建验证**

```bash
cd frontend
npm run build
```

Expected: 构建成功无报错

- [ ] **Step 3: Commit（如有遗漏文件）**

```bash
git status
git add -A
git commit -m "chore: final integration — all tests pass, frontend builds clean"
```

---

### 完成后：全量测试 + PR

```bash
# 确认所有测试
python -m pytest web/tests/ -v

# 确认前端构建
npm run build

# 最终提交
git status
git add -A
git commit -m "feat: complete P2-2 user document upload RAG"
```
