# System Prompt 架构重构 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Chat Agent 的 SystemPrompt 从"1 条拼合 SystemMessage"重构为"3 层独立 SystemMessage"（工具规则 → 角色性格 → 系统框架），解决工具规则被稀释和 Character.system_prompt 形同虚设的问题。

**Architecture:** `add_system_prompt()` 输出从 1 条合并的 SystemMessage 改为 1-3 条独立 SystemMessage。工具规则作为 chat.py 代码常量（非 DB），角色性格 + Memory 独立为第 2 条，DB 中精简后的系统框架为第 3 条。

**Tech Stack:** Django ORM, pytest, model_bakery

**Spec:** `docs/superpowers/specs/2026-06-05-system-prompt-architecture-design.md`

**Branch:** `feature/gqyin/chat-agent-tool-calling`（在当前分支上继续）

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/web/views/friend/message/chat/chat.py` | 修改 | 新增 TOOL_RULES 常量 + 重构 add_system_prompt |
| `backend/web/tests/test_system_prompt.py` | 修改 | 适配新架构的 SystemMessage 分离 |
| 数据库 `web_systemprompt` | 数据修改 | UPDATE id=1, DELETE id=4 |

---

### Task 1: 更新已有测试 + 新增测试（TDD — 预期失败）

**Files:**
- Modify: `backend/web/tests/test_system_prompt.py`

**前置**：先确认当前 DB 中有 REPLY 类型的 SystemPrompt（用于测试隔离）。

- [ ] **Step 1: 读取当前 test_system_prompt.py**

确认只有 `TestSystemPromptLoading` 类，2 个测试方法。第 2 个（Memory）不受影响，保持不变。

- [ ] **Step 2: 替换 test_add_system_prompt_loads_reply_prompts**

将原有的验证逻辑替换为适配 3 层架构的版本。**这个测试预期会 FAIL（因为 chat.py 尚未修改）**：

```python
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
```

- [ ] **Step 3: 新增 test_personality_before_framework**

验证角色性格在系统框架之前：

```python
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

    # 找到包含"性格"和"框架"的 SystemMessage 的索引
    personality_idx = next(i for i, m in enumerate(messages) if "性格" in m.content)
    framework_idx = next(i for i, m in enumerate(messages) if "框架" in m.content)
    assert personality_idx < framework_idx, \
        f"性格({personality_idx})应在框架({framework_idx})之前"
```

- [ ] **Step 4: 新增测试：边界情况**

```python
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

    # 预期：TOOL_RULES + 框架 + HumanMessage = 3 条（无角色性格层）
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
```

- [ ] **Step 5: 运行测试，确认失败**

```bash
cd backend; python -m pytest web/tests/test_system_prompt.py -v
```

预期：`test_add_system_prompt_loads_reply_prompts` 和新增测试 FAIL（chat.py 尚未修改）

- [ ] **Step 6: Commit**

```bash
git add backend/web/tests/test_system_prompt.py
git commit -m "test: SystemPrompt 架构重构 — 更新测试适配 3 层分离（预期失败）"
```

---

### Task 2: 重构 add_system_prompt() + 新增 TOOL_RULES 常量

**Files:**
- Modify: `backend/web/views/friend/message/chat/chat.py`

- [ ] **Step 1: 在 chat.py 顶部 import 区域后、SSERenderer 类之前新增 TOOL_RULES 常量**

```python
# 工具使用规则 — 注入为 Chat Agent 第一条 SystemMessage，优先级最高
TOOL_RULES = (
    "【知识库查询规则】\n"
    "你有 search_knowledge_base 工具可以查询知识库。\n"
    "1. 必须查询的情况：\n"
    "   - 用户询问专业知识、政策法规、技术原理、数据事实\n"
    "   - 用户提及文档内容、平台功能、操作指南\n"
    "   - 任何你不确定、需要查证的信息\n"
    "2. 可以不查的情况：\n"
    "   - 纯问候（\"你好\"\"早上好\"）\n"
    "   - 纯情感交流（\"我今天很难过\"）\n"
    "   - 纯闲聊（\"你喜欢吃什么\"）\n"
    "3. 不确定时宁可查询也不要遗漏。"
)
```

- [ ] **Step 2: 替换 add_system_prompt() 函数**

找到原有的 `add_system_prompt` 函数（约在 line 39-61），完整替换为：

```python
def add_system_prompt(
        inputs: Dict[str, List[BaseMessage]],
        friend: Friend,
) -> dict[str, List[BaseMessage]]:
    """
    为 Chat Agent 构建 3 层独立 SystemMessage：
    1. 工具使用规则（代码常量，最高优先级）
    2. 角色性格 + 长期记忆（Character.system_prompt + Friend.memory）
    3. 系统级框架约束（DB 单条 SystemPrompt.REPLY）
    """
    msgs = inputs['messages']
    system_msgs = []

    # 第 1 条：工具使用规则（代码常量，最高优先级）
    system_msgs.append(SystemMessage(TOOL_RULES))

    # 第 2 条：角色性格 + 长期记忆
    personality = friend.character.system_prompt.strip()
    memory = (friend.memory or "").strip()
    personality_parts = []
    if personality:
        personality_parts.append(f"【角色性格】\n{personality}")
    if memory:
        personality_parts.append(f"【与用户的长期记忆】\n{memory}")
    if personality_parts:
        system_msgs.append(SystemMessage("\n\n".join(personality_parts)))

    # 第 3 条：系统级框架（DB 单条）
    framework = SystemPrompt.objects.filter(
        title=SystemPrompt.Title.REPLY
    ).first()
    if framework and framework.prompt.strip():
        system_msgs.append(SystemMessage(framework.prompt))

    return {**inputs, 'messages': system_msgs + msgs}
