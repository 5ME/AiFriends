# RAG 引用来源 + Retrieval Trace 落库 — 设计文档

> **Date:** 2026-06-06 | **Scope:** `search_knowledge_base` 返回来源标注 + `RetrievalTrace` 落库 + SSE 携带 citation 事件

**Goal:** 让 RAG 检索可溯源、可评估。`search_knowledge_base` 返回带文档来源标注的结构化文本，每次检索命中写入 `RetrievalTrace` 表，SSE 流中携带结构化 citation 数据供前端展示 "📎 参考来源：xxx文档 第N段"。

**背景:** Phase 1.5 已将 tool-calling 可靠性修复到 100%/87%/0%。现在 RAG 能稳定触发，但检索结果不溯源、无 trace，评估 RAG 质量时无数据可依。本设计为 Phase 3.2（RAG 评估体系）建立数据地基。

---

## 1. 总体流程

```
用户消息
    → app.astream(inputs)
        → Agent 调 search_knowledge_base
            → JOIN 查询 pgvector（拿 title + distance）
            → 写入 RetrievalTrace × N
            → 返回 "[来源1: xxx.pdf 第5段]\n{content}"
        → ToolMessage 到达 tts_sender 循环
            → 正则提取 citations → mq.put_nowait({citations})
        → LLM 流式生成 → mq.put_nowait({content})
    → event_stream 循环
        → yield citations SSE 事件（最先）
        → yield content SSE 事件（随后）
        → yield [DONE]
```

---

## 2. RetrievalTrace 模型

### 2.1 Model

`backend/web/models/retrieval_trace.py`（新增）：

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
    chunk_index = models.IntegerField()                 # 命中 chunk 在文档中的序号
    distance = models.FloatField()                      # 余弦距离（pgvector <=> 返回值）
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', '-created_at']),   # 按用户查最近 trace
            models.Index(fields=['document']),              # 按文档查被引情况
        ]
```

### 2.2 设计要点

| 决策 | 理由 |
|------|------|
| **不关联 Message** | tool 执行时 Message 尚不存在（SSE 流结束后才保存），存 `user` + `created_at` 足以按时间关联 |
| **`distance` 而非 `score`** | pgvector `<=>` 返回余弦距离（越小越相似），存原始值不转换，评估时可按需换算 |
| **`document` 可空** | 系统知识库 chunk 可能 `document_id` 为 NULL |
| **系统知识库 chunk 不写 trace** | 无 `document_id` → 跳过落库。系统知识库的检索命中率、distance 分布无法通过 RetrievalTrace 评估。如需评估，后续给系统知识库 chunk 关联 document |
| **user + created_at 复合索引** | 查询 "用户最近检索了什么" 高频，覆盖索引 |

### 2.3 迁移

全新模型，`makemigrations` 自动生成，不涉及已有表变更。

---

## 3. `search_knowledge_base` 重构

### 3.1 当前问题

`graph.py` 中用 `objects.raw()` 查询，不返回关联字段（`document.title`），无法标注来源。也没有 distance 信息，评估时无从知道检索质量。

### 3.2 目标代码

```python
from django.db import connection

@tool
def search_knowledge_base(query: str, state: Annotated[dict, InjectedState]) -> str:
    """
    在知识库中检索与用户问题相关的文档内容。
    ...  # docstring 不变
    """
    from web.models.document import DocumentChunk, UserDocument
    from web.models.retrieval_trace import RetrievalTrace

    user_id = state.get("user_id")
    logger.info('RAG 知识库检索开始, query=%s, user_id=%s', query[:100], user_id)

    embeddings = CustomEmbeddings(user_id=user_id)
    emb = embeddings.embed_query(query)

    chunk_table = DocumentChunk._meta.db_table
    doc_table = UserDocument._meta.db_table

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
        # 明确 if/elif/else：避免三目运算符优先级歧义
        if title:
            source_label = title
        elif document_id:
            source_label = f"文档{document_id}"
        else:
            source_label = "系统知识库"
        # chunk_index 为 0-based，展示时 +1 为人类友好的 1-based
        parts.append(f"[来源{i+1}: {source_label} 第{chunk_index + 1}段]")
        parts.append(content)
        parts.append("")

        # 写入检索 trace（fail-safe：落库失败不影响工具返回值）
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
                logger.exception('RetrievalTrace 写入失败, document_id=%s', document_id)

    logger.info('RAG 检索完成, hits=%d', len(rows))
    return "\n".join(parts)
