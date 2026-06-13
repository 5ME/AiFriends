# AI Friends 下一步任务规划（2026-06-11）

> 综合 `项目Review报告(Claude-2026-06-11).md` 和 `项目Review报告(Codex-2026-06-11).md` 两份 Review 报告，结合项目当前最新状态制定。
>
> **时间估算说明：** 以下估算为理想编码时间，实际含调试和验证，建议按 +30% buffer 规划（总计 ~27-30h）。

---

## 〇、本轮已修复（不纳入规划）

| 问题 | 来源 | 状态 |
|------|------|------|
| AGENTS.md 严重过时（platform 配置、Character.profile 约定、模型列表、缺失功能） | 两份报告 | ✅ 已修复 |
| README 测试数 99→147、过期功能列表、已知限制 | 两份报告 | ✅ 已修复 |
| README/CLAUDE/AGENTS 中 AI 模型信息未更新为 deepseek-v4-flash 等 | Claude 报告 | ✅ 已修复 |

---

## 一、P0 — 必须立即修复（面试致命伤 / 数据准确性问题）

> **P0 定义：** 数据正确性 bug + 面试中大概率被追问且无法解释的短板。Codex 报告中列为 P0 的"配额系统"已降级到 P1-A1，理由：配额是 2h 的大功能而非紧急 bug，且当前 `record_api_usage` + `RateLimitMiddleware` 已构成基础治理，面试中可以说"已有数据采集和限流基础，配额是下一步"。

### P0-1: 修复 ASR usage 的 `User.id` / `UserProfile.id` 混用 🐛

**来源：** Codex 报告 §5 P0  
**严重程度：** 🔴 Bug — ASR 成本数据可能写入错误的 UserProfile 或直接外键失败  
**预计时间：** 15 分钟  
**面试收益：** ⭐⭐⭐⭐（体现对数据一致性的敏感度）

**问题：** `APIUsage.user` 是 FK → `UserProfile`。Chat/TTS/Memory/Embedding 传的是 `UserProfile.id`，但 ASR 传的是 `self.request.user.id`（Django `User.id`）。如果 `User.id ≠ UserProfile.id`，成本数据会丢失或错账。

**修复：**
```python
# asr/asr.py
- user_id = self.request.user.id
+ user_id = self.request.user.userprofile.id
```

**验证：** 补一个测试 — 创建 `User.id ≠ UserProfile.id` 的场景，验证 ASR usage 正确归属。

---

### P0-2: 修复 `init.sql` 空目录问题 🐛

**来源：** Claude 报告 §二.3  
**严重程度：** 🟡 Bug — Docker 首次启动时 `docker-entrypoint-initdb.d/init.sql` 映射失败  
**预计时间：** 5 分钟  
**面试收益：** ⭐⭐

**问题：** `docker-compose.yml` 映射 `./init.sql:/docker-entrypoint-initdb.d/init.sql`，但 `init.sql` 是一个空目录。

**修复方案（二选一）：**
- **方案 A：** 删除空目录，创建 `init.sql` 文件，内容为 `CREATE EXTENSION IF NOT EXISTS vector;`
- **方案 B：** 删除空目录，移除 docker-compose 中的 init.sql 映射（pgvector 镜像已默认启用 vector 扩展）

---

### P0-3: SSE 背压控制 — `queue.Queue(maxsize=100)` 🔧

**来源：** 两份报告（三连 Review 指出）  
**严重程度：** 🟡 内存无界增长风险  
**预计时间：** 10 分钟  
**面试收益：** ⭐⭐⭐⭐

**修复：**
```python
# chat.py:190
- mq = queue.Queue()
+ mq = queue.Queue(maxsize=100)
```

同时将 `mq.put_nowait()` 改为 `mq.put(timeout=5)`，在队列满时阻塞生产者而非丢弃。

---

### P0-4: WSGI + threading + asyncio.run 短期缓解 🔧

**来源：** 两份报告（三连 Review 指出）  
**严重程度：** 🔴 架构风险  
**预计时间：** 30 分钟  
**面试收益：** ⭐⭐⭐⭐

> **保留在 P0 的理由：** 虽然短期缓解对实际行为的改善有限，但 30 分钟投入即可在面试中回答"我知道这个问题，已做了 daemon + atexit + 独立连接的三重缓解，长期方案是迁移到 Celery/ASGI"——将一个面试致命伤转化为展示架构演进思路的机会。

