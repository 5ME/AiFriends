# 本地测试性能修复 — 23 分钟 → 3.7 秒

> **Date:** 2026-06-07 | **Scope:** pytest 本地运行速度修复，不动业务逻辑

**背景:** 全量 132 测试在本地 Windows 运行耗时 23 分钟，GitHub Actions CI（Ubuntu）只需 10 秒。排查发现三个独立根因叠加，修复后本地测试降至 3.7 秒（375x 提升）。

---

## 1. 根因分析

### 1.1 根因：`localhost` IPv6 DNS 解析超时（主因）

**现象：** 每个涉及 Redis 的 POST 测试耗时 ~21 秒。

**原因链：**

```
RateLimitMiddleware（每次 POST 请求都触发）
  → _check_rate_limit() 执行 Lua 脚本
    → redis.Redis.from_url('redis://localhost:6379/1')
      → DNS 解析: localhost → ::1 (IPv6) 优先
        → TCP connect ::1:6379
          → WSL Docker 端口映射仅绑定 IPv4
          → ::1:6379 无响应
          → Windows OS TCP 默认超时 ≈ 21 秒
          → 回退到 127.0.0.1 (IPv4)
          → 连接成功 → fail-open 放行
```

**为什么 CI 不受影响？** Linux `/etc/hosts` 将 `localhost` 直接映射为 `127.0.0.1`，不走 IPv6 解析。

**为什么之前没暴露？** Redis 连接在两种情况下不会触发这个 bug：
- Redis 未启动 → `socket_connect_timeout=None` 但连接立刻被拒绝（端口关闭返回 RST，不会卡超时）—— 这不太可能，之前 Redis 应该也是通过 WSL Docker 启动的
- 之前 docker-compose 可能在 Windows 项目目录下启动，端口映射方式不同

实际上，之前 Redis 超时 21s + fail-open 就一直存在，只是被误认为是"测试本来就慢"。

**验证：**

```python
# localhost → 21 秒
r = redis.Redis.from_url('redis://localhost:6379/1')
r.ping()  # 21.036s

# 127.0.0.1 → 4 毫秒
r = redis.Redis.from_url('redis://127.0.0.1:6379/1')
r.ping()  # 0.004s
```

### 1.2 根因：`test_tool_calling.py` 每次随常规测试运行（次因）

**现象：** 3 个 slow 测试每次全量跑都执行，额外耗时 ~178 秒。

**原因：** 测试文件标记了 `@pytest.mark.slow`，`pytest.ini` 也注册了 `slow` marker，但 `addopts` 没有加 `-m "not slow"` 过滤。再加上测试环境有 `API_KEY` 环境变量（本地 `.env` 配置了），模块级 `pytest.skip` 不生效。

**GitHub CI 为什么快：** CI 环境没有设置 `API_KEY`，模块级 `pytest.skip(allow_module_level=True)` 直接跳过整个文件。

### 1.3 根因：修复 1.1 后 auth 测试被限流 429（连锁反应）

**现象：** `localhost` 修复后 Redis 连通，限流真正生效。auth 测试在 3 秒内连续发 6+ 次 POST（login 5/min、register 3/min），触发 429。

**原因：** 之前这些测试靠 Redis 超时 fail-open（21s 后放弃限流检查）逃过限流。修复后 Redis 毫秒级响应，限流准确命中。

---

## 2. 修复方案

### 修复 1：Redis URL 全部改用 `127.0.0.1`

| 文件 | 字段 | 旧值 | 新值 |
|------|------|------|------|
| `backend/backend/settings.py` | `CELERY_BROKER_URL` 默认值 | `redis://localhost:6379/0` | `redis://127.0.0.1:6379/0` |
| `backend/backend/settings.py` | `REDIS_URL` 默认值 | `redis://localhost:6379/1` | `redis://127.0.0.1:6379/1` |
| `backend/.env` | `CELERY_BROKER_URL` | `redis://localhost:6379/0` | `redis://127.0.0.1:6379/0` |
| `backend/.env.example` | `CELERY_BROKER_URL` | `redis://localhost:6379/0` | `redis://127.0.0.1:6379/0` |
| `backend/.env.example` | `REDIS_URL` | `redis://localhost:6379/1` | `redis://127.0.0.1:6379/1` |

**为什么有效：** `127.0.0.1` 是 IPv4 字面地址，跳过 DNS 解析和 IPv6 尝试。与 `localhost` 功能完全等价，这是 Windows + WSL Docker 环境下的标准实践。

### 修复 2：`pytest.ini` 默认跳过 slow 测试

```ini
# 旧
addopts = -v --tb=short --reuse-db

# 新
addopts = -v --tb=short --reuse-db -m "not slow"
```

**为什么有效：** `-m "not slow"` 默认跳过带 `@pytest.mark.slow` 标记的测试。CI 环境通过 `API_KEY` 环境变量缺失跳过，本地通过 marker 过滤跳过，双重保护。需要时显式运行：`pytest web/tests/ -m slow`。

### 修复 3：`conftest.py` 全局 disable 限流

```python
@pytest.fixture(autouse=True)
def _disable_rate_limit_for_tests():
    """全局 disable 限流 — test_rate_limit.py 通过自己的 @patch 覆盖此 fixture"""
    with patch('web.middleware.rate_limit.RateLimitMiddleware._check_rate_limit',
               return_value=(True, 999)):
        yield
```

**为什么有效：** autouse fixture 让所有非限流测试的请求直接放行。`test_rate_limit.py` 中有自己的 `@patch('web.middleware.rate_limit.RateLimitMiddleware._check_rate_limit', ...)`，装饰器级别的 patch 会后于 fixture 执行，因此**覆盖** fixture 的 mock，限流测试本身不受影响。

**为什么不用 `settings.REDIS_URL = None` 或调整限流规则？** 前者会改变 Celery broker 配置（共用 `CELERY_BROKER_URL`），后者会让限流测试失效。

---

## 3. 效果对比

| 指标 | 修复前 | 修复后 | 提升 |
|------|--------|--------|------|
| 全量 129 测试（排除 slow） | ~20 分钟 | **3.67 秒** | **327x** |
| 全量 132 测试（含 slow） | ~23 分钟 | ~3 分钟 | 7.6x |
| `test_login_success` | 21.36s | 0.30s | 71x |
| Redis `ping()` | 21.04s | 0.004s | 5260x |

---

## 4. 经验教训

1. **Windows + WSL Docker 下，`localhost` 不可靠。** 始终用 `127.0.0.1` 连接 WSL 中的服务。IPv6 优先解析 + 没有 IPv6 端口映射 = 默认 TCP 超时卡死。
2. **超时设置是防御线。** `redis.Redis.from_url()` 默认 `socket_connect_timeout=None` 使用 OS 默认值。生产代码应该显式设置合理超时（如 `socket_connect_timeout=2`）。
3. **fail-open 掩盖了性能 bug。** 限流中间件的 fail-open 设计让测试"通过"了，但每次请求都在等 Redis 超时，日志也只记录了 WARNING 没有 ERROR，问题被长期忽略。
4. **CI vs 本地环境差异。** CI 的 Linux 环境没有 IPv6 问题 + 没有 `API_KEY`，所以极快。本地 Windows `.env` 有完整 API 配置，反而暴露了问题。环境差异是此类 bug 的高发区。
