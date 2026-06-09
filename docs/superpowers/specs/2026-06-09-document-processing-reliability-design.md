# Phase 2.5: 文档处理可靠性增强 — 设计文档

> **Date:** 2026-06-09 | **Phase:** 2.5 | **Priority:** P1
> **基于:** roadmap §Phase 2, 项目Review报告(2026-05-31)

## 1. 问题

两个可靠性漏洞：

1. **上传时 Celery 任务投递失败 → doc 永久 pending**  
   `upload.py:95` 中 `process_document_task.delay(doc.id)` 未捕获异常。broker 不可达时异常直接抛出，`UserDocument.status` 停留在 `pending`，用户文档列表永远显示"处理中"。

2. **删除文档时未撤销正在处理的 Celery 任务**  
   `remove.py` 直接 `doc.delete()`，未检查是否有 Celery 任务在队列中或正在执行。虽然 `tasks.py` 已处理 `UserDocument.DoesNotExist`（doc 被删后 task 静默跳过），但 task 可能正处于 embedding API 调用阶段，浪费 API 调用和等待时间。

## 2. 设计目标

- 任务投递失败时 doc 标记 `failed`，不永久 pending
- 删除 `pending`/`processing` 文档时撤销对应的 Celery 任务
- task 执行完毕后清理任务追踪信息
- 撤销失败不影响文档删除

## 3. 设计决策

### 3.1 任务 ID 存储方式：模型字段

**选：`UserDocument.celery_task_id` 字段。  
不选：确定性 task ID（`f'process_doc_{doc.id}'`）。**

| 维度 | 模型字段（选） | 确定性 ID（不选） |
|------|--------------|-----------------|
| Migration | 需要一条 migration | 无需 |
| 侵入性 | 模型 + 3 个文件 | 2 个文件 |
| Celery 兼容性 | 标准用法，UUID 全局唯一 | 自定义命名，非标准 |
| 语义 | 空值 = 无待处理任务，清晰 | 无法区分"未投递"与"已撤销" |
| 扩展性 | 可扩展 task_status、retries 等 | 无载体 |
| 重试场景 | UUID 不变，重试仍可 revoke | 命名不变，重试仍可 revoke |

选择理由：

- 标准的 Celery 用法，不侵入 task_id 生成逻辑
- `celery_task_id` 为空即"无待处理任务"，语义明确
- 未来如需扩展（例如记录 retry 次数），有字段载体
- 一条 migration 的成本很低（约 10 秒），换来的扩展性值得

### 3.2 撤销策略：软撤销

**选：`app.control.revoke(task_id)`。  
不选：`app.control.revoke(task_id, terminate=True)` 硬撤销。**

| | 软撤销 `revoke()` | 硬撤销 `revoke(terminate=True)` |
|---|---|---|
| 阻止队列中的 task | ✅ | ✅ |
| 终止正在执行的 task | ❌ | ✅ |
| 副作用 | 无 | SIGTERM 杀进程，finally 不保证执行 |
| 跨 worker | 全部 worker 生效 | 仅当前 worker 进程 |
| 前提条件 | 无 | 需 `--pool=solo` 或 `prefork` |

选择理由：

1. **竞态窗口极小**：上传 → 删除通常间隔数秒，task 大概率还在 Redis 队列中
2. **硬撤销有副作用**：SIGTERM 粗暴终止可能打断 embedding API 调用，不符合 graceful degradation 原则
3. **task 自身有防御**：`tasks.py` 已处理 `UserDocument.DoesNotExist`（L66-68），task 发现 doc 被删后静默返回。最坏情况只是浪费一次 API 调用，不产生脏数据
4. **KISS**：无额外依赖，行为可预期

## 4. 实现方案

### 4.1 模型变更

`UserDocument` 新增字段：

```python
celery_task_id = models.CharField(max_length=255, blank=True, default='',
                                  help_text='Celery task ID for revocation')
```

需生成一条 migration。

### 4.2 `web/views/document/upload.py`

`delay()` 调用包裹 try/except：

```python
try:
    task = process_document_task.delay(doc.id)
    doc.celery_task_id = task.id
    doc.save(update_fields=['celery_task_id'])
except Exception as e:
    logger.exception('Celery 任务投递失败, doc_id=%d', doc.id)
    doc.status = 'failed'
    doc.error_message = f'任务投递失败: {str(e)[:500]}'
    doc.save(update_fields=['status', 'error_message'])
    return Response(
        {'message': '文件已上传但异步处理启动失败，请稍后重试'},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
```

关键点：
- `save(update_fields=[...])` 精确控制字段，避免覆盖其他字段
- `celery_task_id` 在投递成功后立即保存，不等 task 执行
- 失败返回 500，向用户说明"上传成功但处理未启动"

### 4.3 `web/views/document/remove.py`

`doc.delete()` 之前插入撤销逻辑：

```python
# 撤销正在排队的 Celery 任务
if doc.celery_task_id and doc.status in ('pending', 'processing'):
    try:
        app.control.revoke(doc.celery_task_id)
        logger.info('已撤销 Celery 任务, doc_id=%d, task_id=%s',
                    doc.id, doc.celery_task_id)
    except Exception:
        logger.warning('撤销 Celery 任务失败, doc_id=%d, task_id=%s',
                       doc.id, doc.celery_task_id, exc_info=True)
```

