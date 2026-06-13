# 补充测试覆盖实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) to implement this plan task-by-task.

**Goal:** 新增 13 个测试（Homepage 5 + ASR 5 + Insert Documents 3），从 62 tests 提升到 75。

**Architecture:** 3 个独立 Task，纯测试代码，不改生产代码。每个 Task 可独立执行和验证。

**Tech Stack:** pytest, pytest-django, model_bakery, unittest.mock

**Branch:** `feature/gqyin/test-coverage`

---

## File Map

| 文件 | 操作 | Task |
|------|------|------|
| `backend/web/tests/test_homepage.py` | Create | 1 |
| `backend/web/tests/test_asr.py` | Create | 2 |
| `backend/web/tests/conftest.py` | Modify — `mock_asr_ws` fixture | 2 |
| `backend/web/tests/test_document.py` | Modify — 追加 3 tests | 3 |

---

### Task 1: Homepage 测试（5 tests）

**Files:**
- Create: `backend/web/tests/test_homepage.py`

- [ ] **Step 1: 创建 `backend/web/tests/test_homepage.py`**

```python
from rest_framework import status
from web.models.character import Character
from web.models.user import UserProfile


class TestHomepageIndex:
    """GET /api/homepage/index/"""

    def test_list_returns_characters(self, api_client, character):
        resp = api_client.get("/api/homepage/index/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["message"] == "success"
        assert len(data["characters"]) >= 1
        assert any(c["name"] == "Test Character" for c in data["characters"])

    def test_list_pagination(self, api_client, user, voice):
        """items_count=0 → max 20"""
        author = UserProfile.objects.get(user=user)
        for i in range(25):
            Character.objects.create(
                author=author, name=f"Char {i}", voice=voice,
            )
        resp = api_client.get("/api/homepage/index/?items_count=0")
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.json()["characters"]) == 20

        # 翻页
        resp2 = api_client.get("/api/homepage/index/?items_count=20")
        assert len(resp2.json()["characters"]) >= 5

    def test_search_by_name(self, api_client, character):
        resp = api_client.get("/api/homepage/index/?search_text=Test")
        assert resp.status_code == status.HTTP_200_OK
        names = [c["name"] for c in resp.json()["characters"]]
        assert "Test Character" in names

    def test_search_by_introduction(self, api_client, character):
        resp = api_client.get(
            "/api/homepage/index/?search_text=" + character.introduction[:5]
        )
        assert resp.status_code == status.HTTP_200_OK

    def test_search_empty_text(self, api_client, character):
        resp = api_client.get("/api/homepage/index/?search_text=")
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.json()["characters"]) >= 1
```

- [ ] **Step 2: 运行测试**

```bash
cd backend && python -m pytest web/tests/test_homepage.py -v
```

Python: `D:\MyWork\Miniconda3\envs\py312\python.exe`

预期：5 passed

- [ ] **Step 3: 运行全量测试**

```bash
cd backend && python -m pytest web/tests/ -q
```

预期：67 passed（62 + 5）

- [ ] **Step 4: Commit**

```bash
git add backend/web/tests/test_homepage.py
git commit -m "test: add homepage index tests

Cover character listing, pagination, search by name, search by
introduction, and empty search.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: ASR 测试（5 tests + conftest fixture）

**Files:**
- Create: `backend/web/tests/test_asr.py`
- Modify: `backend/web/tests/conftest.py`

- [ ] **Step 1: 在 conftest.py 中添加 `mock_asr_ws` fixture**

```python
@pytest.fixture
def mock_asr_ws():
    """Mock ASR WebSocket — task-started → result-generated → task-finished"""
    mock_ws = AsyncMock()

    async def ws_async_iterator():
        # First message: task-started
        yield json.dumps({"header": {"event": "task-started"}})
        # Then: result-generated with final sentence
        yield json.dumps({
            "header": {"event": "result-generated"},
            "payload": {
                "output": {
                    "transcription": {
                        "sentence_end": True,
                        "text": "你好",
                    }
                }
            }
        })
        # Finally: task-finished
        yield json.dumps({"header": {"event": "task-finished"}})

    mock_ws.__aiter__ = ws_async_iterator
    return mock_ws
