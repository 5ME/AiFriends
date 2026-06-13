# AI Friends 项目技术 Review（Codex 2026-05-22 版）

> 视角：资深后端架构师 / AI 应用技术面试官  
> 目标岗位：Java 后端 / AI 应用工程师  
> Review 日期：2026-05-22  
> 评估依据：当前仓库代码、上一版 review、README/CLAUDE/docs、后端测试执行结果。  
> 验证结果：使用 `D:\MyWork\Miniconda3\envs\py312\python.exe -m pytest web/tests/ -v`，并将 pytest 临时目录切到工作区后，后端 **49 个测试全部通过**。

---

## 0. 总体判断

AI Friends 当前已经从“AI 应用 Demo”明显向“有工程意识的 AI 应用项目”迈进了一步。和上一版相比，最关键的变化是：

| 变化 | 当前评价 |
|---|---|
| SQLite → PostgreSQL / pgvector | 运行环境已切到 PostgreSQL，测试环境仍用 SQLite；这是后端求职信号的明显提升 |
| LanceDB → pgvector | RAG 查询已迁移到 `DocumentChunk + VectorField + pgvector <=>` |
| 测试体系 | 已新增 pytest 测试目录，覆盖 auth / friend / character / chat agent / memory agent，49 个测试可跑通 |
| Character.profile 拆分 | 已拆成 `introduction` 和 `system_prompt`，比原先“一字段双用途”更专业 |
| 数据模型优化 | `Friend` 有唯一约束，`Message(friend, -created_at)` 有索引，`Message.input` 改为 JSONField |
| 日志与异常 | 继续保留 `logger.exception()` 和 rotating file 日志 |
| README | 仍明显落后于代码，仍写 SQLite / LanceDB，会影响开源展示和面试可信度 |

一句话评价：

> 当前项目已经达到“AI 应用岗位加分项目”的标准，并且比上一版更接近真实后端工程项目；但还没到“高级后端生产级项目”。剩余短板集中在配置安全、RAG 工程化、异步任务、可观测性、Docker/CI、限流成本控制，以及少数实现细节的正确性。

从招聘视角看，你现在最值得讲的是：

```text
Django + PostgreSQL/pgvector + LangGraph + SSE/TTS 双流 + VAD/ASR/TTS 语音闭环
+ 长期记忆 + JWT 双 Token + pytest 测试体系
```

这已经比普通个人项目强很多。  
但不要把它包装成“高并发生产级平台”，因为目前还没有压测、异步任务队列、request_id、健康检查、限流、Docker 一键部署和用户级 RAG。

---

## 1. 项目亮点：最适合写进简历

### P0：实时语音 AI 交互闭环

项目最强的亮点仍然是这条链路：

```text
浏览器端 VAD
→ PCM16 语音采集
→ DashScope ASR WebSocket
→ LangGraph Chat Agent
→ pgvector RAG / 长期记忆
→ SSE 文本流
→ DashScope TTS WebSocket
→ base64 MP3 音频块
→ 前端 MediaSource 流式播放
```

这不是简单套壳 ChatGPT，而是多组件协同的 AI 应用闭环。它能体现你对实时交互、流式输出、外部 AI 服务编排和前后端协作的理解。

**简历建议：**

> 实现浏览器端 VAD、PCM16 编码、ASR 识别、LangGraph Agent 推理、TTS 合成、MSE 流式播放的端到端实时语音交互链路，支持用户语音输入、AI 文本/语音同步回复与语音打断。

### P0：SSE + TTS WebSocket 双流编排

`chat.py` 里通过 `StreamingHttpResponse` 返回 SSE，同时后端线程内用 `asyncio.gather()` 协调：

- LLM token 流；
- TTS WebSocket 发送文本；
- TTS WebSocket 接收音频；
- SSE 向前端交错推送文本和音频。

这个点比普通 API CRUD 更能体现后端复杂度，因为它涉及 I/O 编排、流式协议、浏览器播放队列和异常处理。

**简历建议：**

> 基于 Django SSE 与 DashScope TTS WebSocket 实现文本/音频双流式输出，单次聊天请求同时返回 LLM token 增量和 base64 音频块，前端通过 Media Source Extensions 实时播放。

### P0：LangGraph Agent + Tool Calling + pgvector RAG

当前 Chat Agent 使用 LangGraph 构建 `agent -> tools -> agent` 循环，并绑定：

- `get_time`
- `search_knowledge_base`

RAG 已从 LanceDB 迁移到 PostgreSQL + pgvector，使用 `DocumentChunk.embedding <=> query_embedding` 做向量距离排序。

这对 AI 应用岗位很加分，因为它说明你不是只会调 LLM，而是把 Agent、工具、向量库和业务数据库结合起来。

**简历建议：**

> 基于 LangGraph 构建支持 Tool Calling 的 Chat Agent，集成 PostgreSQL pgvector 向量检索，实现角色对话中的 RAG 增强回答。

### P0：PostgreSQL / pgvector 迁移

