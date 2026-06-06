# Chat Agent System Prompt 架构重构 — 设计文档

> **Date:** 2026-06-05 | **Scope:** 工具规则/角色性格/系统框架 三层解耦

**Goal:** 修复 SystemPrompt 表中全局性格模板压制 `Character.system_prompt`、工具规则被稀释的问题。将三种不同性质的指令拆为独立 SystemMessage，实现职责分离。

**背景:** [chat-agent-tool-calling-design](2026-06-05-chat-agent-tool-calling-design.md) 的方案 A 在评估脚本（无角色性格、无历史消息）中达到 87% 隐含检索命中率，但真实聊天中仅约 20%。根因：DB 中 528 字的全局性格模板排在第 1 位，230 字的工具规则排在第 2 位，角色性格 28 字拼在末尾——三种内容挤在一条 SystemMessage 中，工具规则注意力严重衰减。

---

## 1. 当前架构 vs 目标架构

### 1.1 当前

```
add_system_prompt() 输出 1 条 SystemMessage:
┌────────────────────────────────────────┐
│ [DB id=1 order=1] 528字性格模板        │ ← "回复不超过100字""80%短句""禁止列表"
│ [DB id=4 order=2] 230字工具规则         │ ← 被前面性格模板淹没
│ 【角色性格】28字（用户创建角色时填写）  │ ← 权重最低，有等于无
│ 【长期记忆】648字                       │
└────────────────────────────────────────┘
```

三个问题：
1. 工具规则排位靠后，在长上下文中注意力衰减
2. 全局性格模板（528 字）压制 `Character.system_prompt`，用户精心填写的角色性格形同虚设
3. 三种不同性质的内容（行为指令、角色设定、系统约束）挤在一条消息里，LLM 无法区分边界

### 1.2 目标

```
add_system_prompt() 输出 3 条独立 SystemMessage:
┌────────────────────────────────────────┐
│ SystemMessage 1: 工具规则（代码常量）  │ ← 最高优先级，独立消息不被稀释
├────────────────────────────────────────┤
│ SystemMessage 2: 角色性格              │ ← Character.system_prompt + Memory
│   （用户创建角色时填写）               │
├────────────────────────────────────────┤
│ SystemMessage 3: 系统框架（DB 单条）   │ ← 基础约束底线
│   "真诚、不编造、自然口语化"           │
└────────────────────────────────────────┘
```

**核心原则**：每条 SystemMessage 一个职责。工具规则、角色性格、系统框架互不混合。

---

## 2. SystemPrompt 表变更

### 2.1 id=1 精简

当前 528 字包含 9 条格式化规则 + 性格描述 + 情绪概率表。精简为 ~100 字纯系统级基础约束：

```
你是 AI Friends 平台上的 AI 角色。

基本原则：
1. 真诚交流，不确定的事不要编造，可以诚实说"我不太确定"
2. 自然口语化表达，方便语音合成
3. 可以表达情绪、开玩笑、吐槽，保持真实朋友的交流感
4. 拒绝回答违法、有害、涉及隐私安全的内容
```

删除的项目和原因：

| 删除内容 | 原因 |
|----------|------|
| "回复总长度不超过 100 字" | 格式限制 → 移交给 Character.system_prompt |
| "80% 使用小于 4 字的短句" | 风格限制 → 同上 |
| "30% 只讲一句话" | 同上 |
| "禁止列表""禁止符号""禁止空格" | 格式限制 → 同上 |
| "情绪概率分配表（90% 概率...40% 开心...）" | 性格描述 → 同上 |
| "第 9 条：知识性问题认真回答" | 由独立工具规则 SystemMessage 覆盖 |

### 2.2 id=4 删除

工具规则已移到 `chat.py` 代码常量，DB 中不再需要。

### 2.3 关于保留单行的设计理由

重构后 SystemPrompt.REPLY 类型仅保留 1 条记录。保留 `order_number` 字段但不依赖排序（用 `.first()` 而非 `.order_by().all()`）。一条记录 = 一个语义单元。如果未来需要另一条系统级指令，应用新的 `Title` 类型（如 `SAFETY`），而非在 `REPLY` 下用 order_number 区分不同性质的条目。

