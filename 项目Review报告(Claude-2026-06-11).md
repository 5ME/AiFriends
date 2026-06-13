# AI Friends 项目深度 Review（2026-06-11 · 第三轮）

> 视角：资深后端架构师 / AI 应用技术面试官
> 目标岗位：Java 后端开发工程师 / AI 应用工程师（社招）
> 评估人背景假设：Java 为主语言，Python 基础，上一份工作后端开发

---

## 〇、与上次 Review（2026-05-31）的对比总览

上次 Review 距今 11 天，项目持续快速迭代。以下是逐项对比：

### 已解决（上次 Review 指出的问题）

| 问题 | 上次状态 | 当前状态 |
|------|---------|---------|
| **CI/CD** | 🔴 缺失 | ✅ GitHub Actions CI（pytest 147 测试自动运行） |
| **请求耗时监控** | 🟡 缺失 | ✅ `RequestIdMiddleware` 记录 `duration_ms` |
| **SECRET_KEY 弱 fallback** | 🟡 DEBUG=False 时仍可用弱密钥 | ✅ 生产模式无环境变量时拒绝启动（`ImproperlyConfigured`） |
| **docker-compose 不可移植** | 🟡 硬编码 Linux 路径 | ✅ 环境变量密码 + named volumes |
| **Photo.vue 重复** | 🟢 低 | ✅ 抽取为 `useImageCropper` composable，三处复用 |
| **前端无全局错误提示** | 🟡 缺失 | ✅ Toast 基础设施（`useToast` + `ToastContainer`）|
| **首页/音色缓存** | 🟡 无 Redis 缓存 | ✅ Redis 已引入（限流 + Celery broker）|
| **AI 调用重试** | 🟢 chat 未使用 | ✅ Chat Agent 有 `record_api_usage` 记录，Memory/Document 有分类重试 |
| **系统知识库全量删除+插入** | 🟡 全量重建 | ✅ `content_hash` 增量更新，跳过未变 chunk |
| **README 过期信息** | 🟡 测试数/功能过期 | ✅ 已更新（但仍需同步最新数据）|

### 新增改进（上次 Review 未涉及的全新功能）

| 功能 | 说明 |
|------|------|
| **Redis 滑动窗口限流** | Lua 原子脚本，区分用户/IP，fail-open，6 条规则覆盖 login/register/chat/asr/upload |
| **API 使用量追踪** | `APIUsage` 模型记录 llm/embedding/tts/asr 的 token/duration/success |
| **健康检查增强** | DB + Redis + Celery 三组件独立检测，任一失败返回 503 degraded |
| **RAG 引用来源 + RetrievalTrace** | JOIN 查询获取文档标题，来源标记 `[来源N: title 第M段]`，检索 trace 落库 |
| **文档处理可靠性增强** | `celery_task_id` 追踪 → 删除时撤销任务 → 投递失败标记 failed |
| **Django Admin 注册** | UserDocument + DocumentChunk 注册后台，支持搜索过滤、N+1 优化 |
| **SystemPrompt 3 层分离** | 工具规则（硬编码）→ 角色性格+记忆 → 系统框架（DB），互不耦合 |
| **前端 Toast 基础设施** | `useToast` composable + `ToastContainer` 组件 + daisyUI alert 样式 |
| **前端平台自动检测** | Vite MODE 自动切换 django/cloud，不再手动改 config.js |
| **知识库前端页面** | UploadZone 拖拽上传 + DocumentCard 文档卡片 + 轮询状态更新 |

### 仍待解决（上次指出但未处理）

| 问题 | 严重程度 | 上次状态 | 当前状态 |
|------|---------|---------|---------|
| **WSGI + threading + asyncio.run** | 🔴 高 | `chat.py:194` 裸线程 | **仍未修改**（`chat.py:194` 同一行）|
| **API 版本化** | 🟡 中 | 无 `/api/v1/` | **仍未修改** |
| **手动分页** | 🟡 中 | `items[offset:offset+20]` | **仍未修改** |
| **SSE 背压控制** | 🟢 低 | `queue.Queue()` 无 maxsize | **仍未修改**（`chat.py:190`）|
| **自定义音色 CRUD 前端** | 🟢 低 | 后端有，前端未接 | **仍未修改** |