上一版最大短板之一是 SQLite。当前代码已经切到运行环境 PostgreSQL，测试环境用 SQLite，并增加了：

- `Friend(user_profile, character)` 唯一约束；
- `Friend(user_profile)` 索引；
- `Message(friend, -created_at)` 索引；
- `DocumentChunk.embedding` pgvector 字段；
- PostgreSQL 连接健康检查配置 `CONN_HEALTH_CHECKS=True`。

这对 Java 后端岗位是重要加分项，因为它能把项目从“Demo 数据库”拉到真实互联网后端会讨论的数据库层面。

**简历建议：**

> 将项目主库从 SQLite 迁移至 PostgreSQL，并基于 pgvector 替换独立向量库；为好友关系、消息查询增加唯一约束和复合索引，提升数据一致性与聊天历史查询效率。

### P0：pytest 测试体系

当前已有 49 个后端测试，并且本次验证通过。覆盖范围包括：

- 登录 / 注册 / refresh token / 登出 / 获取用户信息；
- 好友创建、去重、删除、列表、is_friend、计数；
- 角色创建、编辑、删除、权限校验；
- LangGraph 路由、Tool Calling、RAG tool；
- SSE 事件格式、`[DONE]` 标记、消息落库；
- Memory Agent 更新和图逻辑。

这点非常重要。上一版“零测试”是硬伤，现在已经变成求职亮点。

**简历建议：**

> 引入 pytest-django + model_bakery 构建后端测试体系，覆盖认证、好友关系、角色 CRUD、Chat Agent/SSE、Memory Agent 等核心链路，并通过 mock 隔离 LLM 与 TTS 外部依赖。

### P1：Character 展示简介与系统提示词拆分

原先 `Character.profile` 同时承担“用户可见简介”和“LLM system prompt”。现在已拆成：

- `introduction`：前端展示；
- `system_prompt`：发送给 LLM。

这是很好的产品/工程边界修复，能体现你有维护长期项目的意识。

**简历建议：**

> 将角色公开简介与 LLM 系统提示词拆分为独立字段，避免展示内容与模型控制指令耦合，提升角色配置的可维护性和安全边界。

### P1：JWT 双 Token + 前端并发刷新队列

前端 `api.js` 仍保留 access token 内存存储、refresh token httpOnly cookie、并发 401 刷新队列。这是很真实的业务系统细节。

**简历建议：**

> 设计 JWT access/refresh 双令牌认证机制，access token 存于前端内存，refresh token 存于 httpOnly cookie，并通过 subscriber queue 解决并发 401 下的重复刷新问题。

---

## 2. 项目中体现出的工程能力与架构能力

### 已经体现出的能力

| 能力 | 代码/设计证据 | 招聘视角评价 |
|---|---|---|
| 全栈交付能力 | Django + Vue + Vite + Pinia + Tailwind + 部署文档 | 能独立完成产品闭环 |
| AI 应用整合能力 | LangGraph、pgvector、ASR、TTS、Memory、SSE | AI 应用岗位强相关 |
| 流式系统意识 | SSE、WebSocket、MSE、Nginx 缓冲关闭 | 有真实复杂度 |
| 数据库工程意识 | PostgreSQL、pgvector、索引、唯一约束 | 比上一版明显进步 |
| 测试意识 | 49 个 pytest 测试全绿 | 已跨过 Demo 项目第一道工程门槛 |
| 认证安全意识 | JWT 双 Token、httpOnly cookie、并发刷新 | 后端基础较扎实 |
| 可维护性意识 | `introduction/system_prompt` 拆分，日志体系，设计文档 | 有迭代和重构意识 |
| 学习迁移能力 | Java 背景独立完成 Python/Vue/AI 工程 | 对招聘方是正面信号 |

### 仍未充分体现的能力

| 能力缺口 | 影响 |
|---|---|
| 异步任务架构 | Memory 仍同步执行，用户上传 RAG 未来也需要队列 |
| 生产配置管理 | `SECRET_KEY`、`DEBUG`、`ALLOWED_HOSTS`、生产 IP 仍硬编码 |
| 可观测性 | 有日志，但缺 request_id、指标、链路追踪、耗时统计 |
| 成本治理 | LLM / ASR / TTS 没有用户限额和限流 |
| Docker/CI | 新人不能一键启动，测试没有自动化流水线证明 |
| RAG 产品化 | pgvector 有了，但仍是全局预置知识库，不是用户级知识库 |
| 高并发证据 | 没有压测报告，不能讲高并发 |

---

## 3. 最能体现“高级后端工程师”能力的设计

### 3.1 SSE + WebSocket 的实时链路编排

这是项目里最有技术深度的部分。

真实难点包括：

- LLM token 是流式生成；
- TTS 需要边接收文本边返回音频；
- 后端需要把文本和二进制音频统一封装成 SSE JSON；
- 前端需要通过 MSE 队列避免 `SourceBuffer` 并发写入；
- 用户语音输入时需要打断旧输出；
- Nginx 代理默认缓冲会破坏实时性，需要 `X-Accel-Buffering: no`。

