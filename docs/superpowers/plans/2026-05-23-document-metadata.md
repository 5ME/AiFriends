# DocumentChunk 元数据 + UserDocument 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新建 UserDocument 模型，为 DocumentChunk 添加元数据字段，pgvector HNSW 索引，search_knowledge_base 用户隔离，测试环境切换到 PostgreSQL。

**Architecture:** 7 个独立 Task，每个 Task 有完整的 test → implement → verify → commit 循环。

**Tech Stack:** Django 6.0, PostgreSQL 17 + pgvector 0.8, LangGraph 1.1.4, pytest

**Branch:** `feature/gqyin/document-metadata`

---

## File Map

| 文件 | 操作 | 所属 Task |
|------|------|-----------|
| `backend/web/models/document.py` | Modify | Task 1 |
| `backend/web/migrations/0013_*.py` | Create (auto) | Task 1 |
| `backend/backend/settings.py` | Modify | Task 2 |
| `backend/web/tests/conftest.py` | Modify | Task 2 |
| `backend/web/documents/utils/insert_documents.py` | Modify | Task 3 |
| `backend/web/views/friend/message/chat/graph.py` | Modify | Task 4 |
| `backend/web/views/friend/message/chat/chat.py` | Modify | Task 5 |
| `backend/web/tests/test_document.py` | Create | Task 6 |
| `backend/web/tests/test_chat_agent.py` | Modify | Task 7 |

---

### Task 1: UserDocument 模型 + DocumentChunk 新字段 + HNSW 索引

**Files:**
- Modify: `backend/web/models/document.py`
- Create: `backend/web/migrations/0013_*.py`（makemigrations 自动生成）

TDD 不适用于模型创建（Django 的 migration 本身就是基础设施），直接实现后验证。

- [ ] **Step 1: 修改 models/document.py**

```python
from django.db import models
from pgvector.django import VectorField


class UserDocument(models.Model):
    """用户上传的文档 / 系统知识库文档"""
    owner = models.ForeignKey(
        'user.UserProfile', on_delete=models.CASCADE, null=True, blank=True,
        db_index=True,
    )
    title = models.CharField(max_length=200)
    file_url = models.CharField(max_length=500, blank=True, default='')
    file_type = models.CharField(max_length=20, blank=True, default='')
    status = models.CharField(
        max_length=20,
        choices=[('pending', 'pending'), ('processing', 'processing'),
                 ('completed', 'completed'), ('failed', 'failed')],
        default='completed',
    )
    error_message = models.TextField(blank=True, default='')
    chunks_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        owner_name = self.owner.user.username if self.owner else 'system'
        return f'{self.title} - {owner_name}'


class DocumentChunk(models.Model):
    content = models.TextField()
    embedding = VectorField(dimensions=1024)
    document = models.ForeignKey(
        UserDocument, on_delete=models.CASCADE, null=True, blank=True,
        db_index=True,
    )
    owner = models.ForeignKey(
        'user.UserProfile', on_delete=models.CASCADE, null=True, blank=True,
        db_index=True,
    )
    chunk_index = models.IntegerField(default=0)
    token_count = models.IntegerField(default=0)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['owner']),
            models.Index(fields=['document']),
        ]

    def __str__(self):
        return f'Chunk {self.chunk_index} of {self.document_id}'
```

- [ ] **Step 2: 生成 migration**

```bash
cd backend && python manage.py makemigrations web --name add_userdocument_documentchunk_metadata
```

- [ ] **Step 3: 编辑 migration 文件，手动加入 HNSW 索引**

在 `operations` 列表中加入：

```python
from pgvector.django import HnswIndex

operations = [
    migrations.CreateModel(name='UserDocument', ...),
    migrations.AddField(...),  # DocumentChunk 新字段
    migrations.AddIndex(...),  # owner, document 索引
    # 手动添加以下：
    migrations.RunSQL(
        sql="CREATE EXTENSION IF NOT EXISTS vector",
        reverse_sql="",
    ),
    HnswIndex(
        model_name='documentchunk',
        name='document_chunk_embedding_hnsw_idx',
        fields=['embedding'],
        opclasses=['vector_cosine_ops'],
    ),
]
```

