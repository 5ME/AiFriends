# P1-A1: 用户每日配额系统 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 AI Friends 新增用户每日 API 配额系统，补齐成本治理三层闭环（限流→配额→记账）。

**Architecture:** 新增 `UserQuota` 模型（user+date 唯一约束）；`check_quota()` 函数返回 `(allowed, current, limit)` 供各 view 灵活处理；`record_api_usage()` 新增 `update_quota` 参数，调用后通过 `F()` 表达式原子递增配额计数。Memory Agent 不扣用户额度。

**Tech Stack:** Django ORM (`get_or_create` + `F()` 原子更新), PostgreSQL `unique_together`

**Design Doc:** `docs/superpowers/specs/2026-06-12-user-daily-quota-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/web/models/quota.py` | **Create** | UserQuota 模型 |
| `backend/web/migrations/XXXX_add_user_quota.py` | **Create** | 自动生成迁移 |
| `backend/web/models/__init__.py` | **Modify** | 导出 UserQuota |
| `backend/web/utils/quota.py` | **Create** | check_quota() 函数 + API_TYPE_TO_FIELD 映射 |
| `backend/web/utils/usage.py` | **Modify** | 加 update_quota 参数 + 配额原子更新 |
| `backend/backend/settings.py` | **Modify** | 加 QUOTA_* 常量 |
| `backend/web/views/friend/message/memory/tasks.py` | **Modify** | 两处 `record_api_usage` 加 `update_quota=False` |
| `backend/web/views/friend/message/chat/chat.py` | **Modify** | post() 加 LLM 配额检查；work() 加 TTS 配额检查；新增 `_stream_llm_only` |
| `backend/web/views/friend/message/asr/asr.py` | **Modify** | post() 加 ASR 配额检查 |
| `backend/web/views/document/upload.py` | **Modify** | post() 加 embedding 配额检查 |
| `backend/web/views/document/tasks.py` | **Modify** | Celery 任务内加 embedding 配额检查 |
| `backend/web/tests/test_quota.py` | **Create** | check_quota + record_api_usage + 模型单元测试 |
| `backend/web/tests/test_chat_agent.py` | **Modify** | Chat view 配额超限测试 |
| `backend/web/tests/test_asr.py` | **Modify** | ASR view 配额超限测试 |
| `backend/web/tests/test_document.py` | **Modify** | 上传配额超限测试 |
| `backend/web/tests/test_document_processing.py` | **Modify** | Celery 配额超限测试 |

---

### Task 1: UserQuota 模型 + 迁移

**Files:**
- Create: `backend/web/models/quota.py`
- Create: `backend/web/migrations/XXXX_add_user_quota.py` (auto)
- Modify: `backend/web/models/__init__.py`

- [ ] **Step 1: 创建模型文件**

`backend/web/models/quota.py`:
```python
"""User daily API quota model"""
from django.db import models
from web.models.user import UserProfile


class UserQuota(models.Model):
    """用户每日 API 配额消耗记录。

    同一用户同一天只有一行 — unique_together('user', 'date') 保证。
    四种 API 独立计数，互不影响。
    """
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    date = models.DateField()

    llm_tokens_used = models.IntegerField(default=0)
    tts_chars_used = models.IntegerField(default=0)
    asr_seconds_used = models.IntegerField(default=0)
    embedding_tokens_used = models.IntegerField(default=0)

    class Meta:
        unique_together = ('user', 'date')
```

- [ ] **Step 2: 导出模型**

`backend/web/models/__init__.py` — 在现有 imports 末尾追加：
```python
from .quota import UserQuota
```

- [ ] **Step 3: 生成迁移**

```bash
cd backend && python manage.py makemigrations web --name add_user_quota
```

- [ ] **Step 4: 运行迁移并验证**

```bash
cd backend && python manage.py migrate
```

Expected: `Applying web.XXXX_add_user_quota... OK`

- [ ] **Step 5: 验证模型可用**

```bash
cd backend && python -c "from web.models.quota import UserQuota; print('OK:', UserQuota._meta.db_table)"
```

Expected: `OK: web_userquota`

---

### Task 2: check_quota() 函数

**File:** Create: `backend/web/utils/quota.py`