---

## 一、项目亮点（更新版）

### S 级（必须写进简历，面试官最可能追问）

| 亮点 | 简历价值 | 相比上次的变化 |
|------|---------|---------------|
| **双 Agent 架构（LangGraph）** | ⭐⭐⭐⭐⭐ | SystemPrompt 3 层分离（工具规则/角色性格/系统框架）；Memory Agent 增加 API usage 追踪 |
| **全双工流式语音对话** | ⭐⭐⭐⭐⭐ | 无变化（架构稳定）；新增 TTS usage 同步写入避免 `SynchronousOnlyOperation` |
| **JWT 双 Token 无感刷新** | ⭐⭐⭐⭐ | 无变化 |
| **pgvector 向量检索 + RAG** | ⭐⭐⭐⭐⭐ | 大幅升级：增量更新（hash 对比避免重复 embedding） + 引用来源标记 + RetrievalTrace 落库 + 删除文档撤销 Celery 任务 |
| **Redis 限流 + API 成本治理** | ⭐⭐⭐⭐⭐ | **全新**：滑动窗口 Lua 原子限流 + APIUsage 模型追踪用量 + fail-open 容错 |

### A 级（加分项，选择性写进简历）

| 亮点 | 简历价值 | 说明 |
|------|---------|------|
| **Celery + Redis 异步任务** | ⭐⭐⭐⭐ | 任务撤销（revoke）+ 投递失败标记 + celery_task_id 生命周期管理 + 区分 4xx/5xx/429 重试 |
| **Request ID + 请求耗时全链路追踪** | ⭐⭐⭐⭐ | Middleware 注入 → 日志集成 → Response header + 每个请求记录 method/path/status/duration |
| **健康检查三组件检测** | ⭐⭐⭐ | DB + Redis + Celery 独立检测，降级语义正确（503 degraded） |
| **Django REST Framework 纯 APIView 设计** | ⭐⭐⭐ | 每个端点一个文件，不使用 DRF Serializer |
| **前后端一体化部署** | ⭐⭐⭐ | Nginx + Gunicorn + Unix Socket + docker-compose（PG+Redis） |
| **Dual-DB 策略** | ⭐⭐⭐ | 测试库 `aifriends_test`（同引擎 pgvector），避免兼容性问题 |
| **文档处理状态机 + 前端轮询** | ⭐⭐⭐ | pending→processing→completed/failed + `useDocumentPolling` 自动停止 |
| **前端 Toast 通知系统** | ⭐⭐⭐ | 模块级 reactive 单例 + readonly 暴露 + 自动移除 + 最多 5 条 |
| **GitHub Actions CI** | ⭐⭐⭐ | push/PR 触发，pgvector 服务容器，147 测试自动运行 |

---

## 二、工程能力与架构能力评估（更新版）

### 做得更好的地方（相比上次的新增亮点）

**1. Redis 限流的 Lua 原子脚本实现 — 面试高价值点**

```lua
-- rate_limit.py 中的 Lua 脚本
-- 滑动窗口日志算法：原子性地执行 ZREMRANGEBYSCORE + ZADD + ZCARD + EXPIRE
redis.call('ZREMRANGEBYSCORE', key, 0, now - window_ms)
redis.call('ZADD', key, now, member)
local count = redis.call('ZCARD', key)
redis.call('EXPIRE', key, math.ceil(window_ms / 1000))
```

这是"Java 后端工程师懂 Redis 原子操作"的有力证据。关键设计：
- 区分 auth user（`user:{id}`）/ anonymous IP（`ip:{ip}`）两种 key
- Fail-open：Redis 不可达时放过请求，记录异常日志
- 6 条规则精确匹配不同端点的不同频率需求
- 跳过路径白名单（health/refresh_token/static/media/admin）
- 仅限制写方法（POST/PUT/PATCH/DELETE），GET 放行

