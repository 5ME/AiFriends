# 健康检查增强 — 设计文档

> **Date:** 2026-06-07 | **Scope:** 纯后端基础设施，不改前端。`GET /api/health/` 增加 Redis + Celery 连通性检测。

**Goal:** 将健康检查从单一 DB 检测扩展到 DB + Redis + Celery 三组件，为容器编排（K8s liveness/readiness probe）和运维监控提供完整的状态信号。

**背景:** 当前 `health.py` 只检查 PostgreSQL 连通性。项目已引入 Redis（限流）和 Celery（文档处理 + Memory Agent），这两个组件都是生产核心依赖。健康检查必须覆盖它们。

---

## 1. 当前状态

`backend/web/views/health.py`：

```python
class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            from django.db import connections
            connections['default'].cursor()
            return Response({'status': 'ok', 'db': 'ok'})
        except Exception as e:
            logger.exception('健康检查失败: %s', e)
            return Response(
                {'status': 'degraded', 'db': 'error'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
```

**问题：**
- 只检查 DB，Redis/Celery 挂了仍返回 200
- 单一组件失败就全量 503，无法区分哪个组件挂了
- 纯文本 `{'status': 'ok'}` 缺少结构化组件状态

---

## 2. 目标设计

### 2.1 响应格式

```json
// 全部健康 → 200
{"status": "ok", "db": "ok", "redis": "ok", "celery": "ok"}

// 部分降级 → 503
{"status": "degraded", "db": "ok", "redis": "error", "celery": "ok"}

// 全部故障 → 503
{"status": "degraded", "db": "error", "redis": "error", "celery": "error"}
```

### 2.2 HTTP 语义

| 场景 | HTTP Code |
|------|-----------|
| 全部 ok | 200 |
| 任一 degraded | 503 |

K8s/Docker Compose 的 `healthcheck` 指令依赖退出码判断容器是否就绪。503 触发容器重启/摘流。

---

## 3. 检查方法

### 3.1 三个独立检查

```python
def _check_db():
    """PostgreSQL 连通性"""
    from django.db import connections
    connections['default'].cursor()
    return "ok"

def _check_redis():
    """Redis 连通性（使用限流 redis 客户端）"""
    r = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
    r.ping()
    return "ok"

def _check_celery():
    """Celery worker 存活检测"""
    insp = app.control.inspect()
    stats = insp.ping()  # → {"worker@hostname": {"ok": "pong"}} 或 None
    if not stats:
        raise RuntimeError("No Celery workers responding")
    return "ok"
```

### 3.2 设计决策

| 决策 | 理由 |
|------|------|
| **Redis 用 `redis.Redis.from_url()` 而非 `django-redis`** | 项目限流中间件已用 `redis` 包直连，与现有模式一致。不引入新的依赖 |
| **每次请求新建 Redis 连接** | 健康检查是低频请求（K8s probe 默认 10s 一次），连接池收益极微。新建连接 2s 超时保证 probe 快速返回 |
| **Celery 用 `inspect().ping()`** | Celery 官方推荐方式。通过 broker（Redis）向所有 worker 发送 ping，worker 通过 broker 回复 pong。同时验证了 broker 连通性 + worker 存活 |
| **三个检查独立 try/except** | Redis 挂了不影响 DB 检查结果，反之亦然。运维看到 `db:ok, redis:error, celery:error` 就能立刻定位 Redis 故障 |
| **Celery 检查不内联超时** | `inspect().ping()` 自身有 `timeout` 参数（默认 1s），worker 未响应时返回 `None` 而非抛异常 |

### 3.3 Celery worker 无响应时的处理

`inspect().ping()` 在以下情况返回 `None`（而非抛异常）：
- 无 worker 注册到 broker
- worker 在 timeout（默认 1s）内未响应

处理方式：返回 `None` 即视为 `degraded`。

```python
def _check_celery():
    insp = app.control.inspect()
    stats = insp.ping()
    if not stats:
        raise RuntimeError("No Celery workers responding")
    return "ok"
```

### 3.4 完整代码

```python
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
import logging

import redis
from django.conf import settings
from backend.celery import app

logger = logging.getLogger(__name__)


def _check_db():
    from django.db import connections
    connections['default'].cursor()
    return "ok"


def _check_redis():
    r = redis.Redis.from_url(
        settings.REDIS_URL,
        socket_connect_timeout=2,
    )
    r.ping()
    return "ok"


def _check_celery():
    insp = app.control.inspect()
    stats = insp.ping()
    if not stats:
        raise RuntimeError("No Celery workers responding")
    return "ok"


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        checks = [
            ("db", _check_db),
            ("redis", _check_redis),
            ("celery", _check_celery),
        ]

        result = {"status": "ok"}
        all_ok = True

        for name, check_fn in checks:
            try:
                result[name] = check_fn()
            except Exception as e:
                logger.warning("健康检查 %s 失败: %s", name, e)
                result[name] = "error"
                all_ok = False

        if not all_ok:
            result["status"] = "degraded"
            return Response(result, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(result)
```

---

## 4. 边界情况

