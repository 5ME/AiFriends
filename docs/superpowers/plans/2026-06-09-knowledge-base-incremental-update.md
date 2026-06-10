# Phase 2.6: 系统知识库增量更新 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `insert_documents.py` 从全量删除+全量插入改为 SHA-256 hash 对比增量更新，避免重复 embedding 浪费。

**Architecture:** DocumentChunk 新增 `content_hash` 字段；`_insert_with_loader` 改为 hash 对比算法：匹配保留、变更的批量 embed+bulk_create、多余的删除；新增 2 个 raw 文件导入。

**Tech Stack:** Django ORM, Python hashlib, pgvector

**Design doc:** `docs/superpowers/specs/2026-06-09-knowledge-base-incremental-update-design.md`

---

### File Structure

| 文件 | 职责 |
|------|------|
| `web/models/document.py` | DocumentChunk 新增 `content_hash` CharField |
| `web/migrations/XXXX_*.py` | Auto-generated migration |
| `web/documents/utils/insert_documents.py` | 重写 `_insert_with_loader` 增量算法 + 新增 2 个文档 |
| `web/tests/test_document.py` | 更新 3 个旧测试 + 新增 6 个增量测试 |

---

### Task 1: 模型新增 `content_hash` + Migration

**Files:**
- Modify: `web/models/document.py`
- Create: Migration (auto)

- [ ] **Step 1: 添加字段到 DocumentChunk**

`web/models/document.py` 的 `DocumentChunk` 类中，`chunk_index` 之后插入：

用 Edit 工具：
`old_string`:
```
    chunk_index = models.IntegerField(default=0)
    token_count = models.IntegerField(default=0)
```
`new_string`:
```
    chunk_index = models.IntegerField(default=0)
    token_count = models.IntegerField(default=0)
    content_hash = models.CharField(max_length=64, blank=True, default='',
                                    help_text='SHA-256 of content for incremental update')
```

- [ ] **Step 2: 生成并应用 migration**

```bash
cd backend && D:\MyWork\Miniconda3\envs\py312\python.exe manage.py makemigrations web --name add_content_hash
```
Expected: `web/migrations/XXXX_add_content_hash.py` created.

```bash
cd backend && D:\MyWork\Miniconda3\envs\py312\python.exe manage.py migrate
```
Expected: "Applying web.XXXX_add_content_hash... OK"

- [ ] **Step 3: Commit**

```bash
git add backend/web/models/document.py backend/web/migrations/*add_content_hash*.py
git commit -m "feat: DocumentChunk 新增 content_hash 字段，用于增量更新"
```

---

### Task 2: 重写 `insert_documents.py` — 增量算法

**Files:**
- Modify: `web/documents/utils/insert_documents.py`

- [ ] **Step 1: 替换整个文件内容**

用 Write 工具覆盖 `web/documents/utils/insert_documents.py`：

```python
"""系统知识库批量导入 — hash 对比增量更新"""
import hashlib
import logging

from web.documents.loaders import get_loader
from web.documents.services import CustomEmbeddings, chunk_documents
from web.models.document import DocumentChunk, UserDocument

logger = logging.getLogger(__name__)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _insert_with_loader(title: str, file_path: str, file_type: str):
    """增量导入：只 embed 新增/变更的 chunk，内容不变的原地保留"""
    # 1. load + chunk
    loader = get_loader(file_type)
    new_chunks = chunk_documents(loader.load(file_path))

    # 2. get_or_create 系统文档
    sys_doc, _ = UserDocument.objects.get_or_create(
        title=title,
        defaults={'status': 'completed'}
    )

    # 3. 查询已有 chunks，按 chunk_index 索引
    old_chunks = {
        c.chunk_index: c
        for c in DocumentChunk.objects.filter(document=sys_doc)
    }
    old_indexes = set(old_chunks.keys())
    new_indexes = set(range(len(new_chunks)))

    # 4. 分类：需要 embedding 的 chunk
    to_embed = []

    for i, chunk in enumerate(new_chunks):
        new_hash = _sha256(chunk.page_content)
        old = old_chunks.get(i)
        if old and old.content_hash == new_hash:
            continue          # hash 匹配 → 保留不动
        to_embed.append((chunk, i, new_hash))

    to_remove = old_indexes - new_indexes

    # 5. 批量删除需要替换的旧 chunks
    replace_indexes = {i for _, i, _ in to_embed} & old_indexes
    if replace_indexes:
        DocumentChunk.objects.filter(
            document=sys_doc, chunk_index__in=list(replace_indexes)
        ).delete()

    # 6. 批量 embedding + 批量插入
    changed = False
    if to_embed:
        texts = [c.page_content for c, _, _ in to_embed]
        vectors = CustomEmbeddings(user_id=None).embed_documents(texts)
        objs = [
            DocumentChunk(
                content=chunk.page_content, embedding=vector,
                document=sys_doc, chunk_index=i,
                content_hash=new_hash,
                token_count=len(chunk.page_content),
                metadata=chunk.metadata,
            )
            for (chunk, i, new_hash), vector in zip(to_embed, vectors)
        ]
        DocumentChunk.objects.bulk_create(objs, batch_size=50)
        changed = True

    # 7. 删除多余的旧 chunks
    if to_remove:
        DocumentChunk.objects.filter(
            document=sys_doc, chunk_index__in=list(to_remove)
        ).delete()
        changed = True

    # 8. 仅在变更时更新 doc 元信息
    if changed:
        sys_doc.chunks_count = DocumentChunk.objects.filter(
            document=sys_doc
        ).count()
        sys_doc.save(update_fields=['chunks_count'])

    logger.info('已更新 %d 条向量记录 → %s', sys_doc.chunks_count, title)


def insert_documents():
    _insert_with_loader('百炼平台概述',
                        './web/documents/raw/Bailian_Overview.txt', 'txt')
    _insert_with_loader('百炼平台概述 Markdown',
                        './web/documents/raw/Bailian_Overview.md', 'md')
    _insert_with_loader('Claude Prompting Best Practices',
                        './web/documents/raw/claude-prompting-best-practices.md', 'md')
    _insert_with_loader('Coding Plan Overview',
                        './web/documents/raw/coding-plan-overview.md', 'md')


def insert_markdown_documents():
    _insert_with_loader('百炼平台概述 Markdown',
                        './web/documents/raw/Bailian_Overview.md', 'md')
```

