# P1-A1: 用户每日配额系统 — 设计文档

> 日期：2026-06-12  
> 来源：`docs/superpowers/specs/2026-06-11-next-steps-roadmap.md` P1-A1  
> 状态：待实施

---

## 一、问题陈述

### 1.1 当前状态

项目已有两层成本基础：
- **`RateLimitMiddleware`**：Redis 滑动窗口，按分钟频率限流（防刷）
- **`APIUsage` + `record_api_usage()`**：记录每次 AI API 调用的 token/耗时/成败（记账）

```
请求 → 限流检查（频率）→ API 调用 → 记录用量
```

### 1.2 缺失环节

- 限流只管频率（burst），不管**日总量**。一个用户每小时发 5 次，一天 120 次，轻松烧掉几十块钱
- APIUsage 数据堆在那没人看——不知道谁是大户、哪种 API 最烧钱
- 面试方向："AI 项目怎么控制成本？"——只能讲一半故事

### 1.3 目标

补齐"总量控制"环节，形成完整的三层闭环：

```
请求 → RateLimitMiddleware（频率）→ check_quota()（总量）→ API 调用 → record_api_usage（记账+扣减）
```

---

## 二、核心设计

### 2.1 API 类型对齐

代码中 `APIUsage.API_TYPES` 已定义 4 种类型：`llm`、`tts`、`asr`、`embedding`。配额设计与代码一致：

| API 类型 | 字段名 | 调用方 | 是否扣用户配额 |
|----------|--------|--------|-------------|
| `llm` | `llm_tokens_used` | Chat Agent (`chat.py:232`) | ✅ 是 |
| `llm` | — | Memory Agent (`tasks.py:73,84`) | ❌ **不扣**（系统后台功能，不由用户触发） |
| `tts` | `tts_chars_used` | TTS (`chat.py` `_tts_usage`) | ✅ 是 |
| `asr` | `asr_seconds_used` | ASR (`asr.py:91`) | ✅ 是 |
| `embedding` | `embedding_tokens_used` | Embeddings (`embeddings.py:52,62`) | ✅ 是 |

**设计决策 — Memory Agent 不扣用户配额：**

Memory 是后台异步任务，用户不知情也不可控——消耗应由系统承担。通过 `record_api_usage(update_quota=False)` 实现，Memory Agent 用量仍记录到 `APIUsage`（可观测），但不更新 `UserQuota`。

### 2.2 数据模型

```python
class UserQuota(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    date = models.DateField()

    llm_tokens_used = models.IntegerField(default=0)
    tts_chars_used = models.IntegerField(default=0)
    asr_seconds_used = models.IntegerField(default=0)
    embedding_tokens_used = models.IntegerField(default=0)

    class Meta:
        unique_together = ('user', 'date')
```

- `unique_together = ('user', 'date')` 确保同一用户同一天只有一行
- 计数原子更新：`UserQuota.objects.filter(pk=quota.pk).update(llm_tokens_used=F('llm_tokens_used') + consumed)`

### 2.3 配额检查函数

```python
def check_quota(user_id: int, api_type: str) -> tuple[bool, int, int]:
    """检查用户今日配额是否超限。

    Returns:
        (allowed, current_usage, limit)
        - allowed: True 表示未超限，False 表示已超
        - current_usage: 今日已用量
        - limit: 今日限额
    """
```

**设计决策 — 返回判断值 vs 内部抛异常：**

| 方案 | 调用方式 | 优缺点 |
|------|---------|--------|
| **A: 返回判断值** ✅ | `allowed, cur, limit = check_quota(...)` | 调用方自行处理，灵活适配不同超限行为 |
| B: 内部返回 Response | `resp = check_quota(...); if resp: return resp` | 简单但死板，TTS 需要静默降级就无法处理 |

Chat 超限返回 HTTP 429，TTS 超限静默降级纯文本——行为不同，需要灵活处理。选择 A。

### 2.4 配额检查策略

**设计决策 — 预估预留 vs 先放后扣 vs 硬预检：**

| 方案 | 做法 | 选择理由 |
|------|------|---------|
| A: 预估+预留 | 调用前按输入 × 2 预估，先扣预留，完成后修正 | 最精确，但实现复杂 |
| **B: 先放后扣** ✅ | 调用前只检查"今日已实耗"是否超限，完成后扣减 | 最简实现；配合分钟限流，单次超限可忽略；最后一次调用少许超支（~百 token）在成本上无关紧要 |
| C: 硬预检 | 调用前查已耗 + 输入量，超就拒 | 对流式输出不准（输出通常比输入大），无实用优势 |

方案 B 是最简实现，配合 `RateLimitMiddleware` 的分钟级限流，恶意用户无法在单次调用中造成巨大损耗。几百 token 的超限（< 1 分钱）完全可以接受。