**短期修复（不改变架构，降低风险）：**
1. `thread.daemon = True` — worker 退出时自动清理
2. `atexit.register()` 清理活跃的 TTS WebSocket 连接
3. 线程内创建独立的 Django 数据库连接：`connections['default'].inc_thread_connection()`

**长期方案（下一轮架构迭代）：**
- 将 TTS WebSocket 处理迁移到 Celery 任务
- 或迁移到 ASGI（Daphne/Uvicorn）以原生支持 async

---

## 二、P1 — 高优先级（闭环治理 + 面试强加分）

### Phase A: 成本治理闭环（预计 3.5 小时）

#### P1-A1: 用户每日配额系统

**来源：** Codex 报告 §5 P0, §10 Phase 1  
**预计时间：** 2 小时  
**面试收益：** ⭐⭐⭐⭐⭐

> **P0→P1 降级理由：** Codex 将此标为 P0（项目完整性），本 roadmap 的 P0 侧重"数据正确性 bug + 面试致命伤"。配额是功能增量而非 bug，且当前 `record_api_usage` + `RateLimitMiddleware` 已有基础治理。面试中"已有数据采集和限流，配额是下一步"是合理的回答。

**任务：**
- [ ] 新增 `UserQuota` 模型（user FK, date, chat_tokens_used/limit, tts_chars_used/limit, asr_seconds_used/limit, embedding_tokens_used/limit）
- [ ] 新增 `check_quota(user, api_type, amount)` 函数 — 调用前检查，超限返回 False
- [ ] 在 Chat/TTS/ASR/Embedding 调用前检查配额，超限时返回 HTTP 429 + 具体提示
- [ ] `record_api_usage()` 同步更新当日配额消耗
- [ ] 测试覆盖

#### P1-A2: APIUsage Admin 展示 + 聚合接口

**来源：** Codex 报告 §10 Phase 1  
**预计时间：** 1 小时  
**面试收益：** ⭐⭐⭐

**任务：**
- [ ] `APIUsageAdmin` 注册到 Django Admin（list_display: user, api_type, model_name, token_count, duration_ms, success, created_at）
- [ ] `GET /api/admin/usage/summary/` — 按用户/日期/类型聚合的用量摘要
- [ ] Admin 中按 user/api_type/date 过滤

#### P1-A3: APIUsage 数据保留策略

**来源：** Claude 报告 §四 数据层面  
**预计时间：** 30 分钟  
**面试收益：** ⭐⭐⭐

**任务：**
- [ ] Celery 定时任务：每天凌晨聚合前一天的 usage 到 `APIUsageDaily` 汇总表
- [ ] 删除 90 天前的原始 `APIUsage` 记录
- [ ] 在 settings.py 中配置 `API_USAGE_RETENTION_DAYS = 90`

---

### Phase B: RAG 可解释性闭环（预计 5-6 小时）

#### P1-B1: 前端展示 RAG citations

**来源：** 两份报告  
**预计时间：** 1.5 小时  
**面试收益：** ⭐⭐⭐⭐⭐

**任务：**
- [ ] `InputField.vue` 消费 `data.citations` SSE 事件
- [ ] 将 citations 挂到当前 AI 消息对象上
- [ ] `Message.vue` 在 AI 回复下方展示"📚 参考来源"折叠面板
- [ ] 每条 citation 显示：文档标题 + 段落号（可点击展开内容片段）

#### P1-B2: RAG 评估体系搭建

**来源：** Codex 报告 §5 P1, §10 Phase 2  
**预计时间：** 3-4 小时（含手工 QA 标注）  
**面试收益：** ⭐⭐⭐⭐⭐

> **时间上调理由：** 30-50 条高质量 QA 的手工标注需要理解知识库内容、设计有代表性的 query、标注 ground truth。标注本身可能就需要 1.5-2h。

**任务：**
- [ ] 构建 30-50 条 QA eval 数据集（基于系统知识库内容手工标注）
- [ ] 编写评估脚本：对每条 question，调用 `search_knowledge_base`，计算 hit@1 / hit@3 / MRR
- [ ] 输出评估报告（Markdown 表格）
- [ ] `RetrievalTrace` 增加 `message_id` 或 `request_id` 字段，关联到具体聊天消息

#### P1-B3: RAG no-answer 策略

