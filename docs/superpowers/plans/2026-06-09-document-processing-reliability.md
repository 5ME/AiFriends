# Phase 2.5: 文档处理可靠性增强 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复文档处理两个可靠性漏洞 — Celery 任务投递失败时标记 failed（非永久 pending），删除文档时撤销正在处理的 Celery 任务。

**Architecture:** `UserDocument` 新增 `celery_task_id` 字段存储任务 ID；`upload.py` 捕获 `delay()` 异常；`remove.py` 在 `delete()` 前调用 `app.control.revoke()`；`tasks.py` 只在永久失败时清空 task_id，可重试失败保留以支持撤销。

**Tech Stack:** Django ORM, Celery, pytest + unittest.mock

**Design doc:** `docs/superpowers/specs/2026-06-09-document-processing-reliability-design.md`

---

### File Structure

| 文件 | 职责 |
|------|------|
| `web/models/document.py:18-20` | 新增 `celery_task_id` CharField |
| `web/migrations/XXXX_*.py` | Auto-generated migration |
| `web/views/document/upload.py:88-101` | `delay()` try/except + 保存 task_id |
| `web/views/document/remove.py:1-4,31-38` | 新增 import `app`；`revoke()` before `doc.delete()` |
| `web/views/document/tasks.py:21,60-82` | 成功/永久失败清空 task_id；可重试失败保留 |
| `web/tests/test_document.py` | 新增 6 个测试（upload enqueue failure + remove revoke） |
| `web/tests/test_document_processing.py` | 新增 4 个测试（task 完成/失败后的 task_id 状态） |

---

### Task 1: 模型新增 `celery_task_id` + Migration

**Files:**
- Modify: `web/models/document.py:18-20`
- Create: Migration (auto)

- [ ] **Step 1: 添加字段到 UserDocument**

在 `chunks_count` 之后插入：

```python
    celery_task_id = models.CharField(max_length=255, blank=True, default='',
                                      help_text='Celery task ID for revocation')
```

用 Edit 工具，`old_string`:
```
    error_message = models.TextField(blank=True, default='')
    chunks_count = models.IntegerField(default=0)
```
`new_string`:
```
    error_message = models.TextField(blank=True, default='')
    chunks_count = models.IntegerField(default=0)
    celery_task_id = models.CharField(max_length=255, blank=True, default='',
                                      help_text='Celery task ID for revocation')
```

- [ ] **Step 2: 生成 migration**

Run:
```bash
cd backend && D:\MyWork\Miniconda3\envs\py312\python.exe manage.py makemigrations web --name add_celery_task_id
```
Expected: `web/migrations/XXXX_add_celery_task_id.py` created.

- [ ] **Step 3: 应用 migration + 验证模型**

Run:
```bash
cd backend && D:\MyWork\Miniconda3\envs\py312\python.exe manage.py migrate
```
Expected: "Applying web.XXXX_add_celery_task_id... OK"

Quick smoke check:
```bash
cd backend && D:\MyWork\Miniconda3\envs\py312\python.exe -c "from web.models.document import UserDocument; print('celery_task_id' in [f.name for f in UserDocument._meta.get_fields()])"
```
Expected: `True`

- [ ] **Step 4: Commit**

```bash
git add backend/web/models/document.py backend/web/migrations/*add_celery_task_id*.py
git commit -m "feat: UserDocument 新增 celery_task_id 字段，用于 Celery 任务撤销追踪"
```

---

### Task 2: `upload.py` — delay() 异常捕获 + 保存 task_id

**Files:**
- Modify: `web/views/document/upload.py:88-101`

- [ ] **Step 1: 替换 delay() 调用块**

当前代码（L88-101）：
```python
        doc = UserDocument.objects.create(
            owner=request.user.userprofile,
            title=sanitize_title(file.name),
            file_url=save_to_media(file, ext),
            file_type=ext,
            status='pending',
        )
        process_document_task.delay(doc.id)

        logger.info('文档上传成功, doc_id=%d, title=%s', doc.id, doc.title)
        return Response(
            {'id': doc.id, 'title': doc.title, 'status': doc.status},
            status=status.HTTP_201_CREATED,
        )
```

