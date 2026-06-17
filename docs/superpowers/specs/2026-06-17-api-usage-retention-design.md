# P1-A3: APIUsage 数据保留策略 — 设计文档

> 日期：2026-06-17  
> 来源：`docs/superpowers/specs/2026-06-11-next-steps-roadmap.md` P1-A3  
> 状态：待实施

---

## 一、问题陈述

### 1.1 当前状态

`APIUsage` 表记录每次 AI API 调用的原始明细（每条一行），数据无限增长：

```
记录粒度: 每次调用 → 每天 N 条（用户 × 消息 × API 类型）
增长估算: 假设 DAU 10 人，每人 20 条消息，每条产生 1 llm + 1 tts → 400 条/天 ≈ 15 万条/年
```

模型 TODO 注释已标记清理需求：
```python
# TODO: 数据积累 3-6 个月后评估清理策略
```

### 1.2 目标

1. **汇总保留**：按天聚合原始明细，长期保留成本数据
2. **明细清理**：90 天后自动删除原始 `APIUsage` 记录，控制存储增长
3. **自动化**：Celery Beat 每天定时执行，无需人工干预

---

## 二、方案选择

### 2.1 汇总 + 删除的关系

| | 方案 A：组合任务（✅ 选择） | 方案 B：两独立任务 | 方案 C：只删不聚合（❌ 拒绝） |
|---|---|---|---|
| **描述** | 一个任务先聚合后删除 | Beat 调度两个独立任务 | 直接删 90 天前数据 |
| **优点** | 简单，聚合先于删除有保障 | 各自故障隔离 | 实现最简单 |
| **缺点** | 任务失败时两者一起失败 | 需协调顺序，多一层配置 | 丢失历史汇总 |

**选择 A 的理由：** 任务本身逻辑简单（两个 SQL 操作），失败概率低；组合任务天然保证聚合先于删除。B 方案的"故障隔离"在这么简单的场景下过度设计。

### 2.2 调度方式

| | 方案 A：`celery beat` 静态配置（✅ 选择） | 方案 B：`django-celery-beat`（❌ 拒绝） |
|---|---|---|
| **描述** | `app.conf.beat_schedule` 字典配置 | 通过 Django Admin 动态管理定时任务 |
| **优点** | 零依赖，代码即配置，版本控制 | 可在 Admin 中修改调度，无需重启 |
| **缺点** | 修改调度需改代码 | 新增依赖 + 数据库迁移，大材小用 |

**选择 A 的理由：** 当前只有一个定时任务（且未来不会频繁增加），静态配置简单可靠。`django-celery-beat` 引入了额外的模型、迁移和管理复杂度，对于"每天凌晨跑一次"的场景是过度引入。

### 2.3 幂等策略

| | 方案 A：`ignore_conflicts=True`（✅ 选择） | 方案 B：`update_or_create`（❌ 拒绝） |
|---|---|---|
| **描述** | `bulk_create(..., ignore_conflicts=True)` | 逐行 update_or_create |
| **优点** | 批量操作，性能好；唯一约束保证幂等 | 重复运行会更新已有行 |
| **缺点** | 重复运行时静默跳过，不会更新旧值 | N+1 查询，逐行操作慢 |

**选择 A 的理由：** 每天的汇总数据是确定的（同一批原始数据聚合结果不变），不需要 update。`unique_together = (date, user, api_type)` 配合 `ignore_conflicts=True` 一次 SQL 搞定，高效且正确。

### 2.4 调度时间

**选择凌晨 2:00 而非 0:00：** 给跨天边缘的请求留 2 小时缓冲窗口，确保前一天所有 `APIUsage` 记录已落库（避免遗漏 23:55-23:59 的聊天产生的记录）。

---

## 三、核心设计

### 3.1 数据模型 — `APIUsageDaily`

```python
class APIUsageDaily(models.Model):
    """按天聚合的 API 用量摘要（永久保留）"""
    date = models.DateField()
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE,
                             null=True, blank=True)
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
```

**字段说明：**
- `UniqueConstraint(date, user, api_type)` — 一个用户一天每种 API 类型最多一行，也是幂等的保证。使用 `UniqueConstraint` 而非 `unique_together`（Django 4.2+ 弃用）
- `user` 允许 `null=True` — 系统知识库的 embedding 调用 `user=None`
- 复用 `APIUsage.API_TYPES` 常量，保持枚举一致
- **注：** ASR 类型的 `token_count` 实际存储 PCM16 样本数，因此 ASR 行的 `total_tokens` 字段语义为"总样本数"（非 token）。这是 `APIUsage` 的既有设计，P1-A3 不做改变

