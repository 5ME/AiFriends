# Chat Agent Tool-Calling 可靠性 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 通过 A→B→C 三层递进方案恢复 Chat Agent `search_knowledge_base` tool-calling 可靠性。

**Architecture:** 先写脚本化评估工具（pytest，真实 API 调用，非 mock），跑 baseline → 方案 A1（SystemPrompt）→ A2（docstring），每步量化对比 tool-call 命中率。不达标则进入方案 B（默认预检索 + 闲聊豁免），仍不行则方案 C（回退 v3.2）。

**Tech Stack:** pytest, Django ORM, model_bakery, LangGraph `app.invoke()`, DashScope API (deepseek-v4-flash)

**Spec:** `docs/superpowers/specs/2026-06-05-chat-agent-tool-calling-design.md`

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/web/tests/test_tool_calling.py` | **新增** | 脚本化评估：15 题 × 3 轮，统计 tool-call 命中率，输出报告 |
| `backend/web/views/friend/message/chat/graph.py` | 修改 | A2: tool docstring 优化；C: model 回退 v3.2 |
| `backend/web/views/friend/message/chat/chat.py` | 可能修改 | B: 闲聊判定 + 预检索逻辑 |

> 方案 A1（SystemPrompt 新增）通过 `manage.py shell` 或 Django Admin 操作数据库，不涉及代码变更。

---

### Task 1: 编写脚本化评估工具

**Files:**
- Create: `backend/web/tests/test_tool_calling.py`

**依赖**: 需要 `DASHSCOPE_API_KEY` 和 `DASHSCOPE_API_BASE` 环境变量（或 .env 中的 `API_KEY` / `API_BASE`）。测试调用真实 DashScope API。

- [ ] **Step 1: 检查环境变量**

```bash
cd backend; python -c "import os; print('API_KEY:', 'SET' if os.getenv('API_KEY') else 'MISSING'); print('API_BASE:', os.getenv('API_BASE', 'MISSING'))"
```

确认 API_KEY 和 API_BASE 已设置。如果未设置，检查 `.env` 文件是否存在且被 python-dotenv 加载。

- [ ] **Step 2: 创建测试文件骨架 + 问题集 + 辅助函数**

```python
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

    LangGraph 消息序列: SystemMessage → HumanMessage → AIMessage(tool_calls) → ToolMessage → AIMessage(最终回复)

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
```

- [ ] **Step 3: 添加 pytest fixture + baseline 测试**

追加到 `test_tool_calling.py`：

```python
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


@pytest.mark.slow
@pytest.mark.django_db
class TestToolCallingBaseline:
    """Baseline: 当前 v4-flash + 现有 prompt 的 tool-call 命中率"""

    def test_explicit_search(self, chat_app, friend, system_prompt_reply):
        """明确需要检索 — 期望 ≥ 90%"""
        hits, total = _run_eval(chat_app, friend, TEST_QUESTIONS["明确需要检索"])
        rate = hits / total if total else 0
        print(f"\n明确需要检索: {hits}/{total} ({rate:.0%})")
        assert rate >= 0.90, f"明确检索命中率 {rate:.0%} < 90%"

    def test_implicit_search(self, chat_app, friend, system_prompt_reply):
        """隐含需要检索 — 记录 baseline 供后续对比"""
        hits, total = _run_eval(chat_app, friend, TEST_QUESTIONS["隐含需要检索"])
        rate = hits / total if total else 0
        print(f"\n隐含需要检索: {hits}/{total} ({rate:.0%})")

    def test_chat_no_search(self, chat_app, friend, system_prompt_reply):
        """纯闲聊 — 期望 ≤ 5%（基本不应触发）"""
        hits, total = _run_eval(chat_app, friend, TEST_QUESTIONS["纯闲聊（不应检索）"])
        rate = hits / total if total else 0
        print(f"\n纯闲聊误触: {hits}/{total} ({rate:.0%})")
        assert rate <= 0.05, f"闲聊误触率 {rate:.0%} > 5%"
```

- [ ] **Step 4: 注册 slow marker**

检查 `pytest.ini` 或 `pyproject.toml` 是否需要注册 `slow` marker。

```bash
cd backend; python -c "import pytest; print(pytest.__version__)"
```

如果 `pyproject.toml` 中没有 `[tool.pytest.ini_options]` 的 `markers` 段，添加：

```toml
[tool.pytest.ini_options]
markers = [
    "slow: 耗时测试（真实 API 调用），不随常规测试运行",
]
```

- [ ] **Step 5: 运行 baseline 测试，验证工具链可用**

```bash
cd backend; python -m pytest web/tests/test_tool_calling.py::TestToolCallingBaseline -v -s -m slow
```

预期：测试能跑通（assert 可能 FAIL，但框架本身不报错）。记录 baseline 结果。

- [ ] **Step 6: Commit**

```bash
git add backend/web/tests/test_tool_calling.py pyproject.toml
git commit -m "test: Chat Agent tool-calling 脚本化评估（baseline）"
```

---

### Task 2: 方案 A1 — 新增 SystemPrompt 工具使用规则

**无代码变更**，通过 Django shell 操作数据库。

- [ ] **Step 1: 确认当前 REPLY 类型的 SystemPrompt 条目**

```bash
cd backend; python manage.py shell -c "
from web.models.friend import SystemPrompt
for sp in SystemPrompt.objects.filter(title='reply').order_by('order_number'):
    print(f'[{sp.order_number}] {sp.prompt[:80]}...')
