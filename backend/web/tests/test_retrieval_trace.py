import json
import pytest
import re
from unittest.mock import patch, MagicMock, AsyncMock

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage


CITATION_RE = re.compile(r'\[来源(\d+): (.+?) 第(\d+)段\]')


def _setup_cursor_mock(mock_cursor_method, rows):
    """Set up mock cursor with __enter__ to support context manager usage."""
    mock_cursor_instance = MagicMock()
    mock_cursor_instance.__enter__.return_value = mock_cursor_instance
    mock_cursor_instance.fetchall.return_value = rows
    mock_cursor_method.return_value = mock_cursor_instance
    return mock_cursor_instance


class TestSearchKnowledgeBaseResult:
    """验证 search_knowledge_base 返回值格式"""

    @patch("web.views.friend.message.chat.graph.CustomEmbeddings")
    @patch("web.views.friend.message.chat.graph.ChatOpenAI")
    @patch("django.db.backends.base.base.BaseDatabaseWrapper.cursor")
    def test_returns_source_markers(self, mock_cursor_method, mock_llm_class,
                                     mock_embeddings_class):
        """tool 返回值应包含 [来源N: title 第M段] 格式标记"""
        from web.views.friend.message.chat.graph import ChatGraph

        _setup_cursor_mock(mock_cursor_method, [
            (1, "社保制度介绍...", 0, 3, "社保政策.pdf", 0.15),
            (2, "养老保险说明...", 4, 3, "社保政策.pdf", 0.22),
        ])

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
    @patch("django.db.backends.base.base.BaseDatabaseWrapper.cursor")
    def test_empty_result_returns_not_found(self, mock_cursor_method, mock_llm_class,
                                              mock_embeddings_class):
        """无命中时返回 '未找到相关信息'"""
        from web.views.friend.message.chat.graph import ChatGraph

        _setup_cursor_mock(mock_cursor_method, [])  # 空结果

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
    @patch("django.db.backends.base.base.BaseDatabaseWrapper.cursor")
    def test_system_knowledge_no_title(self, mock_cursor_method, mock_llm_class,
                                         mock_embeddings_class):
        """系统知识库 chunk（无 document_id + 无 title）显示 '系统知识库'"""
        from web.views.friend.message.chat.graph import ChatGraph

        _setup_cursor_mock(mock_cursor_method, [
            (1, "系统知识内容...", 0, None, None, 0.30),  # NULL document + NULL title
        ])

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


@pytest.mark.django_db
class TestRetrievalTracePersistence:
    """验证 RetrievalTrace.objects.create() 调用行为 — mock create 验证调用次数和参数"""

    @patch("web.models.retrieval_trace.RetrievalTrace.objects.create")
    @patch("web.views.friend.message.chat.graph.CustomEmbeddings")
    @patch("web.views.friend.message.chat.graph.ChatOpenAI")
    @patch("django.db.backends.base.base.BaseDatabaseWrapper.cursor")
    def test_writes_trace_for_each_hit(self, mock_cursor_method, mock_llm_class,
                                         mock_embeddings_class, mock_create, user_profile):
        """3 个命中 chunk（均有 document_id）→ 调用 create() 3 次"""
        from web.views.friend.message.chat.graph import ChatGraph

        _setup_cursor_mock(mock_cursor_method, [
            (1, "内容A", 2, 1, "DocA", 0.10),
            (2, "内容B", 5, 1, "DocA", 0.12),
            (3, "内容C", 1, 2, "DocB", 0.15),
        ])

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

        app = ChatGraph.create_app()
        app.invoke(
            {"messages": [HumanMessage(content="测试")], "user_id": user_profile.id}
        )

        # 3 个有 document_id 的 chunk → 调用 create 3 次
        assert mock_create.call_count == 3
        # 验证 query 参数正确
        assert mock_create.call_args_list[0][1]["query"] == "test query text"
        assert mock_create.call_args_list[0][1]["chunk_index"] == 2
        assert mock_create.call_args_list[0][1]["distance"] == 0.10
        # 第 3 条是不同 document
        assert mock_create.call_args_list[2][1]["document_id"] == 2

    @patch("web.models.retrieval_trace.RetrievalTrace.objects.create")
    @patch("web.views.friend.message.chat.graph.CustomEmbeddings")
    @patch("web.views.friend.message.chat.graph.ChatOpenAI")
    @patch("django.db.backends.base.base.BaseDatabaseWrapper.cursor")
    def test_no_document_id_skips_trace(self, mock_cursor_method, mock_llm_class,
                                          mock_embeddings_class, mock_create, user_profile):
        """系统知识库 chunk（无 document_id）不调用 create()"""
        from web.views.friend.message.chat.graph import ChatGraph

        _setup_cursor_mock(mock_cursor_method, [
            (1, "系统内容", 0, None, None, 0.30),  # NULL document_id
        ])

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

        app = ChatGraph.create_app()
        app.invoke(
            {"messages": [HumanMessage(content="测试")], "user_id": user_profile.id}
        )

        mock_create.assert_not_called()

    @patch("web.models.retrieval_trace.RetrievalTrace.objects.create")
    @patch("web.views.friend.message.chat.graph.CustomEmbeddings")
    @patch("web.views.friend.message.chat.graph.ChatOpenAI")
    @patch("django.db.backends.base.base.BaseDatabaseWrapper.cursor")
    def test_empty_result_no_trace(self, mock_cursor_method, mock_llm_class,
                                     mock_embeddings_class, mock_create, user_profile):
        """无命中时不调用 create()"""
        from web.views.friend.message.chat.graph import ChatGraph

        _setup_cursor_mock(mock_cursor_method, [])

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

        app = ChatGraph.create_app()
        app.invoke(
            {"messages": [HumanMessage(content="测试")], "user_id": user_profile.id}
        )

        mock_create.assert_not_called()


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