这部分面试可以讲得很深，尤其适合 AI 应用工程师和偏平台后端岗位。

但要诚实说明当前限制：

- 用户关闭页面后，后端 LLM/TTS 调用未真正取消；
- 每个请求创建线程，长连接多时会占用 worker 资源；
- `queue.Queue()` 无上限，缺少背压；
- TTS 失败没有文本-only 降级；
- 没有首 token 延迟、TTS 首包延迟指标。

### 3.2 PostgreSQL + pgvector 合并业务库与向量库

从 LanceDB 切到 pgvector是一个对求职更友好的方向：

- 运维更简单；
- 业务数据与向量数据在同一个数据库；
- 未来做用户级 RAG 时可以用 `user_id/document_id` 做权限过滤；
- Java 后端也更容易讨论 PostgreSQL、索引、事务和 SQL。

但当前 pgvector 仍处于最小实现：

- `DocumentChunk` 只有 `content/embedding/created_at`，缺少 `document_id/user_id/source/chunk_index`；
- 没有 HNSW / IVFFlat 向量索引；
- migration 没有显式创建 `vector` 扩展；
- 只有 mock 测试，没有真实 PostgreSQL 集成测试；
- 查询是全局知识库，不支持用户隔离。

面试时可以说：

> 当前完成了从独立向量库到 pgvector 的迁移，下一步会给 DocumentChunk 增加文档元数据、用户权限字段和 HNSW 索引，并把文档处理改为异步任务。

### 3.3 测试体系覆盖核心链路

这是这轮最重要的工程化进步。你现在可以在面试中明确说：

> 我补了后端自动化测试，覆盖认证、角色、好友、Chat Agent、SSE 事件格式、Memory Agent，并通过 mock 隔离外部 LLM/TTS 调用。

这会显著改善面试官对项目“只是 Demo”的判断。

但当前测试仍有两个问题：

- 一些权限失败用例期望 `500`，例如非作者查看/编辑/删除角色，这在真实 API 里应该是 `403` 或 `404`；
- 测试环境用 SQLite，运行环境用 PostgreSQL，能提升本地稳定性，但也可能漏掉 PostgreSQL/pgvector 的真实 SQL 问题。

### 3.4 Character `introduction/system_prompt` 拆分

这是一个很好的架构修正。它体现你理解：

- 用户展示字段和模型控制字段不应混在一起；
- 简介是产品信息；
- system prompt 是模型行为配置；
- 两者权限、长度、审查和安全风险不同。

这比上一版 `profile.split('\n')[0]` 的约定成熟很多。

### 3.5 JWT 并发刷新队列

前端并发刷新仍然是可讲的工程细节。它可以延伸到：

- access token 不落 localStorage；
- refresh token 用 httpOnly cookie；
- 多请求同时 401 时只发一次 refresh；
- 刷新失败统一 logout；
- 登录接口 401 不触发 refresh。

不过面试官会继续追问 CSRF 和 Cookie 策略，这部分还要准备。

---

## 4. 当前不足与短板

### P0：`SystemPrompt.title` 枚举值与查询条件不匹配

这是当前我看到的最值得立即修的代码正确性问题。

模型里：

```python
class Title(models.TextChoices):
    REPLY = 'reply', '回复'
    MEMORY = 'memory', '记忆'
```

但代码里仍然查询：

```python
SystemPrompt.objects.filter(title__exact='回复')
SystemPrompt.objects.filter(title__exact='记忆')
```

这会导致系统提示词可能查不到，因为数据库实际值应是 `'reply'` / `'memory'`，中文只是 label。

影响：

- Chat Agent 可能缺少全局回复 prompt；
- Memory Agent 可能缺少记忆总结 prompt；
- 测试未覆盖此问题，因为测试没有创建 `SystemPrompt` 数据并验证拼接结果。

优先级：**P0，立即修。**

建议：

```python
SystemPrompt.objects.filter(title=SystemPrompt.Title.REPLY)
SystemPrompt.objects.filter(title=SystemPrompt.Title.MEMORY)
```

### P0：配置安全仍然不达标

`settings.py` 仍硬编码：

- `SECRET_KEY`
- `DEBUG = True`
- `ALLOWED_HOSTS`
- 生产 IP
- `MEDIA_URL`

虽然已有 `.env.example`，但其中也缺少：

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `CORS_ALLOWED_ORIGINS`
- `MEDIA_BASE_URL`

面试官会问：

- 生产环境怎么保证 `DEBUG=False`？
- 密钥是否进过 git 历史？
- 本地、测试、生产配置怎么区分？
- 为什么 README/部署文档还要求手工改 `DEBUG` 和前端 `platform`？

优先级：**P0。**

### P0：README 仍然过期

当前 README 仍写：

