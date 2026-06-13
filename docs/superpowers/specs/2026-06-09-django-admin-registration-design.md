# Phase 2.4: Django Admin 注册 — 设计文档

> **Date:** 2026-06-09 | **Phase:** 2.4 | **Priority:** P2
> **基于:** roadmap §Phase 2, 项目Review报告(2026-05-31)

## 1. 背景

当前 `web/admin.py` 已注册 UserProfile、Character、Voice、Friend、Message、SystemPrompt，但 UserDocument 和 DocumentChunk 未注册。运维排查文档处理问题时只能直接查数据库，效率低。

## 2. 设计目标

- UserDocument + DocumentChunk 注册到 Django Admin
- 支持按 title/owner 搜索
- 支持按 status/file_type 过滤
- 展示 chunks_count、error_message 等运维关注字段

## 3. 实现方案

新增 import：

```python
from web.models.document import UserDocument, DocumentChunk
```

### 3.1 UserDocumentAdmin

```python
@admin.register(UserDocument)
class UserDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'file_type', 'status',
                    'chunks_count', 'created_at')
    search_fields = ('title', 'owner__user__username')
    list_filter = ('status', 'file_type')
    readonly_fields = ('chunks_count', 'celery_task_id', 'created_at', 'updated_at')
    raw_id_fields = ('owner',)
```

| 配置 | 值 | 理由 |
|------|-----|------|
| `list_display` | title, owner, file_type, status, chunks_count, created_at | 运维最关心的 6 个字段 |
| `search_fields` | title, owner__user__username | 按文档名搜 / 按用户名搜 |
| `list_filter` | status, file_type | 快速筛选失败文档 / 只看 PDF |
| `readonly_fields` | chunks_count, celery_task_id, created_at, updated_at | 系统自动维护，人工改会破坏一致性 |

不展示的字段：
- `error_message` — TextField 太宽放列表会撑爆，详情页自然可见
- `file_url` — 内部存储路径，运维无需关注

### 3.2 DocumentChunkAdmin

```python
@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ('document', 'chunk_index', 'token_count', 'owner', 'created_at')
    search_fields = ('content', 'document__title')
    list_filter = ('document__file_type',)
    exclude = ('embedding',)
    list_select_related = ('document', 'owner')
    raw_id_fields = ('document', 'owner')
```

| 配置 | 值 | 理由 |
|------|-----|------|
| `list_display` | document, chunk_index, token_count, owner, created_at | chunk 索引、所属文档、字符数 |
| `search_fields` | content, document__title | 全文搜 chunk 内容 / 按文档标题搜 chunk |
| `list_filter` | document__file_type | 按文档类型间接筛选 chunk |
| `exclude` | embedding | 1024 维向量，给人看无意义（见 §3.3） |
| `list_select_related` | document, owner | 避免 FK 字段的 N+1 查询

### 3.3 设计决策：embedding 排除

**选：`exclude = ('embedding',)`（列表和详情页都不展示）。  
不选：`list_display` 不含但详情页展示。**

| | 排除 | 详情页展示 |
|---|---|---|
| 实用价值 | Admin 不需要看向量 | 渲染 1024 浮点数到 input，无实用价值 |
| 安全性 | 无编辑入口 → 无误操作风险 | 手动编辑保存会损坏向量数据 |
| 性能 | 不渲染 → 页面秒开 | 渲染 1024 个数字 → 慢 |

选择理由：Admin 是给人运维用的，embedding 是给 pgvector 做余弦检索用的。调试 embedding 质量用 `python manage.py shell` 跑相似度查询比在 Admin 翻向量高效。

## 4. 影响范围

| 文件 | 变更 | 说明 |
|------|------|------|
| `web/admin.py` | 修改 | 新增 1 行 import + UserDocumentAdmin + DocumentChunkAdmin，约 18 行 |

无 migration、无 view 变更、无前端变更。

## 5. 测试

| # | 测试 | 验证点 |
|---|------|--------|
| 1 | Admin changelist 可访问 | UserDocument + DocumentChunk Admin 页面返回 200 |
| 2 | search_fields 生效 | 搜索 title 能找到对应 doc |

测试文件：`web/tests/test_admin.py`（新增）。

---

*Design Date: 2026-06-09*
*Based on: roadmap Phase 2, 项目Review报告(2026-05-31)*
