# P1-B3 RAG No-Answer 策略 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `search_knowledge_base` 加距离阈值 + LLM 自主检索条数 + 无结果诚实告知

**Architecture:** 4 层改动 — settings 配置（RAG_DEFAULT_MAX_RESULTS / RAG_SIMILARITY_THRESHOLD / RAG_MAX_TOOL_CALLS）→ graph.py 工具阈值过滤 + max_results 参数 → graph.py 循环硬保险 → chat.py TOOL_RULES prompt 诚实策略

**Tech Stack:** Django 6.0, LangGraph, pgvector, pytest + mock

**Spec:** `docs/superpowers/specs/2026-06-17-rag-no-answer-strategy-design.md`

---

### Task 1: 添加 settings 配置项

**Files:**
- Modify: `backend/backend/settings.py:283`（QUOTA_EMBEDDING_TOKENS_PER_DAY 之后）

- [ ] **Step 1: 在配额配置区域末尾插入 3 个 RAG 配置**

找到 `QUOTA_EMBEDDING_TOKENS_PER_DAY = 500_000`，在其后插入：

```python
# RAG 向量检索配置
RAG_DEFAULT_MAX_RESULTS = 5        # 单次检索默认返回条数（LLM 可通过 max_results 覆盖）
RAG_SIMILARITY_THRESHOLD = 0.5     # 余弦距离阈值（pgvector <=>，0=完全相同 2=语义相反）
RAG_MAX_TOOL_CALLS = 5             # 单次对话最多工具调用次数（防止异常循环）
```

- [ ] **Step 2: 验证**

