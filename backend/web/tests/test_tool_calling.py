"""
Chat Agent Tool-Calling 脚本化评估

不 mock API，调用真实 DashScope API 评估 LLM tool-calling 行为。
标记为 slow（不随常规测试运行），需设置 API_KEY 环境变量。

使用方式:
  python -m pytest web/tests/test_tool_calling.py -v -s -m slow
"""

import pytest

from langchain_core.messages import HumanMessage

from web.views.friend.message.chat.graph import ChatGraph
from web.views.friend.message.chat.chat import add_system_prompt
from web.models.friend import SystemPrompt


# ── 测试问题集 ──────────────────────────────────────────

TEST_QUESTIONS = {
    "明确需要检索": [
        "帮我查一下知识库，社保制度是什么？",
        "我上传的文档里有没有关于就业政策的说明？",
        "查询知识库，告诉我平台支持哪些功能？",
        "根据文档内容，AI 在社保领域有哪些应用？",
        "我之前上传的资料里，关于退休年龄是怎么规定的？",
    ],
    "隐含需要检索": [
        "社保制度和就业贡献之间有什么关系？",
        "为什么说社会保障是社会的安全网？",
        "这个平台怎么用？",
        "AI 能帮我做什么？",
        "怎样提高工作效率？",
    ],
    "纯闲聊（不应检索）": [
        "你好，今天天气不错",
        "我今天心情不太好",
        "你喜欢吃什么？",
        "讲个笑话吧",
        "谢谢你",
    ],
}


def _has_search_tool_call(result: dict) -> bool:
    """检查 LangGraph invoke 结果中是否包含 search_knowledge_base 调用。

    LangGraph 消息序列: SystemMessage -> HumanMessage -> AIMessage(tool_calls) -> ToolMessage -> AIMessage(最终回复)

    必须遍历全部消息，不能只看 result['messages'][-1]（最终回复不带 tool_calls）。
    """
    for msg in result.get('messages', []):
        tool_calls = getattr(msg, 'tool_calls', None) or []
        for tc in tool_calls:
            if tc.get('name') == 'search_knowledge_base':
                return True
    return False


def _run_eval(app, test_friend, questions: list[str], rounds: int = 3) -> tuple[int, int]:
    """对问题列表跑 N 轮，返回 (命中次数, 总次数)"""
    hits = 0
    total = 0
    for question in questions:
        for _ in range(rounds):
            inputs = {
                'messages': [HumanMessage(question)],
                'user_id': test_friend.user_profile_id,
            }
            inputs = add_system_prompt(inputs, test_friend)
            result = app.invoke(inputs)
            if _has_search_tool_call(result):
                hits += 1
            total += 1
    return hits, total


# ── Fixtures ─────────────────────────────────────────────

@pytest.fixture
def chat_app():
    """创建 ChatGraph agent（使用当前 graph.py 配置的模型）"""
    return ChatGraph.create_app()


@pytest.fixture
def system_prompt_reply(db):
    """确保至少有一条 reply 类型的 SystemPrompt（add_system_prompt 依赖它）"""
    prompts = SystemPrompt.objects.filter(title=SystemPrompt.Title.REPLY)
    if not prompts.exists():
        SystemPrompt.objects.create(
            title=SystemPrompt.Title.REPLY,
            order_number=0,
            prompt="你是一个友好的 AI 助手，根据对话历史回答用户的问题。",
        )
    return list(prompts)


# ── Baseline 测试 ────────────────────────────────────────

@pytest.mark.slow
@pytest.mark.django_db
class TestToolCallingBaseline:
    """Baseline: 当前 v4-flash + 现有 prompt 的 tool-call 命中率"""

    def test_explicit_search(self, chat_app, friend, system_prompt_reply):
        """明确需要检索 -- 期望 >= 90%"""
        hits, total = _run_eval(chat_app, friend, TEST_QUESTIONS["明确需要检索"])
        rate = hits / total if total else 0
        print(f"\n明确需要检索: {hits}/{total} ({rate:.0%})")
        assert rate >= 0.90, f"明确检索命中率 {rate:.0%} < 90%"

    def test_implicit_search(self, chat_app, friend, system_prompt_reply):
        """隐含需要检索 -- 记录 baseline 供后续对比"""
        hits, total = _run_eval(chat_app, friend, TEST_QUESTIONS["隐含需要检索"])
        rate = hits / total if total else 0
        print(f"\n隐含需要检索: {hits}/{total} ({rate:.0%})")

    def test_chat_no_search(self, chat_app, friend, system_prompt_reply):
        """纯闲聊 -- 期望 <= 5%（基本不应触发）"""
        hits, total = _run_eval(chat_app, friend, TEST_QUESTIONS["纯闲聊（不应检索）"])
        rate = hits / total if total else 0
        print(f"\n纯闲聊误触: {hits}/{total} ({rate:.0%})")
        assert rate <= 0.05, f"闲聊误触率 {rate:.0%} > 5%"