替换为：
```python
        doc = UserDocument.objects.create(
            owner=request.user.userprofile,
            title=sanitize_title(file.name),
            file_url=save_to_media(file, ext),
            file_type=ext,
            status='pending',
        )

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

        logger.info('文档上传成功, doc_id=%d, title=%s', doc.id, doc.title)
        return Response(
            {'id': doc.id, 'title': doc.title, 'status': doc.status},
            status=status.HTTP_201_CREATED,
        )
```

- [ ] **Step 2: Commit**

```bash
git add backend/web/views/document/upload.py
git commit -m "feat: upload delay() 异常捕获 — 投递失败标记 failed 而非永久 pending"
```

---

### Task 3: `remove.py` — 删除前撤销 Celery 任务

**Files:**
- Modify: `web/views/document/remove.py:1-4,31-38`

- [ ] **Step 1: 添加 import**

在 `from web.models.document import UserDocument` 之后插入：
```python
from backend.celery import app
```

- [ ] **Step 2: doc.delete() 之前插入 revoke 逻辑**

当前（L31-38）：
```python
        # 删除 media 文件
        if doc.file_url:
            file_path = os.path.join(settings.MEDIA_ROOT, doc.file_url)
            if os.path.exists(file_path):
                os.remove(file_path)

        # 级联删除 DocumentChunks（Django CASCADE）
        doc.delete()
```

替换为：
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

        # 删除 media 文件
        if doc.file_url:
            file_path = os.path.join(settings.MEDIA_ROOT, doc.file_url)
            if os.path.exists(file_path):
                os.remove(file_path)

        # 级联删除 DocumentChunks（Django CASCADE）
        doc.delete()
```

- [ ] **Step 3: Commit**

```bash
git add backend/web/views/document/remove.py
git commit -m "feat: 删除文档时撤销正在处理的 Celery 任务（软撤销）"
```

---

### Task 4: `tasks.py` — 成功/永久失败清空 task_id，可重试失败保留

**Files:**
- Modify: `web/views/document/tasks.py:21,60-82`

- [ ] **Step 1: 成功路径 — 清空 celery_task_id**

当前（L60-63）：
```python
        doc.status = 'completed'
        doc.chunks_count = len(objs)
        doc.save()
```

替换为：
```python
        doc.status = 'completed'
        doc.chunks_count = len(objs)
        doc.celery_task_id = ''
        doc.save(update_fields=['status', 'chunks_count', 'celery_task_id'])
```

- [ ] **Step 2: 失败路径 — 永久故障清空，可重试保留**

当前（L69-82）：
```python
    except Exception as exc:
        logger.exception('文档处理失败, doc_id=%d', doc_id)
        # 尝试更新状态为 failed
        try:
            doc.status = 'failed'
            doc.error_message = str(exc)[:500]
            doc.save()
        except Exception:
            pass
        # 4xx 永久故障不重试（429 除外），其余重试一次
        if isinstance(exc, APIStatusError) and \
               400 <= exc.status_code < 500 and exc.status_code != 429:
            return
        raise process_document_task.retry(exc=exc, countdown=10)
```

替换为：
```python
    except Exception as exc:
        logger.exception('文档处理失败, doc_id=%d', doc_id)
        # 尝试更新状态为 failed（不更新 celery_task_id）
        try:
            doc.status = 'failed'
            doc.error_message = str(exc)[:500]
            doc.save(update_fields=['status', 'error_message'])
        except Exception:
            pass
        # 4xx 永久故障不重试（429 除外），清空 task_id
        # 其余重试一次，保留 task_id 以支持重试期间撤销
        if isinstance(exc, APIStatusError) and \
               400 <= exc.status_code < 500 and exc.status_code != 429:
            try:
                doc.celery_task_id = ''
                doc.save(update_fields=['celery_task_id'])
            except Exception:
                pass
            return
        raise process_document_task.retry(exc=exc, countdown=10)