- [ ] **Step 1: 创建配额工具模块**

`backend/web/utils/quota.py`:
```python
"""User daily quota checking utility"""
from django.conf import settings
from django.utils import timezone

API_TYPE_TO_FIELD = {
    'llm':       'llm_tokens_used',
    'tts':       'tts_chars_used',
    'asr':       'asr_seconds_used',
    'embedding': 'embedding_tokens_used',
}

API_TYPE_TO_SETTING = {
    'llm':       'QUOTA_LLM_TOKENS_PER_DAY',
    'tts':       'QUOTA_TTS_CHARS_PER_DAY',
    'asr':       'QUOTA_ASR_SECONDS_PER_DAY',
    'embedding': 'QUOTA_EMBEDDING_TOKENS_PER_DAY',
}


def check_quota(user_id: int, api_type: str):
    """检查用户今日 API 配额是否超限。

    Args:
        user_id: UserProfile.id
        api_type: 'llm' | 'tts' | 'asr' | 'embedding'

    Returns:
        (allowed, current_usage, limit)
        - allowed: True 表示未超限
        - current_usage: 今日已用量
        - limit: 今日限额（0 表示该 API 被禁用）
    """
    from web.models.quota import UserQuota

    limit = getattr(settings, API_TYPE_TO_SETTING[api_type], 0)
    if limit == 0:
        return (False, 0, 0)

    field_name = API_TYPE_TO_FIELD[api_type]
    today = timezone.localdate()

    quota = UserQuota.objects.filter(user_id=user_id, date=today).first()
    current = getattr(quota, field_name, 0) if quota else 0

    return (current < limit, current, limit)
```

- [ ] **Step 2: 验证导入**

```bash
cd backend && python -c "from web.utils.quota import check_quota, API_TYPE_TO_FIELD; print('OK')"
```

---

### Task 3: record_api_usage() 增强

**File:** Modify: `backend/web/utils/usage.py`

- [ ] **Step 1: 重写 usage.py**

Replace entire file:
```python
"""API usage recording utility"""
import logging

from web.utils.quota import API_TYPE_TO_FIELD

logger = logging.getLogger(__name__)


def record_api_usage(*, user_id, api_type, model_name,
                     token_count=0, duration_ms=0,
                     success=True, error_message='',
                     update_quota=True):
    """记录 AI API 调用用量 + 更新用户每日配额。

    update_quota=False 用于系统功能（如 Memory Agent），
    用量仍写入 APIUsage 但跳过量配额更新。
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
        return

    if not (update_quota and user_id is not None):
        return

    try:
        _update_quota(user_id, api_type, token_count)
    except Exception:
        logger.exception('UserQuota 更新失败: user=%s, type=%s', user_id, api_type)


def _update_quota(user_id, api_type, token_count):
    from django.db.models import F
    from django.utils import timezone
    from web.models.quota import UserQuota

    quota_value = _quota_value(api_type, token_count)
    field_name = API_TYPE_TO_FIELD[api_type]

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
    UserQuota.objects.filter(pk=quota.pk).update(
        **{field_name: F(field_name) + quota_value}
    )


def _quota_value(api_type, token_count):
    """ASR 配额值转换：采样点 → 秒"""
    if api_type == 'asr':
        return max(token_count // 16000, 1)
    return token_count
```

- [ ] **Step 2: 验证现有调用方不受影响**

```bash
cd backend && python -c "from web.utils.usage import record_api_usage; print('OK')"
```

---

### Task 4: Settings 常量

**File:** Modify: `backend/backend/settings.py`

- [ ] **Step 1: 追加配额常量**

In `settings.py`, find a suitable location after existing app-specific settings (near `RATE_LIMIT_RULES` at ~line 259) and append:

```python
# 用户每日 API 配额
QUOTA_LLM_TOKENS_PER_DAY = 10_000
QUOTA_TTS_CHARS_PER_DAY = 10_000
QUOTA_ASR_SECONDS_PER_DAY = 300
QUOTA_EMBEDDING_TOKENS_PER_DAY = 50_000
```

- [ ] **Step 2: 验证 settings 可读**