```bash
cd backend; python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 3: Commit**

```bash
git add backend/backend/settings.py
git commit -m "feat: RAG 检索配置项 — max_results/threshold/max_tool_calls"
```

---

### Task 2: 编写测试（TDD — 红阶段）

**Files:**
- Modify: `backend/web/tests/test_chat_agent.py`（追加到 `TestChatGraphRouting` 类末尾）

- [ ] **Step 1: 追加 3 个测试到 `TestChatGraphRouting`**

参照现有 `test_search_knowledge_base_tool` 模式：三层 `@patch` + `mock_llm.invoke.side_effect` 两步响应（第一次带 tool_calls 触发工具，第二次空 tool_calls 结束）。

```python
    @patch("web.views.friend.message.chat.graph.CustomEmbeddings")
    @patch("web.views.friend.message.chat.graph.ChatOpenAI")
    @patch("django.db.backends.base.base.BaseDatabaseWrapper.cursor")
    def test_search_knowledge_base_threshold_filters_all(
            self, mock_cursor_method, mock_llm_class, mock_embeddings_class):
        """全部结果超阈值 → 返回「未找到相关信息」"""
        from web.views.friend.message.chat.graph import ChatGraph

        mock_cursor_instance = MagicMock()
        mock_cursor_instance.__enter__.return_value = mock_cursor_instance
        # distance=0.8, 0.9 → 均超过 RAG_SIMILARITY_THRESHOLD=0.5
        mock_cursor_instance.fetchall.return_value = [
            (1, "不相关内容", 0, 5, "doc.pdf", 0.8),
            (2, "另一条不相关内容", 1, 5, "doc.pdf", 0.9),
        ]
        mock_cursor_method.return_value = mock_cursor_instance

        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1] * 1024
        mock_embeddings_class.return_value = mock_embeddings

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            AIMessage(content="", tool_calls=[{
                "name": "search_knowledge_base",
                "args": {"query": "test", "max_results": 3},
                "id": "call_1", "type": "tool_call",
            }]),
            AIMessage(content="完成", tool_calls=[]),
        ]
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm_class.return_value = mock_llm

        app = ChatGraph.create_app()
        result = app.invoke({"messages": [HumanMessage(content="Query")], "user_id": 42})

        tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert len(tool_messages) >= 1
        assert "知识库中未找到相关信息" in tool_messages[0].content

    @patch("web.views.friend.message.chat.graph.CustomEmbeddings")
    @patch("web.views.friend.message.chat.graph.ChatOpenAI")
    @patch("django.db.backends.base.base.BaseDatabaseWrapper.cursor")
    def test_search_knowledge_base_threshold_filters_partial(
            self, mock_cursor_method, mock_llm_class, mock_embeddings_class):
        """部分超阈值 → 只保留 distance < 0.5 的结果"""
        from web.views.friend.message.chat.graph import ChatGraph

        mock_cursor_instance = MagicMock()
        mock_cursor_instance.__enter__.return_value = mock_cursor_instance
        # distance=0.3 ✅, 0.8 ❌, 0.4 ✅ → 保留 2 条
        mock_cursor_instance.fetchall.return_value = [
            (1, "相关内容A", 0, 5, "doc.pdf", 0.3),
            (2, "不相关内容", 1, 5, "doc.pdf", 0.8),
            (3, "相关内容B", 2, 5, "doc.pdf", 0.4),
        ]
        mock_cursor_method.return_value = mock_cursor_instance

        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1] * 1024
        mock_embeddings_class.return_value = mock_embeddings

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            AIMessage(content="", tool_calls=[{
                "name": "search_knowledge_base",
                "args": {"query": "test", "max_results": 3},
                "id": "call_1", "type": "tool_call",
            }]),
            AIMessage(content="完成", tool_calls=[]),
        ]
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm_class.return_value = mock_llm

        app = ChatGraph.create_app()
        result = app.invoke({"messages": [HumanMessage(content="Query")], "user_id": 42})

        tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert len(tool_messages) >= 1
        content = tool_messages[0].content
        assert "相关内容A" in content
        assert "不相关内容" not in content
        assert "相关内容B" in content
        assert "[来源1:" in content and "[来源2:" in content

    @patch("web.views.friend.message.chat.graph.CustomEmbeddings")
    @patch("web.views.friend.message.chat.graph.ChatOpenAI")
    @patch("django.db.backends.base.base.BaseDatabaseWrapper.cursor")
    def test_search_knowledge_base_max_results_param(
            self, mock_cursor_method, mock_llm_class, mock_embeddings_class):
        """LLM 通过 max_results 参数控制检索条数"""
        from web.views.friend.message.chat.graph import ChatGraph

        mock_cursor_instance = MagicMock()
        mock_cursor_instance.__enter__.return_value = mock_cursor_instance
        mock_cursor_instance.fetchall.return_value = [
            (1, "结果1", 0, 5, "doc.pdf", 0.1),
            (2, "结果2", 1, 5, "doc.pdf", 0.2),
        ]
        mock_cursor_method.return_value = mock_cursor_instance

        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.1] * 1024
        mock_embeddings_class.return_value = mock_embeddings

        mock_llm = MagicMock()
        # LLM 传入 max_results=1
        mock_llm.invoke.side_effect = [
            AIMessage(content="", tool_calls=[{
                "name": "search_knowledge_base",
                "args": {"query": "test", "max_results": 1},
                "id": "call_1", "type": "tool_call",
            }]),
            AIMessage(content="完成", tool_calls=[]),
        ]
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm_class.return_value = mock_llm

        app = ChatGraph.create_app()
        result = app.invoke({"messages": [HumanMessage(content="Query")], "user_id": 42})

        # 验证 max_results=1 被传递到 SQL 的 LIMIT 参数
        sql = mock_cursor_instance.execute.call_args[0][0]
        params = mock_cursor_instance.execute.call_args[0][1]
        assert "LIMIT %s" in sql
        assert params[-1] == 1  # max_results 作为最后一个参数

        tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert len(tool_messages) >= 1
```

- [ ] **Step 2: 运行新增测试 — 预期 FAIL**

```bash
cd backend; python -m pytest web/tests/test_chat_agent.py -k "threshold or max_results" -v
```

Expected: FAIL — 工具实现尚未修改

- [ ] **Step 3: Commit**

```bash
git add backend/web/tests/test_chat_agent.py
git commit -m "test: RAG 阈值过滤 + max_results 参数测试（红阶段）"
```

---

### Task 3: 实现 graph.py 改动

**Files:**
- Modify: `backend/web/views/friend/message/chat/graph.py:1-6,34-48,76,80-81,142-146`

- [ ] **Step 1: 添加 settings import**

在 `graph.py` 顶部 import 区添加：

```python
from django.conf import settings
```

- [ ] **Step 2: 改造 `search_knowledge_base` — 加 max_results 参数 + 默认值**

```python
@tool
def search_knowledge_base(
    query: str,
    max_results: int = None,
    state: Annotated[dict, InjectedState]
) -> str:
    # ...
    # LLM 未指定时使用 settings 默认值
    if max_results is None:
        max_results = getattr(settings, 'RAG_DEFAULT_MAX_RESULTS', 5)