> **注意：** Django 的 `makemigrations` 不会自动生成 HNSW 索引。需手动在 migration 文件中添加 `from pgvector.django import HnswIndex` 和使用 `HnswIndex()` 或原始的 `RunSQL`。

- [ ] **Step 4: 运行 migration**

```bash
cd backend && python manage.py migrate
```

预期：`Applying web.0013_add_userdocument_documentchunk_metadata... OK`

- [ ] **Step 5: 验证 HNSW 索引存在**

```bash
docker exec -it <pg-container> psql -U <user> -d <db> -c "\di document_chunk_embedding_hnsw_idx"
```

- [ ] **Step 6: Commit**

```bash
git add backend/web/models/document.py backend/web/migrations/0013_*.py
git commit -m "feat: add UserDocument model and DocumentChunk metadata fields

- New model UserDocument for document ownership and status tracking
- DocumentChunk gains document FK, owner FK, chunk_index, token_count, metadata
- HNSW vector index on DocumentChunk.embedding for cosine similarity search
- Migration includes CREATE EXTENSION IF NOT EXISTS vector

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: 测试环境 SQLite → PostgreSQL

**Files:**
- Modify: `backend/backend/settings.py`
- Modify: `backend/web/tests/conftest.py`

- [ ] **Step 1: 修改 settings.py — pytest 检测切到 PG**

读 `settings.py` 中 `_is_pytest` 逻辑（约在第 85-101 行），将测试库名改为 PG：

```python
# settings.py — pytest 检测部分
if _is_pytest():
    DATABASES['default']['NAME'] = f"{PG_NAME}_test"
    # 删除之前的 SQLite 整个 ENGINE 替换逻辑
```

> **注意当前代码可能用法：** 当前 `_is_pytest()` 通过 `any('pytest' in arg for arg in sys.argv)` 检测，会切换整个 `DATABASES['default']` 到 SQLite。改为只修改 `NAME`，保持 ENGINE 为 PG。

- [ ] **Step 2: 修改 conftest.py — 添加 pgvector 扩展 fixture**

```python
# conftest.py 新增
@pytest.fixture(scope="session", autouse=True)
def pgvector_extension(django_db_setup, django_db_blocker):
    """确保测试库中 pgvector 扩展可用"""
    from django.db import connection
    with django_db_blocker.unblock():
        with connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
```

- [ ] **Step 3: 确保测试库存在**

```bash
docker exec -it <pg-container> psql -U <user> -c "CREATE DATABASE aifriends_test;"
```

- [ ] **Step 4: 运行现有测试验证环境切换**

```bash
cd backend && python -m pytest web/tests/ -v
```

预期：全部 51 个测试在 PG 上通过（可能有个别 mock 测试需调整）

- [ ] **Step 5: Commit**

```bash
git add backend/backend/settings.py backend/web/tests/conftest.py
git commit -m "test: switch pytest database from SQLite to PostgreSQL

Pytest now uses ${PG_NAME}_test database on the same PG instance.
Add session-scoped fixture to ensure pgvector extension is available.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: insert_documents.py 适配新模型

**Files:**
- Modify: `backend/web/documents/utils/insert_documents.py`

- [ ] **Step 1: 修改 insert_documents()**

```python
def insert_documents():
    loader = TextLoader('./web/documents/Bailian_Overview.txt', encoding='utf-8')
    docs = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = text_splitter.split_documents(docs)
    logger.info('已切分成 %d 个片段', len(chunks))

    embeddings = CustomEmbeddings()

    sys_doc, _ = UserDocument.objects.get_or_create(
        title='百炼平台概述',
        defaults={'status': 'completed'}
    )

    DocumentChunk.objects.filter(document=sys_doc).delete()

    for i, chunk in enumerate(chunks):
        emb = embeddings.embed_query(chunk.page_content)
        DocumentChunk.objects.create(
            content=chunk.page_content,
            embedding=emb,
            document=sys_doc,
            owner=None,
            chunk_index=i,
        )

    sys_doc.chunks_count = len(chunks)
    sys_doc.save()
    logger.info('已插入 %d 条向量记录', len(chunks))
```