- [ ] **Step 2: Commit**

```bash
git add backend/web/documents/utils/insert_documents.py
git commit -m "feat: insert_documents 改为 hash 对比增量更新，避免重复 embedding"
```

---

### Task 3: 更新现有测试 + 新增增量测试

**Files:**
- Modify: `web/tests/test_document.py`

- [ ] **Step 1: 更新 test_insert_documents_idempotent — 验证第二次不调 API**

当前代码（L111-131）。在 `insert_documents()` 第二次调用后、`assert chunk_count_2 == chunk_count_1` 之后，新增：

```python
        # 第二次执行：hash 匹配，不应再次调用 embedding API
        mock_embeddings.embed_documents.assert_called_once()
```

用 Edit 工具：
`old_string`:
```
        insert_documents()
        chunk_count_2 = DocumentChunk.objects.filter(
            document__title='百炼平台概述'
        ).count()
        assert chunk_count_2 == chunk_count_1
        assert UserDocument.objects.filter(title='百炼平台概述').count() == 1
```
`new_string`:
```
        insert_documents()
        chunk_count_2 = DocumentChunk.objects.filter(
            document__title='百炼平台概述'
        ).count()
        assert chunk_count_2 == chunk_count_1
        assert UserDocument.objects.filter(title='百炼平台概述').count() == 1
        # 第二次执行：hash 匹配，不应再次调用 embedding API
        mock_embeddings.embed_documents.assert_called_once()
```

- [ ] **Step 2: 同样更新 test_insert_markdown_documents_idempotent**

`old_string`:
```
        insert_markdown_documents()
        count_2 = DocumentChunk.objects.filter(
            document__title='百炼平台概述 Markdown'
        ).count()
        assert count_2 == count_1
```
`new_string`:
```
        insert_markdown_documents()
        count_2 = DocumentChunk.objects.filter(
            document__title='百炼平台概述 Markdown'
        ).count()
        assert count_2 == count_1
        # 第二次执行：hash 匹配，不应再次调用 embedding API
        mock_embeddings.embed_documents.assert_called_once()
```

- [ ] **Step 3: 更新 test_delete_only_own_chunks — 新增 content_hash 断言**

当前（L154-181）。在 `assert other_count == 1` 之后新增：

```python
        # 验证 content_hash 已设置
        own_chunks = DocumentChunk.objects.filter(document__title='百炼平台概述')
        for c in own_chunks:
            assert c.content_hash != ''  # SHA-256 64-char
            assert len(c.content_hash) == 64
```

用 Edit 工具：
`old_string`:
```
        assert other_count == 1
        assert DocumentChunk.objects.get(document=other_doc).content == 'keep me'
```
`new_string`:
```
        assert other_count == 1
        assert DocumentChunk.objects.get(document=other_doc).content == 'keep me'
        # 验证 content_hash 已设置
        own_chunks = DocumentChunk.objects.filter(document__title='百炼平台概述')
        for c in own_chunks:
            assert c.content_hash != ''
            assert len(c.content_hash) == 64
```

- [ ] **Step 4: 新增测试 #2 — 重复导入不调 API**

在 `TestInsertDocuments` 类末尾新增：

```python
    @patch("web.documents.utils.insert_documents.CustomEmbeddings")
    def test_repeat_insert_skips_embedding(self, mock_embeddings_class, db):
        """重复导入且内容不变 → 不调用 embedding API"""
        from web.documents.utils.insert_documents import insert_documents

        mock_embeddings = MagicMock()
        mock_embeddings.embed_documents.return_value = [[0.0] * 1024]
        mock_embeddings_class.return_value = mock_embeddings

        insert_documents()
        # 重置 mock，第二次执行
        mock_embeddings.embed_documents.reset_mock()
        insert_documents()

        # 第二次执行不应调用 embedding
        mock_embeddings.embed_documents.assert_not_called()
```