```

使用 `import json` 已在 conftest 顶部存在。确保 `from unittest.mock import AsyncMock` 已导入。

- [ ] **Step 2: 创建 `backend/web/tests/test_asr.py`**

```python
import json
from unittest.mock import patch, AsyncMock

from rest_framework import status


def _dummy_audio():
    """生成一小段假 PCM 音频数据"""
    return b"\x00\x00" * 160  # ~320 bytes


class TestASREndpoint:
    """POST /api/friend/message/asr/asr/"""

    @patch("web.views.friend.message.asr.asr.websockets.connect")
    def test_asr_success(self, mock_ws_connect, auth_client, mock_asr_ws):
        mock_ws_connect.return_value = mock_asr_ws
        mock_asr_ws.send = AsyncMock()

        resp = auth_client.post(
            "/api/friend/message/asr/asr/",
            {"audio": _dummy_audio()},
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["text"] == "你好"

    def test_asr_missing_audio(self, auth_client):
        resp = auth_client.post("/api/friend/message/asr/asr/", {})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_asr_requires_auth(self, api_client):
        resp = api_client.post(
            "/api/friend/message/asr/asr/",
            {"audio": _dummy_audio()},
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("web.views.friend.message.asr.asr.websockets.connect")
    def test_asr_transcription_concat(self, mock_ws_connect, auth_client):
        """多个 sentence_end 片段正确拼接"""
        mock_ws = AsyncMock()

        async def ws_iter():
            yield json.dumps({"header": {"event": "task-started"}})
            # 中间结果 (sentence_end=false) — 应被忽略
            yield json.dumps({
                "header": {"event": "result-generated"},
                "payload": {
                    "output": {
                        "transcription": {
                            "sentence_end": False,
                            "text": "中间",
                        }
                    }
                }
            })
            # 最终结果
            yield json.dumps({
                "header": {"event": "result-generated"},
                "payload": {
                    "output": {
                        "transcription": {
                            "sentence_end": True,
                            "text": "第一句",
                        }
                    }
                }
            })
            yield json.dumps({
                "header": {"event": "result-generated"},
                "payload": {
                    "output": {
                        "transcription": {
                            "sentence_end": True,
                            "text": "第二句",
                        }
                    }
                }
            })
            yield json.dumps({"header": {"event": "task-finished"}})

        mock_ws.__aiter__ = ws_iter
        mock_ws.send = AsyncMock()
        mock_ws_connect.return_value = mock_ws

        resp = auth_client.post(
            "/api/friend/message/asr/asr/",
            {"audio": _dummy_audio()},
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["text"] == "第一句第二句"

    @patch("web.views.friend.message.asr.asr.websockets.connect")
    def test_asr_task_failed(self, mock_ws_connect, auth_client):
        """task-failed 事件返回 500"""
        mock_ws = AsyncMock()

        async def ws_iter():
            yield json.dumps({"header": {"event": "task-started"}})
            yield json.dumps({"header": {"event": "task-failed"}})

        mock_ws.__aiter__ = ws_iter
        mock_ws.send = AsyncMock()
        mock_ws_connect.return_value = mock_ws

        resp = auth_client.post(
            "/api/friend/message/asr/asr/",
            {"audio": _dummy_audio()},
        )
        assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
```

- [ ] **Step 3: 运行 ASR 测试**

```bash
cd backend && python -m pytest web/tests/test_asr.py -v
```

预期：5 passed

- [ ] **Step 4: 运行全量测试**

```bash
cd backend && python -m pytest web/tests/ -q
```

预期：72 passed（67 + 5）

- [ ] **Step 5: Commit**

```bash
git add backend/web/tests/test_asr.py backend/web/tests/conftest.py
git commit -m "test: add ASR endpoint tests and mock WebSocket fixture

Cover success, missing audio, auth required, multi-sentence
concatenation, and task-failed error handling.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: Insert Documents 测试（3 tests，追加到 test_document.py）

**Files:**
- Modify: `backend/web/tests/test_document.py`

- [ ] **Step 1: 在 test_document.py 末尾追加 3 个测试**

```python
class TestInsertDocuments:
    """insert_documents 幂等性和隔离性"""

    @patch("web.documents.utils.insert_documents.CustomEmbeddings")
    def test_insert_documents_idempotent(self, mock_embeddings_class):
        from web.documents.utils.insert_documents import insert_documents
        from web.models.document import UserDocument

        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.0] * 1024
        mock_embeddings_class.return_value = mock_embeddings

        insert_documents()
        chunk_count_1 = DocumentChunk.objects.filter(
            document__title='百炼平台概述'
        ).count()
        assert chunk_count_1 > 0

        insert_documents()
        chunk_count_2 = DocumentChunk.objects.filter(
            document__title='百炼平台概述'
        ).count()
        assert chunk_count_2 == chunk_count_1
        assert UserDocument.objects.filter(title='百炼平台概述').count() == 1

    @patch("web.documents.utils.insert_documents.CustomEmbeddings")
    def test_insert_markdown_documents_idempotent(self, mock_embeddings_class):
        from web.documents.utils.insert_documents import insert_markdown_documents
        from web.models.document import UserDocument

        mock_embeddings = MagicMock()
        mock_embeddings.embed_query.return_value = [0.0] * 1024
        mock_embeddings_class.return_value = mock_embeddings

        insert_markdown_documents()
        count_1 = DocumentChunk.objects.filter(
            document__title='百炼平台概述 Markdown'
        ).count()
        assert count_1 > 0

        insert_markdown_documents()
        count_2 = DocumentChunk.objects.filter(
            document__title='百炼平台概述 Markdown'
        ).count()
        assert count_2 == count_1

    def test_delete_only_own_chunks(self, db):
        """insert_documents 只删自己文档的 chunks"""
        from web.documents.utils.insert_documents import insert_documents
        from web.models.document import UserDocument, DocumentChunk

        other_doc = UserDocument.objects.create(title='other', status='completed')
        DocumentChunk.objects.create(
            content='keep me', embedding=[0.0] * 1024,
            document=other_doc,
        )

        with patch("web.documents.utils.insert_documents.CustomEmbeddings") as mock_class:
            mock_embeddings = MagicMock()
            mock_embeddings.embed_query.return_value = [0.0] * 1024
            mock_class.return_value = mock_embeddings

            insert_documents()

        # 自己的 chunks 应该被插入了
        own_count = DocumentChunk.objects.filter(
            document__title='百炼平台概述'
        ).count()
        assert own_count > 0

        # 其他文档的 chunks 不受影响
        other_count = DocumentChunk.objects.filter(
            document=other_doc
        ).count()
        assert other_count == 1
        assert DocumentChunk.objects.get(document=other_doc).content == 'keep me'
```

确保文件顶部已有 `from unittest.mock import patch, MagicMock` 和 `from web.models.document import DocumentChunk`。

当前 `test_document.py` 导入行：
```python
import pytest
from web.models.document import UserDocument, DocumentChunk
```

需改为：
```python
import pytest
from unittest.mock import patch, MagicMock
from web.models.document import UserDocument, DocumentChunk
```

- [ ] **Step 2: 运行新测试**

```bash
cd backend && python -m pytest web/tests/test_document.py -v
```

预期：12 passed（9 原有 + 3 新）

- [ ] **Step 3: 运行全量测试**

```bash
cd backend && python -m pytest web/tests/ -q
```

预期：75 passed（72 + 3）

- [ ] **Step 4: Commit**

```bash
git add backend/web/tests/test_document.py
git commit -m "test: add insert_documents idempotency and isolation tests

Verify that insert_documents and insert_markdown_documents are
idempotent on repeated execution, and that per-document deletion
does not affect chunks belonging to other documents.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Verification Checklist

```
[ ] test_homepage.py: 5 passed
[ ] test_asr.py: 5 passed
[ ] test_document.py: 12 passed (9 + 3 new)
[ ] 75 tests total (62 + 13)
[ ] 0 production code changes
```