### 2.5 默认限额

**设计决策 — 全局常量 vs 默认+可覆盖 vs 分级：**

| 方案 | 代码量 | 复杂度 | 收益 | 当前选择 | 后续升级 |
|------|--------|--------|------|---------|---------|
| **A: 全局常量** ✅ | settings.py 4 行 + 1 函数 | 低 | 所有人统一 | ✅ 当前 | — |
| B: 默认+可覆盖 | A + UserProfile 迁移 + Admin | 中 | 个别用户可调 | ❌ 无此场景 | 升级路径：加 nullable 字段 → check 函数加 `coalesce(user_override, global_default)` |
| C: 分级 | B + Tier 模型 + 管理界面 | 高 | 完整付费体系 | ❌ 无付费体系 | 需重构 check 逻辑 |

全局常量足矣。升级到 B 只需 4 个 IntegerField + 一行改代码。

```python
# settings.py
QUOTA_LLM_TOKENS_PER_DAY = 10_000          # ~20 轮对话
QUOTA_LLM_OVERHEAD_RATIO = 1.8            # 中文 token/char 经验系数（扣除系统 prompt）
QUOTA_TTS_CHARS_PER_DAY = 10_000           # ~20 条语音
QUOTA_ASR_SECONDS_PER_DAY = 300            # ~20 次语音输入
QUOTA_EMBEDDING_TOKENS_PER_DAY = 50_000    # ~100 个 chunk
```

**设计决策 — 独立限额 vs 统一预算池：**

选择独立限额：如果统一预算池，TTS 大量消耗会吃掉 LLM 额度导致用户无法聊天，不如各 API 独立管控。

### 2.6 ASR 配额单位处理

`record_api_usage` 中 ASR 的 `token_count` 传入的是 PCM16 采样点数（`len(pcm_data) // 2`），不是秒。16000 个采样点 = 1 秒。

配额存储和检查使用秒为单位的语义字段 `asr_seconds_used`，因此在配额更新映射中需转换：

```python
API_TYPE_TO_FIELD = {
    'llm':       'llm_tokens_used',
    'tts':       'tts_chars_used',
    'asr':       'asr_seconds_used',
    'embedding': 'embedding_tokens_used',
}

# ASR 配额更新时：采样点 → 秒
if api_type == 'asr':
    quota_value = max(token_count // 16000, 1)  # 至少计 1 秒
else:
    quota_value = token_count
```

`check_quota()` 比较时使用相同的 `asr_seconds_used` 字段，单位一致。

### 2.7 LLM 系统开销扣除

Chat Agent 每次调用会注入 3 层 SystemMessage（工具规则 + 角色设定 + 框架约束），这些是系统级固定开销，不由用户触发。当前 `total_tokens` 将所有上下文合并计算，用户配额被不合理稀释。

**实测数据（消息 #83，红孩儿角色）：**

```
工具规则 (220 chars)        → ~420 token  ← 系统
角色性格 (28 chars)         →  ~65 token  ← 系统
框架约束 (132 chars)        → ~250 token  ← 系统
用户消息 (11 chars)         →  ~22 token  ← 用户
AI 回复                     →  160 token  ← 用户
────────────────────────────────────────
总消耗: 917 token
系统 overhead: ~735 token (80%)
用户实际:      ~182 token
```

**方案**：基于实际 system prompt 内容长度估算 overhead，从配额中扣除。

```python
# settings.py
QUOTA_LLM_OVERHEAD_RATIO = 1.8  # 中英文混合 token/char 经验系数

# chat.py — add_system_prompt() 之后计算
system_chars = (
    len(TOOL_RULES) +
    len("【角色性格】\n") + len(friend.character.system_prompt) +
    len(framework.prompt if framework else "")
)
system_overhead = int(system_chars * QUOTA_LLM_OVERHEAD_RATIO)
```

**扣除 vs 不扣除：**

| 组成部分 | 扣？ | 理由 |
|---------|------|------|
| 工具规则 (TOOL_RULES) | ✅ 扣 | 代码常量，用户不可见 |
| 角色设定 (system_prompt) | ✅ 扣 | 创建者选的，不是用户选的 |
| 框架约束 (SystemPrompt.REPLY) | ✅ 扣 | 平台配置，用户不可控 |
| 长期记忆 (memory) | ❌ 不扣 | 用户历史对话产物 |
| 历史对话 | ❌ 不扣 | 用户行为 |
| 用户消息 + AI 回复 | ❌ 不扣 | 用户行为 + 结果 |

**`record_api_usage` 适配**：新增 `quota_deduct` 参数，不传时默认 = `token_count`（保持 TTS/ASR/Embedding 不变）。