```

- [ ] **Step 3: Commit**

```bash
git add backend/web/views/document/tasks.py
git commit -m "feat: task 成功/永久故障时清空 celery_task_id，可重试失败保留以支持撤销"
```

---

### Task 5: 测试 — upload + remove 视图 (test_document.py)

**Files:**
- Modify: `web/tests/test_document.py`

- [ ] **Step 1: 新增测试 #1 — enqueue 失败标记 failed**

在 `TestDocumentUpload` 类末尾（L240 之后）新增：

```python
    @patch("web.views.document.upload.process_document_task.delay")
    def test_upload_enqueue_failure(self, mock_delay, auth_client):
        """delay() 抛异常 → doc 标记 failed，返回 500"""
        mock_delay.side_effect = Exception("Broker connection error")
        file = SimpleUploadedFile('test.txt', b'Hello', content_type='text/plain')
        resp = auth_client.post('/api/document/upload/', {'file': file})
        assert resp.status_code == 500
        assert '处理启动失败' in resp.data['message']
        doc = UserDocument.objects.latest('id')
        assert doc.status == 'failed'
        assert '任务投递失败' in doc.error_message
```

- [ ] **Step 2: 新增测试 #2 — 正常上传保存 celery_task_id**

在 `TestDocumentUpload` 类末尾新增：

```python
    @patch("web.views.document.upload.process_document_task.delay")
    def test_upload_saves_celery_task_id(self, mock_delay, auth_client):
        """正常上传 → celery_task_id 非空"""
        mock_result = MagicMock()
        mock_result.id = 'test-task-uuid-123'
        mock_delay.return_value = mock_result
        file = SimpleUploadedFile('hello.txt', b'Hello World',
                                  content_type='text/plain')
        resp = auth_client.post('/api/document/upload/', {'file': file})
        assert resp.status_code == 201
        doc = UserDocument.objects.get(id=resp.data['id'])
        assert doc.celery_task_id == 'test-task-uuid-123'
```

- [ ] **Step 3: 新增测试 #3 — 删除 pending 文档 revoke 被调用**

在 `TestDocumentRemove` 类末尾（L274 之后）新增：

```python
    @patch("web.views.document.remove.app.control.revoke")
    def test_delete_pending_doc_revokes_task(self, mock_revoke, auth_client,
                                              user_profile):
        """删除 pending 文档 → revoke 被调用"""
        doc = UserDocument.objects.create(
            title='pending-doc', owner=user_profile, status='pending',
            celery_task_id='task-pending-123',
        )
        resp = auth_client.post('/api/document/remove/', {'id': doc.id})
        assert resp.status_code == 200
        mock_revoke.assert_called_once_with('task-pending-123')
        assert not UserDocument.objects.filter(id=doc.id).exists()
```

- [ ] **Step 4: 新增测试 #4 — 删除 processing 文档 revoke 被调用**

```python
    @patch("web.views.document.remove.app.control.revoke")
    def test_delete_processing_doc_revokes_task(self, mock_revoke, auth_client,
                                                 user_profile):
        """删除 processing 文档 → revoke 被调用"""
        doc = UserDocument.objects.create(
            title='processing-doc', owner=user_profile, status='processing',
            celery_task_id='task-processing-456',
        )
        resp = auth_client.post('/api/document/remove/', {'id': doc.id})
        assert resp.status_code == 200
        mock_revoke.assert_called_once_with('task-processing-456')
        assert not UserDocument.objects.filter(id=doc.id).exists()
```

- [ ] **Step 5: 新增测试 #5 — 删除 completed 文档跳过 revoke**

```python
    @patch("web.views.document.remove.app.control.revoke")
    def test_delete_completed_doc_skips_revoke(self, mock_revoke, auth_client,
                                                user_profile):
        """删除 completed 文档 → revoke 不调用"""
        doc = UserDocument.objects.create(
            title='completed-doc', owner=user_profile, status='completed',
            celery_task_id='task-completed-789',
        )
        resp = auth_client.post('/api/document/remove/', {'id': doc.id})
        assert resp.status_code == 200
        mock_revoke.assert_not_called()
        assert not UserDocument.objects.filter(id=doc.id).exists()