```

- [ ] **Step 3: 确认旧代码中不再有 `order_by('order_number')` 引用**

```bash
cd backend; grep -n "order_number" web/views/friend/message/chat/chat.py
```

预期：无输出（或仅在注释中）

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend; python -m pytest web/tests/test_system_prompt.py -v
```

预期：全部 6 个测试 PASS（2 个旧 Memory 测试 + 4 个新测试）。注意 `test_add_system_prompt_loads_reply_prompts` 如果依赖 DB 中已有的 prompt 内容，需要检查 DB 状态。

但此时还有 `test_create_system_message_loads_memory_prompts` 测试，它测试的是 Memory Agent（不受影响），应该继续 PASS。

- [ ] **Step 5: 运行已有测试确保无回归**

```bash
cd backend; python -m pytest web/tests/ -v --ignore=web/tests/test_tool_calling.py
```

预期：111 个测试全部 PASS（或与重构前相同的通过数）。

- [ ] **Step 6: Commit**

```bash
git add backend/web/views/friend/message/chat/chat.py
git commit -m "refactor: Chat Agent SystemPrompt 3 层分离 — 工具规则/角色性格/系统框架"
```

---

### Task 3: 数据库数据迁移

**无代码变更**，通过 Django shell 操作。

- [ ] **Step 1: 确认 id=1 和 id=4 内容匹配预期**

```bash
cd backend; python manage.py shell -c "
from web.models.friend import SystemPrompt
for sp in SystemPrompt.objects.filter(title='reply').order_by('id'):
    print(f'id={sp.id} order={sp.order_number}: {sp.prompt[:60]}...')
"
```

- [ ] **Step 2: 精简 id=1**

```bash
cd backend; python manage.py shell -c "
from web.models.friend import SystemPrompt
sp = SystemPrompt.objects.get(id=1)
sp.prompt = '''你是 AI Friends 平台上的 AI 角色。

基本原则：
1. 真诚交流，不确定的事不要编造，可以诚实说\"我不太确定\"
2. 自然口语化表达，方便语音合成
3. 可以表达情绪、开玩笑、吐槽，保持真实朋友的交流感
4. 拒绝回答违法、有害、涉及隐私安全的内容'''
sp.save()
print(f'Updated id=1, new length={len(sp.prompt)}')
"
```

- [ ] **Step 3: 删除 id=4**

```bash
cd backend; python manage.py shell -c "
from web.models.friend import SystemPrompt
deleted, _ = SystemPrompt.objects.filter(id=4).delete()
print(f'Deleted {deleted} row(s)')
"
```

- [ ] **Step 4: 验证已删除且仅剩一条 reply**

```bash
cd backend; python manage.py shell -c "
from web.models.friend import SystemPrompt
reply_count = SystemPrompt.objects.filter(title='reply').count()
print(f'REPLY rows: {reply_count}')  # 预期: 1
"
```

- [ ] **Step 5: Commit**（可选，DB 快照无文件变更）

如果 DB 数据通过 fixture 或 seed 管理，此步骤可跳过 commit。后续 Task 4 统一提交。

---

### Task 4: 评估验证

- [ ] **Step 1: 重跑 tool-calling 评估脚本**

```bash
cd backend; python -m pytest web/tests/test_tool_calling.py -v -s -m slow
```

预期：三类指标不退化于之前的 100%/87%/0%。如果提升（因为工具规则现在作为独立首条消息），在报告中标注是架构重构的贡献。

- [ ] **Step 2: 对比前后结果**

| 阶段 | 明确检索 | 隐含检索 | 闲聊误触 | 备注 |
|------|---------|---------|---------|------|
| 旧 A1+A2（1 条合并） | 100% | 87% | 0% | DB 工具规则在性格之后 |
| 新架构（3 层分离） | ? | ? | ? | 工具规则独立首条 |

---

### Task 5: 清理提交

- [ ] **Step 1: 提交设计文档**

```bash
git add docs/superpowers/specs/2026-06-05-system-prompt-architecture-design.md docs/superpowers/plans/2026-06-05-system-prompt-architecture.md
git commit -m "docs: SystemPrompt 架构重构设计文档 + 实施计划"
```

- [ ] **Step 2: 检查是否有遗留文件**

```bash
git status
```