```

Tool description 中追加：
```
根据问题类型选择 max_results：简单事实查询传 1-2，需要多角度信息传 3-5。
```

- [ ] **Step 3: SQL LIMIT 参数化**

```python
cursor.execute(f"""
    ... LIMIT %s
""", [emb, user_id, emb, max_results])
```

- [ ] **Step 4: 加距离阈值过滤**

在 `if not rows:` 之前，插入：

```python
            # 按阈值过滤不相关结果，阈值内保留
            threshold = getattr(settings, 'RAG_SIMILARITY_THRESHOLD', 0.5)
            rows = [r for r in rows if r[5] < threshold]

            if not rows:
                return "知识库中未找到相关信息。请尝试更换关键词后重新检索。"
```

注：原 `if not rows: return "知识库中未找到相关信息。"` 改为上面新版本。

- [ ] **Step 5: should_continue 加循环保护**

```python
def should_continue(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        # 统计已完成的 ToolMessage 次数，超过上限强制结束
        tool_call_count = sum(
            1 for msg in state["messages"]
            if isinstance(msg, ToolMessage)
        )
        if tool_call_count >= getattr(settings, 'RAG_MAX_TOOL_CALLS', 5):
            return "end"
        return "tools"
    return "end"
```

需要补充 import `ToolMessage`（如果 `from langgraph.prebuilt import ToolNode` 已存在，`ToolMessage` 可以从 `langchain_core.messages` 导入）。

- [ ] **Step 6: 运行所有 RAG 测试验证**

```bash
cd backend; python -m pytest web/tests/test_chat_agent.py -v
```

Expected: 原有 6 个 + 新增 3 个 = 9 个全部 PASS

- [ ] **Step 7: Commit**

```bash
git add backend/web/views/friend/message/chat/graph.py
git commit -m "feat: RAG 距离阈值 + max_results 参数 + 循环保护"
```

---

### Task 4: 更新 TOOL_RULES（chat.py）

**Files:**
- Modify: `backend/web/views/friend/message/chat/chat.py:45-46`

- [ ] **Step 1: TOOL_RULES 追加 no-answer 指令**

在 `TOOL_RULES` 字符串末尾（`"3. 不确定时宁可查询也不要遗漏。"` 之后）追加：

```python
TOOL_RULES = (
    # ... 现有内容不变，在末尾加 ...
    "3. 不确定时宁可查询也不要遗漏。\n"
    "4. 当 search_knowledge_base 返回\"知识库中未找到相关信息\"时，\n"
    "   直接告知用户\"我目前的知识库中没有找到这方面的信息\"，\n"
    "   不要尝试编造或猜测答案。"
)
```

- [ ] **Step 2: 验证 Django 配置正常**

```bash
cd backend; python manage.py check
```

- [ ] **Step 3: Commit**

```bash
git add backend/web/views/friend/message/chat/chat.py
git commit -m "feat: TOOL_RULES 追加 RAG no-answer 诚实策略"
```

---

### Task 5: 最终验证

- [ ] **Step 1: 运行全量测试**

```bash
cd backend; python -m pytest web/tests/ -v
```

Expected: 全部通过（188 tests: 185 原有 + 3 新增）

- [ ] **Step 2: Commit（如有遗漏文件）**

---

## Self-Review 结果

1. **Spec coverage:**
   - settings 配置（RAG_DEFAULT_MAX_RESULTS / RAG_SIMILARITY_THRESHOLD / RAG_MAX_TOOL_CALLS）→ Task 1
   - search_knowledge_base max_results 参数 + 阈值过滤 → Task 3
   - should_continue 循环保护 → Task 3
   - TOOL_RULES prompt 层 → Task 4
   - 3 个测试（全超阈值 / 部分超阈值 / max_results） → Task 2

2. **Placeholder scan:** 无 TBD/TODO。

3. **Type consistency:** `RAG_DEFAULT_MAX_RESULTS`、`RAG_SIMILARITY_THRESHOLD`、`RAG_MAX_TOOL_CALLS` 在 settings、graph.py、测试中名称一致。
