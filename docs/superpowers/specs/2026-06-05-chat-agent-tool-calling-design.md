# Chat Agent Tool-Calling 可靠性 — 设计文档

> **Date:** 2026-06-05 | **Scope:** 修复 v4-flash tool‑calling，提升 Agentic RAG 可靠性

**Goal:** `deepseek-v3.2` → `deepseek-v4-flash` 后 Chat Agent 不再自主调用 `search_knowledge_base`。在保持 Agentic RAG 架构的前提下，通过 A→B→C 三层递进方案恢复 tool-calling 可靠性。

---

## 1. 问题定义

### 1.1 现象

Chat Agent 从 `deepseek-v3.2` 切换到 `deepseek-v4-flash` 后，`search_knowledge_base` tool 不再被自主调用。即使 prompt 中明确要求"查询知识库后再回答"，LLM 也直接生成回复，不触发 tool call。

### 1.2 根因假设（待验证）

| 假设 | 可能性 | 说明 |
|------|--------|------|
| v4-flash tool-calling 指令遵循能力弱于 v3.2 | 高 | Flash 模型为速度/成本优化，复杂指令遵循可能降级 |
| System prompt 缺少 tool 使用指引 | 高 | 当前 prompt 只描述角色性格，不涉及工具使用规则 |
| tool docstring 触发描述不够丰富 | 中 | v3.2 能从简短描述推断，v4-flash 可能需要更明确的场景列表 |
| `tool_choice` 参数未显式设置 | 低 | LangChain 默认 `"auto"`，但不同模型对 `auto` 的敏感度不同 |

### 1.3 约束

- 保持 Agentic RAG 架构，不降级为朴素 RAG（Always-on 检索）
- 工具调用仍由 LLM 自主决策（不强制 `tool_choice="required"`，闲聊不应查知识库）
- Memory Agent 不受影响（它不需要 tool，v4-flash 继续使用）

---

## 2. 解决方案（A → B → C 三层递进）

### 2.1 方案 A：Prompt & Tool Description 优化（代码之外 + 代码之内）

**A1 — System prompt 新增工具使用规则**

在 `SystemPrompt` 表中新增一条 `reply` 类型的 prompt（`order_number` 适当），内容：

```
【知识库查询规则】
1. 当用户问题涉及以下任一情况时，必须先调用 search_knowledge_base 查询知识库：
   - 专业知识、政策法规、技术原理、数据事实
   - 文档内容、平台说明、操作指南
   - 任何你不确定、需要查证的信息
2. 仅在以下情况可以不查知识库：
   - 纯问候（"你好""早上好"）
   - 纯情感交流（"我今天很难过"）
   - 纯闲聊（"你喜欢吃什么"）
3. 不确定是否需要查询时，宁可查询也不要遗漏。
```

**A2 — tool docstring 优化**

`graph.py` 中 `search_knowledge_base` 的 docstring 从简短描述优化为包含明确触发场景的丰富描述：

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
```

### 2.2 方案 B：检索意图关键词预判层

如果方案 A 调优后 v4-flash 仍不稳定，在 LangGraph agent 之前加一个轻量预判步骤。

**流程变化：**

```
当前：用户消息 → Agent (LLM+tools) → 回复
方案B：用户消息 → 闲聊判定？
          ├─ YES（闲聊）→ 正常 Agentic RAG（LLM 仍可自主调 tool 兜底）
          └─ NO（默认）→ 同步检索 → 结果注入 system prompt → Agent 直接用结果回复
```

**预判实现** — 关键词匹配（零延迟、零成本）：

```python
# 策略反转：默认触发预检索，关键词 + 长度联合判定豁免明确闲聊
CHAT_KEYWORDS = re.compile(
    r'^(你好|再见|谢谢|早安|晚安|早上好|晚上好|拜拜|哈哈|嘿嘿|嗯嗯|哦哦)[!！。.]?$'
)

def _is_chat(user_message: str) -> bool:
    """判定是否为纯闲聊（不触发预检索，走正常 Agentic RAG 流程）
    
    双重条件同时满足才算闲聊：
    1. 长度 ≤ 6 字 — 防止"你好，社保是什么"被误判为闲聊
    2. 匹配闲聊关键词 — 防止短的非闲聊消息被豁免
    """
    stripped = user_message.strip()
    if len(stripped) > 6:
        return False
    return bool(CHAT_KEYWORDS.search(stripped))