**2. API 使用量追踪的"旁路"设计**

`record_api_usage()` 是一个 fire-and-forget 函数——所有异常内部 catch+log，绝不阻塞调用方。在 chat/TTS/embedding/ASR/Memory 5 个调用点统一记录。这是生产环境中监控 AI 成本的标准做法。

**3. RAG 引用来源的完整可追溯链路**

```
用户发消息 → search_knowledge_base 工具调用
  → pgvector <=> 余弦检索 + JOIN UserDocument 获取标题
  → 格式化输出 `[来源N: 标题 第M段]`
  → RetrievalTrace 落库（user, query, document_id, chunk_index, distance）
  → LangGraph ToolMessage 检测 → 正则提取 citation
  → SSE citations 事件推送前端
```

每一轮检索都有数据库记录，可事后分析检索质量（相关性 distance、哪些文档被命中）。

**4. 系统知识库增量更新的 hash 对比方案**

```python
# insert_documents.py
new_hash = hashlib.sha256(chunk.page_content.encode()).hexdigest()
if old.content_hash == new_hash:
    continue  # 跳过，不重复 embedding
```

这是工程上正确的方案：SHA-256 hash 比较替代全量删除+插入，省去不必要的 embedding API 调用（省钱+省时间）。同时处理了历史数据无 hash 的兜底（`content_hash=''` 视为需更新）。

**5. 文档删除 + Celery 任务撤销的联动**

```
用户删除文档 → 检查 doc.celery_task_id
  → app.control.revoke(task_id)  # 取消排队/等待中的任务
  → 软撤销：正在执行的任务在 tasks.py 中检查文档是否存在
  → 级联删除 DocumentChunk
```

"最佳努力"策略（revoke 失败记录 warning 但不阻止删除）体现工程权衡意识。

**6. 前端 Toast 系统的设计质量**

- `reactive()` 模块级单例 → 全局共享状态
- `readonly()` 暴露 → 防止消费者误修改
- 自动移除（非 error）+ 手动关闭（error 永不清除）
- 最多 5 条上限 → 防止 toast 堆积
- daisyUI alert 颜色通过静态 class 对象避免 Tailwind JIT 漏生成

**7. SystemPrompt 3 层分离**

```
Layer 1: TOOL_RULES（硬编码） — "何时调用 search_knowledge_base / get_time"
Layer 2: Character.system_prompt + Friend.memory — 角色性格 + 长期记忆
Layer 3: SystemPrompt(title=REPLY) — 系统级框架约束（DB 可配置）
```

三层独立、职责清晰：工具使用规则不能被角色性格覆盖，框架约束独立于角色定制。这是 LangChain 生产实践的体现。

### 做得不够好的地方

**1. Django 视图中运行 asyncio 的线程安全问题（三连 Review 仍未解决）**

```python
# chat.py:194 — 连续 3 次 Review 指出的问题
thread = threading.Thread(target=self.work, args=(app, inputs, mq, voice_id, user_id))
thread.start()

# chat.py:265
def work(self, ...):
    asyncio.run(self.run_tts_task(...))
```

风险矩阵：
- Django WSGI + 裸线程：数据库连接非线程安全（每个线程需要独立连接）
- gunicorn worker 退出时后台线程被强杀 → DashScope TTS WebSocket 泄漏
- `asyncio.run()` 创建新 event loop，与 Django 的同步 ORM 模型冲突
- `queue.Queue()` 无 maxsize → 内存无界增长风险

**2. AGENTS.md 严重过时**

