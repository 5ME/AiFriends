# P1-C3: SSE 流并发验证 设计文档

> 状态：草稿 | 2026-06-26

## 一、问题

C1（TTS 降级）和 C2（SSE 断连检测）为 SSE 流引入了 `threading.Event`、排空模式、`_output_buffer` 等多线程/多协程交互。这些改动在单请求下通过测试，但并发场景下的正确性未验证。

**需要验证：**
- 多个 SSE 流并发时，`cancel_event`/`_output_buffer`/`_tts_usage` 等实例属性不跨请求串扰
- C2 的 generator `finally` 在并发断连时正常触发，不挂死线程
- C1 的 TTS 降级在并发压力下不会误设 `has_error`

**不验证：**
- 系统吞吐上限、并发拐点、网络带宽瓶颈（硬件限制，无参考价值）
- API 限流阈值（DashScope 控制，非应用层面）

## 二、环境选择

| 选项 | 采用？ | 理由 |
|------|:---:|------|
| 本地笔记本（Ultra 7 + 32GB） | ✅ | 迭代快；验证并发正确性不依赖硬件规格 |
| 云服务器（4vCPU + 4GiB） | ❌ | 部署成本高，CPU 更弱反而引入噪音 |

## 三、工具选择

| 选项 | 采用？ | 理由 |
|------|:---:|------|
| **asyncio 简单脚本（~40 行）** | ✅ | 5 并发验证正确性，不需要 Locust 的趋势图/HTTP metrics |
| Locust | ❌ | 为大规模渐进式压测设计；对 5 并发+SSE 流是过度工程；需额外学习/维护成本 |

### Locust 的问题

1. Locust 的 HTTP 用户模型基于 requests 库 → 不支持 `text/event-stream` 消费 → 需要自定义 `User` 类，复杂度接近手写脚本
2. 5 并发不产生有意义的分布曲线 — dist chart 上只有 5 个点
3. 脚本完成后无法复用（后续不做生产级压测）

## 四、测试场景设计

### 场景 1：基础并发 — 5 用户同时聊天

```
5 个 asyncio Task 并发:
  1. 登录获取 token
  2. POST SSE → 消费流 → 收 [DONE]
  3. 验证:
     - HTTP 200
     - 无 "error" 事件（除非 TTS 真挂了）
     - 至少 1 个 "content" 事件
```

**目的：** 验证 C1/C2 修改未引入死锁或竞争。

### 场景 2：并发断连 — 3 个正常 + 2 个中途断开

```
5 个 asyncio Task:
  Task 1-3: 正常消费完 SSE（跟场景 1 一样）
  Task 4-5: 收到首个 content 后立刻 close() 连接
```

**目的：** 验证 C2 的 generator finally 正确触发，cancel_event 不误影响其他请求。检查后端日志确认无 Internal Server Error。

**额外验证：** Task 4-5 的断连路径会触发 `work()` 的排空分支（`cancel_event.is_set()` → 从 `_output_buffer` 保存 Message）。断连请求内部走 `_has_error=False`（非异常退出），正常请求走 `event_stream` 的正常路径。验证：断连请求的处理不影响 Task 1-3 的 `has_error` 状态——正常请求的 SSE 流不出现 `error` 事件。

注：Django 每个 HTTP 请求创建新的 `MessageChatView` 实例，`self._output_buffer` 等属性天然隔离。此场景验证的是 `threading.Event` 和 `queue.Queue` 的跨请求隔离（它们不是实例属性，由 `event_stream()` 函数内创建，每次调用独立）。

### 场景 3：重复 3 轮 — 验证不累积

```
场景 1 × 3 轮 → 检查 Django 进程内存/线程数未增长
```

**目的：** 验证 daemon 线程正常退出（`mq.put(None)` 送达）、Python GC 回收 `_output_buffer`。

## 五、指标

只收 3 个指标，不设目标值（本地环境没参考意义）：

| 指标 | 来源 | 用途 |
|------|------|------|
| 首 token/sentence 延迟 | 首个 `content` 事件的时间戳 | 存在性检查（有就行，绝对值不重要） |
| 总耗时 | SSE [DONE] 时间 | 存在性检查 |
| 成功/失败计数 | HTTP status + 无 error 事件 | 正确性验证（必须 100%） |

## 六、不做的

- ❌ 10/50/100 渐进式压测（roadmap 原始设计）— 无意义，瓶颈在 API 限流
- ❌ 性能图表 — 5 个数据点不成图
- ❌ 生产环境压测 — 需要云服务器 + 真实 API 配额
- ❌ 自动化 CI 集成 — 依赖真实 API_KEY，不做

## 七、文件规划

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/web/tests/concurrency_verify.py` | 新建 | 独立脚本，`python` 直接跑，不入 pytest |
| `docs/performance/2026-06-26-c3-concurrency-report.md` | 新建 | 单次运行结果记录，以后有改进可对照 |

## 八、变更记录

| # | 时间 | 变更 | 原因 |
|---|------|------|------|
| 1 | 2026-06-26 | 初版 | C3 并发验证设计启动 |
| 2 | 2026-06-26 | 场景 2 明确 has_error 跨请求隔离验证 + Django 实例隔离说明 | Review: 缺少 C1 降级路径的并发验证 |
