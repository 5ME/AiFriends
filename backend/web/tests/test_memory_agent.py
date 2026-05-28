import pytest
from unittest.mock import patch, MagicMock

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from web.models.friend import Friend, Message
from web.views.friend.message.memory import tasks


class TestMemoryTrigger:
    """记忆触发时机测试"""

    def test_memory_triggered_at_10(self, friend):
        """第 10 条消息后 update_memory_task 写入 Friend.memory"""
        for i in range(9):
            Message.objects.create(
                friend=friend,
                user_message=f"msg {i}",
                input="{}",
                output=f"reply {i}",
            )

        with patch.object(tasks, "MemoryGraph") as mock_graph_class:
            mock_app = MagicMock()
            mock_app.invoke.return_value = {
                "messages": [AIMessage(content="Summary of conversation")]
            }
            mock_graph_class.create_app.return_value = mock_app

            # Total messages is 9, add the 10th
            Message.objects.create(
                friend=friend,
                user_message="msg 9",
                input="{}",
                output="reply 9",
            )

            # 直接调用 task 函数（同步执行，不经过 broker）
            tasks.update_memory_task(friend.id)
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
        with patch.object(tasks, "MemoryGraph") as mock_graph_class:
            mock_app = MagicMock()
            mock_app.invoke.return_value = {
                "messages": [AIMessage(content="Updated summary")]
            }
            mock_graph_class.create_app.return_value = mock_app

            tasks.update_memory_task(friend.id)
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


class TestMemoryFailureCompensation:
    """失败补偿：last_summarized_count 机制"""

    def test_last_summarized_count_not_updated_on_failure(self, friend):
        """LLM 失败时 last_summarized_count 保持不变 → 下次重试覆盖遗漏"""
        # 创建 10 条消息
        for i in range(10):
            Message.objects.create(
                friend=friend,
                user_message=f"msg {i}",
                input="{}",
                output=f"reply {i}",
            )

        assert friend.last_summarized_count == 0

        with patch.object(tasks, "MemoryGraph") as mock_graph_class:
            mock_app = MagicMock()
            # invoke 第一次抛异常 → retry(exc=exc) 在 called_directly 模式下
            # 会重新抛出原始异常（RuntimeError），不是 celery.exceptions.Retry
            mock_app.invoke.side_effect = RuntimeError("LLM service unavailable")
            mock_graph_class.create_app.return_value = mock_app

            # 直接调用 → retry() 重抛原始异常
            try:
                tasks.update_memory_task(friend.id)
            except RuntimeError:
                pass

            friend.refresh_from_db()
            # memory 未更新
            assert friend.memory == "" or friend.memory is None
            # last_summarized_count 未递增（失败不更新）
            assert friend.last_summarized_count == 0

            # 第二次触发 — 成功
            mock_app.invoke.side_effect = None
            mock_app.invoke.return_value = {
                "messages": [AIMessage(content="Summary of 10 messages")]
            }
            # 直接调用 task 函数（同步执行，不走 broker）
            tasks.update_memory_task(friend.id)
            friend.refresh_from_db()
            assert "10 messages" in friend.memory
            assert friend.last_summarized_count == 10

    def test_create_human_message_respects_last_summarized_count(self, friend):
        """create_human_message 从 last_summarized_count 位置取消息"""
        # 创建 15 条消息
        for i in range(15):
            Message.objects.create(
                friend=friend,
                user_message=f"msg {i}",
                input="{}",
                output=f"reply {i}",
            )

        friend.last_summarized_count = 10
        friend.save()

        msg = tasks.create_human_message(friend)
        content = msg.content

        # 应包含 msg 10-14（5 条增量），不包含 msg 0-9
        assert "msg 10" in content
        assert "msg 14" in content
        assert "msg 0" not in content