```

- [ ] **Step 6: 新增测试 #9 — 重试中删除文档 revoke 被调用**

```python
    @patch("web.views.document.remove.app.control.revoke")
    def test_delete_during_retry_revokes_task(self, mock_revoke, auth_client,
                                               user_profile):
        """task 失败重试中用户删除 → revoke 被调用"""
        doc = UserDocument.objects.create(
            title='retrying-doc', owner=user_profile, status='processing',
            celery_task_id='task-retrying-123',
        )
        resp = auth_client.post('/api/document/remove/', {'id': doc.id})
        assert resp.status_code == 200
        mock_revoke.assert_called_once_with('task-retrying-123')
        assert not UserDocument.objects.filter(id=doc.id).exists()
```

- [ ] **Step 7: 新增测试 #10 — revoke 失败不阻断删除**

```python
    @patch("web.views.document.remove.app.control.revoke")
    def test_revoke_failure_does_not_block_delete(self, mock_revoke, auth_client,
                                                   user_profile):
        """revoke 抛异常 → 删除仍成功"""
        mock_revoke.side_effect = Exception("Revoke failed")
        doc = UserDocument.objects.create(
            title='revoke-fail-doc', owner=user_profile, status='pending',
            celery_task_id='task-revoke-fail',
        )
        resp = auth_client.post('/api/document/remove/', {'id': doc.id})
        assert resp.status_code == 200
        assert not UserDocument.objects.filter(id=doc.id).exists()
```

- [ ] **Step 8: 更新已存在的 test_upload_txt_success — 适配 mock delay 返回值**

当前 `upload.py` 会访问 `task.id`，需要在 mock 上设置 `return_value.id`。

用 Edit 工具：
`old_string`:
```
    @patch("web.views.document.upload.process_document_task.delay")
    def test_upload_txt_success(self, mock_delay, auth_client, user_profile):
        """正常上传 .txt"""
        file = SimpleUploadedFile('hello.txt', b'Hello World',
                                  content_type='text/plain')
```
`new_string`:
```
    @patch("web.views.document.upload.process_document_task.delay")
    def test_upload_txt_success(self, mock_delay, auth_client, user_profile):
        """正常上传 .txt"""
        mock_delay.return_value.id = 'test-task-id'
        file = SimpleUploadedFile('hello.txt', b'Hello World',
                                  content_type='text/plain')
```

- [ ] **Step 9: 运行新增测试验证通过**

```bash
cd backend && D:\MyWork\Miniconda3\envs\py312\python.exe -m pytest web/tests/test_document.py -v
```
Expected: All test_document.py tests pass (existing + 8 new).

- [ ] **Step 10: Commit**

```bash
git add backend/web/tests/test_document.py
git commit -m "test: 文档上传 enqueue 失败 + 删除撤销 7 个测试用例"
```

---

### Task 6: 测试 — task 处理中的 celery_task_id 状态 (test_document_processing.py)

**Files:**
- Modify: `web/tests/test_document_processing.py`

- [ ] **Step 1: 新增测试 #6 — task 成功后清空 celery_task_id**

在 `TestDocumentProcessing` 类中新增独立测试（不扩展现有 `test_process_txt_document`，确保因变量独立）：

```python
    @patch("web.views.document.tasks.CustomEmbeddings")
    def test_task_clears_celery_task_id_on_completion(
            self, mock_embeddings, user_profile):
        """task 执行成功 → celery_task_id 清空"""
        emb_mock = MagicMock()
        emb_mock.embed_documents.return_value = [[0.1] * 1024, [0.2] * 1024]
        mock_embeddings.return_value = emb_mock

        from web.views.document.tasks import process_document_task
        doc = _dummy_upload(user_profile, 'test.txt')
        # 模拟上传时已设置 task_id
        doc.celery_task_id = 'task-before-complete'
        doc.save(update_fields=['celery_task_id'])

        process_document_task(doc.id)

        doc.refresh_from_db()
        assert doc.status == 'completed'
        assert doc.celery_task_id == ''