- [ ] **Step 2: 修改 insert_markdown_documents()**

```python
def insert_markdown_documents():
    loader = TextLoader('./web/documents/Bailian_Overview.md', encoding='utf-8')
    docs = loader.load()

    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]
    md_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=False
    )
    md_chunks = []
    for doc in docs:
        md_chunks.extend(md_splitter.split_text(doc.page_content))

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    final_chunks = text_splitter.split_documents(md_chunks)

    embeddings = CustomEmbeddings()

    sys_doc, _ = UserDocument.objects.get_or_create(
        title='百炼平台概述 Markdown',
        defaults={'status': 'completed'}
    )

    DocumentChunk.objects.filter(document=sys_doc).delete()

    for i, chunk in enumerate(final_chunks):
        emb = embeddings.embed_query(chunk.page_content)
        DocumentChunk.objects.create(
            content=chunk.page_content,
            embedding=emb,
            document=sys_doc,
            owner=None,
            chunk_index=i,
        )

    sys_doc.chunks_count = len(final_chunks)
    sys_doc.save()
    logger.info('已插入 %d 条向量记录', len(final_chunks))
```

- [ ] **Step 3: 验证幂等性**

```bash
cd backend && python manage.py shell -c "
from web.documents.utils.insert_documents import insert_documents
insert_documents()
# 再跑一次，验证不报错，不产生重复 UserDocument
insert_documents()
from web.models.document import UserDocument
print(UserDocument.objects.filter(title='百炼平台概述').count())  # 应为 1
"
```

- [ ] **Step 4: Commit**

```bash
git add backend/web/documents/utils/insert_documents.py
git commit -m "refactor: adapt insert_documents to UserDocument model

Replace DocumentChunk.objects.all().delete() with per-document deletion.
Use get_or_create for idempotent system document management.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: search_knowledge_base 用户隔离（graph.py）

**Files:**
- Modify: `backend/web/views/friend/message/chat/graph.py`

- [ ] **Step 1: AgentState 加 user_id 字段**

```python
# 改前
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

# 改后
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_id: int
```

- [ ] **Step 2: search_knowledge_base 用 InjectedState**

```python
from langgraph.prebuilt import InjectedState

# 改前
@tool
def search_knowledge_base(query: str) -> str:
    ...
    chunks = DocumentChunk.objects.raw(
        f"SELECT id, content FROM {table} ORDER BY embedding <=> %s::vector LIMIT 3",
        [emb]
    )
    ...

# 改后
@tool
def search_knowledge_base(query: str, state: Annotated[dict, InjectedState]) -> str:
    ...
    user_id = state.get("user_id")
    chunks = DocumentChunk.objects.raw(
        f"SELECT id, content, chunk_index, document_id "
        f"FROM {table} "
        f"WHERE owner_id IS NULL OR owner_id = %s "
        f"ORDER BY embedding <=> %s::vector LIMIT 3",
        [user_id, emb]
    )
    ...
```

- [ ] **Step 3: 验证工具调用接口**

```bash
cd backend && python -m pytest web/tests/test_chat_agent.py::TestChatGraphRouting -v
```

预期：5 passed（mock LLM 的测试不受影响）

- [ ] **Step 4: Commit**

```bash
git add backend/web/views/friend/message/chat/graph.py
git commit -m "feat: add user-aware RAG filtering to search_knowledge_base

- Add user_id to AgentState for request context propagation
- Use InjectedState to pass user_id from state to tool
- Query filters: WHERE owner_id IS NULL (global) OR owner_id = user_id

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: chat.py 传入 user_id

**Files:**
- Modify: `backend/web/views/friend/message/chat/chat.py`

- [ ] **Step 1: inputs 中加 user_id**

在 `event_stream` 方法中（约在第 148 行附近），`inputs` 构造处：