- [ ] **Step 5: 新增测试 #4 — 新增 chunk（新文档）**

```python
    @patch("web.documents.utils.insert_documents.CustomEmbeddings")
    def test_new_document_is_imported(self, mock_embeddings_class, db):
        """新增 raw 文件后的文档 → 正常导入"""
        from web.documents.utils.insert_documents import insert_documents
        from web.models.document import DocumentChunk

        mock_embeddings = MagicMock()
        mock_embeddings.embed_documents.return_value = [[0.0] * 1024]
        mock_embeddings_class.return_value = mock_embeddings

        insert_documents()

        # 新增的 claude-prompting-best-practices.md 应被导入
        count = DocumentChunk.objects.filter(
            document__title='Claude Prompting Best Practices'
        ).count()
        assert count > 0

        # coding-plan-overview.md 也应被导入
        count2 = DocumentChunk.objects.filter(
            document__title='Coding Plan Overview'
        ).count()
        assert count2 > 0
```

- [ ] **Step 6: 新增测试 #5 — 删除多余 chunk**

```python
    @patch("web.documents.utils.insert_documents.CustomEmbeddings")
    def test_extra_chunks_are_removed(self, mock_embeddings_class, db):
        """旧 chunks 中有新文件不存在的 index → 被删除"""
        from web.documents.utils.insert_documents import insert_documents
        from web.models.document import UserDocument, DocumentChunk

        # 手动创建多余的旧 chunk（index=99 不在新文件中）
        sys_doc, _ = UserDocument.objects.get_or_create(
            title='百炼平台概述', defaults={'status': 'completed'}
        )
        DocumentChunk.objects.create(
            content='extra chunk', embedding=[0.0] * 1024,
            document=sys_doc, chunk_index=99,
            content_hash='abc123',
        )
        assert DocumentChunk.objects.filter(document=sys_doc, chunk_index=99).exists()

        mock_embeddings = MagicMock()
        mock_embeddings.embed_documents.return_value = [[0.0] * 1024]
        mock_embeddings_class.return_value = mock_embeddings

        insert_documents()

        # 多余的 chunk_index=99 应被删除
        assert not DocumentChunk.objects.filter(
            document=sys_doc, chunk_index=99
        ).exists()
```

- [ ] **Step 7: 新增测试 #6 — 历史数据兜底**

```python
    @patch("web.documents.utils.insert_documents.CustomEmbeddings")
    def test_historical_empty_hash_triggers_reembed(self, mock_embeddings_class, db):
        """content_hash='' 的历史数据 → 触发重新 embedding"""
        from web.documents.utils.insert_documents import insert_documents
        from web.models.document import UserDocument, DocumentChunk

        # 手动创建旧格式数据（content_hash=''）
        sys_doc, _ = UserDocument.objects.get_or_create(
            title='百炼平台概述', defaults={'status': 'completed'}
        )
        DocumentChunk.objects.create(
            content='stale content', embedding=[0.0] * 1024,
            document=sys_doc, chunk_index=0,
            content_hash='',  # 旧数据无 hash
        )

        mock_embeddings = MagicMock()
        mock_embeddings.embed_documents.return_value = [[0.1] * 1024]
        mock_embeddings_class.return_value = mock_embeddings

        insert_documents()

        # 旧 chunk 应被替换，hash 应更新为非空
        chunks = DocumentChunk.objects.filter(document=sys_doc)
        for c in chunks:
            assert c.content_hash != ''
            assert len(c.content_hash) == 64
```

- [ ] **Step 8: 运行新增测试**

```bash
cd backend && D:\MyWork\Miniconda3\envs\py312\python.exe -m pytest web/tests/test_document.py::TestInsertDocuments -v
```
Expected: All InsertDocuments tests pass (existing + new).

- [ ] **Step 9: Commit**

```bash
git add backend/web/tests/test_document.py
git commit -m "test: insert_documents 增量更新测试 — 跳过重复、新文档、多余删除、历史兜底"
```

---

### Task 4: 全量测试验证 + 提交

- [ ] **Step 1: 运行全量测试**

```bash
cd backend && D:\MyWork\Miniconda3\envs\py312\python.exe -m pytest web/tests/ -v
```
Expected: All tests pass.

- [ ] **Step 2: 设计文档提交**

```bash
git add docs/superpowers/specs/2026-06-09-knowledge-base-incremental-update-design.md docs/superpowers/plans/2026-06-09-knowledge-base-incremental-update.md
git commit -m "docs: Phase 2.6 系统知识库增量更新 — 设计文档 + 实施计划"
```

---

*Plan Date: 2026-06-09*
*Based on: docs/superpowers/specs/2026-06-09-knowledge-base-incremental-update-design.md*
