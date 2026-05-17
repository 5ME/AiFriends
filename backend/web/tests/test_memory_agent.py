import pytest
from unittest.mock import patch, MagicMock

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from web.models.friend import Friend, Message


class TestMemoryTrigger:
    """记忆触发时机测试"""

    def test_memory_triggered_at_10(self, friend):
        """第 10 条消息后 update_memory 写入 Friend.memory"""
        from web.views.friend.message.memory import update

        # Create 9 existing messages
        for i in range(9):
            Message.objects.create(
                friend=friend,
                user_message=f"msg {i}",
                input="{}",
                output=f"reply {i}",
            )

        with patch.object(update, "MemoryGraph") as mock_graph_class:
            mock_app = MagicMock()
            mock_app.invoke.return_value = {
                "messages": [AIMessage(content="Summary of conversation")]
            }
            mock_graph_class.create_app.return_value = mock_app

            # Total messages is now 9, add the 10th
            Message.objects.create(
                friend=friend,
                user_message="msg 9",
                input="{}",
                output="reply 9",
            )

            update.update_memory(friend)
            friend.refresh_from_db()
            assert friend.memory == "Summary of conversation"

    def test_memory_not_triggered_at_5(self, friend):
        """5 条消息时 count % 10 != 0"""
        for i in range(5):
            Message.objects.create(
                friend=friend,
                user_message=f"msg {i}",
                input="{}",
                output=f"reply {i}",
            )
        count = Message.objects.filter(friend=friend).count()
        assert count == 5
        assert count % 10 != 0


class TestMemoryField:
    """记忆字段更新测试"""

    def test_memory_field_updated(self, friend):
        """Friend.memory 被写入新值"""
        from web.views.friend.message.memory import update

        with patch.object(update, "MemoryGraph") as mock_graph_class:
            mock_app = MagicMock()
            mock_app.invoke.return_value = {
                "messages": [AIMessage(content="Updated summary")]
            }
            mock_graph_class.create_app.return_value = mock_app

            update.update_memory(friend)
            friend.refresh_from_db()
            assert friend.memory == "Updated summary"
            assert friend.updated_at is not None


class TestMemoryGraph:
    """Memory Agent 图逻辑测试"""

    @patch("web.views.friend.message.memory.graph.ChatOpenAI")
    def test_memory_agent_graph(self, mock_llm_class):
        """Mock LLM → 图返回摘要 AIMessage"""
        from web.views.friend.message.memory.graph import MemoryGraph

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content="记忆摘要: 用户讨论了天气")
        mock_llm_class.return_value = mock_llm

        app = MemoryGraph.create_app()
        result = app.invoke({
            "messages": [
                SystemMessage(content="你是一个记忆摘要助手"),
                HumanMessage(content="user: 今天天气真好\nai: 是啊"),
            ]
        })

        assert len(result["messages"]) >= 2
        last = result["messages"][-1]
        assert isinstance(last, AIMessage)
        assert "记忆摘要" in last.content