**来源：** Codex 报告 §7.3 面试追问  
**预计时间：** 30 分钟  
**面试收益：** ⭐⭐⭐⭐

> **收益上调理由：** 直接影响用户体验——RAG 胡说八道 vs 诚实说"不知道"。面试中展示"用 distance 阈值防止幻觉"比"后台数据清理"更有说服力。

**任务：**
- [ ] 在 `search_knowledge_base` 中增加 `distance` 阈值（如 `> 0.5` 视为不相关）
- [ ] 所有结果 distance 超过阈值时，返回"知识库中未找到相关信息"
- [ ] Chat Agent prompt 增加指令：无检索结果时直接说"我不确定"，不编造

---

### Phase C: 实时语音链路稳定性（预计 4.5-5 小时）

#### P1-C1: TTS 失败降级纯文本

**来源：** Codex 报告 §5 P1, §10 Phase 3  
**预计时间：** 1 小时  
**面试收益：** ⭐⭐⭐⭐

**任务：**
- [ ] TTS WebSocket 连接失败或超时时，不设置 `has_error = True`
- [ ] 仅 `logger.warning` 记录 TTS 失败，LLM 文本流正常返回
- [ ] SSE 可选发送 `{"audio_available": false}` 事件告知前端

#### P1-C2: SSE 客户端断开检测 + 后端取消

**来源：** Codex 报告 §5 P1  
**预计时间：** 1.5 小时  
**面试收益：** ⭐⭐⭐⭐

**任务：**
- [ ] 前端 `AbortController` 集成到 `streamApi.js`
- [ ] 后端 Django 视图检测 `request.is_disconnected()`（Django 6.0+ 支持）
- [ ] 客户端断开时，通过 `threading.Event` 通知后台线程停止 LLM/TTS 调用
- [ ] `queue.Queue(maxsize=100)` + `put(timeout=5)` 配合背压

#### P1-C3: 并发压测

**来源：** 两份报告  
**预计时间：** 2.5 小时（含多组压测运行 + 报告撰写）  
**面试收益：** ⭐⭐⭐⭐⭐

> **时间上调理由：** 10/50/100 并发三轮压测 + locust 脚本调试 + 数据收集 + 报告撰写，1.5h 不够。

**任务：**
- [ ] 编写 locust 压测脚本（模拟 10/50/100 并发用户发消息）
- [ ] 压测指标：首 token 延迟、首音频延迟、总耗时、成功率、SSE 断连率
- [ ] 输出压测报告（Markdown + 图表）
- [ ] 记录瓶颈并写入 `docs/performance/` 目录

---

### Phase D: 部署与可观测性增强（预计 4 小时）

#### P1-D1: Docker Compose 全应用一键启动

**来源：** 两份报告  
**预计时间：** 3 小时（含 Dockerfile 调试）  
**面试收益：** ⭐⭐⭐⭐

> **时间上调理由：** 两个 Dockerfile（multi-stage）+ nginx 配置 + docker-compose 整合 + 调试周期，2h 偏乐观。

**任务：**
- [ ] 编写 Django 应用的 `Dockerfile`（multi-stage：前端 build → 后端收集 static）
- [ ] 编写 Celery Worker 的 `Dockerfile`（复用同一 image，不同 command）
- [ ] `docker-compose.yml` 新增 `web`、`worker`、`nginx` 服务
- [ ] Nginx 配置模板（反向代理 Django + 静态文件）
- [ ] `.env.example` 增加 Docker 部署相关变量

#### P1-D2: Health Check 分离 liveness / readiness

**来源：** Codex 报告 §5 P1  
**预计时间：** 30 分钟  
**面试收益：** ⭐⭐⭐

**任务：**
- [ ] `GET /api/health/live/` — 仅检查进程存活，始终返回 200
- [ ] `GET /api/health/ready/` — 检查 DB + Redis + Celery（原 `/api/health/` 逻辑）
- [ ] 原 `/api/health/` 保留兼容，内部重定向到 `/api/health/ready/`

#### P1-D3: CI 添加 Redis 服务

**来源：** Claude 报告 §四 架构层面  
**预计时间：** 15 分钟  
**面试收益：** ⭐⭐⭐

> **收益上调理由：** 面试可能被追问"限流在 CI 中怎么测的？mock 还是真实 Redis？"——CI 中有真实 Redis 比 mock 更有说服力。

