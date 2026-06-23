import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from rest_framework import status

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage


class TestChatGraphRouting:
    """Layer 1: LangGraph graph logic — mock ChatOpenAI.invoke() to test agent routing"""

    @patch("web.views.friend.message.chat.graph.ChatOpenAI")
    def test_agent_no_tool_calls(self, mock_llm_class):
        """LLM returns plain text → should route to END (no tool_calls)"""
        from web.views.friend.message.chat.graph import ChatGraph

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content="Hello!", tool_calls=[])
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm_class.return_value = mock_llm

        app = ChatGraph.create_app()
        result = app.invoke({"messages": [HumanMessage(content="Hi")]})

        assert len(result["messages"]) >= 2
        last = result["messages"][-1]
        assert isinstance(last, AIMessage)
        assert last.content == "Hello!"

    @patch("web.views.friend.message.chat.graph.ChatOpenAI")
    def test_agent_with_tool_calls(self, mock_llm_class):
        """LLM returns tool_calls → should route to tools node"""
        from web.views.friend.message.chat.graph import ChatGraph

        mock_llm = MagicMock()
        # Use side_effect to return different AIMessage instances for
        # each call — the add_messages reducer deduplicates messages
        # with the same ID, so reusing the same object causes the
        # second agent output to be swallowed, leaving ToolMessage as
        # the last message and breaking should_continue.
        mock_llm.invoke.side_effect = [
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "get_time", "args": {}, "id": "call_1", "type": "tool_call",
                }],
            ),
            AIMessage(content="OK", tool_calls=[]),
        ]
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm_class.return_value = mock_llm

        app = ChatGraph.create_app()
        result = app.invoke({"messages": [HumanMessage(content="What time is it?")]})

        tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert len(tool_messages) >= 1

    @patch("web.views.friend.message.chat.graph.ChatOpenAI")
    def test_tools_to_agent_loop(self, mock_llm_class):
        """After tools node executes, should return to agent (loop)"""
        from web.views.friend.message.chat.graph import ChatGraph

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            AIMessage(content="", tool_calls=[{
                "name": "get_time", "args": {}, "id": "call_1", "type": "tool_call",
            }]),
            AIMessage(content="The time is 12:00", tool_calls=[]),
        ]
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm_class.return_value = mock_llm

        app = ChatGraph.create_app()
        result = app.invoke({"messages": [HumanMessage(content="What time is it?")]})

        last = result["messages"][-1]
        assert last.content == "The time is 12:00"

    @patch("web.views.friend.message.chat.graph.CustomEmbeddings")
    @patch("web.views.friend.message.chat.graph.ChatOpenAI")
    @patch("django.db.backends.base.base.BaseDatabaseWrapper.cursor")
    def test_search_knowledge_base_tool(self, mock_cursor_method, mock_llm_class,
                                         mock_embeddings_class):
        """search_knowledge_base JOIN 查询 + 返回 [来源] 标记"""
        from web.views.friend.message.chat.graph import ChatGraph

        # cursor() 返回 cursor 实例（支持 context manager）
        mock_cursor_instance = MagicMock()
        # __enter__ 返回自身，确保 with connection.cursor() as cursor:
        # 中的 cursor 仍指向同一个 mock（保有 fetchall.return_value 等）
        mock_cursor_instance.__enter__.return_value = mock_cursor_instance
        mock_cursor_instance.fetchall.return_value = [
            (1, "阿里云百炼平台介绍内容...", 2, 5, "平台使用指南.pdf", 0.12),
            (2, "另一段检索内容...", 7, 5, "平台使用指南.pdf", 0.18),
        ]
        mock_cursor_method.return_value = mock_cursor_instance

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
        result = app.invoke({"messages": [HumanMessage(content="What is Bailian")], "user_id": 42})

        # 验证 ToolMessage 包含来源标记
        tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert len(tool_messages) >= 1
        content = tool_messages[0].content
        assert "[来源1: 平台使用指南.pdf 第3段]" in content
        assert "阿里云百炼平台介绍内容" in content

    def test_get_time_tool_format(self):
        """get_time tool returns correct time format YYYY-MM-DD HH:MM:SS"""
        from web.views.friend.message.chat.graph import ChatGraph

        with patch("web.views.friend.message.chat.graph.ChatOpenAI") as mock_llm_class:
            mock_llm = MagicMock()
            # Use side_effect to provide different AIMessage instances
            # for each call — avoids add_messages deduplication.
            mock_llm.invoke.side_effect = [
                AIMessage(
                    content="",
                    tool_calls=[{
                        "name": "get_time", "args": {}, "id": "call_t", "type": "tool_call",
                    }],
                ),
                AIMessage(content="OK", tool_calls=[]),
            ]
            mock_llm.bind_tools.return_value = mock_llm
            mock_llm_class.return_value = mock_llm

            app = ChatGraph.create_app()
            result = app.invoke({"messages": [HumanMessage(content="What time?")]})

        tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert len(tool_msgs) >= 1
        # format: YYYY-MM-DD HH:MM:SS
        import re
        time_pattern = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"
        assert re.match(time_pattern, tool_msgs[0].content), \
            f"Unexpected format: {tool_msgs[0].content}"

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
        # call_args_list[0] 是 SELECT 检索查询（后续 RetrievalTrace INSERT 走同一 mock cursor）
        sql = mock_cursor_instance.execute.call_args_list[0][0][0]
        params = mock_cursor_instance.execute.call_args_list[0][0][1]
        assert "LIMIT %s" in sql
        assert params[-1] == 1  # max_results 作为最后一个参数

        tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert len(tool_messages) >= 1