```

### 3.3 关键变化

| 旧 | 新 | 原因 |
|----|----|------|
| `objects.raw()` | `connection.cursor()` | 需要 LEFT JOIN 拿 `title` + 用 `<=>` 算子拿 `distance` |
| 返回纯内容片段 | 返回 `[来源N: title 第M段]` 标记 | LLM 看到文档名，能自然引用来源 |
| 无 trace | 命中即写 `RetrievalTrace` | Phase 3.2 评估的数据基础 |

### 3.4 为什么用自然语言标记而非 JSON

| | 自然语言 + 标记 | JSON |
|----|----|----|
| LLM 阅读 | 直接理解，无解析负担 | 需先"解码"JSON 结构 |
| 自然引用 | `[来源1: 社保.pdf]` 提示 LLM 自然提及 | LLM 需自行推断用途 |
| v4-flash 兼容 | 友好（Flash 模型指令遵循弱于 Full） | 有风险 |
| 前端解析 | 正则一行 | `json.loads()` 一行 |

**结论：** 标记方案对 LLM 和前端双方都最优。LLM 看到人类可读的标注，能自然地说出"根据你上传的社保政策解读.pdf..."。

---

## 4. SSE 流携带 citation 事件

### 4.1 流序列

LangGraph `stream_mode="messages"` 的消息时序：

```
AIMessage(tool_calls=[search_knowledge_base])  ← agent 决策
    ↓
ToolMessage(name="search_knowledge_base")       ← 工具执行完成（含来源标记）
    ↓
AIMessageChunk("根据")                           ← LLM 流式回复开始
AIMessageChunk("你上传的")
AIMessageChunk("社保政策...")
```

**关键：** `ToolMessage` 在第一个 `AIMessageChunk` 之前到达。在此处 emit citations 事件，前端就能在文本到来前拿到来源数据。

### 4.2 `tts_sender()` — 检测 ToolMessage

`chat.py` 中 `tts_sender()` 的 `app.astream()` 循环里，新增 `ToolMessage` 检测分支：

```python
import re
from langchain_core.messages import ToolMessage

CITATION_RE = re.compile(r'\[来源(\d+): (.+?) 第(\d+)段\]')

async for msg, metadata in app.astream(inputs, stream_mode="messages"):
    # 新增：检测知识库检索结果，提取引用来源
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
        if msg.content:
            # TTS 发送 + content 入队逻辑不变
            ...
```

### 4.3 `event_stream()` — 转发 citations 到 SSE

```python
while True:
    msg = mq.get()
    if msg is None:
        break
    # 新增：转发 citation 事件
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

### 4.4 SSE 事件格式

```
data: {"citations":[{"index":1,"title":"社保政策解读.pdf","chunk_index":5},{"index":2,"title":"就业指南.md","chunk_index":12}]}

data: {"content":"根据你上传的社保政策解读.pdf..."}

data: {"audio":"..."}

data: [DONE]
```

与现有 `content`/`audio`/`error` 事件格式一致。前端只需在 SSE 解析 switch 中新增一个 `citations` 分支。

### 4.5 边界情况

| 场景 | 行为 |
|------|------|
| LLM 不调 tool（纯闲聊） | 无 ToolMessage → 无 citations 事件 |
| 检索无结果 | 返回 "未找到相关信息" → 无 `[来源]` 标记 → 正则无匹配 → 无 citations 事件 |
| 多次检索（agent 循环） | 每次 ToolMessage 都 emit，前端以最后一次为准 |
| 系统知识库 chunk（无 document） | 来源标记显示 "系统知识库"，不写 RetrievalTrace（无 document_id） |

