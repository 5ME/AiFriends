import pytest

from web.models.friend import SystemPrompt
from langchain_core.messages import HumanMessage


class TestSystemPromptLoading:
    """验证 SystemPrompt 查询使用正确的枚举值"""

    def test_add_system_prompt_loads_reply_prompts(self, friend):
        """chat.py 的 add_system_prompt 应加载 title='reply' 的 SystemPrompt"""
        from web.views.friend.message.chat.chat import add_system_prompt

        SystemPrompt.objects.create(
            title=SystemPrompt.Title.REPLY,
            order_number=0,
            prompt="【测试规则】请用文言文回答",
        )

        inputs = {"messages": [HumanMessage(content="你好")]}
        result = add_system_prompt(inputs, friend)

        messages = result["messages"]
        assert len(messages) == 2  # SystemMessage + HumanMessage
        system_msg = messages[0]
        assert "请用文言文回答" in system_msg.content
        assert friend.character.system_prompt in system_msg.content

    def test_create_system_message_loads_memory_prompts(self, friend):
        """memory/update.py 的 create_system_message 应加载 title='memory' 的 SystemPrompt"""
        from web.views.friend.message.memory.update import create_system_message

        SystemPrompt.objects.create(
            title=SystemPrompt.Title.MEMORY,
            order_number=0,
            prompt="【记忆规则】请用第三人称总结",
        )

        msg = create_system_message()
        assert "请用第三人称总结" in msg.content