```bash
cd backend && python -c "from django.conf import settings; print(settings.QUOTA_LLM_TOKENS_PER_DAY)"
```

Expected: `10000`

---

### Task 5: Memory Agent — update_quota=False

**File:** Modify: `backend/web/views/friend/message/memory/tasks.py`

- [ ] **Step 1: 修改成功路径（line 72-75）**

```python
# Before:
        record_api_usage(
            user_id=user_id, api_type='llm', model_name='deepseek-v4-flash',
            token_count=token_count, duration_ms=duration_ms, success=True,
        )

# After: 加 update_quota=False
        record_api_usage(
            user_id=user_id, api_type='llm', model_name='deepseek-v4-flash',
            token_count=token_count, duration_ms=duration_ms, success=True,
            update_quota=False,
        )
```

- [ ] **Step 2: 修改失败路径（line 83-87）**

```python
# Before:
            record_api_usage(
                user_id=user_id, api_type='llm', model_name='deepseek-v4-flash',
                token_count=0, duration_ms=duration_ms,
                success=False, error_message=str(exc)[:500],
            )

# After: 加 update_quota=False
            record_api_usage(
                user_id=user_id, api_type='llm', model_name='deepseek-v4-flash',
                token_count=0, duration_ms=duration_ms,
                success=False, error_message=str(exc)[:500],
                update_quota=False,
            )
```

- [ ] **Step 3: 运行 Memory Agent 测试**

```bash
cd backend && python -m pytest web/tests/test_memory_agent.py -v
```

Expected: 5 passed

---

### Task 6: Chat View — LLM 配额检查

**File:** Modify: `backend/web/views/friend/message/chat/chat.py`

- [ ] **Step 1: 在 post() 中加配额检查**

At the top of `chat.py`, add import:
```python
from web.utils.quota import check_quota
```

In `post()`, after `friend = friends.first()` (line 155) and before `app = ChatGraph.create_app()` (line 156), insert:

```python
        # === 用户每日 LLM 配额检查 ===
        allowed, cur, limit = check_quota(friend.user_profile_id, 'llm')
        if not allowed:
            return Response(
                {'message': f'今日对话配额已用尽({cur}/{limit})，请明天再试'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
```

- [ ] **Step 2: 运行 Chat Agent 测试**

```bash
cd backend && python -m pytest web/tests/test_chat_agent.py -v
```

Expected: 11 passed

---

### Task 7: ASR View — ASR 配额检查

**File:** Modify: `backend/web/views/friend/message/asr/asr.py`

- [ ] **Step 1: 在 post() 中加配额检查**

At the top of `asr.py`, add import:
```python
from web.utils.quota import check_quota
```

In `post()`, after `user_id = self.request.user.userprofile.id` (current line 31) and before `text = asyncio.run(...)` (line 32), insert:

```python
            # === 用户每日 ASR 配额检查（sync 上下文） ===
            allowed, cur, limit = check_quota(user_id, 'asr')
            if not allowed:
                return Response(
                    {'message': f'今日语音识别配额已用尽({cur}/{limit})，可继续打字聊天'},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )
```

- [ ] **Step 2: 运行 ASR 测试**

```bash
cd backend && python -m pytest web/tests/test_asr.py -v
```

Expected: 6 passed

---

### Task 8: TTS — 配额检查 + 静默降级

**File:** Modify: `backend/web/views/friend/message/chat/chat.py`

- [ ] **Step 1: 在 work() 中加 TTS 配额检查**

In `work()` (line 259-280), before `try:`, add:

```python
        # === TTS 配额检查（sync 上下文，避免 async 内调 ORM） ===
        tts_allowed, _, _ = check_quota(self._caller_user_id, 'tts')
        if not tts_allowed:
            logger.warning('TTS 跳过：今日配额已用尽, user_id=%s', self._caller_user_id)
```

Wait — `work()` doesn't have access to `user_id` for quota check. Let me re-read. Actually `user_id` is passed as a parameter to `work()`. But `check_quota` is imported at the top.

In `work()`, after the docstring/signature, before `try:`, insert:

```python
        # === TTS 配额检查（sync 上下文，避免 async 内调 ORM） ===
        tts_allowed, _, _ = check_quota(user_id, 'tts')
        if not tts_allowed:
            logger.warning('TTS 跳过：今日配额已用尽, user_id=%s', user_id)
```

