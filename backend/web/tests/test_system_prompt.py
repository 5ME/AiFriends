import pytest

from web.models.friend import SystemPrompt
from langchain_core.messages import HumanMessage


class TestSystemPromptLoading:
    """验证 SystemPrompt 查询使用正确的枚举值"""

    def test_add_system_prompt_loads_reply_prompts(self, friend):
        """chat.py add_system_prompt 应输出 3 层独立 SystemMessage"""
        from web.views.friend.message.chat.chat import add_system_prompt, TOOL_RULES

        SystemPrompt.objects.create(
            title=SystemPrompt.Title.REPLY,
            order_number=0,
            prompt="【测试框架】基础行为约束",
        )

        # 设置角色性格（确保不被 DB 内容淹没）
        friend.character.system_prompt = "我是角色性格测试"
        friend.character.save()

        inputs = {"messages": [HumanMessage(content="你好")]}
        result = add_system_prompt(inputs, friend)

        messages = result["messages"]
        # 预期：TOOL_RULES + 角色性格 + 框架约束 + HumanMessage = 4 条
        assert len(messages) == 4, f"Expected 4 messages, got {len(messages)}"

        # 第 1 条：工具规则（代码常量）
        msg0 = messages[0]
        assert "知识库查询规则" in msg0.content
        assert msg0.content == TOOL_RULES

        # 第 2 条：角色性格
        msg1 = messages[1]
        assert "我是角色性格测试" in msg1.content
        assert "角色性格" in msg1.content

        # 第 3 条：系统框架（DB）
        msg2 = messages[2]
        assert "基础行为约束" in msg2.content

        # 第 4 条：用户消息
        msg3 = messages[3]
        assert msg3.content == "你好"

    def test_create_system_message_loads_memory_prompts(self, friend):
        """memory/tasks.py 的 create_system_message 应加载 title='memory' 的 SystemPrompt"""
        from web.views.friend.message.memory.tasks import create_system_message

        SystemPrompt.objects.create(
            title=SystemPrompt.Title.MEMORY,
            order_number=0,
            prompt="【记忆规则】请用第三人称总结",
        )

        msg = create_system_message()
        assert "请用第三人称总结" in msg.content

    def test_personality_before_framework(self, friend):
        """角色性格 SystemMessage 应在系统框架之前"""
        from web.views.friend.message.chat.chat import add_system_prompt

        SystemPrompt.objects.create(
            title=SystemPrompt.Title.REPLY,
            order_number=0,
            prompt="【框架】",
        )
        friend.character.system_prompt = "【性格】"
        friend.character.save()

        inputs = {"messages": [HumanMessage(content="test")]}
        result = add_system_prompt(inputs, friend)
        messages = result["messages"]

        personality_idx = next(i for i, m in enumerate(messages) if "性格" in m.content)
        framework_idx = next(i for i, m in enumerate(messages) if "框架" in m.content)
        assert personality_idx < framework_idx, \
            f"性格({personality_idx})应在框架({framework_idx})之前"

    def test_no_personality_skips_second_message(self, friend):
        """Character.system_prompt 和 memory 均为空时，不注入第 2 条"""
        from web.views.friend.message.chat.chat import add_system_prompt

        SystemPrompt.objects.create(
            title=SystemPrompt.Title.REPLY,
            order_number=0,
            prompt="【框架】",
        )
        friend.character.system_prompt = ""  # 空
        friend.memory = ""  # 空
        friend.character.save()
        friend.save()

        inputs = {"messages": [HumanMessage(content="test")]}
        result = add_system_prompt(inputs, friend)
        messages = result["messages"]

        contents = [m.content for m in messages]
        assert not any("角色性格" in c for c in contents), \
            "空性格不应注入角色性格 SystemMessage"

    def test_no_framework_skips_third_message(self, friend):
        """DB 中无 REPLY 记录时，不注入第 3 条"""
        from web.views.friend.message.chat.chat import add_system_prompt

        # 确保 DB 中无 REPLY
        SystemPrompt.objects.filter(title=SystemPrompt.Title.REPLY).delete()

        friend.character.system_prompt = "【性格】"
        friend.character.save()

        inputs = {"messages": [HumanMessage(content="test")]}
        result = add_system_prompt(inputs, friend)
        messages = result["messages"]

        # 预期：TOOL_RULES + 角色性格 + HumanMessage = 3 条（无框架层）
        assert len(messages) == 3, f"Expected 3 messages, got {len(messages)}"

    def test_tool_rules_always_first(self, friend):
        """工具规则始终是 messages[0]，无论其他层是否存在"""
        from web.views.friend.message.chat.chat import add_system_prompt, TOOL_RULES

        # 无 DB 框架、无角色性格 — 极端情况
        SystemPrompt.objects.filter(title=SystemPrompt.Title.REPLY).delete()
        friend.character.system_prompt = ""
        friend.memory = ""
        friend.character.save()
        friend.save()

        inputs = {"messages": [HumanMessage(content="test")]}
        result = add_system_prompt(inputs, friend)

        assert result["messages"][0].content == TOOL_RULES
        assert len(result["messages"]) == 2  # TOOL_RULES + HumanMessage