---

## 3. `chat.py` 代码变更

### 3.1 新增工具规则常量

```python
# 工具使用规则（作为第一条 SystemMessage，优先级最高）
TOOL_RULES = (
    "【知识库查询规则】\n"
    "你有 search_knowledge_base 工具可以查询知识库。\n"
    "1. 必须查询的情况：\n"
    "   - 用户询问专业知识、政策法规、技术原理、数据事实\n"
    "   - 用户提及文档内容、平台功能、操作指南\n"
    "   - 任何你不确定、需要查证的信息\n"
    "2. 可以不查的情况：\n"
    "   - 纯问候（"你好""早上好"）\n"
    "   - 纯情感交流（"我今天很难过"）\n"
    "   - 纯闲聊（"你喜欢吃什么"）\n"
    "3. 不确定时宁可查询也不要遗漏。"
)
```

### 3.2 重构 `add_system_prompt()`

```python
def add_system_prompt(
    inputs: Dict[str, List[BaseMessage]],
    friend: Friend,
) -> dict[str, List[BaseMessage]]:
    """为 Chat Agent 构建 3 层独立的 SystemMessage"""
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

**关键变化**：

| 旧 | 新 |
|----|----|
| `order_by('order_number')` 遍历拼接 | `.first()` 取唯一一条 |
| 1 条 SystemMessage | 1-3 条独立 SystemMessage（按需） |
| Character.system_prompt 拼在 DB 内容之后 | 角色性格独立在第 2 条，在系统框架之前 |
| 无工具规则 | 代码常量 TOOL_RULES 作为首条 |

### 3.3 不修改的部分

- `MessageChatView.post()` — 调用方不变
- `add_recent_messages()` — 历史消息逻辑不变
- `event_stream()` — 流式逻辑不变

---

## 4. 测试

### 4.1 已有测试更新

`backend/web/tests/test_system_prompt.py` — 当前验证 `order_by('order_number')` 遍历拼接。需更新为验证 `.first()` 单条取用 + SystemMessage 顺序。

### 4.2 评估脚本重跑

`backend/web/tests/test_tool_calling.py` — `add_system_prompt()` 重构后重跑 baseline，确认 tool-call 命中率不退化。

### 4.3 新增测试

| 测试 | 验证点 |
|------|--------|
| `test_tool_rules_first` | `messages[0].content` 等于 `TOOL_RULES` |
| `test_personality_before_framework` | 角色性格 SystemMessage 在系统框架之前 |
| `test_framework_single_row` | 使用 `.first()` 而非 `.order_by().all()` |
| `test_no_personality_skips_second` | Character.system_prompt 为空时不注入第 2 条 |
| `test_no_framework_skips_third` | DB 中 REPLY 为空时不注入第 3 条 |

---

## 5. 数据迁移

只改 1 行记录，不涉及 schema 变更，不需要 migration。

```sql
-- 精简 id=1
UPDATE web_systemprompt SET prompt = '...' WHERE id = 1;

-- 删除 id=4
DELETE FROM web_systemprompt WHERE id = 4;
```

通过 Django shell 或 Admin 执行即可。

---

## 6. 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/web/views/friend/message/chat/chat.py` | 修改 | 新增 TOOL_RULES 常量 + 重构 add_system_prompt |
| `backend/web/tests/test_system_prompt.py` | 修改 | 适配新架构 |
| 数据库 `web_systemprompt` | 数据修改 | UPDATE id=1, DELETE id=4 |

---

## 7. 验收标准

| 验证点 | 方法 | 标准 |
|--------|------|------|
| 工具规则为第一条消息 | 脚本评估：查 `inputs['messages'][0]` | 等于 TOOL_RULES |
| 角色性格独立生效 | 修改 Character.system_prompt 后聊天 | 回复风格跟随变化 |
| 工具调用命中率 | 重跑 `test_tool_calling.py` | 不退化于 87% |
| 已有测试 | `pytest web/tests/ -v --ignore=test_tool_calling.py` | 全部通过 |
| 知识问题触发 RAG | 前端手工测试 ≥5 条 | ≥60% |
| 闲聊不触发 RAG | 前端手工测试 ≥3 条 | 0% |