Then pass `tts_allowed` to `run_tts_task`:
```python
            asyncio.run(self.run_tts_task(app, inputs, mq, voice_id, user_id, tts_allowed))
```

- [ ] **Step 2: 修改 run_tts_task 签名 + 降级路径**

Change signature:
```python
    async def run_tts_task(
            self,
            app: CompiledStateGraph,
            inputs,
            mq: queue.Queue,
            voice_id: str,
            user_id: int,
            tts_allowed: bool = True,
    ):
```

At the start of the method body (after `task_id = uuid.uuid4().hex`), add:

```python
        if not tts_allowed:
            # 跳过 TTS：只跑 LLM 文字流，TTS usage 不记录（无 _tts_usage）
            await self._stream_llm_only(app, inputs, mq, user_id)
            return
```

(The rest of `run_tts_task` unchanged — the TTS WebSocket path.)

- [ ] **Step 3: 新增 `_stream_llm_only` 方法**

Add after `tts_receiver` method (end of file):

```python
    async def _stream_llm_only(
            self,
            app: CompiledStateGraph,
            inputs,
            mq: queue.Queue,
            user_id: int,
    ):
        """仅 LLM 文字流的降级路径 — TTS 配额超限或 TTS 失败时使用。"""
        try:
            async for msg, metadata in app.astream(inputs, stream_mode="messages"):
                if isinstance(msg, ToolMessage) and msg.name == "search_knowledge_base":
                    citations = []
                    for m in CITATION_RE.finditer(msg.content):
                        citations.append({
                            "index": int(m.group(1)),
                            "title": m.group(2),
                            "chunk_index": int(m.group(3)),
                        })
                    if citations:
                        mq.put_nowait({'citations': citations})

                elif isinstance(msg, BaseMessageChunk):
                    if msg.content:
                        mq.put_nowait({'content': msg.content})
                    if hasattr(msg, 'usage_metadata') and msg.usage_metadata:
                        mq.put_nowait({'usage': msg.usage_metadata})
        except Exception:
            logger.exception('LLM 文字流异常（TTS 降级模式）')
            try:
                mq.put_nowait({'error': '系统异常，请稍后重试'})
            except queue.Full:
                pass
```

(Note: This is the core of `tts_sender` minus the `await ws.send(...)` TTS parts.)

- [ ] **Step 4: 运行 Chat Agent 测试**

```bash
cd backend && python -m pytest web/tests/test_chat_agent.py -v
```

Expected: 11 passed

- [ ] **Step 5: Verify TTS skip does not break LLM text stream**

Manually verify: `python -m pytest web/tests/test_chat_agent.py::TestChatSSEEndpoint::test_sse_text_stream -v`

---

### Task 9: Embedding — 上传 + Celery 配额检查

**Files:**
- Modify: `backend/web/views/document/upload.py`
- Modify: `backend/web/views/document/tasks.py`

- [ ] **Step 1: 上传 view 加配额检查**

`upload.py` — add import at top:
```python
from web.utils.quota import check_quota
```

In `post()`, after `error = _validate_file(file)` block and before `ext = file.name.rsplit(...)` (current line 86), insert:

```python
        # === 用户每日 embedding 配额检查 ===
        user_id = request.user.userprofile.id
        allowed, cur, limit = check_quota(user_id, 'embedding')
        if not allowed:
            return Response(
                {'message': f'今日文档处理配额已用尽({cur}/{limit})，请明天再试'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
```

- [ ] **Step 2: Celery 任务加配额检查**

`tasks.py` — add import at top:
```python
from web.utils.quota import check_quota
```

In `process_document_task()`, after `doc.status = 'processing'` line and before `logger.info(...)` (between current lines 22-23), insert:

```python
        # === 用户每日 embedding 配额检查 ===
        if doc.owner_id:
            allowed, cur, limit = check_quota(doc.owner_id, 'embedding')
            if not allowed:
                doc.status = 'failed'
                doc.error_message = f'今日文档处理配额已用尽({cur}/{limit})'
                doc.celery_task_id = ''
                doc.save(update_fields=['status', 'error_message', 'celery_task_id'])
                logger.warning('文档处理跳过: 配额已用尽, doc_id=%d, user_id=%d', doc_id, doc.owner_id)
                return
```