- 后端：SQLite；
- 向量存储：LanceDB；
- RAG：LanceDB 向量搜索；
- 模型结构里没有 `document.py`；
- 没有说明 pytest 49 tests；
- 没有说明 PostgreSQL / pgvector；
- 没有 `.env.example` 使用方式；
- 没有测试运行方式。

这会严重影响 GitHub 展示和面试可信度。  
代码已经进化了，README 还停在上一代，这很容易让招聘方觉得项目管理不严谨。

优先级：**P0。**

### P1：pgvector RAG 只是最小实现，不是工程化 RAG

当前 RAG 已经从 LanceDB 换成 pgvector，这是进步。但仍有明显短板：

| 问题 | 影响 |
|---|---|
| `DocumentChunk` 无 `document_id/user_id` | 无法做用户级权限隔离 |
| 无 `source/chunk_index/token_count` | 无法返回引用来源和管理 chunk |
| 无向量索引 | 数据量上来后查询性能不稳 |
| 无文档状态表 | 无法展示上传、解析、失败、重试状态 |
| 插入脚本会清空全表 | 不适合多文档、多用户 |
| 没有 rerank | 检索质量有限 |
| 没有真实召回评测 | 不能证明 RAG 效果 |

优先级：**P1。**

### P1：测试有了，但测试质量还可以继续提高

测试体系已经是重大进步，但还有几个真实工程问题：

1. 权限失败期望 `500`，这不合理。非作者访问/编辑/删除应是 `403` 或 `404`。
2. 测试环境用 SQLite，运行环境用 PostgreSQL，pgvector SQL 没有被真实验证。
3. 没有 coverage 报告。
4. 没有 CI。
5. 没有前端测试或 E2E。
6. 没有 ASR 端点测试。
7. 没有文件上传安全测试。

优先级：**P1。**

### P1：Memory 仍同步执行

聊天结束后，达到 10 条消息时仍同步调用：

```python
update.update_memory(friend)
```

这会把额外 LLM 摘要调用挂在聊天请求尾部。虽然 SSE 已经 `[DONE]`，但服务端资源仍被占用。

更成熟的方案：

```text
Chat 结束写入 Message
→ 投递 Celery / Redis / RabbitMQ 任务
→ Worker 调用 Memory Agent
→ 更新 Friend.memory
→ 记录任务状态、失败重试、耗时
```

优先级：**P1。**

### P1：缺少 request_id、指标和健康检查

目前有日志，但还不够生产化。

真实公司更希望看到：

- 每个请求有 `request_id`；
- 响应头返回 `X-Request-ID`；
- 日志记录 user_id / friend_id / endpoint / latency；
- LLM 记录 token 消耗；
- SSE 记录首 token 延迟；
- TTS 记录首包延迟；
- RAG 记录召回 chunk；
- `/api/health/` 检查 DB / Redis / 外部服务；
- Sentry 或类似错误追踪。

优先级：**P1。**

### P1：限流和成本控制缺失

AI 应用和普通 CRUD 最大不同是：每次请求都可能直接烧钱。

当前没有看到：

- 登录/注册限流；
- 聊天接口限流；
- ASR 文件大小限制；
- TTS 字符数限制；
- 用户每日 token 额度；
- 用户每日语音秒数额度；
- 超额降级策略。

这在面试中一定会被追问。

优先级：**P1。**

### P2：Docker / CI/CD 缺失

当前有 `.env.example`，但没有：

- Dockerfile；
- docker-compose.yml；
- GitHub Actions；
- 一键初始化 PostgreSQL + pgvector；
- 一键插入示例知识库；
- 一键跑测试。

对个人项目不是致命，但对开源展示和工程成熟度有影响。

优先级：**P2。**

---

## 5. 面试官视角：还缺少哪些真正有含金量的内容

按求职价值排序：

| 排名 | 缺口 | 为什么有含金量 |
|---|---|---|
| 1 | 修复 SystemPrompt 枚举查询 bug | 这是直接正确性问题，必须先修 |
| 2 | README / 文档同步更新 | 面试官和 GitHub 访客首先看文档 |
| 3 | 用户级 RAG | AI 应用岗位最值钱的扩展 |
| 4 | Celery / Redis 异步任务 | 证明你理解长耗时任务解耦 |
| 5 | request_id + 健康检查 + 指标 | 生产排障能力核心证据 |
| 6 | 限流与成本治理 | AI 应用区别于普通 Web 的关键 |
| 7 | Docker Compose + CI | 提升开源可复现和团队协作可信度 |
| 8 | PostgreSQL/pgvector 集成测试 | 证明迁移不是只在 ORM 层跑通 |
| 9 | RAG 评测集 | 从“能检索”升级到“能评估效果” |
| 10 | Java 辅助服务 | 主投 Java 后端时增强技术栈匹配 |

---

## 6. 哪些地方像 Demo，哪些地方接近真实生产项目

### 更接近真实生产项目的地方