AGENTS.md（Codex agent 的指令文件）包含多处错误信息：
- ❌ "Set `platform = 'cloud'` in `config.js`" → 已改为自动检测
- ❌ `Character.profile` 双角色约定（第一行/public，全文/LLM）→ 已拆分为 `introduction` / `system_prompt`
- ❌ "Models live in three files" → 现在有 6 个 model 文件（新增 document.py, retrieval_trace.py, usage.py）
- ❌ Memory Agent model 写的是 `tongyi-xiaomi-analysis-flash` → 实际是 `deepseek-v4-flash`
- ❌ 缺少：Celery 异步任务、健康检查、Request ID、限流、文档 RAG、RetrievalTrace、Toast

这会导致其他 AI 编程助手（Codex）基于错误假设修改代码。

**3. init.sql 是目录而非文件**

`docker-compose.yml` 将 `./init.sql:/docker-entrypoint-initdb.d/init.sql` 映射为文件，但 `init.sql` 实际是一个空目录。Docker 启动时会产生错误（目录无法作为 SQL 文件执行）。

**4. README 信息部分过期**

- "99 个测试" → 实际 147 个
- "无速率限制和成本治理" → 已实现
- 项目结构缺少：`middleware/rate_limit.py`、`models/retrieval_trace.py`、`models/usage.py`、`composables/useToast.js`、`components/ToastContainer.vue`

**5. 前端未消费 RAG citations SSE 事件**

后端已经发送 `{"citations": [...]}` SSE 事件,但前端 `InputField.vue` 只处理 `data.content`、`data.audio`、`data.error`，citations 事件被静默忽略。RAG 引用链路在 UI 层断开——用户看不到检索来源。

**6. CI 未配置 Redis/Celery 服务**

GitHub Actions workflow 只有 PostgreSQL service container，没有 Redis。限流测试和健康检查的 Redis/Celery 部分需要依赖 mock/patch 才能通过，无法在 CI 中验证真实的 Redis 交互。

---

## 三、最能体现"高级后端工程师"能力的设计（更新版）

### 1. Redis Lua 滑动窗口限流 ★新增

```python
# 原子操作：ZREMRANGEBYSCORE + ZADD + ZCARD + EXPIRE 在单次 Redis 调用中完成
# 避免竞态条件，无需分布式锁
lua_script = """
redis.call('ZREMRANGEBYSCORE', key, 0, now - window_ms)
redis.call('ZADD', key, now, member)
local count = redis.call('ZCARD', key)
redis.call('EXPIRE', key, math.ceil(window_ms / 1000))
return count
"""
```

面试中展示这段代码可以证明：理解 Redis 原子性、滑动窗口算法原理、Lua 脚本的应用场景。

### 2. 异步任务的失败分类 + 撤销联动 ★增强

```python
# 4xx ≠ 429：永久故障不重试 + 清空 celery_task_id（允许下次重试）
# 5xx / 429 / 网络错误：临时故障重试 + 保留 celery_task_id（支持撤销）
# 删除时：app.control.revoke(task_id) + 级联删除
```

这是完整的异步任务生命周期管理——创建、执行、重试、撤销、完成，每个状态转换都有明确定义。

### 3. API Usage 的 fire-and-forget 旁路设计 ★新增

```python
def record_api_usage(**kwargs):
    try:
        APIUsage.objects.create(**kwargs)
    except Exception:
        logger.exception('API usage 记录失败')  # 静默失败，不阻塞业务
```

监控代码不能影响业务流程——这是可观测性设计的基本原则。每个 AI 调用点（LLM/TTS/ASR/Embedding）都在对应位置记录 usage。

### 4. 文档处理状态机 ★增强

```
upload → pending ──→ enqueue 失败 → failed（投递失败）
       → pending ──→ processing ──→ completed
                                  ├→ failed（4xx 永久故障，清 celery_task_id）
                                  └→ failed（5xx 重试后仍失败，清 celery_task_id）
删除 → revoke(celery_task_id) → 软撤销（运行中任务检测 doc 不存在则跳过）
```

相比上一版，增加了"投递失败"和"任务撤销"两个状态转换，状态机更完整。