The `if doc.owner_id:` guard handles system documents (global knowledge base) where `owner_id` is NULL.

- [ ] **Step 3: 运行文档相关测试**

```bash
cd backend && python -m pytest web/tests/test_document.py web/tests/test_document_processing.py -v
```

Expected: all 22+8=30 tests pass

---

### Task 10: 单元测试 — check_quota + record_api_usage + 模型

**File:** Create: `backend/web/tests/test_quota.py`

- [ ] **Step 1: 创建测试文件**

`backend/web/tests/test_quota.py`:
```python
"""Tests for check_quota, record_api_usage quota update, and UserQuota model"""
import time
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone

from web.models.quota import UserQuota
from web.utils.quota import check_quota
from web.utils.usage import record_api_usage


@pytest.mark.django_db
class TestCheckQuota:
    """check_quota() 函数测试"""

    def test_under_limit_returns_allowed(self, user_profile):
        """配额未超 → allowed=True"""
        allowed, cur, limit = check_quota(user_profile.id, 'llm')
        assert allowed is True
        assert cur == 0
        assert limit == 10_000

    def test_over_limit_returns_denied(self, user_profile):
        """配额已超 → allowed=False"""
        today = timezone.localdate()
        UserQuota.objects.create(
            user=user_profile, date=today,
            llm_tokens_used=10_000,
        )
        allowed, cur, limit = check_quota(user_profile.id, 'llm')
        assert allowed is False
        assert cur == 10_000
        assert limit == 10_000

    def test_different_api_types_independent(self, user_profile):
        """不同 API 类型独立计数"""
        today = timezone.localdate()
        UserQuota.objects.create(
            user=user_profile, date=today,
            llm_tokens_used=10_000,  # LLM 已满
            tts_chars_used=0,
        )
        # LLM 超限
        assert check_quota(user_profile.id, 'llm')[0] is False
        # TTS 仍然可用
        assert check_quota(user_profile.id, 'tts')[0] is True

    def test_no_quota_row_means_zero(self, user_profile):
        """没有记录 → current=0"""
        allowed, cur, _ = check_quota(user_profile.id, 'embedding')
        assert allowed is True
        assert cur == 0

    def test_cross_day_isolation(self, user_profile):
        """跨天配额隔离"""
        today = timezone.localdate()
        UserQuota.objects.create(
            user=user_profile, date=today,
            llm_tokens_used=10_000,
        )
        # 今天超限
        assert check_quota(user_profile.id, 'llm')[0] is False
        # 模拟明天：新日期无记录 → 从 0 开始
        with patch.object(timezone, 'localdate', return_value=today.replace(day=today.day + 1)):
            assert check_quota(user_profile.id, 'llm')[0] is True

    @override_settings(QUOTA_LLM_TOKENS_PER_DAY=0)
    def test_zero_limit_means_disabled(self, user_profile):
        """限额=0 → API 禁用"""
        allowed, cur, limit = check_quota(user_profile.id, 'llm')
        assert allowed is False
        assert limit == 0


@pytest.mark.django_db
class TestRecordApiUsageQuota:
    """record_api_usage 配额更新测试"""

    def test_updates_quota_on_first_call(self, user_profile):
        """首次调用创建配额行并递增"""
        record_api_usage(
            user_id=user_profile.id, api_type='llm',
            model_name='deepseek-v4-flash', token_count=500,
        )
        today = timezone.localdate()
        quota = UserQuota.objects.get(user=user_profile, date=today)
        assert quota.llm_tokens_used == 500

    def test_updates_quota_on_second_call(self, user_profile):
        """第二次调用原子递增"""
        today = timezone.localdate()
        UserQuota.objects.create(
            user=user_profile, date=today, llm_tokens_used=300,
        )
        record_api_usage(
            user_id=user_profile.id, api_type='llm',
            model_name='deepseek-v4-flash', token_count=200,
        )
        quota = UserQuota.objects.get(user=user_profile, date=today)
        assert quota.llm_tokens_used == 500

    def test_update_quota_false_skips_quota(self, user_profile):
        """update_quota=False → APIUsage 写入但配额不更新"""
        record_api_usage(
            user_id=user_profile.id, api_type='llm',
            model_name='deepseek-v4-flash', token_count=500,
            update_quota=False,
        )
        assert not UserQuota.objects.filter(user=user_profile).exists()

    def test_user_none_skips_quota(self):
        """user_id=None → 跳过配额更新"""
        record_api_usage(
            user_id=None, api_type='llm',
            model_name='deepseek-v4-flash', token_count=500,
        )
        assert not UserQuota.objects.exists()

    def test_asr_converts_samples_to_seconds(self, user_profile):
        """ASR 采样点 → 秒转换"""
        record_api_usage(
            user_id=user_profile.id, api_type='asr',
            model_name='gummy-realtime-v1',
            token_count=16000 * 3,  # 3 秒的采样点
        )
        today = timezone.localdate()
        quota = UserQuota.objects.get(user=user_profile, date=today)
        assert quota.asr_seconds_used == 3

    def test_asr_minimum_one_second(self, user_profile):
        """ASR 不足 1 秒按 1 秒计"""
        record_api_usage(
            user_id=user_profile.id, api_type='asr',
            model_name='gummy-realtime-v1',
            token_count=100,  # < 16000 采样点
        )
        quota = UserQuota.objects.get(user=user_profile, date=timezone.localdate())
        assert quota.asr_seconds_used == 1

    def test_different_users_isolated(self, user_profile):
        """不同用户配额隔离"""
        from django.contrib.auth.models import User
        other_user = User.objects.create_user(username='quota_test_other')
        from web.models.user import UserProfile
        other_profile = UserProfile.objects.create(user=other_user)

        record_api_usage(
            user_id=user_profile.id, api_type='llm',
            model_name='deepseek-v4-flash', token_count=100,
        )
        record_api_usage(
            user_id=other_profile.id, api_type='llm',
            model_name='deepseek-v4-flash', token_count=200,
        )
        assert UserQuota.objects.get(user=user_profile).llm_tokens_used == 100
        assert UserQuota.objects.get(user=other_profile).llm_tokens_used == 200


@pytest.mark.django_db
class TestUserQuotaModel:
    """UserQuota 模型测试"""

    def test_unique_user_date(self, user_profile):
        """同一用户同一天不能有两行"""
        today = timezone.localdate()
        UserQuota.objects.create(user=user_profile, date=today)
        with pytest.raises(Exception):
            UserQuota.objects.create(user=user_profile, date=today)

    def test_defaults_are_zero(self, user_profile):
        """新建记录的 consumed 字段默认为 0"""
        today = timezone.localdate()
        quota = UserQuota.objects.create(user=user_profile, date=today)
        assert quota.llm_tokens_used == 0
        assert quota.tts_chars_used == 0
        assert quota.asr_seconds_used == 0
        assert quota.embedding_tokens_used == 0
```