| 点 | 理由 |
|---|---|
| PostgreSQL 运行库 | 摆脱 SQLite Demo 感 |
| pgvector | 向量检索与业务库统一，运维更真实 |
| pytest 49 tests | 已有核心链路回归测试 |
| JWT 双 Token | 认证设计方向正确 |
| refresh 并发队列 | 处理真实竞态问题 |
| SSE + TTS WebSocket | 有实时系统复杂度 |
| MSE 音频队列 | 处理浏览器流式播放细节 |
| Character 字段拆分 | 产品字段和模型控制字段解耦 |
| 数据库约束/索引 | 有数据一致性和查询优化意识 |
| 日志系统 | 有基础排障能力 |

### 仍像 Demo 的地方

| 点 | 原因 |
|---|---|
| README 过期 | 文档和代码不一致 |
| 配置硬编码 | 生产配置管理不专业 |
| 无 Docker/CI | 不利于复现和协作 |
| RAG 只有全局知识库 | 不是用户级产品能力 |
| DocumentChunk 元数据太少 | 无权限、无来源、无文档管理 |
| Memory 同步 | 长耗时 AI 任务未异步化 |
| 无限流 | AI 成本不可控 |
| 无 request_id/指标 | 线上问题不可追踪 |
| 权限失败返回 500 | API 语义还不够成熟 |
| 无压测 | 不能讲高并发 |

---

## 7. 冲击 Java 后端 / AI 应用工程师还应补哪些能力

### Java 后端方向

| 优先级 | 能力 | 建议 |
|---|---|---|
| P0 | Spring Boot 3 | 不建议全量重写，可做一个 Java RAG 文档管理 / 额度服务 |
| P0 | PostgreSQL 深度 | 索引、事务、锁、EXPLAIN、连接池、JSONB、pgvector 都要能讲 |
| P0 | Redis | 限流、缓存、refresh token 黑名单、任务状态 |
| P0 | MQ | RabbitMQ / Kafka / RocketMQ，重点讲异步任务、重试、幂等 |
| P1 | JVM 并发 | 线程池、CompletableFuture、虚拟线程、背压 |
| P1 | Spring Security | 对标当前 JWT 双 Token 方案 |
| P1 | Testcontainers | 用 PostgreSQL/Redis 容器跑集成测试 |
| P1 | 可观测性 | Micrometer、Prometheus、Grafana、日志 MDC |

### AI 应用工程师方向

| 优先级 | 能力 | 建议 |
|---|---|---|
| P0 | RAG 工程化 | 上传、解析、切分、embedding、索引、召回、rerank、权限隔离 |
| P0 | Agent 工程化 | Tool schema、工具权限、失败重试、状态持久化 |
| P0 | 流式体验 | 首 token、TTS 首包、取消、断线恢复、文本-only 降级 |
| P1 | PromptOps | prompt 版本、评测集、回归测试 |
| P1 | 成本治理 | token 统计、用户额度、模型路由、小模型摘要 |
| P1 | AI 可观测性 | 每次对话记录模型、token、耗时、RAG 命中 |

---

## 8. 最值得扩展的功能方向：按求职价值排序

### 1. 用户上传文档构建个人 RAG

这是当前最高求职价值方向。

推荐最小闭环：

```text
用户上传文档
→ 创建 UserDocument(status=UPLOADED)
→ 文件存本地/OSS
→ 投递异步任务
→ 解析文档
→ chunk 切分
→ embedding 批处理
→ 写入 DocumentChunk(user_id, document_id, chunk_index, content, embedding)
→ status=COMPLETED
→ Chat Agent 按 user_id / document_id 过滤召回
→ 回复中返回引用来源
```

建议模型：

```text
UserDocument
- id
- owner_id
- title
- file_url
- file_type
- status
- error_message
- chunks_count
- created_at
- updated_at

DocumentChunk
- id
- document_id
- owner_id
- chunk_index
- content
- embedding
- token_count
- metadata
- created_at
```

建议索引：

```sql
CREATE INDEX document_chunk_owner_idx ON web_documentchunk(owner_id);
CREATE INDEX document_chunk_document_idx ON web_documentchunk(document_id);
CREATE INDEX document_chunk_embedding_hnsw
ON web_documentchunk USING hnsw (embedding vector_cosine_ops);
```

### 2. Celery / Redis 异步任务

把以下任务异步化：

- Memory 更新；
- 文档解析；
- embedding；
- 自定义音色创建；
- 用量统计落库；
- RAG 重建。

这对后端岗位非常加分，因为它体现解耦、重试、幂等、任务状态管理。

### 3. 配置安全 + README 更新

这是短平快但收益很大的事情。

立刻做：

- `SECRET_KEY` 环境变量化；
- `DEBUG` 环境变量化；
- README 改成 PostgreSQL / pgvector；
- README 增加测试运行命令；
- README 增加 `.env.example`；
- README 增加已知限制。

### 4. request_id + health check + 指标

建议新增：

- `RequestIdMiddleware`
- `GET /api/health/`
- 日志字段：request_id、user_id、endpoint、latency_ms
- Chat 指标：first_token_latency、total_latency、tokens、tts_latency、rag_hit_count