```python
# 改前
inputs = {"messages": msgs}

# 改后
inputs = {
    "messages": msgs,
    "user_id": friend.user_profile.id,  # 传入当前聊天的用户
}
```

- [ ] **Step 2: 验证**

```bash
cd backend && python -m pytest web/tests/test_chat_agent.py::TestChatSSEEndpoint -v
```

预期：5 passed

- [ ] **Step 3: Commit**

```bash
git add backend/web/views/friend/message/chat/chat.py
git commit -m "feat: pass user_id to ChatGraph for RAG permission filtering

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: test_document.py 新测试

**Files:**
- Create: `backend/web/tests/test_document.py`

- [ ] **Step 1: 写测试**

```python
import pytest
from web.models.document import UserDocument, DocumentChunk


class TestUserDocument:
    """UserDocument 模型基本操作"""

    def test_create_system_document(self, db):
        """owner=null 表示系统文档"""
        doc = UserDocument.objects.create(title='测试文档')
        assert doc.owner is None
        assert doc.status == 'completed'

    def test_create_user_document(self, user_profile):
        """owner 指向用户"""
        doc = UserDocument.objects.create(title='我的文档', owner=user_profile)
        assert doc.owner == user_profile

    def test_get_or_create_idempotent(self, db):
        """重复调用不产生重复记录"""
        doc1, created1 = UserDocument.objects.get_or_create(
            title='幂等测试', defaults={'status': 'completed'}
        )
        assert created1 is True

        doc2, created2 = UserDocument.objects.get_or_create(
            title='幂等测试', defaults={'status': 'completed'}
        )
        assert created2 is False
        assert doc1.id == doc2.id
        assert UserDocument.objects.filter(title='幂等测试').count() == 1


class TestDocumentChunkMetadata:
    """DocumentChunk 新字段"""

    def test_chunk_belongs_to_document(self, db):
        """document FK 关联文档"""
        doc = UserDocument.objects.create(title='测试')
        chunk = DocumentChunk.objects.create(
            content='hello', embedding=[0.0] * 1024, document=doc, chunk_index=0
        )
        assert chunk.document == doc
        assert chunk.chunk_index == 0

    def test_chunk_belongs_to_user(self, user_profile):
        """owner FK 关联用户"""
        chunk = DocumentChunk.objects.create(
            content='我的内容', embedding=[0.0] * 1024,
            owner=user_profile, chunk_index=0,
        )
        assert chunk.owner == user_profile

    def test_chunk_metadata_json(self, db):
        """metadata JSON 字段可存储扩展信息"""
        chunk = DocumentChunk.objects.create(
            content='test', embedding=[0.0] * 1024,
            metadata={'header': '第一章', 'source_page': 5},
        )
        chunk.refresh_from_db()
        assert chunk.metadata['header'] == '第一章'


class TestOwnerFiltering:
    """owner 过滤查询验证"""

    def test_global_chunks_have_null_owner(self, db):
        """全局知识库 chunks owner 为 null"""
        chunk = DocumentChunk.objects.create(
            content='global', embedding=[0.0] * 1024,
        )
        assert chunk.owner is None

    def test_filter_by_owner(self, user_profile):
        """按 owner 过滤个人 chunks"""
        DocumentChunk.objects.create(
            content='user chunk', embedding=[0.1] * 1024,
            owner=user_profile,
        )
        DocumentChunk.objects.create(
            content='global chunk', embedding=[0.2] * 1024,
            owner=None,
        )
        user_chunks = DocumentChunk.objects.filter(owner=user_profile)
        globals_ = DocumentChunk.objects.filter(owner__isnull=True)
        assert user_chunks.count() == 1
        assert globals_.count() == 1

    def test_mixed_recall(self, user_profile):
        """owner IS NULL OR owner = user_id 同时召回全局和个人"""
        DocumentChunk.objects.create(
            content='user', embedding=[0.3] * 1024, owner=user_profile
        )
        DocumentChunk.objects.create(
            content='global', embedding=[0.4] * 1024, owner=None
        )
        from django.db.models import Q
        mixed = DocumentChunk.objects.filter(
            Q(owner__isnull=True) | Q(owner=user_profile)
        )
        assert mixed.count() == 2