- [ ] **Step 2: 运行新测试**

```bash
cd backend && python -m pytest web/tests/test_quota.py -v
```

Expected: all new tests pass (15 tests)

---

### Task 11: 集成测试 — View 层配额检查

**Files:**
- Modify: `backend/web/tests/test_chat_agent.py`
- Modify: `backend/web/tests/test_asr.py`
- Modify: `backend/web/tests/test_document.py`
- Modify: `backend/web/tests/test_document_processing.py`

- [ ] **Step 1: Chat view 配额超限测试**

Append to `test_chat_agent.py` (inside `TestChatSSEEndpoint` class):

```python
    @patch("web.views.friend.message.chat.chat.check_quota")
    def test_quota_exceeded_returns_429(self, mock_check, auth_client, friend):
        """LLM 配额超限 → 429"""
        mock_check.return_value = (False, 10_000, 10_000)
        resp = auth_client.post(
            "/api/friend/message/chat/",
            {"friend_id": friend.id, "message": "你好"},
        )
        assert resp.status_code == 429
        assert "配额" in resp.json()["message"]
```

- [ ] **Step 2: ASR view 配额超限测试**

Append to `test_asr.py` (inside `TestASREndpoint` class):

```python
    @patch("web.views.friend.message.asr.asr.check_quota")
    def test_quota_exceeded_returns_429(self, mock_check, auth_client):
        """ASR 配额超限 → 429"""
        mock_check.return_value = (False, 300, 300)
        resp = auth_client.post(
            "/api/friend/message/asr/asr/",
            {"audio": _dummy_audio()},
        )
        assert resp.status_code == 429
        assert "配额" in resp.json()["message"]
```