| 场景 | 行为 |
|------|------|
| Redis 未配置（`REDIS_URL` 缺省） | `redis.Redis.from_url('redis://localhost:6379/1')` 使用默认地址，连不上返回 `redis: error` |
| Celery worker 未启动 | `inspect().ping()` 返回 `None` → `celery: error` |
| Redis + Celery 同时挂 | DB 仍 ok 但 status=degraded, 503 |
| Redis 挂导致 Celery 也挂 | `redis: error, celery: error`，运维能区分根因（Redis 故障导致 broker 不可达） |
| 限流中间件 fail-open 已处理 Redis 不可用 | 健康检查独立暴露 Redis 故障，不影响请求处理 |
| Broker (Redis) 网络不可达（防火墙丢包） | `inspect().ping()` 依赖 broker 连接，TCP 可能阻塞到 OS 默认超时（30-60s）。本机 Redis 挂了是端口拒绝（瞬间返回），此场景仅跨机部署时可能。K8s probe `timeoutSeconds` 兜底 |

---

## 5. 测试

`backend/web/tests/test_health.py`（扩展现有 2 测试）：

| 测试 | 验证点 |
|------|--------|
| `test_health_ok`（适配） | 全部组件 ok → 200 + `{"status":"ok","db":"ok","redis":"ok","celery":"ok"}` |
| `test_health_has_request_id`（不变） | X-Request-ID 仍存在 |
| `test_health_db_error`（新增） | mock `connections['default'].cursor()` 抛异常 → 503 + db:error |
| `test_health_redis_error`（新增） | mock `redis.Redis.from_url().ping()` 抛异常 → 503 + redis:error |
| `test_health_celery_error`（新增） | mock `app.control.inspect().ping()` 返回 None → 503 + celery:error |
| `test_health_partial_degraded`（新增） | Redis 挂 + DB/Celery 正常 → 503 + 仅 redis:error |

###  5.1 Mock 策略

`health.py` 模块顶部 `import redis` + `from backend.celery import app`，mock 路径基于模块命名空间：

```python
from unittest.mock import patch, MagicMock

# Happy-path：全部组件正常 → 200
@patch("web.views.health.app.control.inspect")
@patch("web.views.health.redis.Redis.from_url")
def test_health_ok(self, mock_redis_from_url, mock_inspect, api_client):
    # Redis ping 成功
    mock_redis_client = MagicMock()
    mock_redis_from_url.return_value = mock_redis_client
    # Celery worker 响应
    mock_insp = MagicMock()
    mock_insp.ping.return_value = {"worker@host": {"ok": "pong"}}
    mock_inspect.return_value = mock_insp

    resp = api_client.get("/api/health/")
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "ok", "db": "ok", "redis": "ok", "celery": "ok"
    }

# Redis 故障
def test_health_redis_error(self, api_client):
    with patch("web.views.health.redis.Redis.from_url") as mock_redis:
        mock_client = MagicMock()
        mock_client.ping.side_effect = ConnectionError("Connection refused")
        mock_redis.return_value = mock_client

        resp = api_client.get("/api/health/")
        assert resp.status_code == 503
        data = resp.json()
        assert data["redis"] == "error"
        assert data["status"] == "degraded"

# Celery 无 worker
def test_health_celery_error(self, api_client):
    with patch("web.views.health.app.control.inspect") as mock_inspect:
        mock_insp = MagicMock()
        mock_insp.ping.return_value = None  # 无 worker 响应
        mock_inspect.return_value = mock_insp

        resp = api_client.get("/api/health/")
        assert resp.status_code == 503
        data = resp.json()
        assert data["celery"] == "error"
```

---

## 6. 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/web/views/health.py` | **修改** | 抽取 `_check_*` 函数 + 增加 Redis/Celery 检查 |
| `backend/web/tests/test_health.py` | **修改** | 适配现有测试 + 新增 4 个测试 |

**改动范围：2 个文件，约 70 行，无新增文件。**

---

## 7. 验收标准

| 验证点 | 方法 | 标准 |
|--------|------|------|
| 全组件正常 | 手动 `curl /api/health/` | 200 + `{"status":"ok","db":"ok","redis":"ok","celery":"ok"}` |
| Redis 不可用 | 停 Redis 后 `curl /api/health/` | 503 + redis:error，其他组件仍 ok |
| Celery 未启动 | 停 Celery 后 `curl /api/health/` | 503 + celery:error |
| 已有测试不退化 | `pytest web/tests/test_health.py -v` | 全部通过（含新增 4 个） |
| Request ID 不变 | `curl -I /api/health/` | X-Request-ID 仍返回 |

---

## 8. 不做什么

- **不加 Celery worker 数量/队列深度检查** — 这是 metrics/monitoring 的职责，不是 health probe 的职责
- **不检查外部 AI 服务（DashScope）** — 第三方服务不可控，挂了不应让容器重启
- **不引入 `django-redis` 依赖** — 项目已用 `redis` 直连
- **不加重试逻辑** — 健康检查是瞬时快照，K8s 会按 interval 重试
- **不检查 Redis 的 DB index (0 vs 1)** — 两个 index 共享同一 Redis 实例，ping 足以验证连通性
