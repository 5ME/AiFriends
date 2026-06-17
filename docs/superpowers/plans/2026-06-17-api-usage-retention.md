# P1-A3 APIUsage 数据保留策略 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每天凌晨自动聚合前一天 APIUsage → APIUsageDaily，删除 90 天前的原始明细。

**Architecture:** Celery Beat 每天 2:00 触发一个任务，先按 (date, user, api_type) 聚合 APIUsage 到 APIUsageDaily（`ignore_conflicts=True` 幂等），再批量删除过期记录。`UniqueConstraint` 保证聚合行唯一。

**Tech Stack:** Django 6.0 ORM, Celery (Beat + Worker), PostgreSQL

**Spec:** `docs/superpowers/specs/2026-06-17-api-usage-retention-design.md`

---

### Task 1: 结构准备 — `web/tasks.py` 转为 `web/tasks/` 包

**Files:**
- Create: `backend/web/tasks/__init__.py`
- Delete: `backend/web/tasks.py`

- [ ] **Step 1: 创建 `web/tasks/` 目录**

```bash
mkdir backend\web\tasks
```

- [ ] **Step 2: 创建 `web/tasks/__init__.py`（原 `tasks.py` 内容，暂不 import cleanup_usage_task）**

```python
"""Celery 任务入口 — autodiscover_tasks 自动扫描此模块及其子包"""
from web.views.friend.message.memory.tasks import update_memory_task  # noqa: F401
from web.views.document.tasks import process_document_task  # noqa: F401
```

> **注：** `cleanup_usage_task` 的 import 将在 Task 4（文件创建后）添加，避免导入不存在的模块。

- [ ] **Step 3: 删除旧 `web/tasks.py`**

```bash
Remove-Item backend\web\tasks.py
```

- [ ] **Step 4: 验证 Django 能正常启动**

```bash
cd backend; python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 5: Commit**

```bash
git add backend/web/tasks/
git rm backend/web/tasks.py
git commit -m "refactor: web/tasks.py → web/tasks/ 包，为 cleanup_usage 腾空间"
```

---

### Task 2: 新增 `APIUsageDaily` 模型

**Files:**
- Modify: `backend/web/models/usage.py`
- Modify: `backend/web/models/__init__.py`

- [ ] **Step 1: 在 `usage.py` 末尾添加 `APIUsageDaily` 模型**

```python
class APIUsageDaily(models.Model):
    """按天聚合的 API 用量摘要（永久保留）。

    每天凌晨由 Celery Beat 任务从 APIUsage 聚合写入。
    一条记录 = 一个用户一天一种 API 类型的汇总。
    """

    date = models.DateField()
    user = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE,
        null=True, blank=True,
    )
    api_type = models.CharField(max_length=20, choices=APIUsage.API_TYPES)
    total_tokens = models.IntegerField(default=0)
    call_count = models.IntegerField(default=0)
    total_duration_ms = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['date', 'user', 'api_type'],
                name='unique_daily_user_api',
            ),
        ]
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['user', '-date']),
        ]

    def __repr__(self):
        return (
            f'<APIUsageDaily date={self.date} user_id={self.user_id} '
            f'api_type={self.api_type} tokens={self.total_tokens} calls={self.call_count}>'
        )
```

- [ ] **Step 2: 更新 `models/__init__.py` — 注册新模型**

Old → New:
```diff
-from .usage import APIUsage
+from .usage import APIUsage, APIUsageDaily
```

- [ ] **Step 3: 生成 migration**

```bash
cd backend; python manage.py makemigrations web --name add_api_usage_daily
```

Expected: `Migrations for 'web': web/migrations/00XX_add_api_usage_daily.py`

- [ ] **Step 4: 运行 migration**

```bash
python manage.py migrate
```

Expected: `Applying web.00XX_add_api_usage_daily... OK`

- [ ] **Step 5: 验证模型可用**

```bash
python manage.py shell -c "from web.models.usage import APIUsageDaily; print(APIUsageDaily._meta.db_table)"
```

Expected: `web_apiusagedaily`

- [ ] **Step 6: Commit**

```bash
git add backend/web/models/usage.py backend/web/models/__init__.py backend/web/migrations/00XX_add_api_usage_daily.py
git commit -m "feat: 新增 APIUsageDaily 聚合模型"
```

---

### Task 3: 编写测试（TDD — 先写测试，预期失败）

**Files:**
- Create: `backend/web/tests/test_usage_cleanup.py`

- [ ] **Step 1: 创建测试文件 — 6 个测试用例**

```python
"""P1-A3 APIUsage 数据保留策略 — 聚合 + 清理测试"""
from datetime import timedelta

