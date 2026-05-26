# DocumentChunk 元数据 + UserDocument 模型设计

> **Date:** 2026-05-23 | **Scope:** 纯后端数据模型层，不改 API，不改前端

**Goal:** 为 DocumentChunk 添加元数据字段，新建 UserDocument 模型，创建 pgvector HNSW 索引。测试环境从 SQLite 切换到 PostgreSQL。

---

## 1. 模型设计

### 1.1 UserDocument（新建）

```python
class UserDocument(models.Model):
    owner = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, null=True, blank=True,
        db_index=True,
    )
    title = models.CharField(max_length=200)
    file_url = models.CharField(max_length=500, blank=True, default='')
    file_type = models.CharField(max_length=20, blank=True, default='')
    status = models.CharField(
        max_length=20,
        choices=[('pending', '待处理'), ('processing', '处理中'),
                 ('completed', '已完成'), ('failed', '失败')],
        default='completed',
    )
    error_message = models.TextField(blank=True, default='')
    chunks_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

### 1.2 DocumentChunk（改现有）

**新增字段：**

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `document` | FK→UserDocument, null=True, CASCADE | null | 关联文档 |
| `owner` | FK→UserProfile, null=True, CASCADE | null | 关联用户 |
| `chunk_index` | IntegerField | 0 | 文档内片段序号 |
| `token_count` | IntegerField | 0 | token 数量 |
| `metadata` | JSONField | dict | 扩展信息 |

**新增索引：** `owner` 单列、`document` 单列、HNSW 向量索引。

### 1.3 设计决策

- `owner` 和 `document` 可空：null = 全局知识库
- `UserDocument.title` 无 unique 约束：P2-2 自行决定重名策略（覆盖/拒绝/允许）
- 存量行迁移后新字段 = null/default，查询兼容

---

## 2. pgvector HNSW 索引

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE INDEX document_chunk_embedding_hnsw_idx
  ON web_documentchunk
  USING hnsw (embedding vector_cosine_ops);
```

---

## 3. search_knowledge_base 权限过滤

### 3.1 AgentState 加字段

```python
# graph.py — 改前
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

# graph.py — 改后
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_id: int  # 新增
```

### 3.2 Tool 注入

```python
from langgraph.prebuilt import InjectedState

@tool
def search_knowledge_base(query: str, state: Annotated[dict, InjectedState]) -> str:
    user_id = state.get("user_id")
    emb = CustomEmbeddings().embed_query(query)
    table = DocumentChunk._meta.db_table
    chunks = DocumentChunk.objects.raw(
        f"SELECT id, content, chunk_index, document_id "
        f"FROM {table} "
        f"WHERE owner_id IS NULL OR owner_id = %s "
        f"ORDER BY embedding <=> %s::vector LIMIT 3",
        [user_id, emb]
    )
    return ...
```

### 3.3 调用链

```
chat.py: inputs = {"messages": [...], "user_id": request.user.userprofile.id}
  → graph.invoke(inputs)
    → LLM 决定调用 search_knowledge_base(query, ...)
      → InjectedState 注入 state → tool 拿到 user_id
        → pgvector: WHERE owner_id IS NULL OR owner_id = %s
```

`state.get("user_id")` 返回 None 时退化为纯全局搜索，不崩溃。

---

## 4. insert_documents.py 适配

两个函数各改 3 点：

```python
# 1. get_or_create 系统文档记录（重复执行不产生重复记录）
sys_doc, _ = UserDocument.objects.get_or_create(
    title='百炼平台概述',
    defaults={'status': 'completed'}
)

# 2. 只删自己的旧 chunks（不动其他文档或用户的 chunks）
DocumentChunk.objects.filter(document=sys_doc).delete()

# 3. 插入时绑定 document + chunk_index
for i, chunk in enumerate(chunks):
    DocumentChunk.objects.create(
        content=chunk.page_content,
        embedding=emb,
        document=sys_doc,
        owner=None,
        chunk_index=i,
    )

sys_doc.chunks_count = len(chunks)
sys_doc.save()
```

---

## 5. 测试环境 SQLite → PostgreSQL

### 5.1 settings.py

```python
if _is_pytest():
    DATABASES['default']['NAME'] = f"{PG_NAME}_test"
```

### 5.2 conftest.py 新增

```python
@pytest.fixture(scope="session", autouse=True)
def test_database_setup(django_db_setup, django_db_blocker):
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
```

### 5.3 前置条件

```bash
docker exec -it <pg-container> psql -U <user> -c "CREATE DATABASE aifriends_test;"
```

### 5.4 测试改动

| 文件 | 改动 |
|------|------|
| `test_chat_agent.py` | `search_knowledge_base` 测试从 mock raw 改为真实 PG 插入/查询 |
| `test_document.py`（新） | UserDocument CRUD、DocumentChunk 关联、insert_documents 幂等性、owner 过滤 |
| `conftest.py` | 可能新增 `user_document` fixture |

---

## 6. 风险清单

| 风险 | 缓解 |
|------|------|
| 测试库 `aifriends_test` 不存在 | 手动 `CREATE DATABASE`，Docker Compose 时自动化 |
| 不传 `user_id` 时崩溃 | `state.get("user_id")` 返回 None → 退化为纯全局搜索 |
| HNSW 在低版本 PG 不可用 | PG 17 + pgvector 0.8 完全支持 |

---

## 7. 验证清单

```
[ ] UserDocument.objects.get_or_create() 重复执行不产生重复记录
[ ] DocumentChunk.document FK 关联 UserDocument 正常
[ ] owner IS NULL 查询全局知识库
[ ] owner = user_id 查询个人知识库
[ ] search_knowledge_base 混合召回全局 + 个人 chunks
[ ] insert_documents 只删自己文档的旧 chunks，不动其他文档
[ ] HNSW 索引存在且生效
[ ] 不传 user_id 时退化为全局搜索，不崩溃
[ ] pytest 全部通过（PG 真实环境）
```