```

关键：先设 `celery_task_id = 'task-before-complete'`，再验证 task 执行后清空为 `''`。不依赖默认值 `''`，避免 trivial pass。

- [ ] **Step 2: 新增测试 #7 — task 永久失败（4xx）清空 celery_task_id**

在 `TestDocumentProcessing` 类末尾（L137 之后）新增：

```python
    @patch("web.views.document.tasks.CustomEmbeddings")
    def test_task_clears_celery_task_id_on_permanent_failure(
            self, mock_embeddings, user_profile):
        """4xx API 错误 → celery_task_id 清空，不重试"""
        from openai import APIStatusError
        response_mock = MagicMock()
        response_mock.status_code = 400
        emb_mock = MagicMock()
        emb_mock.embed_documents.side_effect = APIStatusError(
            'Bad request', response=response_mock, body=None
        )
        mock_embeddings.return_value = emb_mock

        from web.views.document.tasks import process_document_task
        doc = _dummy_upload(user_profile, 'test.txt')
        doc.celery_task_id = 'task-permanent-fail'
        doc.save(update_fields=['celery_task_id'])

        process_document_task(doc.id)

        doc.refresh_from_db()
        assert doc.status == 'failed'
        assert doc.celery_task_id == ''
```

- [ ] **Step 3: 新增测试 #8 — task 可重试失败（5xx）保留 celery_task_id**

```python
    @patch("web.views.document.tasks.process_document_task.retry")
    @patch("web.views.document.tasks.CustomEmbeddings")
    def test_task_keeps_celery_task_id_on_retryable_failure(
            self, mock_embeddings, mock_retry, user_profile):
        """5xx / 网络异常 → celery_task_id 保留，task 被 retry"""
        emb_mock = MagicMock()
        emb_mock.embed_documents.side_effect = Exception("Network timeout")
        mock_embeddings.return_value = emb_mock

        from web.views.document.tasks import process_document_task
        doc = _dummy_upload(user_profile, 'test.txt')
        doc.celery_task_id = 'task-retryable'
        doc.save(update_fields=['celery_task_id'])

        process_document_task(doc.id)

        doc.refresh_from_db()
        assert doc.status == 'failed'
        assert doc.celery_task_id == 'task-retryable'
        mock_retry.assert_called_once()
```

- [ ] **Step 4: 运行新增测试验证通过**

```bash
cd backend && D:\MyWork\Miniconda3\envs\py312\python.exe -m pytest web/tests/test_document_processing.py::TestDocumentProcessing::test_task_clears_celery_task_id_on_completion web/tests/test_document_processing.py::TestDocumentProcessing::test_task_clears_celery_task_id_on_permanent_failure web/tests/test_document_processing.py::TestDocumentProcessing::test_task_keeps_celery_task_id_on_retryable_failure -v
```
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/web/tests/test_document_processing.py
git commit -m "test: task celery_task_id 状态 3 个测试用例"
```

---

### Task 7: 全量测试验证 + 最终 Commit

- [ ] **Step 1: 运行全量测试**

```bash
cd backend && D:\MyWork\Miniconda3\envs\py312\python.exe -m pytest web/tests/ -v
```
Expected: All tests pass（全量通过，3 deselected）。

- [ ] **Step 2: 运行 document 专项测试确认**

```bash
cd backend && D:\MyWork\Miniconda3\envs\py312\python.exe -m pytest web/tests/test_document.py web/tests/test_document_processing.py -v
```
Expected: All document tests pass (existing + new).

- [ ] **Step 3: 最终 Commit（如有遗漏文件）**

```bash
git status
# 如有未提交变更:
git add -A
git commit -m "chore: Phase 2.5 文档处理可靠性增强 — 最终整理"
```

---

*Plan Date: 2026-06-09*
*Based on: docs/superpowers/specs/2026-06-09-document-processing-reliability-design.md*
