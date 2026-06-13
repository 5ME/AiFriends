# 健康检查端点 + Request ID 中间件设计

> **Date:** 2026-05-27 | **Scope:** 纯后端基础设施，不改前端

**Goal:** 添加健康检查端点和 request ID 中间件，实现请求全链路追踪和容器编排就绪。

---

## 1. Request ID 中间件 + 日志集成

### 1.1 中间件

新增 `backend/web/middleware/request_id.py`：

- 用 `threading.local()` 存当前请求的 `request_id`
- `uuid.uuid4().hex` 生成 32 字符 hex
- 存入 `request.request_id`（视图中可访问）和 `threading.local`（日志 Filter 可读取）
- 响应头中返回 `X-Request-ID`
- 无活跃请求时（manage.py 等）`get_request_id()` 返回 `'-'`

### 1.2 日志 Filter

`RequestIdFilter` 实现 `logging.Filter`：每次日志记录时从 `threading.local` 读取 `request_id` 注入 `record.request_id`，供 formatter 使用。

### 1.3 中间件注册

settings.py MIDDLEWARE 中，放在 `SecurityMiddleware` 之后第一位。

### 1.4 日志格式更新

formatters 中嵌入 `[%(request_id)s]`。两个 handler 均注册 `request_id` filter。

---

## 2. 健康检查端点

新增 `backend/web/views/health.py`：

- `GET /api/health/`，`AllowAny`
- DB 正常 → `200 {"status": "ok", "db": "ok"}`
- DB 异常 → `503 {"status": "degraded", "db": "error"}`
- 不检查外部 AI 服务

---

## 3. 文件清单

| 文件 | 操作 |
|------|------|
| `backend/web/middleware/__init__.py` | Create |
| `backend/web/middleware/request_id.py` | Create |
| `backend/web/views/health.py` | Create |
| `backend/backend/settings.py` | Modify — 中间件注册 + 日志格式 |
| `backend/web/urls.py` | Modify — 路由 |
| `backend/web/tests/test_health.py` | Create |

---

## 4. 验证清单

```
[ ] GET /api/health/ → 200 {"status": "ok", "db": "ok"}
[ ] 任意接口响应头带 X-Request-ID（32 字符 hex）
[ ] manage.py check 不崩溃
[ ] 日志行中带 [request_id] 标记
```
