# RAG 引用来源 + Retrieval Trace 落库 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `search_knowledge_base` 返回带文档来源标注的结构化文本 + 检索命中写入 `RetrievalTrace` 表 + SSE 流携带 citations 事件

**Architecture:** 3 层变更 — 数据层（新增 RetrievalTrace 模型）、工具层（graph.py 的 search_knowledge_base 改为 JOIN 查询 + 来源标记 + 落库）、传输层（chat.py 的 SSE 流中检测 ToolMessage → 正则提取 citations → 转发到前端）

**Tech Stack:** Django ORM, pgvector, LangGraph, pytest, model_bakery, unittest.mock

**Spec:** `docs/superpowers/specs/2026-06-06-rag-citation-retrieval-trace-design.md`

**Branch:** `feature/gqyin/rag-citation-trace`（从 master 新建）

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/web/models/retrieval_trace.py` | **新增** | RetrievalTrace 模型 |
| `backend/web/migrations/XXXX_retrieval_trace.py` | **新增** | makemigrations 自动生成 |
| `backend/web/views/friend/message/chat/graph.py` | **修改** | `search_knowledge_base`：JOIN 查询 + 来源标记 + 落库 |
| `backend/web/views/friend/message/chat/chat.py` | **修改** | `tts_sender()` 加 ToolMessage 检测 + `event_stream()` 加 citations 分支 |
| `backend/web/tests/test_chat_agent.py` | **修改** | 适配新 tool 返回格式（mock cursor 替代 mock raw） |
| `backend/web/tests/test_retrieval_trace.py` | **新增** | RetrievalTrace 模型 + 落库 + citation 解析测试 |

---

### Task 1: 新建分支 + RetrievalTrace 模型 + Migration

- [ ] **Step 1: 从 master 新建 feature 分支**

```bash
git -C D:/MyProjects/AiFriends checkout -b feature/gqyin/rag-citation-trace
```

- [ ] **Step 2: 创建 RetrievalTrace 模型**

创建 `backend/web/models/retrieval_trace.py`：

```python
from django.db import models


class RetrievalTrace(models.Model):
    """每次 RAG 检索命中的 chunk 记录，用于排查和评估 RAG 质量"""
    user = models.ForeignKey(
        'UserProfile', on_delete=models.CASCADE, db_index=True,
    )
    query = models.TextField()                          # 检索 query 文本
    document = models.ForeignKey(
        'UserDocument', on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    chunk_index = models.IntegerField()                 # 命中 chunk 在文档中的序号（0-based）
    distance = models.FloatField()                      # 余弦距离（pgvector <=> 返回值）
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', '-created_at']),   # 按用户查最近 trace
            models.Index(fields=['document']),              # 按文档查被引情况
        ]