### 5. 限流与成本控制

建议：

- DRF throttle 或 Redis rate limit；
- 每用户每日 LLM 调用次数；
- 每用户每日 token 数；
- 每用户每日 ASR 秒数；
- 每用户每日 TTS 字符数；
- 超额后返回明确错误。

### 6. 自定义角色音色

产品亮点强，但求职价值略低于用户级 RAG 和异步任务。

需要考虑：

- 音频上传；
- 格式/时长/大小校验；
- DashScope custom voice 任务状态；
- 音色归属用户；
- 删除音色后的角色降级。

### 7. Java 辅助服务

主投 Java 后端时建议做小而清晰的服务，而不是重写全项目。

推荐方向：

- Java Quota Service：用户额度、限流、token 统计；
- Java RAG Document Service：文档上传、状态管理、权限校验；
- Java Gateway：认证、限流、SSE 代理 Python AI 服务。

---

## 9. 高级工程化路线图

### 第 1 阶段：修正与展示专业化，3-5 天

目标：先修面试官一眼能看出来的问题。

- 修复 `SystemPrompt.title` 查询值；
- README 更新为 PostgreSQL / pgvector / pytest；
- `.env.example` 补齐 Django 配置；
- `SECRET_KEY`、`DEBUG`、`ALLOWED_HOSTS` 环境变量化；
- 非作者访问/编辑/删除角色返回 `403/404`，不要返回 500；
- 测试随之改成合理状态码；
- 给测试命令增加 Windows 注意事项，避免默认 TEMP 权限问题。

### 第 2 阶段：RAG 数据模型工程化，1-2 周

目标：让 pgvector RAG 从“能查”变成“能扩展”。

- 增加 `UserDocument`；
- `DocumentChunk` 增加 owner/document/source/chunk_index/token_count；
- migration 创建 pgvector 扩展；
- 增加 HNSW 或 IVFFlat 索引；
- 插入脚本改为按 document 增量插入，不再清空全表；
- Chat Agent 按用户权限过滤；
- 增加真实 pgvector 集成测试。

### 第 3 阶段：异步任务与成本控制，2-3 周

目标：解决 AI 应用长耗时和费用问题。

- 引入 Redis；
- 引入 Celery；
- Memory 更新异步化；
- 文档向量化异步化；
- 增加任务状态表；
- 增加失败重试；
- 增加聊天、ASR、TTS 限流；
- 增加 token / TTS / ASR 用量统计。

### 第 4 阶段：可观测性与运维，2-3 周

目标：让项目更像真实生产系统。

- `request_id` 中间件；
- `/api/health/`；
- 结构化日志；
- Sentry 或类似错误追踪；
- 指标采集；
- 压测报告；
- Dockerfile；
- docker-compose.yml；
- GitHub Actions：pytest + frontend build。

### 第 5 阶段：Java 求职增强，2-4 周

目标：服务于 Java 后端岗位匹配度。

建议做一个 Spring Boot 3 服务：

```text
Java Quota/RAG Service
→ PostgreSQL
→ Redis
→ OpenAPI
→ JUnit 5 + Testcontainers
→ Django 调用 Java API
```

这样能证明你不是只会 Python AI 生态，也能把上一份 Java 后端经验自然接上。

---

## 10. 简历包装建议

### 项目名称

**AI Friends：基于 LangGraph 与 pgvector 的实时语音 AI 角色聊天平台**

### 一句话介绍

独立设计并实现一个支持 AI 角色创建、文本/语音实时对话、RAG 知识检索和长期记忆的全栈 AI 应用，完成前端、后端、Agent 编排、语音链路、PostgreSQL/pgvector 迁移和自动化测试。

### 推荐简历 bullets

- 基于 **Django REST Framework + Vue 3** 实现 AI 角色聊天平台，支持角色创建、好友关系、聊天历史、JWT 登录认证与首页角色探索。
- 基于 **LangGraph** 构建 Chat Agent，支持 Tool Calling，集成时间查询与 pgvector 知识库检索工具，实现 RAG 增强回答。
- 将向量检索从独立 LanceDB 迁移至 **PostgreSQL + pgvector**，新增 `DocumentChunk` 向量模型，并通过 `<=>` 距离排序实现知识库召回。
- 设计 **长期记忆机制**，每 10 条消息触发 Memory Agent 对历史对话进行摘要压缩，并注入后续系统提示词提升多轮对话连续性。
- 实现 **SSE + DashScope TTS WebSocket** 的实时双流输出，单次聊天请求同时推送 LLM 文本增量与 base64 音频块，前端通过 MSE 流式播放。
- 实现浏览器端 **VAD → ASR → LLM → TTS → MSE** 语音闭环，支持用户语音输入、AI 语音回复与语音打断。
- 将角色公开简介与 LLM 系统提示词拆分为 `introduction/system_prompt`，避免展示字段与模型控制字段耦合。
- 为好友关系和消息查询增加数据库约束与索引，包括 `Friend(user_profile, character)` 唯一约束和 `Message(friend, created_at)` 复合索引。
- 引入 **pytest-django + model_bakery** 测试体系，覆盖认证、好友关系、角色 CRUD、Chat Agent/SSE、Memory Agent 等核心链路，外部 LLM/TTS 依赖通过 mock 隔离。
- 设计 JWT 双 Token 认证方案，access token 存于内存，refresh token 存于 httpOnly cookie，并通过 subscriber queue 解决并发 401 刷新问题。