---

## 5. 测试

### 5.1 已有测试适配

`test_chat_agent.py:test_search_knowledge_base_tool` — mock 了 `CustomEmbeddings` + `DocumentChunk.objects.raw`。需改为 mock `connection.cursor()`。cursor 涉及 context manager protocol（`__enter__`/`__exit__`），mock 代码比原来的 `objects.raw` 稍长：

```python
from unittest.mock import MagicMock, patch

@patch("django.db.connection.cursor")
def test_search_knowledge_base_returns_source_markers(self, mock_cursor):
    # cursor() 返回一个 context manager，__enter__ 返回 cursor 实例
    mock_cursor_instance = MagicMock()
    mock_cursor_instance.fetchall.return_value = [
        (1, "检索到的内容", 0, 1, "测试文档.pdf", 0.12),
        (2, "另一段内容", 3, 1, "测试文档.pdf", 0.18),
    ]
    mock_cursor.return_value.__enter__.return_value = mock_cursor_instance

    result = search_knowledge_base("test query", {"user_id": 1})
    assert "[来源1: 测试文档.pdf 第1段]" in result
    assert "检索到的内容" in result
    assert mock_cursor_instance.execute.called
```

### 5.2 新增测试

| 测试 | 验证点 | 类型 |
|------|--------|------|
| `test_search_knowledge_base_returns_source_markers` | 返回文本含 `[来源1: title 第N段]` | 单元（mock cursor） |
| `test_search_knowledge_base_writes_retrieval_trace` | 3 hits → 3 条 RetrievalTrace | 集成 |
| `test_search_knowledge_base_empty_result_no_trace` | 无命中时 trace 表无新增 | 集成 |
| `test_search_knowledge_base_join_title` | LEFT JOIN 拿到 document.title | 单元 |
| `test_citation_re_parsing` | `CITATION_RE` 正确提取 index/title/chunk_index | 单元 |
| `test_sse_emits_citations_before_content` | ToolMessage → citations 入队 → content 入队，顺序正确 | 单元（mock astream） |

---

## 6. 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/web/models/retrieval_trace.py` | **新增** | RetrievalTrace 模型 |
| `backend/web/migrations/XXXX_retrieval_trace.py` | **新增** | makemigrations 自动生成 |
| `backend/web/views/friend/message/chat/graph.py` | **修改** | `search_knowledge_base`：JOIN 查询 + 来源标记 + 落库 |
| `backend/web/views/friend/message/chat/chat.py` | **修改** | `tts_sender()` 加 ToolMessage 检测 + `event_stream()` 加 citations 分支 |
| `backend/web/tests/test_chat_agent.py` | **修改** | 适配新 tool 返回格式（mock cursor 替代 mock raw） |
| `backend/web/tests/test_retrieval_trace.py` | **新增** | RetrievalTrace 模型 + 落库测试 |

---

## 7. 验收标准

| 验证点 | 方法 | 标准 |
|--------|------|------|
| tool 返回来源标记 | 单元测试 | 含 `[来源N: title 第M段]` |
| RetrievalTrace 落库 | 集成测试 | 3 hits → 3 条 trace 记录 |
| SSE 含 citations 事件 | 手工 `curl` + 知识类问题 | 第一条 data.event 为 `citations` |
| 闲聊不产生 citation | 手工 "你好" | SSE 中无 `citations` 事件 |
| 已有测试不退化 | `pytest web/tests/ -v --ignore=test_tool_calling.py` | 全部通过 |

---

## 8. 不做什么

- **不建单独的 migration 管理命令** — 全新模型，`makemigrations` 自动生成
- **不改前端** — 先让 SSE 带上 citation 数据，前端接入在后续迭代中完成
- **不关联 Message 到 RetrievalTrace** — tool 执行时 Message 不存在，按时间关联即可
- **不重跑 `test_tool_calling.py`** — 本次不改 tool-call 行为，不需重新评估