**与 `APIUsage` 的对应关系：**

```
APIUsage (90 天明细)              APIUsageDaily (永久汇总)
───────────────                   ─────────────────────
多条 llm 调用 ──→ 聚合 ──→       date=X, user=Y, api_type=llm
                                  total_tokens=Σ, call_count=Σ
多条 tts 调用 ──→ 聚合 ──→       date=X, user=Y, api_type=tts
                                  total_tokens=Σ, call_count=Σ
```

### 3.2 Celery 任务 — `cleanup_usage_task`

```
cleanup_usage_task()    每天 2:00 执行
  │
  ├─ 1. 聚合昨天
  │      yesterday = localdate() - 1day
  │      APIUsageDaily.aggregate_usage(yesterday)
  │      → filter(created_at__date=yesterday).values(user, api_type)
  │        .annotate(total=Sum, count=Count, duration=Sum)
  │      → bulk_create(ignore_conflicts=True)
  │
  └─ 2. 删除过期明细
         cutoff = localdate() - API_USAGE_RETENTION_DAYS
         → APIUsage.objects.filter(created_at__date__lt=cutoff).delete()
         （直接 inline 在 task 中，因为删除的是 APIUsage 而非 APIUsageDaily 数据）
```

**错误处理：**
- 聚合失败 → `logger.exception()` + return（跳过删除，保护数据）
- 删除失败 → `logger.exception()` 独立报错
- 全异常 catch，不向 Celery Beat 抛出（避免中断调度链）

### 3.3 Beat 调度配置

```python
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'cleanup-usage-daily': {
        'task': 'web.tasks.cleanup_usage.cleanup_usage_task',
        'schedule': crontab(hour=2, minute=0),
    },
}
```

### 3.4 配置项

```python
API_USAGE_RETENTION_DAYS = 90
```

单独一行，放在其他配额配置附近（`settings.py` 配额区域）。

---

## 四、数据生命周期

```
Day 0 (今天)     API 调用 → record_api_usage() → APIUsage (原始明细)
Day 1 (明天 2:00) cleanup_usage_task → 聚合 → APIUsageDaily (汇总)
Day 90            cleanup_usage_task → DELETE FROM APIUsage WHERE date < cutoff
```

---

## 五、测试计划

| # | 场景 | 验证点 |
|---|------|--------|
| 1 | 聚合正确性 | 同天同用户 3 llm + 2 tts → `APIUsageDaily` 各一行，sum/count 正确 |
| 2 | 幂等 | 同一天 `aggregate_usage()` 运行两次 → 不报错，数据不变 |
| 3 | 删除边界 | `retention_days=90` → 91 天前删，89 天前保留 |
| 4 | 空数据集 | `aggregate_usage()` 在无数据时不报错，返回 0 行 |
| 5 | 用户隔离 | 用户 A 和用户 B 的 usage 独立汇总到各自行 |
| 6 | 系统调用 | `user=None` 的 APIUsage 正常聚合（NULL 行） |

测试文件：`backend/web/tests/test_usage_cleanup.py`

---

## 六、实施清单

- [ ] 将 `web/tasks.py` 转为 `web/tasks/__init__.py`（为 `cleanup_usage.py` 腾出空间）
- [ ] 新增 `APIUsageDaily` 模型（`web/models/usage.py`）
- [ ] `web/models/__init__.py` 注册 `APIUsageDaily`（`from .usage import APIUsage, APIUsageDaily`）
- [ ] `makemigrations` 生成迁移
- [ ] `cleanup_usage_task` Celery 任务（`web/tasks/cleanup_usage.py`）
- [ ] `settings.py` 添加 `API_USAGE_RETENTION_DAYS` + `CELERY_BEAT_SCHEDULE`
- [ ] 测试 `backend/web/tests/test_usage_cleanup.py`（6 个用例）
- [ ] `python -m pytest web/tests/ -v` 全部通过（182 个）

---

## 七、运维说明

**启动 Celery Beat（单独进程）：**
```bash
celery -A backend beat --loglevel=info
```

Beat 进程负责按调度触发任务，Worker 进程负责执行。与 Worker 分开运行，两者独立。

**手动触发（补跑历史数据）：**
```bash
python manage.py shell -c "from web.tasks.cleanup_usage import cleanup_usage_task; cleanup_usage_task.delay()"
```

**检查调度状态：**
- Beat 进程日志会有 `Scheduler: Sending due task cleanup-usage-daily` 输出
- Worker 日志会有任务执行记录
