# P1-B3: RAG no-answer 策略 — 设计文档

> 日期：2026-06-17  
> 来源：`docs/superpowers/specs/2026-06-11-next-steps-roadmap.md` P1-B3  
> 状态：待实施

---

## 一、问题陈述

`search_knowledge_base` 工具当前有 3 个不足：

1. **无距离过滤**：pgvector 返回的 top-3 无论相关性高低都喂给 LLM，不相关内容可能导致 LLM 编造答案
2. **检索条数硬编码**：`LIMIT 3` 写死，LLM 无法按需控制（简单事实 vs 多角度分析）
3. **无循环保护**：虽然历史上没出现过死循环，但没有硬保险

---

## 二、方案选择

### 2.1 距离阈值

| | 方案 A：settings 配置（✅ 选择） | 方案 B：硬编码常量 |
|---|---|---|
| **描述** | `RAG_SIMILARITY_THRESHOLD = 0.5` 可配置 | `if distance > 0.5:` 写死在代码 |
| **优点** | 运维可调，无需改代码 | 简单 |
| **缺点** | 多一行配置 | 调参需改代码部署 |

**选择 A 的理由：** 阈值是经验值，需要根据实际效果迭代。一行配置换一个不部署的调参入口，值得。

### 2.2 检索条数

| | 方案 A：max_results 参数（✅ 选择） | 方案 B：保留 LIMIT 3 |
|---|---|---|
| **描述** | LLM 通过工具参数自主决定条数 | 不动 |
| **优点** | 灵活，LLM 天然擅长按需选择 | 零改动 |
| **缺点** | 改动 ~3 行 | LLM 无法控制 |

**选择 A 的理由：** 改动极小（工具签名加一个参数），LLM 能根据不同问题类型做出合理选择。

### 2.3 循环保护

| | 方案 A：硬上限（✅ 选择） | 方案 B：无限循环 |
|---|---|---|
| **描述** | `RAG_MAX_TOOL_CALLS = 5` 强制截断 | 信任 LLM 自我终止 |
| **优点** | 绝对安全 | 零代码 |
| **缺点** | 2 行代码 | 理论上存在小概率死循环 |

**选择 A 的理由：** 防御性编程，2 行代码的保险不会伤害正常流程（LLM 从未超过 3 次 tool calls）。

---

## 三、核心设计

### 3.1 配置项（settings.py）

```python
# RAG 向量检索配置
RAG_DEFAULT_MAX_RESULTS = 5       # 单次检索默认返回条数（LLM 可通过 max_results 覆盖）
RAG_SIMILARITY_THRESHOLD = 0.5    # 余弦距离阈值（pgvector <=>，0=完全相同 2=语义相反）
RAG_MAX_TOOL_CALLS = 5            # 单次对话最多工具调用次数（防止异常循环）
```

### 3.2 search_knowledge_base 改造（graph.py）

**新增参数 `max_results`：**

```python
def search_knowledge_base(
    query: str,
    max_results: int = None,
    state: Annotated[dict, InjectedState]
) -> str:
    # 使用 settings 默认值，LLM 可通过参数覆盖
    if max_results is None:
        max_results = getattr(settings, 'RAG_DEFAULT_MAX_RESULTS', 5)
```

Tool description 新增：
```
根据问题类型选择 max_results：
- 简单事实查询 → 1-2
- 需要多角度信息 → 3-5
```

**SQL 改为参数化 LIMIT：**

```python
cursor.execute(f"""
    ... LIMIT %s
""", [emb, user_id, emb, max_results])
```

**距离阈值过滤：**

```python
# 按阈值过滤不相关结果
threshold = getattr(settings, 'RAG_SIMILARITY_THRESHOLD', 0.5)
filtered_rows = [r for r in rows if r[5] < threshold]

if not filtered_rows:
    return "知识库中未找到相关信息。请尝试更换关键词后重新检索。"
```

### 3.3 循环保护（graph.py）

```python
def should_continue(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        # 统计已完成的 tool_calls 次数，防止异常循环
        tool_call_count = sum(
            1 for msg in state["messages"]
            if isinstance(msg, ToolMessage)
        )
        if tool_call_count >= getattr(settings, 'RAG_MAX_TOOL_CALLS', 5):
            return "end"  # 强制结束，让 LLM 基于已有信息回复
        return "tools"
    return "end"
```

### 3.4 Prompt 层 — TOOL_RULES 更新（chat.py）

在现有 TOOL_RULES 末尾追加 no-answer 指令：

```python
TOOL_RULES = (
    # ... 现有内容不变 ...
    "3. 不确定时宁可查询也不要遗漏。\n"
    "4. 当 search_knowledge_base 返回\"知识库中未找到相关信息\"时，\n"
    "   直接告知用户\"我目前的知识库中没有找到这方面的信息\"，\n"
    "   不要尝试编造或猜测答案。"
)
```

---

## 四、数据流

```
用户: "红孩儿的父亲是谁"
  │
  ├─ agent: search_knowledge_base("红孩儿的父亲是谁", max_results=3)
  │   → 3 条，全部 distance > 0.5
  │   → 返回 "知识库中未找到相关信息。请尝试更换关键词后重新检索。"
  │
  ├─ agent: search_knowledge_base("红孩儿 牛魔王 铁扇公主", max_results=2)
  │   → 2 条，distance 0.3, 0.4  ✅
  │   → 返回 "[来源1: ...] ..."
  │
  └─ agent: "根据资料，红孩儿是牛魔王和铁扇公主的儿子..."
     → end
```

---

## 五、测试计划

| # | 场景 | 验证点 |
|---|------|--------|
| 1 | 全部超阈值 | 返回 "知识库中未找到相关信息..." |
| 2 | 部分超阈值 | 只保留 distance < 0.5 的结果 |
| 3 | max_results 参数 | 返回条数符合参数指定的值 |

追加到 `backend/web/tests/test_chat_agent.py`。

---

## 六、实施清单

- [ ] `settings.py` 添加 3 个 RAG 配置项
- [ ] `graph.py` search_knowledge_base 加 max_results 参数 + 阈值过滤
- [ ] `graph.py` should_continue 加 tool_call_count 限制
- [ ] `chat.py` TOOL_RULES 追加 no-answer 指令
- [ ] 补充 3 个测试到 test_chat_agent.py
- [ ] 运行全量测试（原有 6 个 RAG 测试不能破）