### 暂时不要这样写

在补齐压测、异步任务、Docker/CI、限流和可观测性前，不建议写：

- “高并发生产级 AI 平台”
- “企业级 Agent 系统”
- “完善可观测性”
- “大规模 RAG 知识库”
- “高可用架构”

更稳妥表达：

> 项目已完成 AI 应用核心链路和后端工程化基础，包括 PostgreSQL/pgvector、自动化测试、流式语音交互和 Agent/RAG/Memory；下一阶段重点补齐用户级 RAG、异步任务、可观测性、限流和 Docker/CI。

---

## 11. 真实面试官会怎么看

### 最加分的地方

1. **AI 链路完整**：Agent、RAG、Memory、ASR、TTS、SSE 都有。
2. **实时流式复杂度高**：SSE + WebSocket + MSE 不是普通 CRUD。
3. **PostgreSQL/pgvector 迁移**：从 Demo 数据库进入真实后端讨论范围。
4. **测试体系补齐**：49 个后端测试全绿，是很实在的工程信号。
5. **字段建模优化**：`introduction/system_prompt` 拆分体现产品和模型边界意识。
6. **学习迁移能力强**：Java 背景完成 Python + Vue + AI 工程，有跨栈能力。

### 最容易被质疑的地方

1. `SystemPrompt.title` 查询为什么还用中文 label？
2. README 为什么仍写 SQLite / LanceDB？
3. 为什么非作者访问角色返回 500，而不是 403/404？
4. 用户上传文档 RAG 为什么还没做？
5. Memory 为什么仍同步执行？
6. pgvector 有没有建向量索引？数据量上来怎么办？
7. 用户断开 SSE 后，LLM/TTS 是否继续计费？
8. 如何做 LLM / TTS / ASR 成本控制？
9. 为什么没有 Docker / CI？
10. 有压测数据吗？首 token 延迟、TTS 首包延迟是多少？

---

## 12. 我会追问的技术问题

### 后端 / 系统设计

1. 画出完整聊天链路，从用户点击发送到 AI 语音播放。
2. 为什么前端到后端用 SSE，而不是 WebSocket？
3. 为什么后端到 TTS 用 WebSocket？
4. 当前每个聊天请求创建线程，有什么风险？
5. 如果 100 个用户同时语音聊天，瓶颈在哪里？
6. 用户关闭页面后，如何取消 LLM/TTS 调用？
7. Message 表增长到千万级如何分页和归档？
8. `Friend(user_profile, character)` 为什么要唯一约束？
9. PostgreSQL 连接池和 `CONN_MAX_AGE` 怎么设置？
10. 为什么测试环境用 SQLite，运行环境用 PostgreSQL？风险是什么？

### AI / RAG / Agent

1. 解释 LangGraph 的 `agent -> tools -> agent` 循环。
2. Tool Calling 什么时候触发，什么时候结束？
3. pgvector 的 `<=>` 是什么距离？适合你的 embedding 吗？
4. 为什么 embedding 维度是 1024？
5. DocumentChunk 为什么目前没有 document_id/user_id？
6. 如何做用户级 RAG 权限隔离？
7. 如何设计 chunk size 和 overlap？
8. 如何评估 RAG 命中率和忠实度？
9. Memory 每 10 条总结一次依据是什么？
10. 如何防 prompt injection？

### 工程化 / 安全

1. access token 放内存解决什么问题？
2. httpOnly cookie 能防 XSS 吗？能防 CSRF 吗？
3. refresh token 轮换后旧 token 如何失效？
4. 生产环境如何管理 `SECRET_KEY` 和 DEBUG？
5. 如何给聊天和 ASR 限流？
6. 如何统计单个用户的 token 成本？
7. 如何为 SSE 链路加 request_id？
8. 如何 mock LLM 和 TTS 做自动化测试？
9. Docker Compose 会包含哪些服务？
10. 如果你用 Java 拆一个服务，会拆哪一块，为什么？

---

## 13. 技术深度评分

| 方向 | 评分 | 理由 |
|---|---:|---|
| AI 应用链路 | 8.5/10 | Agent/RAG/Memory/ASR/TTS/SSE 链路完整 |
| 后端工程化 | 6.8/10 | PostgreSQL、索引、测试都有了，但缺异步、配置、CI、可观测 |
| 数据库设计 | 6.8/10 | 已有约束/索引/pgvector，但 RAG 元数据和向量索引不足 |
| 系统设计表达 | 7/10 | 能讲流式链路和 Agent 边界，但缺容量评估 |
| 测试能力 | 7/10 | 49 tests 是明显进步，但集成测试/CI/覆盖率仍缺 |
| 安全治理 | 5/10 | JWT 设计不错，但配置硬编码、CSRF、限流仍缺 |
| 可观测性 | 5/10 | 有日志，无 request_id/指标/追踪 |
| Java 岗位匹配 | 6/10 | 后端基本盘增强，但项目主体仍是 Python |
| AI 岗位匹配 | 8/10 | 已达到明显加分标准 |