import pytest
from django.utils import timezone

from web.models.usage import APIUsage, APIUsageDaily


@pytest.mark.django_db
class TestAggregateUsage:
    """APIUsage → APIUsageDaily 聚合逻辑"""

    def test_aggregate_correctness(self, user_profile):
        """同一天同用户 3 llm + 2 tts → 各一行，sum/count 正确"""
        today = timezone.now()
        # 3 条 llm
        for i in range(3):
            APIUsage.objects.create(
                user=user_profile, api_type='llm', model_name='m1',
                token_count=100, duration_ms=1000, created_at=today,
            )
        # 2 条 tts
        for i in range(2):
            APIUsage.objects.create(
                user=user_profile, api_type='tts', model_name='m2',
                token_count=50, duration_ms=500, created_at=today,
            )

        target_date = timezone.localdate()
        from web.tasks.cleanup_usage import aggregate_usage
        aggregate_usage(target_date)

        llm_row = APIUsageDaily.objects.get(user=user_profile, api_type='llm')
        assert llm_row.total_tokens == 300
        assert llm_row.call_count == 3
        assert llm_row.total_duration_ms == 3000

        tts_row = APIUsageDaily.objects.get(user=user_profile, api_type='tts')
        assert tts_row.total_tokens == 100
        assert tts_row.call_count == 2
        assert tts_row.total_duration_ms == 1000

    def test_idempotent(self, user_profile):
        """同一天运行两次聚合 → 不报错，数据不变"""
        today = timezone.now()
        APIUsage.objects.create(
            user=user_profile, api_type='llm', model_name='m1',
            token_count=100, duration_ms=0, created_at=today,
        )

        target_date = timezone.localdate()
        from web.tasks.cleanup_usage import aggregate_usage
        aggregate_usage(target_date)
        aggregate_usage(target_date)  # 第二次运行

        row = APIUsageDaily.objects.get(user=user_profile, api_type='llm')
        assert row.total_tokens == 100
        assert row.call_count == 1

    def test_empty_dataset(self, db):
        """无数据时聚合不报错"""
        from web.tasks.cleanup_usage import aggregate_usage
        aggregate_usage(timezone.localdate())  # 不应抛异常
        assert APIUsageDaily.objects.count() == 0

    def test_user_isolation(self, user_profile, db):
        """用户 A 和用户 B 的 usage 独立汇总"""
        from django.contrib.auth.models import User
        from web.models.user import UserProfile
        today = timezone.now()

        # 用户 B
        user_b = User.objects.create_user(username="user_b")
        profile_b = UserProfile.objects.create(user=user_b)

        APIUsage.objects.create(
            user=user_profile, api_type='llm', model_name='m1',
            token_count=100, duration_ms=0, created_at=today,
        )
        APIUsage.objects.create(
            user=profile_b, api_type='llm', model_name='m1',
            token_count=200, duration_ms=0, created_at=today,
        )

        target_date = timezone.localdate()
        from web.tasks.cleanup_usage import aggregate_usage
        aggregate_usage(target_date)

        row_a = APIUsageDaily.objects.get(user=user_profile, api_type='llm')
        assert row_a.total_tokens == 100

        row_b = APIUsageDaily.objects.get(user=profile_b, api_type='llm')
        assert row_b.total_tokens == 200

    def test_system_user_null(self, db):
        """user=None 的 APIUsage 正常聚合（NULL 行不冲突）"""
        today = timezone.now()
        for i in range(3):
            APIUsage.objects.create(
                user=None, api_type='embedding', model_name='m1',
                token_count=100, duration_ms=0, created_at=today,
            )

        target_date = timezone.localdate()
        from web.tasks.cleanup_usage import aggregate_usage
        aggregate_usage(target_date)

        row = APIUsageDaily.objects.get(user=None, api_type='embedding')
        assert row.total_tokens == 300
        assert row.call_count == 3


