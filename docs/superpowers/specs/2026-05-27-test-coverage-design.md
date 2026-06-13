# 补充测试覆盖（Homepage + ASR + Insert Documents）

> **Date:** 2026-05-27 | **Scope:** 纯测试，不改生产代码

**Goal:** 补充 Homepage、ASR、insert_documents 三个模块的测试，从 62 提升到 75 tests。

---

## 1. Homepage 测试（5 tests）

`GET /api/homepage/index/`，公开接口，无需认证。

| # | 测试 | 说明 |
|---|------|------|
| 1 | `test_list_returns_characters` | 创建角色 → GET → 200 + characters 列表包含该角色 |
| 2 | `test_list_pagination` | 创建 25 个角色 → items_count=0 → 返回 20 个 |
| 3 | `test_search_by_name` | search_text='Test' → 按 name__icontains 匹配 |
| 4 | `test_search_by_introduction` | search_text 匹配 introduction 字段 |
| 5 | `test_search_empty_text` | search_text='' → 等价于全部列表 |

Fixture：使用已有 `api_client`、`character`。

---

## 2. ASR 测试（5 tests）

`POST /api/friend/message/asr/asr/`，需认证，接收 FormData 含 audio 文件。

ASR 测试核心是 mock WebSocket 协议（与 TTS mock 模式一致）。

| # | 测试 | 说明 |
|---|------|------|
| 1 | `test_asr_success` | 上传 PCM blob → mock WebSocket 返回 result-generated + task-finished → 200 + text |
| 2 | `test_asr_missing_audio` | 不传 audio → 400 |
| 3 | `test_asr_requires_auth` | 未认证 → 401 |
| 4 | `test_asr_transcription_concat` | 多个 result-generated 事件 → 正确拼接为完整文本 |
| 5 | `test_asr_task_failed` | task-failed 事件 → 500 |

新增 conftest fixture：`mock_asr_ws`（mock task-started + result-generated + task-finished 流程）。

---

## 3. Insert Documents 测试（3 tests）

追加到 `test_document.py`。Mock `CustomEmbeddings` 避免真实 API 调用。

| # | 测试 | 说明 |
|---|------|------|
| 1 | `test_insert_documents_idempotent` | 重复执行 → UserDocument count == 1，chunks 数量一致 |
| 2 | `test_insert_markdown_documents_idempotent` | 同理 |
| 3 | `test_delete_only_own_chunks` | 创建两个文档 → 只清理一个 → 另一个 chunks 不受影响 |

---

## 4. 文件清单

| 文件 | 操作 |
|------|------|
| `backend/web/tests/test_homepage.py` | Create |
| `backend/web/tests/test_asr.py` | Create |
| `backend/web/tests/test_document.py` | Modify — 追加 3 tests |
| `backend/web/tests/conftest.py` | Modify — 新增 mock_asr_ws fixture |