---

## 14. 社招竞争力判断

| 岗位方向 | 当前竞争力 | 判断 |
|---|---|---|
| Java 后端初中级 | 明显加分 | PostgreSQL、测试、认证、业务闭环能说明后端能力 |
| Java 高级后端 | 仍不够 | 缺高并发、异步任务、可观测性、Java 技术栈直接证据 |
| AI 应用工程师 | 有较强加分 | 实时语音 + Agent + RAG + Memory 很匹配 |
| AI Agent 工程师 | 有基础 | 需要补 tool 可靠性、评测、状态持久化、多 Agent |
| 全栈工程师 | 竞争力较好 | 前后端完整，交互复杂度高 |
| 开源展示项目 | 有吸引力但需整理 | README 过期、缺 Docker/CI/截图/演示 |

综合判断：

```text
AI 应用亮点：8.5/10
后端工程化：6.8/10
系统设计表达：7/10
简历吸引力：8/10
当前社招竞争力：P5+ 到 P6 入门之间
补齐用户级 RAG + Celery/Redis + 可观测性 + Docker/CI 后：更接近 P6 水平
```

---

## 15. GitHub / 开源社区吸引力

当前项目具备开源吸引力，因为它有：

- AI 角色；
- 实时语音聊天；
- LangGraph Agent；
- pgvector RAG；
- 长期记忆；
- 前后端完整闭环；
- 后端测试。

但开源展示还需要补：

- README 更新；
- 架构图；
- 实时语音链路图；
- 截图 / GIF / 演示视频；
- Docker Compose；
- `.env.example` 完整说明；
- 测试 badge；
- GitHub Actions；
- 示例数据插入命令；
- Known Limitations；
- Roadmap。

如果这些补齐，它会从“个人项目”更像一个可复现的开源 AI 应用模板。

---

## 16. 是否达到“AI 岗位加分项目”标准

结论：**达到，而且比上一版更稳。**

已达到的原因：

- 有实时语音；
- 有 Agent；
- 有 Tool Calling；
- 有 pgvector RAG；
- 有长期记忆；
- 有 JWT 认证；
- 有 PostgreSQL；
- 有自动化测试；
- 有前后端完整闭环；
- 有部署路径。

还不是强加分顶格项目的原因：

- RAG 不是用户级；
- Memory 未异步化；
- 无成本治理；
- 无 RAG 评测；
- 无 request_id/指标；
- 无 Docker/CI；
- 无压测；
- 配置安全不完整。

面试时建议这样定位：

> 我这个项目不是简单调用大模型 API，而是完整实现了一个实时语音 AI 角色聊天系统。核心链路包括浏览器 VAD、ASR、LangGraph Agent、pgvector RAG、长期记忆、SSE 文本流和 TTS 音频流。后续我又补了 PostgreSQL/pgvector 迁移、模型字段拆分、数据库索引约束和 49 个后端自动化测试。目前它已经具备 AI 应用工程项目的核心复杂度；下一阶段我会重点补用户级 RAG、异步任务、成本治理和可观测性。

这比单纯说“生产级”更可信，也更容易打动 Tech Lead。

---

## 17. 最终优先级建议

### 立即做

1. 修复 `SystemPrompt.title` 查询值。
2. 更新 README：PostgreSQL / pgvector / pytest / `.env.example`。
3. `SECRET_KEY`、`DEBUG`、`ALLOWED_HOSTS` 环境变量化。
4. 把非作者访问角色的 500 改为 403/404。

### 两周内做

1. `DocumentChunk` 增加 user/document/source/chunk_index 元数据。
2. 增加 pgvector HNSW 索引。
3. 增加真实 PostgreSQL/pgvector 集成测试。
4. 增加 `/api/health/`。
5. 增加 request_id 日志中间件。

### 一个月内做

1. 用户上传文档 RAG 最小闭环。
2. Celery + Redis，把 Memory 和文档向量化异步化。
3. 增加限流和 token/TTS/ASR 用量统计。
4. Docker Compose。
5. GitHub Actions 跑 pytest + frontend build。

### 如果主投 Java 后端

优先新增一个小型 Spring Boot 服务，不重写全项目：

```text
Java Quota/RAG Service
→ 用户额度 / 文档状态 / 限流 / 管理后台 API
→ PostgreSQL + Redis
→ JUnit 5 + Testcontainers
→ Django 调用 Java 服务
```

这样能把你的 Java 背景和 AI 项目自然连接起来，求职叙事会更完整。