class TestChatSSEEndpoint:
    """Layer 2: SSE endpoint integration — mock ChatGraph.create_app() + websockets"""

    @pytest.fixture
    def mock_compiled_graph(self):
        """Return a mock graph whose astream produces a preset chunk sequence"""
        mock_graph = MagicMock()

        async def mock_astream(inputs, stream_mode="messages"):
            # First chunk: empty content (filtered by tts_sender)
            chunk1 = AIMessageChunk(content="")
            yield (chunk1, {})

            # Second chunk: text content
            chunk2 = AIMessageChunk(content="Hello")
            yield (chunk2, {})

            # Third chunk: more text with usage metadata
            chunk3 = AIMessageChunk(content=" world")
            # Set usage_metadata as a plain attribute
            chunk3.usage_metadata = {
                "input_tokens": 100,
                "output_tokens": 20,
                "total_tokens": 120,
            }
            yield (chunk3, {})

        mock_graph.astream = mock_astream
        return mock_graph

    @pytest.fixture
    def mock_tasks_started_ws(self):
        """Mock WebSocket that responds with task-started, then task-finished for tts_receiver"""
        mock_ws = AsyncMock()

        # Track how many times __aiter__ is called so we can give
        # task-started on the first call and task-finished on the second
        call_counter = [0]

        async def ws_async_iterator():
            call_counter[0] += 1
            if call_counter[0] == 1:
                # First async for (in run_tts_task): task-started
                yield json.dumps({"header": {"event": "task-started"}})
            else:
                # Second async for (in tts_receiver): task-finished triggers break
                yield json.dumps({"header": {"event": "task-finished"}})

        mock_ws.__aiter__ = ws_async_iterator
        return mock_ws

    @patch("web.views.friend.message.chat.chat.websockets.connect")
    @patch("web.views.friend.message.chat.chat.ChatGraph.create_app")
    def test_sse_text_stream(self, mock_create_app, mock_ws_connect,
                             auth_client, friend, mock_compiled_graph, mock_tasks_started_ws):
        """SSE stream should contain content events"""
        mock_create_app.return_value = mock_compiled_graph
        mock_ws_connect.return_value = mock_tasks_started_ws

        resp = auth_client.post(
            "/api/friend/message/chat/",
            {"friend_id": friend.id, "message": "Hi"},
        )
        assert resp.status_code == 200
        assert resp["Content-Type"] == "text/event-stream"

        content = b"".join(resp.streaming_content).decode("utf-8")
        lines = content.strip().split("\n\n")
        content_lines = [l for l in lines if "content" in l and "[DONE]" not in l]
        assert len(content_lines) >= 1

    @patch("web.views.friend.message.chat.chat.websockets.connect")
    @patch("web.views.friend.message.chat.chat.ChatGraph.create_app")
    def test_sse_done_marker(self, mock_create_app, mock_ws_connect,
                             auth_client, friend, mock_compiled_graph, mock_tasks_started_ws):
        """Stream ends → last event is [DONE]"""
        mock_create_app.return_value = mock_compiled_graph
        mock_ws_connect.return_value = mock_tasks_started_ws

        resp = auth_client.post(
            "/api/friend/message/chat/",
            {"friend_id": friend.id, "message": "Hi"},
        )
        content = b"".join(resp.streaming_content).decode("utf-8")
        assert "[DONE]" in content

    @patch("web.views.friend.message.chat.chat.websockets.connect")
    @patch("web.views.friend.message.chat.chat.ChatGraph.create_app")
    def test_sse_message_created(self, mock_create_app, mock_ws_connect,
                                 auth_client, friend, mock_compiled_graph, mock_tasks_started_ws):
        """After stream ends → Message record written to DB"""
        from web.models.friend import Message

        mock_create_app.return_value = mock_compiled_graph
        mock_ws_connect.return_value = mock_tasks_started_ws

        resp = auth_client.post(
            "/api/friend/message/chat/",
            {"friend_id": friend.id, "message": "Hi"},
        )
        # Consume the stream fully
        b"".join(resp.streaming_content)

        assert Message.objects.filter(friend=friend).count() >= 1

    def test_sse_friend_not_found(self, auth_client):
        """Friend does not exist → SSE error stream"""
        resp = auth_client.post(
            "/api/friend/message/chat/",
            {"friend_id": 99999, "message": "Hi"},
        )
        content = b"".join(resp.streaming_content).decode("utf-8")
        assert "error" in content
        assert "[DONE]" in content

    def test_sse_requires_auth(self, api_client, friend):
        """No token → 401"""
        resp = api_client.post(
            "/api/friend/message/chat/",
            {"friend_id": friend.id, "message": "Hi"},
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("web.views.friend.message.chat.chat.check_quota")
    def test_quota_exceeded_returns_429(self, mock_check, auth_client, friend):
        """LLM 配额超限 → 429"""
        mock_check.return_value = (False, 10_000, 10_000)
        resp = auth_client.post(
            "/api/friend/message/chat/",
            {"friend_id": friend.id, "message": "你好"},
        )
        assert resp.status_code == 429
        assert "配额" in resp.json()["message"]

    @patch("web.views.friend.message.chat.chat.check_quota")
    @patch("web.views.friend.message.chat.chat.ChatGraph.create_app")
    def test_tts_quota_exceeded_skips_audio(
        self, mock_create_app, mock_check, auth_client, friend, mock_compiled_graph,
    ):
        """TTS 配额超限 → 文字流正常，无音频"""
        mock_create_app.return_value = mock_compiled_graph

        def side_effect(user_id, api_type):
            if api_type == 'llm':
                return (True, 0, 10_000)
            elif api_type == 'tts':
                return (False, 10_000, 10_000)
            return (True, 0, 10_000)
        mock_check.side_effect = side_effect

        resp = auth_client.post(
            "/api/friend/message/chat/",
            {"friend_id": friend.id, "message": "Hi"},
        )
        assert resp.status_code == 200

        content = b"".join(resp.streaming_content).decode("utf-8")
        lines = content.strip().split("\n\n")

        # 有文字
        content_lines = [l for l in lines if "content" in l and "[DONE]" not in l]
        assert len(content_lines) >= 1, f"Expected content events, got: {lines}"

        # 无音频
        audio_lines = [l for l in lines if "audio" in l]
        assert len(audio_lines) == 0, "TTS 配额超限不应有音频"

        # 有 DONE 哨兵
        assert any("[DONE]" in l for l in lines)


class TestKnowledgeBaseToolDescription:
    """search_knowledge_base tool description 不应限定百炼平台"""

    def test_tool_description_does_not_hardcode_bailian(self):
        """tool description 不应出现'阿里云百炼'字样"""
        import inspect
        from web.views.friend.message.chat.graph import ChatGraph
        source = inspect.getsource(ChatGraph.create_app)
        assert '阿里云百炼' not in source, \
            'search_knowledge_base tool description 不应写死百炼平台'