关键点：
- 仅撤销 `pending`/`processing` 状态的文档（`completed`/`failed` 无在跑任务）
- `revoke()` 本身异常不阻断删除流程（try/except + warning 日志）
- 撤销在 `doc.delete()` 之前执行

### 4.4 `web/views/document/tasks.py`

任务成功和**永久失败**时清空 `celery_task_id`。**可重试失败保留 task_id**——重试期间用户仍可撤销。

```python
# 成功路径（L61 附近）
doc.status = 'completed'
doc.chunks_count = len(objs)
doc.celery_task_id = ''
doc.save(update_fields=['status', 'chunks_count', 'celery_task_id'])

# 失败路径（L73 附近）— 只在确定不重试时清空 task_id
doc.status = 'failed'
doc.error_message = str(exc)[:500]
doc.save(update_fields=['status', 'error_message'])
# 注意：此时不更新 celery_task_id！

# 然后走现有重试决策：
if isinstance(exc, APIStatusError) and \
       400 <= exc.status_code < 500 and exc.status_code != 429:
    doc.celery_task_id = ''                          # ← 新增：永久故障才清空
    doc.save(update_fields=['celery_task_id'])
    return                                           # 不重试
raise process_document_task.retry(exc=exc, countdown=10)  # 重试，task_id 保留
```

为什么这么设计：

| 分支 | celery_task_id | 理由 |
|------|---------------|------|
| 成功 | 清空 | task 已终止，task_id 失效 |
| 4xx 永久故障（非 429） | 清空 | task 已终止，task_id 失效 |
| 5xx / 429 / 网络超时 → retry | **保留** | 重试期间（最长 10s × 2 次），用户仍可 revoke |

关键点：
- 重试期间不清空 task_id，确保删除文档时仍可撤销
- `DoesNotExist` 分支（doc 已被删除）不需要清空——doc 已经不存在了
- 软撤销在重试场景下的有效性取决于 Celery 是否复用原 task_id；即使不生效，`DoesNotExist` 兜底确保无脏数据（§3.2 已接受的 trade-off）

## 5. 边界情况

| 场景 | 行为 |
|------|------|
| Broker 不通，`delay()` 抛异常 | doc → `failed`，返回 500，message 说明处理未启动 |
| 用户上传后立刻删除 | revoke 拦截队列中的 task；万一 task 已在跑，`DoesNotExist` 兜底静默跳过 |
| `revoke()` 本身抛异常 | 不阻断删除，记录 warning 日志 |
| task 已执行完（`completed`/`failed`）后用户删除 | state check 拦住，不尝试 revoke |
| task 重试中用户删除 | 软撤销阻止重试，task 不再 pick up |
| 系统文档（owner=null）被 `insert_documents.py` 导入 | 不经过 upload.py，不设 celery_task_id，删除时跳过 revoke |

## 6. 测试用例

| # | 测试名 | 场景 | 验证点 |
|---|--------|------|--------|
| 1 | `test_upload_enqueue_failure` | mock `delay()` 抛异常 | status=`failed`，error_message 非空，返回 500 |
| 2 | `test_upload_saves_celery_task_id` | 正常上传 | `celery_task_id` 非空 |
| 3 | `test_delete_pending_doc_revokes_task` | 删除 pending 文档 | `revoke` 被调用，doc + chunks 删除 |
| 4 | `test_delete_processing_doc_revokes_task` | 删除 processing 文档 | `revoke` 被调用 |
| 5 | `test_delete_completed_doc_skips_revoke` | 删除 completed 文档 | `revoke` **不**被调用 |
| 6 | `test_task_clears_celery_task_id_on_completion` | task 执行成功 | `celery_task_id` = '' |
| 7 | `test_task_clears_celery_task_id_on_permanent_failure` | task 永久失败（4xx） | `celery_task_id` = ''，不重试 |
| 8 | `test_task_keeps_celery_task_id_on_retryable_failure` | task 可重试失败（5xx） | `celery_task_id` 保留非空，task 已被 retry |
| 9 | `test_delete_during_retry_revokes_task` | task 失败重试中用户删除 | `revoke` 被调用，doc 删除 |
| 10 | `test_revoke_failure_does_not_block_delete` | mock `revoke()` 抛异常 | doc 仍然被删除，返回 200 |

测试沿用现有 mock 模式：`@patch("web.views.document.upload.process_document_task.delay")` 和 `@patch("web.views.document.remove.app.control.revoke")`。

## 7. 影响范围

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `web/models/document.py` | 修改 | 新增 `celery_task_id` 字段 |
| `web/migrations/XXXX_add_celery_task_id.py` | 新增 | migration |
| `web/views/document/upload.py` | 修改 | `delay()` try/except + 保存 task_id |
| `web/views/document/remove.py` | 修改 | 新增 `from backend.celery import app`；`revoke()` before `doc.delete()` |
| `web/views/document/tasks.py` | 修改 | 成功/永久失败时清空 task_id；可重试失败保留 |
| `web/tests/test_document.py` | 修改 | 新增 6 个测试（#1-#5, #10） |
| `web/tests/test_document_processing.py` | 修改 | 新增 4 个测试（#6-#9） |

---

*Design Date: 2026-06-09*
*Based on: 项目Review报告(Claude).md + 项目Review报告(Codex-2026-05-31).md + roadmap Phase 2*