### 5. SystemPrompt 3 层分离 ★新增

工具规则/角色性格/系统框架三层独立，每层有不同的生命周期和修改频率：
- 工具规则：代码常量，随部署变更
- 角色性格+记忆：DB 存储，用户操作变更
- 系统框架：DB 存储，管理员配置变更

这种分层体现了对 LLM prompt engineering 的深入理解——不同来源的 prompt 应该独立注入，而非拼接成一个长字符串。

---

## 四、当前项目的不足与短板（更新版）

### 架构层面

| 问题 | 严重程度 | 说明 |
|------|---------|------|
| **WSGI + 同步视图 + 线程内嵌 asyncio** | 🔴 高 | **三连 Review 未修复**。线程安全、连接泄漏、事件循环冲突 |
| **AGENTS.md 严重过时** | 🔴 高 | 包含错误的 `Character.profile` 约定、平台切换方式、模型列表，会误导其他 AI agent |
| **init.sql 是目录非文件** | 🟡 中 | docker-compose 映射失败，首次启动 PG 初始化脚本不执行 |
| **无 API 版本化** | 🟡 中 | 32+ 端点直接挂在 `/api/` 下 |
| **SSE 背压控制缺失** | 🟡 中 | `queue.Queue()` 无 maxsize，`mq.put_nowait()` 内存无界 |
| **前端未消费 RAG citations** | 🟡 中 | 后端发送 `citations` SSE 事件，前端静默忽略 |
| **CI 无 Redis 服务** | 🟡 中 | 限流/健康检查中 Redis 相关测试在 CI 中依赖 mock |

### 数据层面

| 问题 | 说明 |
|------|------|
| **数据库事务一致性** | Message 保存和 Memory 更新没有事务保证；Memory 触发和 Message 创建在 `event_stream` 中解耦 |
| **并发控制** | 同一用户同时发送多条消息无幂等键、无去重 |
| **APIUsage 无数据保留策略** | usage 数据无限增长，无定时清理或归档机制 |

### 测试层面

| 问题 | 说明 |
|------|------|
| **TTS 无测试** | TTS WebSocket 连接在测试中 mock，实际音频流管道未验证 |
| **Profile 更新无测试** | 头像裁剪、个人信息更新未覆盖 |
| **Voice 管理无测试** | 阿里云 API 调用的 create/list/delete voice 函数无测试 |
| **chat SSE 流无测试** | 流式响应的 SSE 事件格式、TTS 音频块交织、citations 事件未验证 |
| **无集成测试** | 所有测试都是单元测试，无端到端的 HTTP → DB → AI 全链路测试 |
| **CI 无 lint/format 步骤** | 无代码风格检查，PR review 负担重 |

> 测试数量：48 → 99 → **147**（+48），覆盖率持续提升。新增模块（rate_limit、retrieval_trace、document_processing、admin、health）均有测试覆盖。主要缺口：TTS、Voice 管理、SSE 流、Profile 更新。

### 可观测性

| 项目 | 状态 |
|------|------|
| **健康检查端点** | ✅ 三组件检测（DB + Redis + Celery）|
| **请求 ID 追踪** | ✅ + 耗时日志 |
| **结构化日志** | ✅ RotatingFileHandler + Request ID |
| **API 使用量追踪** | ✅ APIUsage 模型记录 4 类 AI 调用 |
| **错误率告警** | ❌ 缺失 |
| **API 访问日志持久化** | ❌ 缺失（middleware 层可记录 method/path/status/duration 到 DB）|
| **AI 调用成功率 Dashboard** | ❌ APIUsage 数据有但无可视化 |

### 运维与 DevOps

| 项目 | 状态 |
|------|------|
| GitHub Actions CI | ✅ pytest 自动运行（无 Redis 服务）|
| Docker 容器化 | 🟡 仅 infrastructure（PG+Redis），应用本身无 Dockerfile |
| docker-compose 一键部署 | 🟡 仅数据库，不含 Django Web + Celery Worker + Nginx |
| CD Pipeline | ❌ |
| 数据库迁移自动化 | ❌ 手动 migrate |
| 静态资源 CDN | ❌ |
| 代码风格检查 | ❌ 无 lint/format |
| Pre-commit hooks | ❌ |

