# AI Friends 测试体系 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从零搭建 pytest + pytest-django + model_bakery 测试体系，覆盖 auth → friend → character → chat agent → memory agent

**Architecture:** `web/tests/` 目录 + `conftest.py` 全局 fixtures。每个测试模块独立可运行。Chat Agent 分两层 mock：图逻辑层（patch ChatOpenAI.invoke）+ SSE 端点层（patch ChatGraph.create_app + websockets）

**Tech Stack:** pytest 8.x, pytest-django 4.x, pytest-mock 3.x, model_bakery 1.x, Django 6.0, SQLite (测试库)

**Spec:** `docs/superpowers/specs/2026-05-17-testing-design.md`

---

### Task 1: 基础设施搭建

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/pytest.ini`
- Create: `backend/web/tests/__init__.py`
- Create: `backend/web/tests/conftest.py`
- Delete: `backend/web/tests.py`

- [ ] **Step 1: 安装测试依赖**

```bash
cd backend && pip install pytest pytest-django pytest-mock model_bakery
```

- [ ] **Step 2: 将依赖写入 requirements.txt**

在 `backend/requirements.txt` 末尾追加：

```
pytest>=8.0
pytest-django>=4.0
pytest-mock>=3.0
model_bakery>=1.0
```

- [ ] **Step 3: 创建 pytest.ini**

```ini
[pytest]
DJANGO_SETTINGS_MODULE = backend.settings
python_files = tests/test_*.py
addopts = -v --tb=short
```

- [ ] **Step 4: 删除旧的 tests.py，创建 tests 包**

```bash
rm backend/web/tests.py
mkdir -p backend/web/tests
```

- [ ] **Step 5: 创建 web/tests/__init__.py**

空文件。

- [ ] **Step 6: 创建 web/tests/conftest.py**

```python
import pytest
from model_bakery import baker
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from web.models.user import UserProfile
from web.models.character import Character, Voice
from web.models.friend import Friend


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    u = baker.make(User, username="testuser")
    baker.make(UserProfile, user=u)
    return u


@pytest.fixture
def auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    client.cookies["refresh_token"] = str(refresh)
    return client


@pytest.fixture
def user_profile(user):
    return UserProfile.objects.get(user=user)


@pytest.fixture
def voice(db):
    return baker.make(Voice, name="Test Voice", voice_id="test_voice_001")


@pytest.fixture
def character(user_profile, voice):
    return baker.make(Character, author=user_profile, name="Test Character", voice=voice)


@pytest.fixture
def friend(user_profile, character):
    return baker.make(Friend, user_profile=user_profile, character=character)


@pytest.fixture
def other_user(db):
    u = baker.make(User, username="otheruser")
    baker.make(UserProfile, user=u)
    return u


@pytest.fixture
def other_auth_client(other_user):
    client = APIClient()
    refresh = RefreshToken.for_user(other_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    client.cookies["refresh_token"] = str(refresh)
    return client
```

- [ ] **Step 7: 验证基础设施**

```bash
cd backend && python -m pytest --collect-only
```

Expected: "no tests collected"

- [ ] **Step 8: Commit**

```bash
git add backend/pytest.ini backend/web/tests/ backend/requirements.txt
git rm backend/web/tests.py
git commit -m "feat: add pytest infrastructure with conftest fixtures"
```

---

### Task 2: test_auth.py — 登录/注册/Token/登出（12 测试）

**Files:**
- Create: `backend/web/tests/test_auth.py`

完整测试代码见 plan mode 文件 `C:\Users\YGQ\.claude\plans\docs-superpowers-specs-2026-05-15-prior-hashed-wigderson.md` Task 2。

覆盖：login_success, login_wrong_password, login_empty_username, login_empty_password, register_success, register_duplicate_username, register_empty_fields, refresh_success, refresh_missing_cookie, refresh_expired_token, logout_success, get_user_info

```bash
cd backend && python -m pytest web/tests/test_auth.py -v
# Expected: 12 passed
```

---

### Task 3: test_friend.py — 好友管理（12 测试）

**Files:**
- Create: `backend/web/tests/test_friend.py`

完整测试代码见 plan mode 文件 Task 3。

覆盖：get_or_create_new, get_or_create_duplicate, get_or_create_missing_character_id, get_or_create_character_not_found, get_or_create_requires_auth, remove_success, remove_other_users_friend, get_list, is_friend_true, is_friend_false, get_count

```bash
cd backend && python -m pytest web/tests/test_friend.py -v
# Expected: 12 passed
```

---

### Task 4: test_character.py — 角色 CRUD + 权限（11 测试）

**Files:**
- Create: `backend/web/tests/test_character.py`

完整测试代码见 plan mode 文件 Task 4。

覆盖：create_success, create_no_auth, create_empty_name, create_empty_profile, get_single_own, get_single_other_author, update_success, update_not_author, delete_success, delete_not_author, get_list

```bash
cd backend && python -m pytest web/tests/test_character.py -v
# Expected: 11 passed
```

---

### Task 5: test_chat_agent.py — LangGraph + SSE（10 测试）

**Files:**
- Create: `backend/web/tests/test_chat_agent.py`

完整测试代码见 plan mode 文件 Task 5。

层级 1（图逻辑）：test_agent_no_tool_calls, test_agent_with_tool_calls, test_tools_to_agent_loop, test_get_time_tool, test_search_knowledge_base_tool

层级 2（SSE）：test_sse_text_stream, test_sse_done_marker, test_sse_message_created, test_sse_friend_not_found, test_sse_requires_auth

```bash
cd backend && python -m pytest web/tests/test_chat_agent.py -v
# Expected: 10 passed
```

---

### Task 6: test_memory_agent.py — 记忆摘要（4 测试）

**Files:**
- Create: `backend/web/tests/test_memory_agent.py`

完整测试代码见 plan mode 文件 Task 6。

覆盖：test_memory_triggered_at_10, test_memory_not_triggered_at_5, test_memory_field_updated, test_memory_agent_graph

```bash
cd backend && python -m pytest web/tests/test_memory_agent.py -v
# Expected: 4 passed
```

---

### Task 7: 全量回归

```bash
cd backend && python -m pytest web/tests/ -v
# Expected: 49 passed
```

---

## 约束与注意事项

1. **Chat Agent SSE 线程 mock** — `event_stream` 在独立线程中运行 `asyncio.run()`，`@patch` 装饰器在模块级别 mock 对子线程同样生效。

2. **ImageField** — model_bakery 可自动生成临时图片，character 测试中手动用 Pillow 创建 SimpleUploadedFile 以确保精确控制。

3. **Memory 触发计数** — 聊天视图中条件是 `message_count % 10 == 0`，测试绕过 SSE 端点直接测 `update_memory` 函数。

4. **权限测试的 500** — 当前代码非作者操作时 `Character.objects.get()` 抛 `DoesNotExist` → 被 `except Exception` 捕获 → 500。这是现有行为，测试如实反映。

5. **PostgreSQL 迁移后** — 所有测试不改代码，切到 PostgreSQL `pytest` 全量重跑即可验证迁移。