**任务：**
- [ ] `.github/workflows/test.yml` 添加 Redis service container
- [ ] 验证限流和健康检查的 Redis 路径在 CI 中真实运行

---

## 三、P2 — 增强项（提升项目深度和完整度）

### P2-1: API 版本化
- **预计时间：** 1 小时
- 添加 `/api/v1/` 前缀，旧 `/api/` 路径保留重定向兼容

### P2-2: 手动分页 → DRF 分页
- **预计时间：** 1 小时
- 首页角色列表、文档列表等处替换为 `PageNumberPagination`

### P2-3: Request-ID 传递到 Celery
- **预计时间：** 30 分钟
- Celery task kwargs 中传入 `request_id`，日志中关联

### P2-4: 前端自动化测试
- **预计时间：** 2 小时
- Vitest + Vue Test Utils 对关键组件（ToastContainer, UploadZone, DocumentCard）编写单元测试

### P2-5: 数据库事务一致性
- **预计时间：** 1 小时
- Message 保存 + Memory 触发用 `transaction.atomic()` 包裹

### P2-6: 代码风格检查
- **预计时间：** 30 分钟
- 后端: ruff; 前端: eslint + prettier; pre-commit hooks

### P2-7: 消息幂等键 🆕
- **来源：** Claude 报告 §五 P0（三连 Review 指出）
- **预计时间：** 30 分钟
- 前端发送消息后禁用按钮（防重复点击）
- 后端 `Message` 表增加 `idempotency_key` 字段 + 唯一约束
- Chat 视图收到重复 key 时返回已有消息（幂等）

### P2-8: Prometheus metrics 端点 🆕
- **来源：** Codex 报告 §10 Phase 4
- **预计时间：** 1 小时
- `GET /api/metrics/` 暴露请求计数、延迟分布、AI 调用成功率
- 可选：`django-prometheus` 快速接入

### P2-9: 后端测试缺口补充 🆕
- **来源：** Claude 报告 §四 测试层面
- **预计时间：** 1.5 小时
- TTS WebSocket mock 测试、SSE 流格式验证（含 citations 事件）、Voice 管理测试

---

## 四、本轮 Deferred（主动选择不做，记录原因）

| 项目 | 原因 |
|------|------|
| **自定义音色完整功能** | 成本高（需要 OSS、前端上传流程、Voice owner 重构），当前有底层 API wrapper 预留扩展点即可。简历写"已预研 DashScope voice enrollment API" |
| **Java Quota Service** | 独立项目，不适合塞进本轮。面 Java 岗位时可以口头讲设计思路 |
| **Sentry 错误追踪** | 依赖外部服务，部署复杂度高。当前 RotatingFileHandler + Request ID 已覆盖基本需求 |
| **CD Pipeline** | 当前无多环境需求，GitHub Actions CI（push/PR 自动测试）已足够 |
| **错误率告警** | 无明确告警渠道（短信/邮件/IM），先完成 Prometheus metrics（P2-8）作为数据基础 |
| **API 访问日志持久化** | 当前 RequestIdMiddleware 已有内存日志，持久化需求不强 |

---

## 五、执行路线图

```
Week 1 (紧急修复) ─────────────────────────────
│ P0-1  ASR usage id 修复          15min  🐛
│ P0-2  init.sql 修复               5min  🐛
│ P0-3  queue.Queue(maxsize=100)   10min  🔧
│ P0-4  WSGI+asyncio 短期缓解      30min  🔧
│ P1-D3 CI 添加 Redis              15min  🔧
│──────────────────────────────────────────
│ 小计: ~1.5h | 全部 P0 清零
│
Week 1-2 (成本治理闭环) ───────────────────────
│ P1-A1 用户每日配额                2h    💰
│ P1-A2 APIUsage Admin + 聚合      1h    💰
│ P1-A3 数据保留策略               30min  💰
│──────────────────────────────────────────
│ 小计: ~3.5h | 成本治理从记录→治理
│
Week 2 (RAG 闭环) ───────────────────────────
│ P1-B1 前端展示 citations         1.5h  📚
│ P1-B3 no-answer 策略            30min  📚
│ P1-B2 RAG eval 体系             3-4h  📚
│──────────────────────────────────────────
│ 小计: ~5-6h | RAG 从可搜→可解释
│
Week 2-3 (语音稳定性) ────────────────────────
│ P1-C1 TTS 失败降级纯文本         1h    🎤
│ P1-C2 SSE 断连检测 + 取消        1.5h  🎤
│ P1-C3 并发压测                   2.5h  🎤
│──────────────────────────────────────────
│ 小计: ~5h | 语音从能跑→可靠
│
Week 3 (部署闭环) ───────────────────────────
│ P1-D1 Docker Compose 全应用      3h    🚀
│ P1-D2 Health Check liveness/ready 30min 🚀
│──────────────────────────────────────────
│ 小计: ~3.5h | 一键部署
│
Week 3-4 (增强项) ───────────────────────────
│ P2-7  消息幂等键                30min  📦
│ P2-5  数据库事务一致性           1h    📦
│ P2-1  API 版本化                 1h    📦
│ P2-2  DRF 分页                   1h    📦
│ P2-6  代码风格检查              30min  📦
│ P2-3  Request-ID 到 Celery      30min  📦
│ P2-8  Prometheus metrics         1h    📦
│ P2-9  后端测试缺口补充           1.5h  📦
│ P2-4  前端自动化测试             2h    📦
│──────────────────────────────────────────
│ 小计: ~9h | 锦上添花
│
══════════════════════════════════════════════
总计: ~27.5h（含 buffer: ~27-30h）
```

