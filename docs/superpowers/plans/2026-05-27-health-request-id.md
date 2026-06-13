# 健康检查端点和 Request ID 中间件实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) to implement this plan task-by-task.

**Goal:** 添加 request_id 中间件 + 日志集成 + 健康检查端点。

**Architecture:** 2 个 Task：中间件/日志集成 → 健康检查端点。TDD 先行。

**Tech Stack:** Django 6.0, pytest, PostgreSQL 17 + pgvector

**Branch:** `feature/gqyin/health-request-id`

---

## File Map

| 文件 | 操作 | Task |
|------|------|------|
| `backend/web/middleware/__init__.py` | Create | 1 |
| `backend/web/middleware/request_id.py` | Create | 1 |
| `backend/backend/settings.py` | Modify | 1 |
| `backend/web/views/health.py` | Create | 2 |
| `backend/web/urls.py` | Modify | 2 |
| `backend/web/tests/test_health.py` | Create | 2 |

---

### Task 1: Request ID 中间件 + 日志 Filter

**Files:**
- Create: `backend/web/middleware/__init__.py`
- Create: `backend/web/middleware/request_id.py`
- Modify: `backend/backend/settings.py`

- [ ] **Step 1: 创建 `backend/web/middleware/__init__.py`（空文件）**

```bash
# 在 backend/web/middleware/ 目录下创建空的 __init__.py
```

- [ ] **Step 2: 创建 `backend/web/middleware/request_id.py`**

```python
import uuid
import threading
import logging

logger = logging.getLogger(__name__)

_local = threading.local()


def get_request_id():
    """供日志 Filter 调用，无活跃请求时返回 '-'"""
    return getattr(_local, 'request_id', '-')


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.request_id = uuid.uuid4().hex
        request.request_id = _local.request_id
        response = self.get_response(request)
        response['X-Request-ID'] = _local.request_id
        return response


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = get_request_id()
        return True
```

- [ ] **Step 3: 修改 `backend/backend/settings.py` — 注册中间件**

找到 MIDDLEWARE 列表，在 `SecurityMiddleware` 之后插入：

```python
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'web.middleware.request_id.RequestIdMiddleware',  # 新增
    ...
]
```

- [ ] **Step 4: 修改 `backend/backend/settings.py` — 更新日志配置**

在 LOGGING dict 中：

a) 两个 formatter 的 format 中加 `%(request_id)s`：
```python
'verbose': {
    'format': '[{levelname}] {asctime} [{request_id}] {module} {process:d} {thread:d}: {message}',
    'style': '{',
},
'simple': {
    'format': '[{levelname}] {asctime} [{request_id}] {module}: {message}',
    'style': '{',
},
```

b) 顶层加 `filters`：
```python
LOGGING = {
    ...
    'filters': {
        'request_id': {
            '()': 'web.middleware.request_id.RequestIdFilter',
        },
    },
    ...
}
```

c) 两个 handler 加 `'filters': ['request_id']`：
```python
'console': {
    'class': 'logging.StreamHandler',
    'formatter': 'simple',
    'filters': ['request_id'],           # 新增
},
'file': {
    'class': 'logging.handlers.RotatingFileHandler',
    ...
    'filters': ['request_id'],           # 新增
},
```

> **注意：** `%(request_id)s` 在 Python 的 `%`-format 中使用。当前 LOGGING 的 formatter style 是 `{`（即 `str.format`），因此实际应写作 `[{request_id}]`。**确认 settings.py 中 formatter 的 style 后再决定用 `%(request_id)s` 还是 `{request_id}`**。本项目两个 formatter 均为 `'style': '{'`，所以格式字符串中用 `{request_id}`，不使用 `%(request_id)s`。

- [ ] **Step 5: 验证**

```bash
cd backend && python manage.py check
```
Python: `D:\MyWork\Miniconda3\envs\py312\python.exe`

预期：`System check identified no issues (0 silenced).`

- [ ] **Step 6: 运行已有测试确认无回归**

```bash
cd backend && python -m pytest web/tests/ -v
```
预期：60 passed