```

- [ ] **Step 3: 生成 migration**

```bash
cd backend; python manage.py makemigrations web --name retrieval_trace
```

- [ ] **Step 4: 应用迁移，确认表创建成功**

```bash
cd backend; python manage.py migrate
```

- [ ] **Step 5: Commit**

```bash
git -C D:/MyProjects/AiFriends add backend/web/models/retrieval_trace.py backend/web/migrations/*retrieval_trace*.py
git -C D:/MyProjects/AiFriends commit -m "feat: 新增 RetrievalTrace 模型（RAG 检索 trace 落库）"
```

---

### Task 2: 更新已有测试 — mock cursor 替代 mock raw（TDD 红阶段）

**Files:**
- Modify: `backend/web/tests/test_chat_agent.py:80-120`

- [ ] **Step 1: 更新 `test_search_knowledge_base_tool` — mock cursor 替代 mock raw**

替换 `test_chat_agent.py` 第 80-120 行的测试方法。新测试 mock `connection.cursor()`（含 context manager protocol），验证新返回格式含 `[来源]` 标记：

```python
    @patch("web.views.friend.message.chat.graph.CustomEmbeddings")
    @patch("web.views.friend.message.chat.graph.ChatOpenAI")
    @patch("django.db.connection.cursor")
    def test_search_knowledge_base_tool(self, mock_cursor, mock_llm_class,
                                         mock_embeddings_class):
        """search_knowledge_base JOIN 查询 + 返回 [来源] 标记"""
        from web.views.friend.message.chat.graph import ChatGraph

        # cursor() 返回 context manager，__enter__ 返回 cursor 实例
        mock_cursor_instance = MagicMock()
        mock_cursor_instance.fetchall.return_value = [
            (1, "阿里云百炼平台介绍内容...", 2, 5, "平台使用指南.pdf", 0.12),
            (2, "另一段检索内容...", 7, 5, "平台使用指南.pdf", 0.18),
        ]
        mock_cursor.return_value.__enter__.return_value = mock_cursor_instance

        # Mock CustomEmbeddings
        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1] * 1024
        mock_embeddings_class.return_value = mock_embeddings

        # Mock LLM: 触发 search_knowledge_base 工具调用
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
        result = app.invoke({"messages": [HumanMessage(content="What is Bailian")]})

        # 验证 ToolMessage 包含来源标记
        tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert len(tool_messages) >= 1
        content = tool_messages[0].content
        assert "[来源1: 平台使用指南.pdf 第3段]" in content
        assert "阿里云百炼平台介绍内容" in content
```

- [ ] **Step 2: 同步更新 import — 移除 `mock_raw`（行 80）**

删除第 80 行的 `@patch("web.models.document.DocumentChunk.objects.raw")` 装饰器行及函数签名中的 `mock_raw` 参数。

- [ ] **Step 3: 运行测试，确认失败（TDD 红）**

```bash
cd backend; python -m pytest web/tests/test_chat_agent.py::TestChatGraphRouting::test_search_knowledge_base_tool -v
```

预期 FAIL — 报错 `AttributeError: ... 'DocumentChunk' object has no attribute 'content'` 或类似错误（因为旧代码用 `objects.raw()` 尚未改为 cursor）。

- [ ] **Step 4: Commit**

```bash
git -C D:/MyProjects/AiFriends add backend/web/tests/test_chat_agent.py
git -C D:/MyProjects/AiFriends commit -m "test: 更新 test_search_knowledge_base_tool mock cursor 替代 raw（预期失败）"
```

---

### Task 3: 重构 search_knowledge_base（TDD 绿阶段）

**Files:**
- Modify: `backend/web/views/friend/message/chat/graph.py:32-67`

- [ ] **Step 1: 替换 search_knowledge_base 函数体**

将 `graph.py` 中 `search_knowledge_base` 工具函数（第 32-67 行）的 `from web.models.document import DocumentChunk` 之后的部分替换为：

```python
            from web.models.document import DocumentChunk, UserDocument
            from web.models.retrieval_trace import RetrievalTrace

            user_id = state.get("user_id")
            logger.info('RAG 知识库检索开始, query=%s, user_id=%s', query[:100], user_id)

            embeddings = CustomEmbeddings(user_id=user_id)
            emb = embeddings.embed_query(query)

            chunk_table = DocumentChunk._meta.db_table
            doc_table = UserDocument._meta.db_table

            # 使用 cursor 执行 JOIN 查询，一次拿到 title + distance
            with connection.cursor() as cursor:
                cursor.execute(f"""
                    SELECT dc.id, dc.content, dc.chunk_index, dc.document_id,
                           ud.title AS document_title,
                           dc.embedding <=> %s::vector AS distance
                    FROM {chunk_table} dc
                    LEFT JOIN {doc_table} ud ON dc.document_id = ud.id
                    WHERE dc.owner_id IS NULL OR dc.owner_id = %s
                    ORDER BY dc.embedding <=> %s::vector
                    LIMIT 3
                """, [emb, user_id, emb])
                rows = cursor.fetchall()

            if not rows:
                return "知识库中未找到相关信息。"

            parts = ["从知识库中找到以下相关信息：\n"]
            for i, row in enumerate(rows):
                _, content, chunk_index, document_id, title, distance = row
                # 明确 if/elif/else 构建来源标签（避免三目运算符优先级歧义）
                if title:
                    source_label = title
                elif document_id:
                    source_label = f"文档{document_id}"
                else:
                    source_label = "系统知识库"
                # chunk_index 在 DB 中为 0-based，展示时转为 1-based
                parts.append(f"[来源{i+1}: {source_label} 第{chunk_index + 1}段]")
                parts.append(content)
                parts.append("")

                # 写入检索 trace（fail-safe：DB 故障不影响工具返回值）
                if document_id:
                    try:
                        RetrievalTrace.objects.create(
                            user_id=user_id,
                            query=query,
                            document_id=document_id,
                            chunk_index=chunk_index,
                            distance=float(distance),
                        )
                    except Exception:
                        logger.exception(
                            'RetrievalTrace 写入失败, document_id=%s', document_id
                        )

            logger.info('RAG 检索完成, hits=%d', len(rows))
            return "\n".join(parts)
```

- [ ] **Step 2: 确认 import 完整性 — 核对 graph.py 顶部 import**

在 `graph.py` 顶部 import 区域确认已有 `from django.db import connection` 行（第 1 行附近）。如果没有，在 `import logging` 和 `import os` 之后、LangChain import 之前新增：

```python
from django.db import connection
```

- [ ] **Step 3: 运行测试，确认通过（TDD 绿）**

```bash
cd backend; python -m pytest web/tests/test_chat_agent.py -v
```

预期：`TestChatGraphRouting` 全部 5 个测试 PASS。

- [ ] **Step 4: Commit**

```bash
git -C D:/MyProjects/AiFriends add backend/web/views/friend/message/chat/graph.py
git -C D:/MyProjects/AiFriends commit -m "feat: search_knowledge_base JOIN 查询 + 来源标记 + RetrievalTrace 落库"
```

---

### Task 4: SSE 流携带 citation 事件

**Files:**
- Modify: `backend/web/views/friend/message/chat/chat.py`

- [ ] **Step 1: 在 `tts_sender()` 的 astream 循环中新增 ToolMessage 检测**

在 `chat.py` 顶部 import 区域确认 `ToolMessage` 已导入（第 13 行已有 `BaseMessageChunk, BaseMessage, SystemMessage, AIMessage`），追加 `ToolMessage`：

如果 `ToolMessage` 未在 import 中，修改第 13 行：
```python
from langchain_core.messages import HumanMessage, BaseMessageChunk, BaseMessage, SystemMessage, AIMessage, ToolMessage
```

在 `tts_sender()` 方法中（约第 329 行），`async for msg, metadata in app.astream(...)` 循环开始处、`BaseMessageChunk` 检查之前，插入 ToolMessage 检测分支：

```python
            # 在 async for 循环内、isinstance(msg, BaseMessageChunk) 之前插入：
            CITATION_RE = re.compile(r'\[来源(\d+): (.+?) 第(\d+)段\]')

            async for msg, metadata in app.astream(inputs, stream_mode="messages"):
                # 检测知识库检索结果 ToolMessage，提取引用来源
                # LangGraph 时序：ToolMessage 在第一个 AIMessageChunk 之前到达，
                # 确保 citations 事件先于 content 发送到前端
                if isinstance(msg, ToolMessage) and msg.name == "search_knowledge_base":
                    citations = []
                    for m in CITATION_RE.finditer(msg.content):
                        citations.append({
                            "index": int(m.group(1)),
                            "title": m.group(2),
                            "chunk_index": int(m.group(3)),
                        })
                    if citations:
                        mq.put_nowait({'citations': citations})

                elif isinstance(msg, BaseMessageChunk):
                    # ... 现有逻辑不变 ...
```

**注意**：`CITATION_RE` 是模块级常量，应移到文件顶部（`TOOL_RULES` 后面），而非在函数内重复编译。实际操作时在 `TOOL_RULES` 常量之后新增：

```python
# 匹配 search_knowledge_base 返回的来源标记：[来源1: 文档标题 第3段]
CITATION_RE = re.compile(r'\[来源(\d+): (.+?) 第(\d+)段\]')
```

然后在 `tts_sender()` 中直接使用 `CITATION_RE`。

- [ ] **Step 2: 在 `event_stream()` 的 while 循环中新增 citations 转发**

在 `event_stream()` 方法（约第 198 行），while 循环中 `if msg is None: break` 之后，新增 citations 处理分支：

```python
            while True:
                msg = mq.get()
                if msg is None:
                    break
                # 新增：转发 RAG 引用来源到 SSE（在 content 之前，前端可提前展示）
                if msg.get('citations', None):
                    yield f'data: {json.dumps({"citations": msg["citations"]}, ensure_ascii=False)}\n\n'
                if msg.get('error', None):
                    has_error = True
                    error_message = msg['error']
                    yield f'data: {json.dumps({"error": error_message}, ensure_ascii=False)}\n\n'
                if msg.get('content', None):
                    full_output.append(msg['content'])
                    yield f'data: {json.dumps({"content": msg["content"]}, ensure_ascii=False)}\n\n'
                if msg.get('audio', None):
                    yield f'data: {json.dumps({"audio": msg["audio"]}, ensure_ascii=False)}\n\n'
                if msg.get('usage', None):
                    full_usage = msg['usage']
```

- [ ] **Step 3: 确认已有 import 无遗漏**

检查 `chat.py` 顶部：
- `import re`（第 8 行附近）— 已有的话不需要加，没有的话追加
- `from langchain_core.messages import ..., ToolMessage` — 追加到第 13 行

- [ ] **Step 4: 运行已有测试确认无回归**

```bash
cd backend; python -m pytest web/tests/test_chat_agent.py web/tests/test_system_prompt.py -v
```

预期：全部 PASS（Task 2 已更新 mock cursor，Task 4 新加的分支不在这些测试的覆盖路径上）。

- [ ] **Step 5: Commit**

```bash
git -C D:/MyProjects/AiFriends add backend/web/views/friend/message/chat/chat.py
git -C D:/MyProjects/AiFriends commit -m "feat: SSE 流携带 RAG citations 事件（ToolMessage 检测 → 正则提取 → 转发）"
```

---

### Task 5: 新增测试 — RetrievalTrace 落库 + citation 解析 + SSE 事件

**Files:**
- Create: `backend/web/tests/test_retrieval_trace.py`

- [ ] **Step 1: 创建测试文件**

创建 `backend/web/tests/test_retrieval_trace.py`：

```python
import json
import pytest
import re
from unittest.mock import patch, MagicMock, AsyncMock

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage


CITATION_RE = re.compile(r'\[来源(\d+): (.+?) 第(\d+)段\]')


class TestSearchKnowledgeBaseResult:
    """验证 search_knowledge_base 返回值格式"""

    @patch("web.views.friend.message.chat.graph.CustomEmbeddings")
    @patch("web.views.friend.message.chat.graph.ChatOpenAI")
    @patch("django.db.connection.cursor")
    def test_returns_source_markers(self, mock_cursor, mock_llm_class,
                                     mock_embeddings_class):
        """tool 返回值应包含 [来源N: title 第M段] 格式标记"""
        from web.views.friend.message.chat.graph import ChatGraph

        # cursor mock：模拟 JOIN 查询返回多行，含 title + distance
        mock_cursor_instance = MagicMock()
        mock_cursor_instance.fetchall.return_value = [
            (1, "社保制度介绍...", 0, 3, "社保政策.pdf", 0.15),
            (2, "养老保险说明...", 4, 3, "社保政策.pdf", 0.22),
        ]
        mock_cursor.return_value.__enter__.return_value = mock_cursor_instance

        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1] * 1024
        mock_embeddings_class.return_value = mock_embeddings

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            AIMessage(content="", tool_calls=[{
                "name": "search_knowledge_base",
                "args": {"query": "社保"},
                "id": "call_1",
                "type": "tool_call",
            }]),
            AIMessage(content="Done", tool_calls=[]),
        ]
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm_class.return_value = mock_llm

        app = ChatGraph.create_app()
        result = app.invoke(
            {"messages": [HumanMessage(content="社保是什么")], "user_id": 1}
        )

        tool_msgs = [m for m in result["messages"]
                     if m.__class__.__name__ == "ToolMessage"]
        assert len(tool_msgs) == 1
        content = tool_msgs[0].content
        # content 含来源标记，chunk_index 为 1-based（原始 0 → 显示 1）
        assert "[来源1: 社保政策.pdf 第1段]" in content
        assert "社保制度介绍" in content
        assert "[来源2: 社保政策.pdf 第5段]" in content
        assert "养老保险说明" in content

    @patch("web.views.friend.message.chat.graph.CustomEmbeddings")
    @patch("web.views.friend.message.chat.graph.ChatOpenAI")
    @patch("django.db.connection.cursor")
    def test_empty_result_returns_not_found(self, mock_cursor, mock_llm_class,
                                              mock_embeddings_class):
        """无命中时返回 '未找到相关信息'"""
        from web.views.friend.message.chat.graph import ChatGraph

        mock_cursor_instance = MagicMock()
        mock_cursor_instance.fetchall.return_value = []  # 空结果
        mock_cursor.return_value.__enter__.return_value = mock_cursor_instance

        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1] * 1024
        mock_embeddings_class.return_value = mock_embeddings

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            AIMessage(content="", tool_calls=[{
                "name": "search_knowledge_base",
                "args": {"query": "稀有内容"},
                "id": "call_1",
                "type": "tool_call",
            }]),
            AIMessage(content="Done", tool_calls=[]),
        ]
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm_class.return_value = mock_llm

        app = ChatGraph.create_app()
        result = app.invoke(
            {"messages": [HumanMessage(content="找一下稀有内容")], "user_id": 1}
        )

        tool_msgs = [m for m in result["messages"]
                     if m.__class__.__name__ == "ToolMessage"]
        assert len(tool_msgs) == 1
        assert "未找到相关信息" in tool_msgs[0].content

    @patch("web.views.friend.message.chat.graph.CustomEmbeddings")
    @patch("web.views.friend.message.chat.graph.ChatOpenAI")
    @patch("django.db.connection.cursor")
    def test_system_knowledge_no_title(self, mock_cursor, mock_llm_class,
                                         mock_embeddings_class):
        """系统知识库 chunk（无 document_id + 无 title）显示 '系统知识库'"""
        from web.views.friend.message.chat.graph import ChatGraph

        mock_cursor_instance = MagicMock()
        mock_cursor_instance.fetchall.return_value = [
            (1, "系统知识内容...", 0, None, None, 0.30),  # NULL document + NULL title
        ]
        mock_cursor.return_value.__enter__.return_value = mock_cursor_instance

        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1] * 1024
        mock_embeddings_class.return_value = mock_embeddings

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            AIMessage(content="", tool_calls=[{
                "name": "search_knowledge_base",
                "args": {"query": "测试"},
                "id": "call_1",
                "type": "tool_call",
            }]),
            AIMessage(content="Done", tool_calls=[]),
        ]
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm_class.return_value = mock_llm

        app = ChatGraph.create_app()
        result = app.invoke(
            {"messages": [HumanMessage(content="测试")], "user_id": 1}
        )

        tool_msgs = [m for m in result["messages"]
                     if m.__class__.__name__ == "ToolMessage"]
        assert len(tool_msgs) == 1
        assert "[来源1: 系统知识库 第1段]" in tool_msgs[0].content


class TestRetrievalTracePersistence:
    """集成测试：验证 RetrievalTrace 落库行为"""

    @patch("web.views.friend.message.chat.graph.CustomEmbeddings")
    @patch("web.views.friend.message.chat.graph.ChatOpenAI")
    @patch("django.db.connection.cursor")
    def test_writes_trace_for_each_hit(self, mock_cursor, mock_llm_class,
                                         mock_embeddings_class, user):
        """3 个命中 chunk（均有 document_id）→ 3 条 RetrievalTrace"""
        from web.views.friend.message.chat.graph import ChatGraph
        from web.models.retrieval_trace import RetrievalTrace

        mock_cursor_instance = MagicMock()
        mock_cursor_instance.fetchall.return_value = [
            (1, "内容A", 2, 1, "DocA", 0.10),
            (2, "内容B", 5, 1, "DocA", 0.12),
            (3, "内容C", 1, 2, "DocB", 0.15),
        ]
        mock_cursor.return_value.__enter__.return_value = mock_cursor_instance

        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1] * 1024
        mock_embeddings_class.return_value = mock_embeddings

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            AIMessage(content="", tool_calls=[{
                "name": "search_knowledge_base",
                "args": {"query": "test query text"},
                "id": "call_1",
                "type": "tool_call",
            }]),
            AIMessage(content="Done", tool_calls=[]),
        ]
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm_class.return_value = mock_llm

        trace_count_before = RetrievalTrace.objects.count()

        app = ChatGraph.create_app()
        app.invoke(
            {"messages": [HumanMessage(content="测试")], "user_id": user.id}
        )

        # 验证 3 条 trace 落库
        traces = RetrievalTrace.objects.filter(user=user).order_by('id')
        assert traces.count() - trace_count_before == 3
        # 验证 query 写入正确
        last_traces = traces[trace_count_before:]
        assert last_traces[0].query == "test query text"
        assert last_traces[0].chunk_index == 2
        assert last_traces[0].distance == 0.10
        # 验证不同 document
        assert last_traces[2].document_id == 2  # DocB

    @patch("web.views.friend.message.chat.graph.CustomEmbeddings")
    @patch("web.views.friend.message.chat.graph.ChatOpenAI")
    @patch("django.db.connection.cursor")
    def test_no_document_id_skips_trace(self, mock_cursor, mock_llm_class,
                                          mock_embeddings_class, user):
        """系统知识库 chunk（无 document_id）不写 RetrievalTrace"""
        from web.views.friend.message.chat.graph import ChatGraph
        from web.models.retrieval_trace import RetrievalTrace

        mock_cursor_instance = MagicMock()
        mock_cursor_instance.fetchall.return_value = [
            (1, "系统内容", 0, None, None, 0.30),  # NULL document_id
        ]
        mock_cursor.return_value.__enter__.return_value = mock_cursor_instance

        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1] * 1024
        mock_embeddings_class.return_value = mock_embeddings

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            AIMessage(content="", tool_calls=[{
                "name": "search_knowledge_base",
                "args": {"query": "系统"},
                "id": "call_1",
                "type": "tool_call",
            }]),
            AIMessage(content="Done", tool_calls=[]),
        ]
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm_class.return_value = mock_llm

        trace_count_before = RetrievalTrace.objects.count()

        app = ChatGraph.create_app()
        app.invoke(
            {"messages": [HumanMessage(content="测试")], "user_id": user.id}
        )

        assert RetrievalTrace.objects.count() == trace_count_before

    @patch("web.views.friend.message.chat.graph.CustomEmbeddings")
    @patch("web.views.friend.message.chat.graph.ChatOpenAI")
    @patch("django.db.connection.cursor")
    def test_empty_result_no_trace(self, mock_cursor, mock_llm_class,
                                     mock_embeddings_class, user):
        """无命中时不写 RetrievalTrace"""
        from web.views.friend.message.chat.graph import ChatGraph
        from web.models.retrieval_trace import RetrievalTrace

        mock_cursor_instance = MagicMock()
        mock_cursor_instance.fetchall.return_value = []
        mock_cursor.return_value.__enter__.return_value = mock_cursor_instance

        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1] * 1024
        mock_embeddings_class.return_value = mock_embeddings

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            AIMessage(content="", tool_calls=[{
                "name": "search_knowledge_base",
                "args": {"query": "不存在"},
                "id": "call_1",
                "type": "tool_call",
            }]),
            AIMessage(content="Done", tool_calls=[]),
        ]
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm_class.return_value = mock_llm

        trace_count_before = RetrievalTrace.objects.count()

        app = ChatGraph.create_app()
        app.invoke(
            {"messages": [HumanMessage(content="测试")], "user_id": user.id}
        )

        assert RetrievalTrace.objects.count() == trace_count_before


class TestCitationParsing:
    """验证 CITATION_RE 正则 + SSE 事件转发"""

    def test_citation_re_parses_source_marker(self):
        """CITATION_RE 从 [来源1: 文档.pdf 第5段] 正确提取 index/title/chunk_index"""
        text = (
            "从知识库中找到以下相关信息：\n\n"
            "[来源1: 社保政策.pdf 第1段]\n内容A\n\n"
            "[来源2: 就业指南.md 第5段]\n内容B\n"
        )

        matches = list(CITATION_RE.finditer(text))
        assert len(matches) == 2

        m1 = matches[0]
        assert m1.group(1) == "1"        # index
        assert m1.group(2) == "社保政策.pdf"  # title
        assert m1.group(3) == "1"        # chunk_index (1-based display)

        m2 = matches[1]
        assert m2.group(1) == "2"
        assert m2.group(2) == "就业指南.md"
        assert m2.group(3) == "5"

    def test_citation_re_no_match_on_plain_text(self):
        """纯文本无 [来源] 标记 → 正则无匹配"""
        text = "知识库中未找到相关信息。"
        matches = list(CITATION_RE.finditer(text))
        assert len(matches) == 0

    @patch("web.views.friend.message.chat.chat.websockets.connect")
    @patch("web.views.friend.message.chat.chat.ChatGraph.create_app")
    def test_sse_emits_citations_event(self, mock_create_app, mock_ws_connect,
                                         auth_client, friend):
        """ToolMessage 含来源标记 → SSE 流中首先出现 citations 事件"""
        from langchain_core.messages import ToolMessage

        mock_graph = MagicMock()

        async def mock_astream(inputs, stream_mode="messages"):
            # 模拟 ToolMessage（检索结果含来源标记）先于 content chunk
            tool_msg = ToolMessage(
                content=(
                    "从知识库中找到以下相关信息：\n\n"
                    "[来源1: 测试文档.pdf 第3段]\n检索到的内容...\n"
                ),
                name="search_knowledge_base",
                tool_call_id="call_1",
            )
            yield (tool_msg, {"langgraph_node": "tools"})
            # 然后是 LLM 流式回复
            chunk = AIMessageChunk(content="根据测试文档...")
            yield (chunk, {"langgraph_node": "agent"})

        mock_graph.astream = mock_astream
        mock_create_app.return_value = mock_graph

        # Mock WebSocket（仅需要 task-started + task-finished）
        mock_ws = AsyncMock()
        call_counter = [0]

        async def ws_async_iterator():
            call_counter[0] += 1
            if call_counter[0] == 1:
                yield json.dumps({"header": {"event": "task-started"}})
            else:
                yield json.dumps({"header": {"event": "task-finished"}})

        mock_ws.__aiter__ = ws_async_iterator
        mock_ws_connect.return_value = mock_ws

        resp = auth_client.post(
            "/api/friend/message/chat/",
            {"friend_id": friend.id, "message": "测试"},
        )
        content = b"".join(resp.streaming_content).decode("utf-8")
        lines = content.strip().split("\n\n")

        # 解析 SSE 事件，找 citations 事件
        citation_lines = [l for l in lines if "citations" in l]
        assert len(citation_lines) >= 1

        data_prefix = "data: "
        citation_data = json.loads(
            citation_lines[0][len(data_prefix):]
        )
        citations = citation_data["citations"]
        assert len(citations) == 1
        assert citations[0]["title"] == "测试文档.pdf"
        assert citations[0]["chunk_index"] == 3

    def test_citation_re_system_knowledge_source(self):
        """系统知识库来源标记 '系统知识库' 也能被正则匹配"""
        text = "[来源1: 系统知识库 第1段]\n系统内容..."
        matches = list(CITATION_RE.finditer(text))
        assert len(matches) == 1
        assert matches[0].group(2) == "系统知识库"
```

- [ ] **Step 2: 运行新增测试**

```bash
cd backend; python -m pytest web/tests/test_retrieval_trace.py -v
```

预期：全部 8 个测试 PASS。

- [ ] **Step 3: Commit**

```bash
git -C D:/MyProjects/AiFriends add backend/web/tests/test_retrieval_trace.py
git -C D:/MyProjects/AiFriends commit -m "test: RetrievalTrace 落库 + citation 解析 + SSE 事件测试"
```

---

### Task 6: 全量回归 + 提交文档

- [ ] **Step 1: 运行已有测试确保无回归**

```bash
cd backend; python -m pytest web/tests/ -v --ignore=web/tests/test_tool_calling.py
```

预期：全部 PASS。

- [ ] **Step 2: 提交设计文档**

```bash
git -C D:/MyProjects/AiFriends add docs/superpowers/specs/2026-06-06-rag-citation-retrieval-trace-design.md docs/superpowers/plans/2026-06-06-rag-citation-retrieval-trace.md
git -C D:/MyProjects/AiFriends commit -m "docs: RAG 引用来源 + RetrievalTrace 落库设计文档 + 实施计划"
```

---

### 验收检查

| 验收点 | 检查方法 | 指标 |
|--------|---------|------|
| tool 返回来源标记 | `test_returns_source_markers` | 通过 |
| RetrievalTrace 落库 | `test_writes_trace_for_each_hit` | 3 hits → 3 条 |
| 无 document_id 不写 trace | `test_no_document_id_skips_trace` | 通过 |
| 无命中不写 trace | `test_empty_result_no_trace` | 通过 |
| citation 正则解析 | `test_citation_re_parses_source_marker` | 通过 |
| SSE 含 citations 事件 | `test_sse_emits_citations_event` | 通过 |
| 已有测试无回归 | `pytest web/tests/ -v --ignore=test_tool_calling.py` | 全部通过 |

---

### 提交历史

```
feature/gqyin/rag-citation-trace
  ├── feat: 新增 RetrievalTrace 模型（RAG 检索 trace 落库）
  ├── test: 更新 test_search_knowledge_base_tool mock cursor 替代 raw（预期失败）
  ├── feat: search_knowledge_base JOIN 查询 + 来源标记 + RetrievalTrace 落库
  ├── feat: SSE 流携带 RAG citations 事件（ToolMessage 检测 → 正则提取 → 转发）
  ├── test: RetrievalTrace 落库 + citation 解析 + SSE 事件测试
  └── docs: RAG 引用来源 + RetrievalTrace 落库设计文档 + 实施计划
```