@pytest.mark.django_db
class TestDeleteOldRecords:
    """90 天前 APIUsage 删除逻辑"""

    def test_retention_boundary(self, user_profile):
        """retention_days=90 → 91 天前删，89 天前保留"""
        from web.tasks.cleanup_usage import delete_old_records

        today = timezone.now()
        old_date = today - timedelta(days=91)
        recent_date = today - timedelta(days=89)

        # auto_now_add 会覆盖 created_at，先 create 再 update
        old_record = APIUsage.objects.create(
            user=user_profile, api_type='llm', model_name='m1',
            token_count=100, duration_ms=0,
        )
        APIUsage.objects.filter(pk=old_record.pk).update(created_at=old_date)

        recent_record = APIUsage.objects.create(
            user=user_profile, api_type='llm', model_name='m1',
            token_count=100, duration_ms=0,
        )
        APIUsage.objects.filter(pk=recent_record.pk).update(created_at=recent_date)

        # 直接测试 delete_old_records，间隔 90 天精确
        # cutoff = today - 90days → 91 天前的被删，89 天前的保留
        cutoff = today.date() - timedelta(days=90)
        delete_old_records(cutoff)

        # 91 天前的应该被删除
        assert not APIUsage.objects.filter(pk=old_record.pk).exists()
        # 89 天前的应该保留
        assert APIUsage.objects.filter(pk=recent_record.pk).exists()