```python
# Chat Agent
record_api_usage(
    ...,
    token_count=total_tokens,
    quota_deduct=max(0, total_tokens - system_overhead),
)
# TTS/ASR/Embedding — 不传 quota_deduct，默认 token_count
```

**自适应验证**：

| 场景 | system_prompt | overhead | quota_deduct (total=917) |
|------|-------------|---------|------|
| 红孩儿 (28 chars) | 394 chars | 709 | 208 |
| 丰富角色 (500 chars) | 866 chars | 1559 | 0（≥total，全免） |
| 超丰富角色 (1000 chars) | 1366 chars | 2459 | 0 |

**已知简化**：`add_system_prompt()` 中 Layer 2 的模板文本（`"【与用户的长期记忆】\n"` 标签 + `"\n\n"` 分隔符 ~14 chars → ~26 token）未单独计入 overhead。这些是系统格式开销，在当前 10000/天限额下 ~0.3%，在 ±20% 误差容忍范围内。后续升级 tiktoken 时可一并修正。

**误差分析**：系数 1.8 对中英文混合有 ±20% 误差。在 10000/天限额下，±100 token = 1%，可接受。以后可升级为 tiktoken 精确计算。

---

## 三、`record_api_usage()` 增强

### 3.1 新增 `update_quota` 参数

```python
def record_api_usage(*, user_id, api_type, model_name,
                     token_count=0, duration_ms=0,
                     success=True, error_message='',
                     update_quota=True,         # 是否更新 UserQuota
                     quota_deduct=None):         # 配额扣除值（默认 = token_count）
    """记录 AI API 调用用量 + 更新用户每日配额。

    update_quota=False 用于系统功能（如 Memory Agent），不扣用户额度。
    quota_deduct 用于 LLM 系统开销扣除（Chat Agent 传入扣除 overhead 后的值）。
    """
    try:
        from web.models.usage import APIUsage
        APIUsage.objects.create(
            user_id=user_id,
            api_type=api_type,
            model_name=model_name,
            token_count=token_count,
            duration_ms=duration_ms,
            success=success,
            error_message=error_message,
        )
    except Exception:
        logger.exception('APIUsage 写入失败: user=%s, type=%s', user_id, api_type)
        return  # APIUsage 写入失败，配额也不更新

    if not (update_quota and user_id is not None):
        return

    # 配额原子更新
    try:
        from django.db.models import F
        from django.utils import timezone
        from web.models.quota import UserQuota

        deduct = quota_deduct if quota_deduct is not None else token_count
        quota_value = _quota_value(api_type, deduct)

        quota, _ = UserQuota.objects.get_or_create(
            user_id=user_id,
            date=timezone.localdate(),
            defaults={
                'llm_tokens_used': 0,
                'tts_chars_used': 0,
                'asr_seconds_used': 0,
                'embedding_tokens_used': 0,
            },
        )
        field_name = API_TYPE_TO_FIELD[api_type]
        UserQuota.objects.filter(pk=quota.pk).update(
            **{field_name: F(field_name) + quota_value}
        )
    except Exception:
        logger.exception('UserQuota 更新失败: user=%s, type=%s', user_id, api_type)
```

### 3.2 调用方修改

| 调用方 | 改动 |
|--------|------|
| Memory Agent (`tasks.py:73,84`) | 加 `update_quota=False` |
| Chat Agent (`chat.py:232`) | 加 `quota_deduct=max(0, total_tokens - system_overhead)` |
| TTS (`chat.py` `_tts_usage`) | 无需改动 |
| ASR (`asr.py:91`) | 无需改动 |
| Embedding | 无需改动 |

---

## 四、四种 API 的集成方式

### 4.1 检查点汇总

| API | 检查点 | 在 sync/async | 超限行为 |
|-----|--------|--------------|---------|
| **LLM (Chat)** | `post()` 中，`StreamingHttpResponse` 创建之前 | sync ✅ | 返回 HTTP 429 |
| **TTS** | `work()` 中，`asyncio.run()` 之前，结果传参进 async | sync ✅ | 静默跳过 TTS |
| **ASR** | `post()` 中，`asyncio.run()` 之前 | sync ✅ | 返回 HTTP 429 |
| **Embedding** | 上传 view + Celery 任务内 | sync ✅ | HTTP 429 / doc.status=failed |

**关键约束**：所有配额检查必须在同步上下文中执行。Django ORM 在 async 内会抛出 `SynchronousOnlyOperation`（与 P0-1 ASR 的 user_id 修复是同一类陷阱）。