---

## 五、从面试官视角，项目还缺少哪些"真正有含金量"的内容

### P0 — 面试必问但当前缺失

1. **数据库事务与一致性保证**（三连 Review 仍未解决）
   - Message 保存和 Memory 更新在不同位置执行，没有事务保证
   - **建议**：`transaction.atomic()` + 异步任务队列保证最终一致性

2. **并发控制**（三连 Review 仍未解决）
   - 同一用户同时发多条消息会怎样？当前没有幂等键、没有去重
   - **建议**：前端发送后禁用按钮 + 后端加幂等键

3. **系统容量评估**（仍未做）
   - 至少做一次压测（locust/wrk），有 QPS/延迟数据在面试中是强加分项

4. **WSGI + asyncio 架构风险**（三连 Review 未修复）
   - 面试官如果问 Django async 会直接追问这个点
   - **建议**：短期方案 — 至少给 `queue.Queue()` 加 `maxsize=100`；长期方案 — 考虑迁移到 Daphne/ASGI 或在 Celery 中处理 TTS WebSocket

### P1 — 体现技术深度的加分项

5. **流式响应的背压控制**（三连 Review 仍未解决）
   - `queue.Queue()` 无大小限制 → `queue.Queue(maxsize=100)` + 生产者阻塞

6. **SSE 连接管理**（仍未解决）
   - 无超时、无心跳、无法检测客户端断开
   - 新增：citations 事件已发送但前端未消费 ← 这是优先修复项

7. **API 版本化**（三连 Review 仍未解决）
   - 32+ 端点，面试官大概率会问"如果 API 要破坏性变更怎么办"

8. **前端 RAG citations 展示**（本次新增缺口）
   - 后端链路完整，前端断开。需要在聊天气泡中展示引用来源

9. **AGENTS.md 修复**（本次新增紧急项）
   - 错误的 `Character.profile` 约定可能导致其他 AI agent 写出 bug

10. **APIUsage 数据保留策略**（本次新增）
    - 无 TTL、无归档、无聚合，表会无限增长

---

## 六、哪些像 Demo，哪些像生产项目（更新版）

### 像 Demo 的地方（面试减分项）

| 特征 | 说明 | 趋势 |
|------|------|------|
| **WSGI + threading + asyncio.run** | 生产项目不会在同步视图中创建裸线程跑 asyncio | → 三连未修复 |
| **AGENTS.md 过时** | 错误的架构描述可能造成 bug | ← 新发现 |
| **init.sql 是空目录** | Docker 启动报错 | ← 新发现 |
| **前端未展示 RAG 引用** | 后端完整但前端断开，用户看不到来源 | ← 新发现 |
| **无 API 版本化** | 32+ 端点直接挂 `/api/` | → 三连指出 |
| **手动 offset 分页** | 无 `PageNumberPagination`、无 Cursor 分页 | → 三连指出 |
| **CI 无 Redis** | 限流/健康检查的 Redis 测试无法在 CI 中验证 | ← 新发现 |
| **管理后台插入 RAG 文档** | `insert_documents.py` 仍需手动执行 | → 未变 |
| **无应用 Dockerfile** | 部署仍需手动配置环境 | → 上次有 Dockerfile 但被移除 |

### 像生产项目的地方（面试加分项）