---

## 六、面试价值矩阵

| 任务 | 时间 | 面试收益 | 性价比 |
|------|------|---------|--------|
| **P1-B1** 前端 RAG citations | 1.5h | ⭐⭐⭐⭐⭐ | 🔥 最高 |
| **P1-B2** RAG eval 体系 | 3-4h | ⭐⭐⭐⭐⭐ | 🔥 最高 |
| **P1-C3** 并发压测 | 2.5h | ⭐⭐⭐⭐⭐ | 🔥 最高 |
| **P1-A1** 用户每日配额 | 2h | ⭐⭐⭐⭐⭐ | 🔥 最高 |
| **P0-1** ASR usage id 修复 | 15min | ⭐⭐⭐⭐ | ⚡ 超高（bug fix） |
| **P0-3** queue maxsize | 10min | ⭐⭐⭐⭐ | ⚡ 超高（trivial fix） |
| **P1-C1** TTS 降级纯文本 | 1h | ⭐⭐⭐⭐ | 🔥 高 |
| **P1-C2** SSE 断连取消 | 1.5h | ⭐⭐⭐⭐ | 🔥 高 |
| **P1-D1** Docker 一键启动 | 3h | ⭐⭐⭐⭐ | 🔥 高 |
| **P0-4** WSGI+asyncio 缓解 | 30min | ⭐⭐⭐⭐ | ⚡ 高 |
| **P1-B3** no-answer 策略 | 30min | ⭐⭐⭐⭐ | ⚡ 高 |
| P1-A2 APIUsage Admin | 1h | ⭐⭐⭐ | 中 |
| P1-D2 liveness/readiness | 30min | ⭐⭐⭐ | 中 |
| P1-A3 数据保留策略 | 30min | ⭐⭐⭐ | 中 |
| P1-D3 CI Redis | 15min | ⭐⭐⭐ | 中 |
| P2-7 消息幂等键 | 30min | ⭐⭐⭐ | 中 |
| P2-8 Prometheus metrics | 1h | ⭐⭐⭐ | 中 |
| P2 其他增强项 | ~7.5h | ⭐⭐~⭐⭐⭐ | 低 |

---

## 七、建议执行顺序

**第一批（今天，1.5h）— P0 清零：**
```
P0-1 ASR usage → P0-2 init.sql → P0-3 queue maxsize → P0-4 WSGI缓解
```
> 顺序调整：ASR usage 提到第一 — 它是真正的数据正确性 bug，修复只需一行代码。

**第二批（本周，7.5h）— 面试核心亮点：**
```
P1-B1 前端 citations → P1-B3 no-answer → P1-B2 RAG eval → P1-A1 用户配额
```

**第三批（下周，8.5h）— 治理闭环 + 语音：**
```
P1-C3 压测 → P1-C1 TTS降级 → P1-C2 SSE断连 → P1-D1 Docker全应用 → P1-A2/A3/D2/D3
```

**第四批（后续，9h）— 锦上添花：**
```
P2-7 幂等 → P2-5 事务 → P2-1 版本化 → P2-2 分页 → P2-6 lint → P2-3 request-id → P2-8 metrics → P2-9 测试缺口 → P2-4 前端测试
```