**Chat 检查点为什么选 `post()` 而非 `event_stream()`**：`event_stream()` 是 generator，被 `StreamingHttpResponse` 包装后内部无法 `return Response(status=429)`。配额检查移到 `post()` 中，在创建响应对象之前就能返回 429。

**TTS 检查点为什么选 `work()` 而非 `run_tts_task()`**：`run_tts_task` 是 async 函数，内部调用 `check_quota()` → ORM → `SynchronousOnlyOperation`。在 `work()` 中提前检查，`allowed` 作为 bool 传参进 async。

### 4.2 LLM (Chat) 超限

```
用户发消息 → MessageChatView.post()
  → check_quota(user_id, 'llm') → 超限
  → return Response({'message': '今日对话配额已用尽(10000/10000)，请明天再试'}, status=429)
  → 前端 toast 显示错误，消息不发送
```

### 4.3 TTS 超限

```
work() → check_quota(user_id, 'tts') → 超限 → tts_allowed=False
  → asyncio.run(run_tts_task(..., tts_allowed=False))
  → run_tts_task 内：if not tts_allowed: skip TTS, 只跑 LLM 流
  → 文字流正常输出，无音频
  → 用户无感知（与 TTS 故障降级行为一致）
```

### 4.4 ASR 超限

```
用户点击麦克风 → ASRView.post()
  → check_quota(user_id, 'asr') → 超限
  → return Response({'message': '今日语音识别配额已用尽(300/300)，可继续打字聊天'}, status=429)
  → 前端 toast 显示错误
```

### 4.5 Embedding 超限（上传时）

```
用户上传文档 → DocumentUploadView.post()
  → check_quota(user_id, 'embedding') → 超限
  → return Response({'message': '今日文档处理配额已用尽(50000/50000)，请明天再试'}, status=429)
  → 前端 toast 显示错误
```

### 4.6 Embedding 超限（Celery 内）

```
Celery 任务执行 → process_document_task()
  → check_quota(owner_id, 'embedding') → 超限
  → doc.status = 'failed'
  → doc.error_message = '今日文档处理配额已用尽(50000/50000)'
  → doc.save()
  → 前端 DocumentCard 显示红色错误文字
```

---

## 五、边界情况

| 场景 | 处理 |
|------|------|
| 同一天、多条消息并发 | `F()` 表达式在数据库层原子更新，不会丢计数 |
| `get_or_create` + `update` 的竞态 | 两个操作不是原子的但不会丢数：`get_or_create` 幂等，`update` 是增量 |
| 限额 = 0（测试/禁用） | 设为 0 表示完全禁用该 API |
| 没有 `UserProfile` 的系统操作 | `user_id=None` 跳过配额检查（当前只有系统知识库导入用到） |
| 跨天 | `date=timezone.localdate()` 自然切换，旧记录保留 |
| Memory Agent token 消耗 | `record_api_usage(update_quota=False)` — 不计入用户配额 |
| ASR 采样点 → 秒转换 | `token_count // 16000`，不足 1 秒按 1 秒计 |

---

## 六、不纳入范围（Deferred）

- **按用户差异化配额**（B 方案）：当前无此需求，通过 settings 常量即可
- **配额重置通知**：无通知渠道，用户通过 429 响应自然感知
- **配额 Dashboard 前端页面**：A2（APIUsage Admin）先在 Admin 管理端查看
- **软配额模式**（超限后 warn 但继续放行）：YAGNI，硬限制更简单安全

---

## 七、测试策略

| # | 测试场景 | 验证点 |
|---|---------|--------|
| 1 | 配额未达上限 → 正常调用 | `check_quota` 返回 `(True, cur, limit)` |
| 2 | 配额已超 → 拒绝 | `check_quota` 返回 `(False, cur, limit)` |
| 3 | `record_api_usage` 后配额递增 | 两次调用后 `used` 正确累加 |
| 4 | 跨天配额隔离 | 不同日期计数独立 |
| 5 | Chat view 超限返回 429 | `test_chat_agent.py` 补充 |
| 6 | ASR view 超限返回 429 | `test_asr.py` 补充 |
| 7 | TTS 超限静默降级 | 文字流正常，无音频 |
| 8 | Embedding 上传超限返回 429 | `test_document.py` 补充 |
| 9 | Embedding Celery 超限设置 failed | `test_document_processing.py` 补充 |
| 10 | Memory Agent 不更新配额 | `record_api_usage(update_quota=False)` 不修改 UserQuota |
| 11 | ASR 采样点 → 秒转换正确 | `len(pcm_data)//2 // 16000` = 实际秒数 |
| 12 | `F()` 原子更新不丢计数 | 模拟并发调用 |
| 13 | LLM 系统开销从配额扣除 | `quota_deduct` < `token_count` 时配额只扣扣除后的值 |