| 特征 | 说明 | 趋势 |
|------|------|------|
| **JWT 双 Token + 订阅者队列刷新** | 真实产品设计 | → 稳定 |
| **Redis Lua 原子限流** | 滑动窗口 + fail-open + 多规则 | ⬆ 新增 |
| **API 使用量追踪** | fire-and-forget + 5 个调用点全覆盖 | ⬆ 新增 |
| **Celery 异步任务 + 分类重试 + 撤销** | 完整生命周期管理 | ⬆ 增强 |
| **Request ID + 请求耗时** | Middleware → 日志 → Response header 全链路 | ⬆ 增强 |
| **健康检查三组件** | DB + Redis + Celery 独立检测 + 降级语义 | ⬆ 增强 |
| **RAG 引用可追溯** | RetrievalTrace 落库 + 来源标记 | ⬆ 新增 |
| **系统知识库增量更新** | hash 对比跳过未变 chunk | ⬆ 新增 |
| **文档处理状态机** | pending→processing→completed/failed + 撤销 | ⬆ 增强 |
| **前端 Toast 系统** | 模块级单例 + readonly + 上限控制 | ⬆ 新增 |
| **Dual-DB 测试策略** | 测试 PG 同引擎 | → 稳定 |
| **文件上传多层防御** | 前端校验 → 魔数字节 → 路径遍历 | → 稳定 |
| **Nginx + Gunicorn + Unix Socket** | 标准部署范式 | → 稳定 |
| **GitHub Actions CI** | 147 测试自动运行 | ⬆ 新增 |
| **processId 输出中断** | 忽略旧 SSE 响应 | → 稳定 |

---

## 七、技术深度评分（更新版）

| 维度 | 上次评分 | 本次评分 | 变化 | 说明 |
|------|---------|---------|------|------|
| **后端基础（CRUD/认证/部署）** | 8/10 | 9/10 | +1 | Toast、Admin、平台自动检测补齐前端工程化 |
| **数据库设计** | 8/10 | 9/10 | +1 | APIUsage、RetrievalTrace、content_hash 增量更新 |
| **异步编程** | 7/10 | 8/10 | +1 | 任务撤销+生命周期管理，但 WSGI+asyncio 仍短板 |
| **AI Agent 设计** | 8/10 | 9/10 | +1 | SystemPrompt 3 层分离 + citations 事件 |
| **RAG 实现** | 8/10 | 9/10 | +1 | 增量更新 + RetrievalTrace + JOIN 查询 + citations |
| **流式处理** | 7/10 | 7/10 | 0 | 仍缺背压控制和 SSE 连接管理 |
| **工程化** | 7/10 | 9/10 | +2 | CI/CD + 限流 + 使用量追踪 + Toast + 健康检查增强 |
| **安全** | 7/10 | 8/10 | +1 | Redis Lua 限流 + SECRET_KEY 强制检查 + fail-open |

**综合评分：8.5/10**（上次：7.1/10）

---

## 八、社招竞争力评估（更新版）

| 目标岗位 | 上次 | 本次 | 说明 |
|---------|------|------|------|
| **Java 后端（P6/高级）** | ⚠️ 偏弱 | ⚠️→✅ 改善 | Redis Lua 限流 + 异步任务生命周期是可迁移的亮点 |
| **Java 后端（P5/中级）** | ✅ 可竞争 | ✅ 有竞争力 | 项目完整度大幅提升，限流/追踪/CI 均可展开讨论 |
| **AI 应用工程师（全栈）** | ✅ 竞争力增强 | ✅ 竞争力强 | 成本治理 + RAG 引用追溯 + Toast 系统是实质提升 |
| **Python 后端（AI 方向）** | ✅ 竞争力增强 | ✅ 竞争力强 | 147 测试 + CI + 限流 + API usage 接近生产标准 |
| **创业公司 / AI Startup** | ✅ 竞争力强 | ✅ 非常强 | 能独立完成完整产品链路 + 成本治理 + 可观测性 |

---

## 九、性价比最高的改进建议（Top 8）