```

**策略反转说明**：原方案用关键词做"守门员"（命中才检索），但隐含检索类问题（"社保和就业什么关系""AI 能帮我做什么""怎样提高效率"）的关键词覆盖率仅 40%，漏掉的问题既不会预检索、LLM 也不自主调 tool，完全失去 RAG。

反转为：**默认触发预检索，闲聊关键词 + 长度上限联合判定豁免**。

**设计取舍 — 宁多查不漏查**：长度过 6 字就默认检索，即使偶尔多查也无害：

| 场景 | 长度 | `_is_chat()` | 预检索? | 影响 |
|------|------|-------------|---------|------|
| "你好" | 2 | True | ❌ | 正常闲聊，合理跳过 |
| "谢谢你" | 3 | True | ❌ | 同上 |
| "你好，社保是什么" | 9 | **False** (>6字) | ✅ | 正确触发 RAG |
| "你好我们来玩诗词接龙吧" | 11 | **False** (>6字) | ✅ | 多余一次检索，但无害 |
| "我不开心" | 4 | ❌ 不匹配 | ✅ | 短消息但非闲聊，触发 |
| "今天天气真好适合出去玩" | 10 | **False** (>6字) | ✅ | 多余一次检索，但无害 |

核心原则：**闲聊多查的代价（一次 embedding ≈ 几分钱）远低于知识问题漏查的代价（完全丢失 RAG）**。不相关的检索结果注入 system prompt 后，LLM 会自行判断忽略，不影响回复质量。

**预检索逻辑**（`post()` 方法中，`app.invoke()` 之前）：

```python
if not _is_chat(message):
    # 同步检索（不含闲聊的消息）
    embeddings = CustomEmbeddings(user_id=friend.user_profile_id)
    emb = embeddings.embed_query(message)
    chunks = DocumentChunk.objects.raw(
        f"SELECT id, content, chunk_index, document_id "
        f"FROM {DocumentChunk._meta.db_table} "
        f"WHERE owner_id IS NULL OR owner_id = %s "
        f"ORDER BY embedding <=> %s::vector LIMIT 3",
        [friend.user_profile_id, emb]
    )
    context = '\n\n'.join([c.content for c in chunks])
    inputs = add_pre_search_context(inputs, context)
```

**注意**：方案 B 的检索在同步上下文中（`post()` 方法），用 `embed_query`（单条 embedding），不会有 `SynchronousOnlyOperation` 问题。

### 2.3 方案 C：Chat Agent 回退 deepseek-v3.2

如果方案 B 也不理想，回退到已验证可靠的配置：

| Agent | 模型 | 原因 |
|-------|------|------|
| Chat Agent | `deepseek-v3.2` | tool-calling 已验证可靠 |
| Memory Agent | `deepseek-v4-flash` | 无 tool，仅摘要，保持低成本 |

改动仅一行（`graph.py` 的 model 名），无需其他代码变更。

### 2.4 方案选择流程

```
方案 A: Prompt + Docstring 优化
  │
  ├─ 脚本评估：三类指标全部达标？
  │   ├─ YES → 手工验证 → 通过 → ✅ 结束
  │   └─ NO ↓
  │
方案 B: 检索意图关键词预判层
  │
  ├─ 手工验证 → 通过 → ✅ 结束
  └─ 不理想 ↓

方案 C: Chat Agent 回退 v3.2 → ✅ 兜底
```

---

## 3. 脚本化评估设计

### 3.1 测试问题集

三类问题，每类 5 条：

```python
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
```

### 3.2 评估流程

```
对每个问题（共 15 条）：
  ├── 跑 3 轮 app.invoke()（非流式）
  ├── 检查 AIMessage.tool_calls 中是否有 search_knowledge_base
  └── 记录: 该问题 tool-call 命中次数 / 3

输出：
  明确需要检索：X/5 → 命中率 A%
  隐含需要检索：X/5 → 命中率 B%
  纯闲聊（不应检索）：X/5 → 误触率 C%
  综合：X/10 → 命中率 D%
```

### 3.3 判定阈值

| 类别 | 阈值 | 理由 |
|------|------|------|
| 明确需要检索 | **≥ 90%** | 明确指令必须高可靠，仅容 API 偶发异常 |
| 隐含需要检索 | **≥ baseline×2 且 ≥ 30%** | 相对 baseline 显著提升 + 绝对底线，避免拍脑袋 |
| 纯闲聊 | **≤ 5%** | 偶发误触可容忍，但不应频繁 |

三类全部达标才算方案 A 通过。任何一类不达标 → 进入方案 B。

### 3.4 技术实现

```python
# 关键代码路径（非流式调用 LangGraph agent）
from web.views.friend.message.chat.graph import ChatGraph
from web.views.friend.message.chat.chat import add_system_prompt

