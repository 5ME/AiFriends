# Phase 2.6: 系统知识库增量更新 — 设计文档

> **Date:** 2026-06-09 | **Phase:** 2.6 | **Priority:** P2
> **基于:** roadmap §Phase 2, 项目Review报告(2026-05-31)

## 1. 问题

当前 `insert_documents.py` 的 `_insert_with_loader` 每次执行都是完整流程：

```
load → chunk → 全量删除旧 chunks → 全量 embedding → 全量插入
```

问题：每次执行都重新调用 embedding API 处理**所有** chunk，即使内容完全没变。`text-embedding-v4` 按 token 计费，重复 embedding 浪费成本和时间。

## 2. 设计目标

- 系统知识库支持增量更新：只有新增或变更的 chunk 才重新 embedding
- 内容未变的 chunk 原地保留，不删不插
- 新增 `raw/` 目录下已有的 2 个未导入文件

## 3. 设计决策

### 3.1 hash 内容：只 hash content

**选：只对 `content`（chunk 文本）做 SHA-256。  
不选：hash `content + metadata`。**

| | 只 hash content（选） | hash content + metadata（不选） |
|---|---|---|
| content 变 | 重 embed ✅ | 重 embed ✅ |
| metadata 变（content 不变） | 不重 embed — 旧 metadata 保留 | 重 embed — 元数据更新 |
| API 调用 | 更少 | 更多 |
| 实际影响 | metadata 极少单独变化 | 引用来源始终最新 |

选择理由：

1. **embedding 只由 content 决定。** `CustomEmbeddings.embed_documents(texts)` 仅读取 `page_content`，metadata 不进入向量空间。检索结果不受 metadata 影响。
2. **metadata 极少单独变化。** 系统知识库文档结构稳定，标题层级几乎不会单独变。
3. **成本优先。** embedding API 按 token 计费，为 metadata 变化重 embed 不值得。
4. **语义一致。** content 相同 → embedding 相同 → hash 匹配即可跳过。

### 3.2 用户文档不改动

Phase 2.6 只改系统知识库（`insert_documents.py`）。用户文档每次上传都是新建 `UserDocument`，不存在"重复 embedding 同一 doc"的问题，无需 hash 逻辑。

## 4. 实现方案

### 4.1 模型变更

`DocumentChunk` 新增字段：

```python
content_hash = models.CharField(max_length=64, blank=True, default='',
                                help_text='SHA-256 of content for incremental update')
```

- `max_length=64` — SHA-256 十六进制固定 64 字符
- `blank=True, default=''` — 兼容历史数据（旧 chunk hash 为空）
- 需生成一条 migration

### 4.2 `_insert_with_loader` 增量算法

```python
import hashlib

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _insert_with_loader(title: str, file_path: str, file_type: str):
    # 1. load + chunk
    loader = get_loader(file_type)
    new_chunks = chunk_documents(loader.load(file_path))

    # 2. get_or_create 系统文档
    sys_doc, _ = UserDocument.objects.get_or_create(
        title=title, defaults={'status': 'completed'}
    )

    # 3. 查询已有 chunks，按 chunk_index 索引
    old_chunks = {
        c.chunk_index: c
        for c in DocumentChunk.objects.filter(document=sys_doc)
    }
    old_indexes = set(old_chunks.keys())
    new_indexes = set(range(len(new_chunks)))

    # 4. 分类：新增/更新（需 embed）/ 保留 / 删除
    to_embed = []          # (chunk, chunk_index, new_hash) — 需要 embedding

    for i, chunk in enumerate(new_chunks):
        new_hash = _sha256(chunk.page_content)
        old = old_chunks.get(i)
        if old and old.content_hash == new_hash:
            continue          # hash 匹配 → 保留不动
        to_embed.append((chunk, i, new_hash))

    to_remove = old_indexes - new_indexes

    # 5. 删除需要替换的旧 chunks（批量 delete）
    replace_indexes = {i for _, i, _ in to_embed} & old_indexes
    if replace_indexes:
        DocumentChunk.objects.filter(
            document=sys_doc, chunk_index__in=list(replace_indexes)
        ).delete()

    # 6. 批量 embedding + 批量插入（只处理需要更新的 chunk）
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
        sys_doc.chunks_count = len(new_chunks)
        sys_doc.save(update_fields=['chunks_count'])
    logger.info('已更新 %d 条向量记录 → %s', len(new_chunks), title)
```

### 4.3 新增 2 个系统文档

```python
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

## 5. 边界情况

| 场景 | 行为 |
|------|------|
| 首次执行（无旧 chunks） | `old_chunks` 为空 → 全部进入 `to_embed`，正常处理 |
| 重复执行（内容完全不变） | 所有 hash 匹配 → `to_embed` 为空 → 不调 API |
| 部分 chunk 内容变了 | 只 embed 变化的 chunk，不变的原地保留 |
| 新文件比旧文件少 chunk 段 | `to_remove = old_indexes - new_indexes`，多余 chunk 被删除 |
| 新文件比旧文件多 chunk 段 | 多出的 chunk 进入 `to_embed` |
| 历史数据 `content_hash=''` | 空 hash ≠ 新 hash → 触发重新 embedding（正确兜底） |

## 6. 测试用例

| # | 测试 | 场景 | 验证点 |
|---|------|------|--------|
| 1 | 首次导入 | 无旧数据 | 所有 chunk 都被 embed + 插入 |
| 2 | 重复导入（内容不变） | 全 hash 匹配 | 不调 embedding API，chunk 数不变 |
| 3 | 部分更新 | 改一个 chunk 内容 | 只 embed 变化的 chunk，其他不动 |
| 4 | 新增 chunk | 文件内容增多 | 新 chunk 被 embed + 插入 |
| 5 | 删除多余 chunk | 文件内容减少 | 多余的旧 chunk 被删除 |
| 6 | 历史数据兜底 | `content_hash=''` | 重新 embedding（与首次行为一致） |

测试沿用 `@patch("web.documents.utils.insert_documents.CustomEmbeddings")` mock 模式。

## 7. 影响范围

| 文件 | 变更 | 说明 |
|------|------|------|
| `web/models/document.py` | 修改 | DocumentChunk 新增 `content_hash` 字段 |
| `web/migrations/XXXX_add_content_hash.py` | 新增 | migration |
| `web/documents/utils/insert_documents.py` | 重写 | `_insert_with_loader` 改为增量算法 + 新增 2 个文件 |
| `web/tests/test_document.py` | 修改 | 更新 insert_documents 测试 + 新增增量测试 |

---

*Design Date: 2026-06-09*
*Based on: roadmap Phase 2, insert_documents.py 当前实现*