| 优先级 | 改进 | 预计时间 | 面试收益 |
|--------|------|---------|---------|
| **1** | 修复 AGENTS.md（更新 profile 约定、platform 配置、模型列表、新功能） | 20 分钟 | ⭐⭐⭐⭐ |
| **2** | 前端消费 RAG citations SSE 事件（聊天气泡展示来源） | 1 小时 | ⭐⭐⭐⭐⭐ |
| **3** | 修复 init.sql（删除空目录或创建实际 SQL 文件初始化 pgvector） | 5 分钟 | ⭐⭐⭐ |
| **4** | 更新 README 最新数据（147 测试、限流、citations、Toast） | 20 分钟 | ⭐⭐⭐ |
| **5** | `queue.Queue(maxsize=100)` — SSE 背压控制（最小改动） | 10 分钟 | ⭐⭐⭐⭐ |
| **6** | CI 添加 Redis 服务（验证限流和健康检查的 Redis 路径） | 15 分钟 | ⭐⭐⭐ |
| **7** | APIUsage 添加数据保留策略（按天聚合 + 定时清理原始数据） | 1 小时 | ⭐⭐⭐ |
| **8** | WSGI+asyncio 短期修复：给 thread 添加 daemon=True + atexit 清理 | 30 分钟 | ⭐⭐⭐⭐ |

---

## 十、总结

从 2026-05-31 到 2026-06-11 的 11 天里，项目取得了超出预期的工程化进步：

- **测试：** 99 → 147（+48，+48%），新增 rate_limit、retrieval_trace、document_processing、admin、health 共 5 个测试模块
- **成本治理：** 从零到完整的 Redis Lua 滑动窗口限流 + APIUsage 四类 AI 调用追踪
- **可观测性：** 健康检查从单组件升级为三组件（DB+Redis+Celery）；Request ID 增加耗时日志
- **RAG：** 增量更新（hash 对比避免重复 embedding）+ 引用来源标记 + RetrievalTrace 落库 + SSE citations 事件 + JOIN 查询文档标题
- **可靠性：** celery_task_id 追踪 → 删除撤销 → 投递失败标记 → 4xx/5xx 分类重试
- **前端：** Toast 通知系统 + useImageCropper 复用 + 平台自动检测 + 知识库页面
- **DevOps：** GitHub Actions CI（147 测试自动运行）+ docker-compose 可移植 + SECRET_KEY 强制检查
- **修复了上次 Review 的 10 个问题**

**当前最大的三个问题：**
1. WSGI + threading + asyncio.run 的架构风险（**三连 Review 未修复**，面试中最容易被追问的短板）
2. AGENTS.md 严重过时（会导致其他 AI agent 基于错误信息修改代码）
3. 前端未消费 RAG citations SSE 事件（后端完整链路在前端断开）

**性价比最高的三个改进（投入少、面试收益大）：**
1. 前端消费 RAG citations — 在聊天气泡中展示检索来源（1 小时，面试展示价值极高）
2. 修复 AGENTS.md — 防止 AI agent 写出 bug（20 分钟）
3. `queue.Queue(maxsize=100)` — 10 分钟修复一个面试减分项

**一句话评价：**
> 这是一个"工程化程度接近生产标准、可观测性和成本治理从无到有建立"的 AI 应用项目。Redis Lua 限流、API 使用量追踪、RAG 引用可追溯、Celery 任务生命周期管理等改进使项目从"有生产意识"提升到"有生产实践"的水平。147 个测试全部通过、GitHub Actions CI 自动化、健康检查三组件降级、SystemPrompt 3 层架构分离都体现了扎实的工程判断力。剩余短板（WSGI+asyncio 架构风险、AGENTS.md 过时、前端 RAG citations 断链）是下一步补齐的关键点。整体来看，项目在 11 天内的进步幅度超过了过去 9 天——这是一个加速成长的信号。

---

*Review Date: 2026-06-11*
*上次 Review: 2026-05-31*
*评估标准：头部互联网公司 P6（高级工程师）/ AI 应用工程师（社招）*
*测试情况：147 passed, 0 failed, 3 deselected in 6.21s*
*Git 提交：2026-05-31 → 2026-06-11 共 ~35 个 commits*