- [ ] **Step 3: Document 上传配额超限测试**

Append to `test_document.py` (inside `TestDocumentUpload` class):

```python
    @patch("web.views.document.upload.check_quota")
    def test_upload_quota_exceeded_returns_429(self, mock_check, auth_client):
        """embedding 配额超限 → 上传被拒"""
        mock_check.return_value = (False, 50_000, 50_000)
        file = SimpleUploadedFile("test.txt", b"hello world", content_type="text/plain")
        resp = auth_client.post("/api/document/upload/", {"file": file})
        assert resp.status_code == 429
        assert "配额" in resp.json()["message"]
```

(Needs import `from django.core.files.uploadedfile import SimpleUploadedFile` — already available at top of `test_document.py`.)

- [ ] **Step 4: Document processing Celery 配额超限测试**

Append to `test_document_processing.py` (inside `TestDocumentProcessing` class):

```python
    @patch("web.views.document.tasks.check_quota")
    def test_celery_quota_exceeded_marks_failed(self, mock_check, auth_client):
        """Celery 任务内配额超限 → doc.status='failed'"""
        mock_check.return_value = (False, 50_000, 50_000)
        user = baker.make(UserProfile)
        doc = baker.make(
            UserDocument, owner=user, file_url="documents/test.txt",
            file_type="txt", status="pending",
        )
        from web.views.document.tasks import process_document_task
        process_document_task(doc.id)
        doc.refresh_from_db()
        assert doc.status == "failed"
        assert "配额" in doc.error_message
```

(Needs imports at top of `test_document_processing.py`: `from web.models.document import UserDocument`, `from web.models.user import UserProfile`, `from model_bakery import baker` — `baker` already imported.)

- [ ] **Step 5: 运行集成测试**

```bash
cd backend && python -m pytest web/tests/test_chat_agent.py::TestChatSSEEndpoint::test_quota_exceeded_returns_429 \
  web/tests/test_asr.py::TestASREndpoint::test_quota_exceeded_returns_429 \
  web/tests/test_document.py::TestDocumentUpload::test_upload_quota_exceeded_returns_429 \
  web/tests/test_document_processing.py::TestDocumentProcessing::test_celery_quota_exceeded_marks_failed \
  -v
```

Expected: 4 passed

---

### Task 12: 全量测试 + Commit

- [ ] **Step 1: 运行全量测试**

```bash
cd backend && python -m pytest web/tests/ -v
```

Expected: ~163 tests passed (148 existing + 15 new)

- [ ] **Step 2: Commit**

```bash
cd D:/MyProjects/AiFriends && git add .
git commit -m @'
feat: P1-A1 用户每日 API 配额系统

- 新增 UserQuota 模型（user+date unique_together，四种 API 独立计数）
- check_quota() 函数：返回 (allowed, current, limit)，调用方自行处理
- record_api_usage() 增强：update_quota 参数 + F() 原子递增配额
- Memory Agent 不扣用户额度（update_quota=False）
- Chat/ASR/Embedding 超限返回 HTTP 429
- TTS 超限静默降级纯文本（_stream_llm_only 降级路径）
- ASR 采样点 → 秒转换（token_count // 16000）
- 12 + 4 个新测试（单元 + 集成）

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

## Execution Order

```
Task 1 (Model) → Task 2 (check_quota) → Task 3 (record_api_usage) → Task 4 (Settings)
  → Task 5 (Memory Agent) → Task 10 (Unit tests) [验证核心逻辑]
  → Task 6 (Chat) → Task 7 (ASR) → Task 8 (TTS) → Task 9 (Embedding) [集成]
  → Task 11 (Integration tests) → Task 12 (Full suite + commit)
```
