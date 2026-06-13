# Phase 2.4: Django Admin 注册 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** UserDocument + DocumentChunk 注册到 Django Admin，支持搜索/过滤/运维排查。

**Architecture:** 在现有 `web/admin.py` 中新增两个 `ModelAdmin` 子类，遵循已有 6 个 model 的注册模式（`@admin.register` 装饰器 + `raw_id_fields`）。

**Tech Stack:** Django Admin

**Design doc:** `docs/superpowers/specs/2026-06-09-django-admin-registration-design.md`

---

### File Structure

| 文件 | 职责 |
|------|------|
| `web/admin.py` | 新增 import + UserDocumentAdmin + DocumentChunkAdmin |
| `web/tests/test_admin.py` | 新增：Admin changelist 可访问 + search 生效 |

---

### Task 1: Admin 注册 + 测试

**Files:**
- Modify: `web/admin.py`
- Create: `web/tests/test_admin.py`

- [ ] **Step 1: 新增 import**

`web/admin.py` 第 2 行之后（`from django.contrib import admin` 之下）插入：

```python
from web.models.document import UserDocument, DocumentChunk
```

用 Edit 工具：
`old_string`:
```
from web.models.character import Character, Voice
```
`new_string`:
```
from web.models.document import UserDocument, DocumentChunk
from web.models.character import Character, Voice
```

- [ ] **Step 2: 新增 UserDocumentAdmin**

在文件末尾追加：

```python

@admin.register(UserDocument)
class UserDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'file_type', 'status',
                    'chunks_count', 'created_at')
    search_fields = ('title', 'owner__user__username')
    list_filter = ('status', 'file_type')
    readonly_fields = ('chunks_count', 'celery_task_id', 'created_at', 'updated_at')
    raw_id_fields = ('owner',)


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ('document', 'chunk_index', 'token_count', 'owner', 'created_at')
    search_fields = ('content', 'document__title')
    list_filter = ('document__file_type',)
    exclude = ('embedding',)
    list_select_related = ('document', 'owner')
    raw_id_fields = ('document', 'owner')
```

- [ ] **Step 3: 写测试文件**

创建 `web/tests/test_admin.py`：

```python
"""Django Admin 注册测试"""
import pytest
from django.contrib.auth.models import User
from web.models.document import UserDocument, DocumentChunk


@pytest.fixture
def admin_client(db):
    """创建 superuser + 已登录的 Django test client"""
    User.objects.create_superuser('admin', 'admin@test.com', 'admin123')
    from django.test import Client
    client = Client()
    client.login(username='admin', password='admin123')
    return client


class TestUserDocumentAdmin:
    """UserDocument Admin 配置"""

    def test_admin_registered(self, admin_client, user_profile):
        """Admin changelist 可访问"""
        UserDocument.objects.create(
            title='admin-test', owner=user_profile,
            file_type='txt', status='completed',
        )
        resp = admin_client.get('/admin/web/userdocument/')
        assert resp.status_code == 200
        assert 'admin-test' in resp.rendered_content

    def test_search_by_title(self, admin_client, user_profile):
        """按 title 搜索能命中"""
        UserDocument.objects.create(
            title='unique-search-term', owner=user_profile,
            file_type='txt', status='completed',
        )
        resp = admin_client.get('/admin/web/userdocument/?q=unique-search-term')
        assert resp.status_code == 200
        assert 'unique-search-term' in resp.rendered_content

    def test_search_no_match(self, admin_client, user_profile):
        """搜索不匹配 → 结果为空"""
        UserDocument.objects.create(
            title='admin-test', owner=user_profile,
            file_type='txt', status='completed',
        )
        resp = admin_client.get('/admin/web/userdocument/?q=nonexistent-xyz')
        assert resp.status_code == 200
        assert 'admin-test' not in resp.rendered_content


class TestDocumentChunkAdmin:
    """DocumentChunk Admin 配置"""

    def test_admin_registered(self, admin_client, user_profile):
        """Admin changelist 可访问"""
        doc = UserDocument.objects.create(
            title='chunk-admin-test', owner=user_profile,
            file_type='txt', status='completed',
        )
        DocumentChunk.objects.create(
            content='test chunk content', embedding=[0.0] * 1024,
            document=doc, chunk_index=0,
        )
        resp = admin_client.get('/admin/web/documentchunk/')
        assert resp.status_code == 200
        assert 'test chunk content' in resp.rendered_content
```

- [ ] **Step 4: 运行测试**

```bash
cd backend && D:\MyWork\Miniconda3\envs\py312\python.exe -m pytest web/tests/test_admin.py -v
```
Expected: 4 passed

- [ ] **Step 5: 运行全量文档相关测试确认无回归**

```bash
cd backend && D:\MyWork\Miniconda3\envs\py312\python.exe -m pytest web/tests/test_document.py web/tests/test_document_processing.py web/tests/test_admin.py -v
```
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add backend/web/admin.py backend/web/tests/test_admin.py
git commit -m "feat: UserDocument + DocumentChunk 注册 Django Admin，支持搜索和过滤"
```

---

*Plan Date: 2026-06-09*
*Based on: docs/superpowers/specs/2026-06-09-django-admin-registration-design.md*