app = ChatGraph.create_app()
for question in questions:
    for round_num in range(3):
        inputs = {
            'messages': [HumanMessage(question)],
            'user_id': test_user.id,
        }
        inputs = add_system_prompt(inputs, test_friend)
        result = app.invoke(inputs)  # 非流式，直接拿最终 state
        # 注意：LangGraph 的 agent → tools → agent 循环会产生多条消息
        # result['messages'][-1] 是最终回复（无 tool_calls），必须遍历全部消息
        has_tool_call = any(
            tc.get('name') == 'search_knowledge_base'
            for msg in result['messages']
            for tc in (getattr(msg, 'tool_calls', None) or [])
        )
```

### 3.5 测试基础设施

需要一个 test fixture 提供真实的数据库对象（复用 pytest 的 `django_db` + `model_bakery`）：

| 对象 | 说明 |
|------|------|
| `test_user` | 通过 `baker.make(UserProfile)` 创建 |
| `test_character` | 带 `system_prompt` 字段的角色 |
| `test_friend` | 关联 user + character |
| `SystemPrompt(reply)` | 现有的 + 方案 A1 新增的 |

### 3.6 输出报告格式

```
============================================================
Chat Agent Tool-Calling 评估报告
模型: deepseek-v4-flash | 方案: baseline / A1 / A2 / A+B
============================================================
类别              命中率       期望       判定
------------------------------------------------------------
明确需要检索       4/5 (80%)    ≥90%      ❌
隐含需要检索       3/5 (60%)    ≥30%      ✅
纯闲聊             0/5 (0%)     ≤5%       ✅
------------------------------------------------------------
综合              7/10 (70%)   —          —
============================================================
每轮耗时: ~2-3s | 总耗时: ~2min
============================================================
```

---

## 4. 实施细节

### 4.1 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/web/tests/test_tool_calling.py` | **新增** | 脚本化评估（pytest） |
| `backend/web/views/friend/message/chat/graph.py` | 修改 | A2: tool docstring 优化 |
| `backend/web/views/friend/message/chat/chat.py` | 可能修改 | 方案 B: 意图预判逻辑 |

> 方案 A1（system prompt）通过 Django Admin 或 `manage.py shell` 直接操作 `SystemPrompt` 表，不涉及代码变更。方案 C 仅改 graph.py 一行。

### 4.2 方案 A 实验步骤

```
Step 1: 跑 baseline 评估（当前 v4-flash + 现有 prompt）
        → 记录三类命中率作为基准

Step 2: A1 — 新增 SystemPrompt 工具规则 → 跑评估
        → 对比 baseline，记录提升幅度

Step 3: A2 — 优化 search_knowledge_base docstring → 跑评估
        → 如果 A1 已达标，A2 仍做（锦上添花）

Step 4: A1+A2 均达标? → 手工验证 → 结束
                       → 不达标 → 进入方案 B
```

### 4.3 方案 B 实施要点

仅在 `chat.py` 的 `post()` 方法中、`app.invoke()` 之前插入预检索逻辑。策略为**默认检索 + 闲聊豁免**：关键词 `_is_chat()` 判定为闲聊时不触发预检索（走正常 Agentic RAG，LLM 仍可自主调 tool 兜底），其余情况先同步检索再将结果作为 `SystemMessage` 追加到 inputs 中。

### 4.4 不做什么

- **不引入 `tool_choice="required"`** — 会强制每次聊天都调 tool，闲聊也要查知识库，不符合 Agentic RAG 的自主决策理念
- **不引入额外的 LLM 调用做意图分类** — 关键词匹配足以应对方案 B 的预判需求，增加 LLM 调用徒增延迟和成本
- **不修改 Memory Agent** — 它不需要 tool，v4-flash 继续使用，不在本次范围内

---

## 5. 验收标准

| 阶段 | 验收方式 | 标准 |
|------|---------|------|
| Baseline | 脚本评估 | 记录当前 v4-flash 三类命中率 |
| 方案 A | 脚本评估 | 三类全部达标（§3.3） |
| 方案 A 手工验证 | 前端聊天 10 条对话 | 知识类问题 RAG 触发 ≥80%，闲聊不触发 |
| 方案 B | 手工验证 | 同方案 A 标准 |
| 方案 C | 手工验证 | RAG 恢复到 v3.2 时期的可靠性 |