```

- [ ] **Step 2: 运行新测试**

```bash
cd backend && python -m pytest web/tests/test_document.py -v
```

预期：7 passed

- [ ] **Step 3: 运行全量测试**

```bash
cd backend && python -m pytest web/tests/ -v
```

预期：58 passed（51 + 7 新）

- [ ] **Step 4: Commit**

```bash
git add backend/web/tests/test_document.py
git commit -m "test: add UserDocument and DocumentChunk metadata tests

Cover UserDocument CRUD, get_or_create idempotency, chunk-document
association, owner filtering, and mixed recall queries.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: 更新 test_chat_agent.py  — 真实 PG 查询

**Files:**
- Modify: `backend/web/tests/test_chat_agent.py`

- [ ] **Step 1: 改为真实 PG 查询**

`test_search_knowledge_base_tool` 当前 mock `DocumentChunk.objects.raw`，改为真实插入 DocumentChunk 数据：

```python
@patch("web.views.friend.message.chat.graph.ChatOpenAI")
def test_search_knowledge_base_tool(self, mock_llm_class):
    from web.views.friend.message.chat.graph import ChatGraph
    from web.models.document import DocumentChunk, UserDocument

    # 真实插入文档 + chunk
    sys_doc = UserDocument.objects.create(title='test doc')
    DocumentChunk.objects.create(
        content="Aliyun Bailian platform introduction...",
        embedding=[0.1] * 1024,
        document=sys_doc,
        chunk_index=0,
    )

    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = [
        AIMessage(
            content="",
            tool_calls=[{
                "name": "search_knowledge_base",
                "args": {"query": "What is Bailian"},
                "id": "call_2",
                "type": "tool_call",
            }],
        ),
        AIMessage(content="Done", tool_calls=[]),
    ]
    mock_llm.bind_tools.return_value = mock_llm
    mock_llm_class.return_value = mock_llm

    app = ChatGraph.create_app()
    result = app.invoke({
        "messages": [HumanMessage(content="What is Bailian")],
        "user_id": None,  # 全局搜索
    })

    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_messages) >= 1
    assert "Bailian" in tool_messages[0].content
```

- [ ] **Step 2: 运行 chat agent 测试**

```bash
cd backend && python -m pytest web/tests/test_chat_agent.py -v
```

预期：10 passed

- [ ] **Step 3: 运行全量测试**

```bash
cd backend && python -m pytest web/tests/ -v
```

预期：58 passed

- [ ] **Step 4: Commit**

```bash
git add backend/web/tests/test_chat_agent.py
git commit -m "test: use real PG queries in search_knowledge_base tests

Replace DocumentChunk.objects.raw mock with real PG inserts and queries.
Add user_id=None to verify global knowledge base search path.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Verification Checklist

完成所有 Task 后：

```
[ ] 58 tests pass (was 51, +7 new document tests)
[ ] UserDocument.objects.get_or_create() 幂等
[ ] DocumentChunk.document FK 关联正常
[ ] owner IS NULL 查询全局知识库
[ ] owner = user_id 查询个人知识库
[ ] search_knowledge_base WHERE owner_id IS NULL OR owner_id = %s
[ ] insert_documents 只删自己文档的 chunks
[ ] HNSW 索引存在：\di document_chunk_embedding_hnsw_idx
[ ] 不传 user_id 时退化为全局搜索
[ ] python manage.py check 通过
```

---

## PR 提交

```bash
gh pr create --title "feat: DocumentChunk metadata fields and UserDocument model" \
  --body "$(cat <<'EOF'
## Summary
- New UserDocument model for document ownership/status tracking
- DocumentChunk gains document FK, owner FK, chunk_index, token_count, metadata
- HNSW vector index for cosine similarity search
- search_knowledge_base filters by owner_id (global + user)
- Test environment switched from SQLite to PostgreSQL
- insert_documents adapted to per-document deletion (no more all().delete())
- 58 tests pass (+7 new document tests)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)" --base master
```