```

- [ ] **Step 2: 运行测试 — 预期 FAIL（`cleanup_usage_task` 尚未实现）**

```bash
cd backend; python -m pytest web/tests/test_usage_cleanup.py -v
```

Expected: `ModuleNotFoundError: No module named 'web.tasks.cleanup_usage'`

- [ ] **Step 3: Commit**

```bash
git add backend/web/tests/test_usage_cleanup.py
git commit -m "test: P1-A3 聚合 + 清理测试（6 个用例，预期失败）"
```

---

### Task 4: 实现 `cleanup_usage_task`

**Files:**
- Create: `backend/web/tasks/cleanup_usage.py`

- [ ] **Step 1: 创建任务文件**

```python
"""Celery 定时任务 — 聚合前一天 APIUsage → APIUsageDaily 并删除过期记录"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Sum
from django.utils import timezone

from backend.celery import app
from web.models.usage import APIUsage, APIUsageDaily

logger = logging.getLogger(__name__)


@app.task
def cleanup_usage_task():
    """聚合昨天的 APIUsage → APIUsageDaily，删除 90 天前的原始记录。

    Celery Beat 每天凌晨 2:00 调度。幂等 — 聚合使用 ignore_conflicts=True。
    """
    today = timezone.localdate()

    # 1. 聚合昨天
    yesterday = today - timedelta(days=1)
    aggregate_usage(yesterday)

    # 2. 删除过期明细
    cutoff = today - timedelta(days=settings.API_USAGE_RETENTION_DAYS)
    delete_old_records(cutoff)


def aggregate_usage(date):
    """聚合指定日期的 APIUsage → APIUsageDaily（幂等）。

    按 (user, api_type) 分组，使用 bulk_create(ignore_conflicts=True)
    基于 UniqueConstraint 保证重复运行不报错、不重复插入。
    """
    rows = (
        APIUsage.objects
        .filter(created_at__date=date)
        .values('user', 'api_type')
        .annotate(
            total_tokens=Sum('token_count'),
            call_count=Count('id'),
            total_duration_ms=Sum('duration_ms'),
        )
    )

    if not rows:
        logger.info('cleanup_usage: 日期 %s 无 APIUsage 记录，跳过聚合', date)
        return

    batch = [
        APIUsageDaily(
            date=date,
            user_id=r['user'],
            api_type=r['api_type'],
            total_tokens=r['total_tokens'],
            call_count=r['call_count'],
            total_duration_ms=r['total_duration_ms'],
        )
        for r in rows
    ]

    APIUsageDaily.objects.bulk_create(batch, ignore_conflicts=True)
    logger.info(
        'cleanup_usage: 日期 %s 聚合完成，%d 行写入 APIUsageDaily',
        date, len(batch),
    )


def delete_old_records(cutoff):
    """删除 created_at__date < cutoff 的 APIUsage 原始记录。"""
    deleted, _ = (
        APIUsage.objects
        .filter(created_at__date__lt=cutoff)
        .delete()
    )
    # Django delete() 返回 (total_deleted, per_model_counts)
    count = deleted
    if count > 0:
        logger.info(
            'cleanup_usage: 删除 %d 条 %s 之前的 APIUsage 记录',
            count, cutoff,
        )
    else:
        logger.info('cleanup_usage: 无 %s 之前的过期记录', cutoff)
```

- [ ] **Step 2: 在 `__init__.py` 中注册 `cleanup_usage_task`**

在 `web/tasks/__init__.py` 末尾追加：

```python
from web.tasks.cleanup_usage import cleanup_usage_task  # noqa: F401
```

- [ ] **Step 3: 运行测试 — 预期全部 PASS**

```bash
cd backend; python -m pytest web/tests/test_usage_cleanup.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/web/tasks/cleanup_usage.py backend/web/tasks/__init__.py
git commit -m "feat: cleanup_usage_task — 聚合 APIUsageDaily + 删除 90 天前记录"
```

---

### Task 5: 配置 `settings.py`

**Files:**
- Modify: `backend/backend/settings.py`

- [ ] **Step 1: 在配额配置区域（`QUOTA_EMBEDDING_TOKENS_PER_DAY` 下方）添加保留天数**

找到 `QUOTA_EMBEDDING_TOKENS_PER_DAY = 500_000` 行，在其后添加：

```python
# APIUsage 原始记录保留天数（超过后自动删除，汇总数据永久保留在 APIUsageDaily）
API_USAGE_RETENTION_DAYS = 90
```

- [ ] **Step 2: 在 Celery 配置区域末尾添加 Beat 调度**

找到 `CELERY_TASK_TIME_LIMIT = 180` 行，在其后添加：

```python
# Celery Beat 定时任务调度
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'cleanup-usage-daily': {
        'task': 'web.tasks.cleanup_usage.cleanup_usage_task',
        'schedule': crontab(hour=2, minute=0),
    },
}
```

- [ ] **Step 3: 验证 Django 配置正常**

```bash
cd backend; python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Commit**

```bash
git add backend/backend/settings.py
git commit -m "feat: API_USAGE_RETENTION_DAYS + Celery Beat 调度 cleanup_usage_task"
```

---

### Task 6: 验证全部测试通过

- [ ] **Step 1: 运行全部测试**

```bash
cd backend; python -m pytest web/tests/ -v
```

Expected: 182 个测试全部通过（176 原有 + 6 新增）

- [ ] **Step 2: Commit（如有遗漏的迁移或其他文件）**

```bash
git add -A
git commit -m "chore: 最终验证 — 182 测试通过"  # 或无变更则跳过
```

---

## Self-Review 结果

1. **Spec coverage:** 每条 spec 需求都有对应任务：
   - APIUsageDaily 模型 → Task 2
   - Celery 任务 → Task 4
   - Beat 调度 → Task 5
   - 测试 6 项 → Task 3（每项一个 test 方法）
   - 配置项 → Task 5
   - tasks.py → tasks/ 包 → Task 1
   - models/__init__.py → Task 2 Step 2

2. **Placeholder scan:** 无 TBD/TODO/placeholder。所有代码完整。

3. **Type consistency:** `cleanup_usage_task` 函数名在 beat schedule、import、测试中一致。`APIUsageDaily` 模型类名在 migration、import、测试中一致。