- [ ] **Step 7: Commit**

```bash
git add backend/web/middleware/__init__.py backend/web/middleware/request_id.py backend/backend/settings.py
git commit -m "feat: add Request ID middleware with logging integration

- RequestIdMiddleware injects uuid4.hex per request (request.request_id)
- X-Request-ID response header for client-side bug reporting
- RequestIdFilter injects request_id into all log records
- console and file handlers now include [request_id] in output
- threading.local() ensures thread-safe per-request isolation
- Fallback to '-' for non-request contexts (manage.py, etc.)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: 健康检查端点

**Files:**
- Create: `backend/web/views/health.py`
- Modify: `backend/web/urls.py`
- Create: `backend/web/tests/test_health.py`

- [ ] **Step 1: 编写测试 `backend/web/tests/test_health.py`**

```python
from rest_framework import status


class TestHealthEndpoint:
    """GET /api/health/"""

    def test_health_ok(self, api_client):
        resp = api_client.get("/api/health/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json() == {"status": "ok", "db": "ok"}

    def test_health_has_request_id(self, api_client):
        resp = api_client.get("/api/health/")
        assert "X-Request-ID" in resp
        rid = resp["X-Request-ID"]
        assert len(rid) == 32
        assert all(c in "0123456789abcdef" for c in rid)
```

- [ ] **Step 2: 运行测试 — 确认 FAIL**

```bash
cd backend && python -m pytest web/tests/test_health.py -v
```
Python: `D:\MyWork\Miniconda3\envs\py312\python.exe`

预期：**FAIL** — `/api/health/` 路由不存在，返回 404。

- [ ] **Step 3: 创建 `backend/web/views/health.py`**

```python
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            from django.db import connections
            connections['default'].cursor()
            return Response({'status': 'ok', 'db': 'ok'})
        except Exception:
            return Response(
                {'status': 'degraded', 'db': 'error'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
```

- [ ] **Step 4: 注册路由 — 修改 `backend/web/urls.py`**

在 urlpatterns 中添加：

```python
path('api/health/', HealthView.as_view()),
```

同时添加 import：
```python
from web.views.health import HealthView
```

- [ ] **Step 5: 运行测试 — 确认 PASS**

```bash
cd backend && python -m pytest web/tests/test_health.py -v
```
预期：**2 passed**

- [ ] **Step 6: 运行全量测试**

```bash
cd backend && python -m pytest web/tests/ -v
```
预期：**62 passed**（60 + 2 新）

- [ ] **Step 7: 验证 X-Request-ID 头能在已有测试中生效**

```bash
cd backend && python -m pytest web/tests/test_auth.py::TestLogin::test_login_success -v
```
预期：PASS，且日志包含 `[request_id]`。

- [ ] **Step 8: Commit**

```bash
git add backend/web/views/health.py backend/web/urls.py backend/web/tests/test_health.py
git commit -m "feat: add health check endpoint

- GET /api/health/ returns 200 {status: ok, db: ok} when DB is healthy
- Returns 503 {status: degraded, db: error} when DB connection fails
- No authentication required (AllowAny)
- Includes X-Request-ID header via middleware

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Verification Checklist

```
[ ] python manage.py check 通过
[ ] 62 tests pass
[ ] GET /api/health/ → 200 {"status": "ok", "db": "ok"}
[ ] 任意接口响应头带 X-Request-ID（32 hex 字符）
[ ] 日志行中带 [request_id] 标记
```

---

## PR 提交

```bash
gh pr create --title "feat: health check endpoint and request ID middleware" \
  --body "$(cat <<'EOF'
## Summary
- Request ID middleware injects uuid4.hex per request (thread-safe via threading.local)
- X-Request-ID response header enables client-side bug reporting
- logging Filter injects request_id into all log records
- GET /api/health/ returns 200 {status: ok, db: ok} or 503 on DB failure

## Test Plan
- [x] 62 tests pass (60 existing + 2 new health endpoint tests)
- [x] X-Request-ID header present and valid on all responses
- [x] python manage.py check passes

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)" --base master
```