"
```

记录当前条目，确定新 entry 的 `order_number`（取现有最大值 + 1）。

- [ ] **Step 2: 创建 Django management command 或直接插入**

由于 SystemPrompt 是数据库记录，创建一个一次性 migration-style 的 management command 更可维护。但如果只是实验，直接用 shell：

```bash
cd backend; python manage.py shell -c "
from web.models.friend import SystemPrompt

# 取最大 order_number + 1
max_order = SystemPrompt.objects.filter(title='reply').order_by('-order_number').first()
next_order = (max_order.order_number + 1) if max_order else 0

sp, created = SystemPrompt.objects.get_or_create(
    title='reply',
    order_number=next_order,
    defaults={
        'prompt': '''【知识库查询规则】
1. 当用户问题涉及以下任一情况时，必须先调用 search_knowledge_base 查询知识库：
   - 专业知识、政策法规、技术原理、数据事实
   - 文档内容、平台说明、操作指南
   - 任何你不确定、需要查证的信息
2. 仅在以下情况可以不查知识库：
   - 纯问候（\"你好\"\"早上好\"）
   - 纯情感交流（\"我今天很难过\"）
   - 纯闲聊（\"你喜欢吃什么\"）
3. 不确定是否需要查询时，宁可查询也不要遗漏。'''
    }
)
print(f'{\"Created\" if created else \"Already exists\"}: SystemPrompt(reply, order={next_order})')
"
```

- [ ] **Step 3: 运行 A1 评估**

```bash
cd backend; python -m pytest web/tests/test_tool_calling.py -v -s -m slow
```

记录 A1 结果，与 baseline 对比。

- [ ] **Step 4: 如果 A1 三类全部达标 → 进入 Task 5（手工验证）；否则继续 Task 3**

---

### Task 3: 方案 A2 — 优化 search_knowledge_base docstring

**Files:**
- Modify: `backend/web/views/friend/message/chat/graph.py:32-38`

- [ ] **Step 1: 更新 docstring**

将 `graph.py` 中 `search_knowledge_base` 函数的 docstring 替换为：

```python
@tool
def search_knowledge_base(query: str, state: Annotated[dict, InjectedState]) -> str:
    """
    在知识库中检索与用户问题相关的文档内容。

    知识库包含：
    - 平台官方文档（使用说明、功能指南）
    - 用户上传的个人文档（工作资料、学习笔记等）

    必须调用此工具的情况：
    - 用户询问任何关于政策、法规、制度、标准的问题
    - 用户询问专业知识、技术原理、行业规范
    - 用户提到"文档""资料""查一下""找一下""有没有相关"
    - 用户问题需要事实依据或数据支撑
    - 你不确定答案、需要查证时

    不需要调用的情况：
    - 纯问候、告别（"你好""再见"）
    - 纯情感倾诉（"我今天心情不好"）
    - 纯角色扮演闲聊（"你喜欢什么颜色"）
    """
    from web.models.document import DocumentChunk

    user_id = state.get("user_id")
    logger.info('RAG 知识库检索开始, query=%s, user_id=%s', query[:100], user_id)
    embeddings = CustomEmbeddings(user_id=user_id)
    # ... 后续代码不变
```

- [ ] **Step 2: 运行 A1+A2 评估**

```bash
cd backend; python -m pytest web/tests/test_tool_calling.py -v -s -m slow
```

记录 A1+A2 结果，与 A1 对比。

- [ ] **Step 3: 如果三类全部达标 → 进入 Task 5（手工验证）；否则进入 Task 4**

---

### Task 4: 决策点 — 方案 A 未达标，进入方案 B

仅当 Task 3 的三类指标未全部达标时执行此 Task。

- [ ] **Step 1: 确认 A1+A2 评估结果**

回看 Task 3 Step 2 的输出，确认哪类未达标。

- [ ] **Step 2: 确认进入方案 B**

方案 A 的优化手段已穷尽（prompt + docstring），未达到预期效果 → 进入方案 B（默认预检索 + 闲聊豁免）。

- [ ] **Step 3: Commit（保存 A 阶段的改动）**

```bash
git add backend/web/views/friend/message/chat/graph.py docs/superpowers/specs/2026-06-05-chat-agent-tool-calling-design.md
git commit -m "feat: Chat Agent tool docstring 优化 + SystemPrompt 工具规则（方案 A）"
```

---

### Task 5: 方案 B — 默认预检索 + 闲聊豁免

**Files:**
- Modify: `backend/web/views/friend/message/chat/chat.py`

**前置**：方案 A 未达标（Task 4 已确认）。

- [ ] **Step 1: 在 chat.py 顶部添加闲聊判定函数**

在 `chat.py` 的 import 区域之后、`SSERenderer` 类之前新增：

```python
import re

# 方案 B：闲聊豁免关键词 + 长度联合判定（默认触发预检索）
CHAT_KEYWORDS = re.compile(
    r'^(你好|再见|谢谢|早安|晚安|早上好|晚上好|拜拜|哈哈|嘿嘿|嗯嗯|哦哦)[!！。.]?$'
)

def _is_chat(user_message: str) -> bool:
    """判定是否为纯闲聊（不触发预检索，走正常 Agentic RAG 流程）

    双重条件同时满足才算闲聊：
    1. 长度 ≤ 6 字 — 防止"你好，社保是什么"被误判
    2. 匹配闲聊关键词 — 防止短的非闲聊消息被豁免
    """
    stripped = user_message.strip()
    if len(stripped) > 6:
        return False
    return bool(CHAT_KEYWORDS.search(stripped))
```

- [ ] **Step 2: 在 post() 方法中插入预检索逻辑**

在 `chat.py` 的 `post()` 方法中，`add_recent_messages()` 之后、`StreamingHttpResponse` 之前插入：

```python
        # 方案 B：默认预检索 + 闲聊豁免
        if not _is_chat(message):
            try:
                from web.models.document import DocumentChunk
                from web.documents.utils.custom_embeddings import CustomEmbeddings
                embeddings = CustomEmbeddings(user_id=friend.user_profile_id)
                emb = embeddings.embed_query(message)
                table = DocumentChunk._meta.db_table
                chunks = DocumentChunk.objects.raw(
                    f"SELECT id, content, chunk_index, document_id "
                    f"FROM {table} "
                    f"WHERE owner_id IS NULL OR owner_id = %s "
                    f"ORDER BY embedding <=> %s::vector LIMIT 3",
                    [friend.user_profile_id, emb]
                )
                context = '\n\n'.join(
                    [f'[参考资料 {i+1}]\n{c.content}' for i, c in enumerate(chunks)]
                )
                if context:
                    inputs['messages'] = [SystemMessage(
                        f'【来自知识库的参考资料】\n\n{context}\n\n请根据以上参考资料回答用户问题。'
                    )] + inputs['messages']
            except Exception:
                logger.exception('预检索失败, friend_id=%s', friend.id)
```

- [ ] **Step 3: 确认 import 完整性**

检查 `chat.py` 顶部是否已有以下 import（没有则添加）：

```python
import re                                    # Step 1 新增
from web.documents.utils.custom_embeddings import CustomEmbeddings  # Step 2 需要
from web.models.document import DocumentChunk  # Step 2 需要
```

- [ ] **Step 4: 手工验证**

启动 dev server，前端聊天测试：
- "社保制度是什么？" → 应看到预检索结果被使用
- "你好" → 不应触发预检索
- "你好我们来玩诗词接龙吧" → >6 字，触发预检索（多一次检索，无害）
- "我不开心" → 短消息但不匹配闲聊关键词，触发预检索

确认回复质量不受影响（不相关的检索结果不妨碍闲聊回复）。

- [ ] **Step 5: Commit**

```bash
git add backend/web/views/friend/message/chat/chat.py
git commit -m "feat: Chat Agent 方案 B — 默认预检索 + 闲聊豁免"
```

---

### Task 6（仅当 B 也不理想）: 方案 C — Chat Agent 回退 deepseek-v3.2

**Files:**
- Modify: `backend/web/views/friend/message/chat/graph.py:61`

- [ ] **Step 1: 回退模型名**

将 `graph.py` 第 61 行的 model 名改回：

```python
# line 61
- model="deepseek-v4-flash",
+ model="deepseek-v3.2",
```

- [ ] **Step 2: 如需，回退方案 B 的预检索逻辑**

如果方案 B 的预检索对 v3.2 造成干扰（v3.2 本身 tool-calling 可靠，预检索反而多余），将 Task 5 的改动 revert：

```bash
git revert <方案B的commit>  # 或手动删除预检索逻辑
```

- [ ] **Step 3: 手工验证**

确认 RAG 恢复到 v3.2 时期的可靠性。

- [ ] **Step 4: Commit**

```bash
git add backend/web/views/friend/message/chat/graph.py
git commit -m "fix: Chat Agent 回退 deepseek-v3.2（方案 C 兜底）"
```

---

### Task 7: 清理 — 提交设计文档 + 更新 memory

- [ ] **Step 1: 与代码一起提交设计文档**

```bash
git add docs/superpowers/specs/2026-06-05-chat-agent-tool-calling-design.md docs/superpowers/plans/2026-06-05-chat-agent-tool-calling.md
git commit -m "docs: Chat Agent tool-calling 设计文档 + 实施计划"
```

- [ ] **Step 2: 更新 memory**

更新 `memory/chat-agent-tool-calling.md`，记录最终采用的方案和结果。
