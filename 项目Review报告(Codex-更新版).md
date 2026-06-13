# AI Friends 项目技术 Review（Codex 更新版）

> 视角：资深后端架构师 / AI 应用技术面试官  
> 目标岗位：Java 后端 / AI 应用工程师  
> Review 日期：2026-05-15  
> 评估依据：当前仓库代码、README、上次 Codex review 报告、`docs/superpowers` 中的迭代记录与路线图。

## 0. 总体判断

AI Friends 是一个完整度较高的个人 AI 应用实践项目：用户可以创建 AI 角色，与角色建立好友关系，并通过文本和语音进行实时对话。系统包含 Agent、RAG、长期记忆、ASR、TTS、SSE 流式输出、JWT 双 Token 认证、Vue 前端和 Django 后端。

和上次 review 相比，项目已经有明显工程化改进：

| 已改进项 | 当前判断 |
|---|---|
| 裸 `except:` | 已基本消除，后端 view 普遍改为 `except Exception` + `logger.exception()` |
| 日志系统 | 已增加 Django `LOGGING`，支持 console + rotating file |
| HTTP 状态码 | 多数接口已从统一 200 改为更合理的 400 / 401 / 404 / 409 / 500 |
| README | 已比上次更专业，结构、功能、部署路径更清晰 |
| 好友侧异常体验 | 角色被删除后的聊天失败不再完全沉默 |
| 迭代意识 | `docs/superpowers` 中已有路线图、设计文档和优先级拆解 |

但项目距离“高级后端工程化项目”仍有距离：

| 主要短板 | 当前状态 |
|---|---|
| 测试体系 | `backend/web/tests.py` 仍为空，前后端都没有有效测试 |
| 数据库 | 仍使用 SQLite，无法支撑生产级并发叙事 |
| 异步任务 | Memory 更新仍同步挂在聊天流结束后 |
| 用户级 RAG | 仍是管理员预置知识库，尚无用户上传、权限隔离、任务状态 |
| 配置管理 | `SECRET_KEY`、`DEBUG`、公网 IP、模型名等仍有硬编码 |
| 可观测性 | 有日志，但缺 request_id、耗时、token 成本、链路追踪、指标面板 |
| 安全治理 | 有 httpOnly refresh token，但 CSRF、限流、密钥轮换、上传安全还不足 |

一句话判断：

> 这是一个“AI 应用链路很有亮点，工程化已开始补课，但还未达到生产级后端项目标准”的个人项目。它已经足够作为 AI 应用岗位加分项，但如果主投 Java 高级后端，还需要用测试、PostgreSQL、Redis/Celery、压测和可观测性补足后端硬实力证据。

## 1. 项目亮点：最适合写进简历

### P0：实时语音 AI 交互闭环

项目最强的简历亮点不是角色 CRUD，而是这条链路：

```text
浏览器 VAD
→ PCM16 音频
→ DashScope ASR WebSocket
→ LangGraph Chat Agent
→ LanceDB RAG / Friend.memory
→ SSE 文本流
→ DashScope TTS WebSocket
→ base64 MP3 音频块
→ 前端 MSE 流式播放
```

这条链路覆盖了浏览器音频、后端流式 I/O、LLM Agent、语音合成和实时播放。对 AI 应用工程师岗位非常加分。

推荐简历写法：

> 实现浏览器端 VAD、PCM16 编码、ASR 识别、LangGraph Agent 推理、TTS 合成、MSE 流式播放的端到端实时语音交互链路，支持用户语音输入、AI 文本/语音同步回复与语音打断。

### P0：SSE + WebSocket 双流编排

`backend/web/views/friend/message/chat/chat.py` 中通过 `StreamingHttpResponse` 向前端推送 SSE，同时在后台线程内用 `asyncio.gather()` 协调 LLM token 流和 TTS WebSocket 音频流。

这个点很适合面试深挖，因为它不是简单调用大模型 API，而是处理了：

- LLM 文本增量输出；
- TTS 双工 WebSocket；
- 文本和音频事件统一走 SSE；
- 前端 MSE 队列播放；
- Nginx 缓冲关闭；
- 用户打断后的前端输出丢弃。

推荐简历写法：

> 基于 Django SSE 与 DashScope TTS WebSocket 实现文本/音频双流式输出，单次聊天请求同时返回 LLM token 增量和 base64 音频块，前端通过 Media Source Extensions 实时播放。

### P0：LangGraph Agent + Tool Calling + RAG

`backend/web/views/friend/message/chat/graph.py` 中使用 LangGraph 构建 `agent -> tools -> agent` 循环，绑定 `get_time` 和 `search_knowledge_base` 工具，并通过 LanceDB 查询知识库。

亮点在于：

- 有 Agent 状态图，而不是只写 prompt；
- 有 Tool Calling；
- 有向量检索；
- 有流式输出；
- 有工具调用后的二次模型决策。

推荐简历写法：

> 基于 LangGraph 构建支持 Tool Calling 的 Chat Agent，集成 LanceDB 向量检索工具，实现角色对话中的 RAG 增强回答。

### P1：长期记忆机制

`backend/web/views/friend/message/memory/update.py` 中每 10 条消息触发 Memory Agent，对最近对话和原始记忆进行摘要压缩，并写入 `Friend.memory`。

这体现了对上下文窗口、对话连续性和成本控制的意识。

推荐简历写法：

> 设计长期记忆机制，周期性调用独立 Memory Agent 对历史对话进行摘要压缩，并在后续会话中注入系统提示词，提升多轮对话连续性。

### P1：JWT 双 Token + 前端并发刷新队列

`frontend/src/js/http/api.js` 中实现 access token 内存存储、refresh token httpOnly cookie、401 并发刷新队列。

这个点比普通“我用了 JWT”更有含金量，因为你处理了多个请求同时 401 的竞态问题。

推荐简历写法：

> 设计 JWT access/refresh 双令牌认证机制，access token 存于前端内存，refresh token 存于 httpOnly cookie，并通过 subscriber queue 解决并发 401 下的重复刷新问题。

### P1：工程化问题修复记录

相比上次，项目已经开始有“从 Demo 往工程项目演进”的轨迹。比如日志、状态码、错误处理、删除体验、路线图文档。这些不一定写在简历 bullets 里，但面试时可以讲。

推荐面试表达：

> 第一版项目主要追求 AI 链路打通，后续我按工程化优先级修复了异常可见性、HTTP 状态码、日志系统和删除链路体验。目前正在补测试、数据库迁移和异步任务。

## 2. 项目体现出的工程能力与架构能力

### 已经体现出的能力

| 能力 | 证据 | 面试价值 |
|---|---|---|
| 全栈交付 | Django + Vue + Vite + Pinia + Tailwind + 部署文档 | 能独立把产品闭环跑起来 |
| AI 应用整合 | LLM、LangGraph、RAG、ASR、TTS、Embeddings | 对 AI 应用岗位加分明显 |
| 流式 I/O 意识 | SSE、WebSocket、MSE、Nginx 缓冲关闭 | 有后端实时系统复杂度 |
| 认证设计意识 | JWT 双 Token、httpOnly cookie、并发刷新 | 比普通 CRUD 项目更真实 |
| 数据建模能力 | UserProfile、Character、Voice、Friend、Message、SystemPrompt | 业务主线比较清晰 |
| 可维护性意识 | 新增日志、状态码、设计文档、路线图 | 已开始从“能跑”走向“能维护” |
| 产品闭环意识 | 角色探索、添加好友、聊天、历史、语音、记忆 | 不是孤立技术 demo |

### 尚未充分体现的能力

| 能力缺口 | 为什么重要 |
|---|---|
| 自动化测试 | 社招后端面试中，测试是工程素养分界线 |
| 数据库设计与调优 | Java 后端面试会重点看索引、事务、慢查询、连接池 |
| 异步任务架构 | AI 应用里的向量化、摘要、音色训练都应异步 |
| 可观测性 | 真实线上问题必须能定位到请求、用户、模型、耗时、成本 |
| 限流与成本控制 | LLM / ASR / TTS 都是直接花钱的外部调用 |
| 安全边界 | Cookie、CSRF、密钥、上传文件、RAG 权限隔离都要能讲 |
| 压测与容量评估 | 没有压测数据就不能说高并发或生产级 |

## 3. 最能体现“高级后端工程师”能力的设计

### 3.1 实时流式链路编排

这是本项目最能讲出技术深度的地方。

真实难点包括：

- Django WSGI 下如何保持 SSE 连接；
- 后台线程如何和同步 generator 通信；
- LLM token 到 TTS 文本输入之间如何流动；
- TTS WebSocket 返回二进制音频时如何转成 SSE JSON；
- 前端如何避免 SourceBuffer 正在更新时重复 append；
- 用户打断时如何避免旧回复继续污染 UI。

但也要诚实承认当前实现的限制：

- 后端没有真正取消已启动的 LLM/TTS 调用；
- 每个请求启动线程，长连接多时会给 WSGI worker 带来压力；
- `queue.Queue()` 无上限，极端情况下缺少背压策略；
- TTS 失败后缺少文本-only 降级路径；
- 同步 Django ORM 在流结束后写库，复杂场景下需要更明确的连接管理。

高级表达方式：

> 当前版本优先保证链路跑通；如果按生产化演进，我会改为 ASGI async view 或独立流式网关，补取消语义、超时、背压、文本-only 降级和链路指标。

### 3.2 Agent 与 Memory 分离

Chat Agent 负责实时生成，Memory Agent 负责摘要压缩。这是一个正确的架构方向。

它体现了：

- 不同任务用不同模型；
- 实时链路和后台认知任务分离；
- 上下文压缩意识；
- 成本与效果的初步权衡。

当前短板是 Memory 仍同步执行。更成熟的方式是：

```text
Chat API 写入 Message
→ 投递 memory_update 任务
→ Celery Worker 调用 Memory Agent
→ 更新 Friend.memory
→ 记录任务状态与失败日志
```

### 3.3 JWT 刷新队列

前端 subscriber queue 处理并发 401，是一个很好的细节。它说明你不是只会“照着教程用 JWT”，而是理解并发请求下的竞态。

但安全上还需要补：

- refresh endpoint 的 CSRF 保护策略；
- cookie secure 在本地开发和生产环境的差异处理；
- refresh token 轮换后的黑名单表是否实际启用；
- 登录、注册、刷新接口限流。

### 3.4 错误处理与日志改进

这次修改后，项目已经不再是“异常静默吞掉”的状态。`settings.py` 中已有文件轮转日志，view 中也普遍有 `logger.exception()`。

这是非常值得肯定的改进，但仍不是终点：

- 现在多处仍是泛化 `except Exception`，业务异常和系统异常区分不足；
- 日志缺少 request_id、user_id、endpoint、latency 等结构化字段；
- 没有错误追踪平台；
- 没有指标聚合。

面试中可以这样讲：

> 我先把异常从不可见变成可见，下一步会从“能看到堆栈”升级到“能按 request_id 追踪完整 AI 链路”。

## 4. 当前项目不足与短板

### P0：测试仍为空

`backend/web/tests.py` 仍只有模板代码。这是当前最影响社招竞争力的点。

为什么严重：

- 认证、权限、删除、聊天这些链路都有回归风险；
- AI 调用虽然可以 mock，但必须证明你知道怎么测边界；
- 没测试会让面试官把项目归为“个人 Demo”。

建议最小补齐：

| 测试范围 | 优先级 | 原因 |
|---|---|---|
| auth 测试 | P0 | 登录、注册、刷新、登出是基础盘 |
| friend 测试 | P0 | 权限和角色删除后的行为很容易出 bug |
| character CRUD 测试 | P0 | 文件上传、作者权限、删除影响都要覆盖 |
| chat SSE 格式测试 | P1 | 可以 mock Agent，验证 SSE 事件协议 |
| memory update 测试 | P1 | mock LLM，验证记忆写入和失败不阻塞 |
| RAG tool 测试 | P1 | mock LanceDB，验证工具调用和空结果 |

### P0：密钥和配置管理仍需立即处理

`settings.py` 中仍硬编码 `SECRET_KEY`，`DEBUG=True`，`ALLOWED_HOSTS` 和生产 IP 也写死。`backend/.env` 虽然被 `.gitignore` 忽略且当前未被 git 跟踪，但本地确实包含云服务 API Key、OSS Key 等敏感信息。

建议：

- 立即把 `SECRET_KEY` 改为环境变量；
- `DEBUG`、`ALLOWED_HOSTS`、`CORS_ALLOWED_ORIGINS`、`MEDIA_URL` 全部环境变量化；
- 确认任何密钥从未推送到公开仓库；
- 如果曾经共享过压缩包、截图或仓库历史，建议轮换 DashScope / OSS Key；
- 增加 `.env.example`，只保留变量名，不放真实值。

### P0：SQLite 限制了后端叙事

SQLite 对个人开发很友好，但不适合承载社招后端里的“生产级”和“并发”叙事。

面试官会追问：

- 多 worker Gunicorn 下 SQLite 写锁会怎样？
- Message 表按 friend/time 查询有没有索引？
- Friend 是否需要唯一约束避免重复关系？
- Memory 更新和 Message 写入是否有事务边界？
- 数据增长后聊天历史如何分页、归档、清理？

建议迁移 PostgreSQL，并补：

- `Friend(user_profile, character)` 唯一约束；
- `Message(friend, created_at)` 索引；
- `Character(author, created_at)` 索引；
- 慢查询分析；
- Docker Compose 一键启动 PostgreSQL。

### P0：用户级 RAG 仍未完成

当前 `search_knowledge_base` 查询固定 LanceDB 表，更像管理员预置知识库，不是用户可用的 RAG 产品。

如果想冲 AI 应用工程师，这是最值得扩展的方向。

真正有含金量的用户级 RAG 应包含：

- 文件上传；
- 文件类型校验；
- 文档解析；
- chunk 切分；
- embedding 异步任务；
- 向量写入；
- 文档状态机；
- 用户/角色权限隔离；
- 删除文档时同步删除向量；
- 召回评测；
- 失败重试。

### P1：同步 Memory 会拖慢聊天尾部

当前聊天 SSE 完成后，如果消息数达到 10，会直接调用 `update_memory(friend)`。这比上次多了异常保护，但架构上仍不理想。

风险：

- Memory LLM 调用慢，会拖住请求生命周期；
- Memory 失败只记录日志，用户侧无状态可查；
- 多个并发聊天可能重复触发摘要；
- 没有任务幂等和锁。

建议改为 Celery + Redis，并设计 `MemoryTask` 状态表。

### P1：SSE 取消语义不完整

前端通过 `processId` 实现了“旧输出不再展示”，这能改善体验，但后端 LLM/TTS 调用仍可能继续执行。

面试官可能会问：

- 用户关闭弹窗后，后端任务是否还在跑？
- 外部模型 API 是否继续计费？
- 如何取消 TTS WebSocket？
- 如何感知客户端断开？
- 如何设置超时？

建议：

- 前端使用 `AbortController`；
- `fetchEventSource` 传入 signal；
- 后端检测连接断开并尝试取消任务；
- 为 LLM/TTS 设置超时；
- 对无法取消的外部调用做成本限额。

### P1：安全和滥用控制不足

当前项目有认证基础，但还缺真实互联网应用常见保护：

- 登录/注册/聊天/ASR 无限流；
- refresh token cookie 涉及 CSRF 讨论；
- 上传图片缺 MIME、大小、尺寸、恶意文件校验；
- RAG 上传未来会涉及文件解析安全；
- 角色 prompt 没有注入治理；
- 用户输入和 RAG 内容没有安全过滤；
- 日志里应避免记录敏感内容和完整 prompt。

### P2：代码组织可继续演进

当前每个 API 一个 view 文件，短期清晰，但随着功能变多会出现：

- service 层缺失；
- view 承担太多业务逻辑；
- 无 serializer，校验逻辑分散；
- Agent / TTS / ASR 外部服务调用缺少 adapter 抽象；
- 配置散落在 Python 和前端 JS 中。

建议后续拆出：

- `services/auth_service.py`
- `services/chat_service.py`
- `services/memory_service.py`
- `services/rag_service.py`
- `integrations/dashscope/`
- `integrations/vector_store/`
- `serializers` 或 Pydantic schema

## 5. 面试官视角：还缺少哪些真正有含金量的内容

按求职价值排序：

| 排名 | 内容 | 为什么有含金量 |
|---|---|---|
| 1 | 自动化测试 | 直接证明工程素养，区分 Demo 和项目 |
| 2 | PostgreSQL + 索引 + 事务 | Java 后端基础盘，面试官一定关心 |
| 3 | Celery + Redis 异步任务 | AI 应用长耗时任务的标准工程解法 |
| 4 | 用户级 RAG | AI 应用岗位强相关，能讲完整链路 |
| 5 | 可观测性 | 真实线上系统必须能定位问题 |
| 6 | 压测报告 | 没数据就不能讲高并发 |
| 7 | 成本治理 | LLM/TTS/ASR 都是付费资源 |
| 8 | Prompt/RAG 评测 | AI 项目从“能用”到“可优化”的关键 |
| 9 | Docker + CI | 开源和面试演示都更专业 |
| 10 | Java 辅助服务 | 如果主投 Java 后端，这能补语言栈匹配度 |

## 6. 哪些地方像 Demo，哪些地方更接近生产项目

### 更像 Demo 的地方

| 点 | 原因 |
|---|---|
| SQLite | 无法支撑生产并发叙事 |
| 零测试 | 工程可信度不足 |
| 同步 Memory | 长耗时 AI 任务未异步化 |
| 固定 RAG 表 | 不是用户级知识库 |
| 配置硬编码 | 多环境部署不专业 |
| 无 Docker | 新人无法一键启动 |
| 无限流 | 容易被刷爆模型成本 |
| 无压测 | 不能证明性能 |
| 无指标 | 线上无法回答慢在哪里 |

### 更接近生产项目的地方

| 点 | 原因 |
|---|---|
| JWT 双 Token | 认证模型方向正确 |
| refresh 并发队列 | 处理真实前端竞态 |
| SSE 响应头 | 考虑 Nginx 缓冲 |
| MSE 音频队列 | 处理浏览器流式播放细节 |
| 日志系统 | 已有基础排障能力 |
| 状态码改进 | API 语义更接近真实项目 |
| Agent / Memory 分离 | 有任务边界意识 |
| 角色删除异常体验 | 开始考虑跨用户影响 |
| 部署文档 | 不止停留在 localhost |

## 7. 冲击 Java 后端 / AI 应用工程师还应补哪些能力

### Java 后端方向

| 优先级 | 能力 | 建议 |
|---|---|---|
| P0 | Spring Boot 3 | 不必重写全项目，可做一个 Java Chat Gateway / RAG 管理服务 |
| P0 | PostgreSQL / MySQL | 索引、事务、锁、慢查询、连接池必须能讲 |
| P0 | Redis | 限流、缓存、任务状态、分布式锁 |
| P0 | MQ | 学 Kafka / RabbitMQ / RocketMQ 的使用场景和可靠性语义 |
| P1 | JVM 并发 | 线程池、CompletableFuture、虚拟线程、背压 |
| P1 | 压测 | JMeter / Locust，输出首 token 延迟、失败率、吞吐 |
| P1 | 微服务 | 网关、鉴权、幂等、重试、降级、熔断 |

### AI 应用工程师方向

| 优先级 | 能力 | 建议 |
|---|---|---|
| P0 | RAG 工程化 | 用户上传、解析、切分、embedding、权限隔离、召回评测 |
| P0 | Agent 工程化 | Tool schema、状态管理、工具失败重试、权限控制 |
| P0 | 流式体验 | 首 token、TTS 首包、取消、断线、降级 |
| P1 | PromptOps | prompt 版本、回归样例集、A/B、效果评估 |
| P1 | 成本治理 | token 统计、用户额度、模型路由、小模型摘要 |
| P1 | 多 provider | DashScope / OpenAI / DeepSeek 适配层 |

## 8. 最值得扩展的功能方向：按求职价值排序

### 1. 用户上传文档构建个人 RAG

求职价值最高。它能同时证明后端、AI、异步任务、权限、文件处理和数据建模能力。

推荐架构：

```text
用户上传文件
→ 创建 Document 记录
→ 文件落本地/OSS
→ Celery 投递 parse_document
→ 文档解析与清洗
→ chunk 切分
→ embedding 批量生成
→ LanceDB 写入 user_id / document_id / chunk_id / version
→ Chat Agent 按权限检索
→ 返回引用来源
```

建议数据模型：

```text
Document(id, owner_id, title, file_url, status, error_message, created_at)
DocumentChunk(id, document_id, chunk_index, text, vector_id, token_count)
RagQueryLog(id, user_id, friend_id, query, hit_chunks, latency_ms)
```

### 2. 测试体系

建议先补最有性价比的测试：

- `test_auth.py`
- `test_friend.py`
- `test_character_crud.py`

然后补 AI mock 测试：

- SSE 事件格式；
- Agent 工具调用；
- Memory 更新失败不影响聊天。

### 3. PostgreSQL + Redis + Celery

这是后端岗位最硬的工程化信号。建议顺序：

```text
Docker Compose
→ PostgreSQL
→ Redis
→ Celery
→ Memory 异步化
→ 文档向量化异步化
```

### 4. 可观测性

增加结构化日志字段：

- request_id；
- user_id；
- friend_id；
- endpoint；
- model；
- input_tokens / output_tokens；
- first_token_latency_ms；
- tts_first_audio_latency_ms；
- rag_hit_count；
- total_latency_ms；
- error_type。

### 5. 限流与成本控制

建议：

- 登录/注册限流；
- ASR 文件大小限制；
- 聊天接口按用户限流；
- 每日 token / TTS 秒数额度；
- 超额后返回明确提示；
- 管理后台查看用户消耗。

### 6. 自定义角色音色

这个功能产品感很强，但求职价值低于 RAG 和工程化。适合作为第二阶段产品亮点。

实现时要考虑：

- 音频采集和上传；
- 文件格式和时长限制；
- DashScope custom voice 任务状态；
- 创建失败重试；
- 用户只能管理自己的音色；
- 删除音色后的角色降级策略。

### 7. Java 辅助服务

主投 Java 后端时非常值得做一个小服务，不建议重写全项目。

可选方向：

- Java RAG Document Service；
- Java API Gateway；
- Java Quota / Billing Service；
- Java Task Status Service。

推荐做法：

```text
Vue / Django Chat
→ Java RAG Service
→ PostgreSQL Document Metadata
→ Redis Task Status
→ Python Worker 做 embedding
```

这样你既保留 Python AI 生态，又能展示 Java 后端能力。

## 9. 高级工程化路线图

### 第一阶段：安全与基础专业化，1 周

目标：先把面试中最容易被一票否决的问题修掉。

- `SECRET_KEY`、`DEBUG`、`ALLOWED_HOSTS`、公网 IP 环境变量化；
- 增加 `.env.example`；
- 检查并轮换可能泄露过的云服务 Key；
- 增加 `/api/health/`；
- 清理生产文档中“手工改 DEBUG / platform”的流程；
- 登录、注册、聊天、ASR 增加基础限流；
- 图片上传增加大小、类型、尺寸校验。

### 第二阶段：测试与数据库，2-3 周

目标：从“能跑”变成“可回归”。

- 引入 `pytest-django`；
- 补 auth / friend / character 测试；
- mock LLM、ASR、TTS；
- SQLite 迁移 PostgreSQL；
- 添加核心索引和唯一约束；
- Docker Compose 启动 Django + PostgreSQL + Redis；
- CI 中运行后端测试和前端 build。

### 第三阶段：异步任务与可观测性，3-5 周

目标：解决 AI 应用长耗时链路。

- 引入 Celery + Redis；
- Memory Agent 改异步；
- 文档解析和 embedding 改异步；
- 增加任务状态表；
- 日志加入 request_id；
- 记录 token 成本、首 token 延迟、TTS 首包延迟；
- 增加错误追踪；
- 输出一次压测报告。

### 第四阶段：用户级 RAG，4-8 周

目标：把项目从 AI 聊天 demo 升级为 AI 应用工程项目。

- 文档上传；
- 文档解析；
- chunk 策略；
- embedding 批处理；
- LanceDB 元数据隔离；
- 删除文档同步删除向量；
- RAG 引用来源；
- RAG 召回评测集；
- prompt 版本管理；
- RAG 查询日志。

### 第五阶段：Java 后端加固，2-4 周

目标：服务于 Java 后端求职定位。

- 新增 Spring Boot 3 服务；
- 提供文档管理 / 额度管理 / API Gateway 任一能力；
- 使用 PostgreSQL + Redis；
- 用 OpenAPI 描述接口；
- Django 调 Java 服务；
- 补 Java 单元测试；
- 面试中讲清服务拆分边界。

## 10. 简历包装建议

### 项目名称

**AI Friends：基于 LangGraph 的实时语音 AI 角色聊天平台**

### 一句话介绍

独立设计并实现一个支持 AI 角色创建、文本/语音实时对话、RAG 知识检索和长期记忆的全栈 AI 应用，完成前端、后端、Agent 编排、语音链路和服务器部署。

### 推荐简历 bullets

- 基于 **Django REST Framework + Vue 3** 实现 AI 角色聊天平台，支持角色创建、好友关系、聊天历史、JWT 登录认证与首页角色探索。
- 基于 **LangGraph** 构建 Chat Agent，支持 Tool Calling，集成时间查询与 LanceDB 知识库检索工具，实现 RAG 增强回答。
- 设计 **长期记忆机制**，每 10 条消息触发 Memory Agent 对历史对话进行摘要压缩，并注入后续系统提示词提升多轮对话连续性。
- 实现 **SSE + DashScope TTS WebSocket** 的实时双流输出，单次聊天请求同时推送 LLM 文本增量与 base64 音频块，前端通过 MSE 流式播放。
- 实现浏览器端 **VAD → ASR → LLM → TTS → MSE** 语音闭环，支持用户语音输入、AI 语音回复与语音打断。
- 设计 JWT 双 Token 认证方案，access token 存于内存，refresh token 存于 httpOnly cookie，并在前端通过 subscriber queue 解决并发 401 刷新问题。
- 完善后端异常处理与日志体系，将核心 API 从静默失败改造为 `logger.exception()` 可追踪，并统一 HTTP 错误状态码。
- 基于 Gunicorn + Nginx 完成服务器部署，并针对 SSE 配置 `X-Accel-Buffering: no`，避免代理缓冲影响实时输出。

### 暂时不要这样写

不建议在补齐工程化前写：

- “生产级高并发 AI 平台”
- “企业级 Agent 系统”
- “高可用架构”
- “大规模 RAG 知识库”
- “完善测试体系”

更稳妥的表达是：

> 项目已打通 AI 应用核心链路，当前正在按生产化标准补齐测试、数据库迁移、异步任务、可观测性和用户级 RAG。

## 11. 真实面试官会怎么看

### 最加分的地方

1. AI 链路完整：Agent、RAG、Memory、ASR、TTS 都有，不是简单套壳聊天。
2. 实时流式体验有难度：SSE、WebSocket、MSE 的组合能讲出真实技术复杂度。
3. 学习迁移能力强：Java 背景能独立完成 Python + Vue + AI 工程。
4. 已开始工程化改进：日志、状态码、错误处理、设计文档都有推进。
5. 产品闭环较完整：角色、好友、聊天、语音、记忆、部署都能跑通。

### 最容易被质疑的地方

1. 为什么还没有测试？
2. 为什么仍然使用 SQLite？
3. Memory 为什么不异步？
4. RAG 为什么还不能用户上传？
5. 用户断开 SSE 后，后端模型调用是否还在计费？
6. refresh token cookie 如何防 CSRF？
7. 如何限制用户刷爆 LLM / ASR / TTS 成本？
8. 是否做过压测？首 token 延迟是多少？
9. 当前日志如何定位单次请求？
10. 项目中哪些设计是你独立判断的，哪些是照文档拼接的？

## 12. 我会追问的技术问题

### 后端与系统设计

1. 画一下聊天链路，从前端输入到 AI 语音播放完整经过哪些组件？
2. 为什么前端到后端用 SSE，而不是 WebSocket？
3. 后端到 DashScope TTS 为什么用 WebSocket？
4. 如果 100 个用户同时语音聊天，当前瓶颈在哪里？
5. 当前每个聊天请求创建线程，有什么风险？
6. 用户关闭页面后，后端如何停止 LLM/TTS 调用？
7. SQLite 在多 worker 写入下有什么问题？
8. Message 表数据量到百万级后如何优化？
9. Friend 是否应该加唯一约束？为什么？
10. 如何设计聊天消息分页？

### AI Agent / RAG

1. 解释你的 LangGraph `agent -> tools -> agent` 循环。
2. Tool Calling 什么时候触发，什么时候结束？
3. RAG 的 chunk size 和 overlap 怎么选？
4. 如何评价 RAG 的召回质量？
5. 如果 LanceDB 返回空结果，Agent 如何回答？
6. 用户上传文档后，如何做权限隔离？
7. 文档删除后，向量如何删除？
8. 如何防 prompt injection？
9. Memory 每 10 条总结一次，这个阈值怎么来的？
10. 如何评估 Memory 摘要是否丢失关键信息？

### 安全与工程化

1. access token 放内存解决了什么问题？
2. httpOnly cookie 能防 XSS 吗？能防 CSRF 吗？
3. refresh token 轮换后旧 token 如何失效？
4. 如何给登录和聊天接口做限流？
5. 日志中如何避免泄露用户隐私和 prompt？
6. 如何 mock LLM 写自动化测试？
7. Docker Compose 会包含哪些服务？
8. 如果 Celery 任务失败，如何重试和告警？
9. 如何统计单个用户的 token 成本？
10. 如果让你用 Java 拆一个服务，你拆哪里，为什么？

## 13. 项目技术深度分析

| 方向 | 深度评价 | 理由 |
|---|---|---|
| AI 应用链路 | 8/10 | 语音、Agent、RAG、Memory、流式输出齐全 |
| 后端工程化 | 5.5/10 | 日志和状态码已补，但测试、DB、异步仍缺 |
| 系统设计 | 6.5/10 | 有任务边界和实时链路意识，但缺容量和可靠性设计 |
| 安全治理 | 5/10 | 有 JWT 思路，但 CSRF、限流、密钥、上传安全不足 |
| 可观测性 | 4.5/10 | 有日志，但还不是结构化链路追踪 |
| 开源可复现 | 5/10 | README 有改善，但缺 Docker、一键启动、示例数据 |
| Java 岗位匹配 | 5.5/10 | 后端意识能体现，但技术栈不是 Java，需补 Java 服务或文档 |
| AI 岗位匹配 | 7.5/10 | 已达到加分标准，但缺评测、用户级 RAG、成本治理 |

## 14. 社招竞争力判断

| 岗位方向 | 当前竞争力 | 判断 |
|---|---|---|
| Java 后端初中级 | 有加分 | 项目体现学习能力和系统整合，但还要补 Java 基础、DB、Redis、MQ |
| Java 高级后端 | 还不够 | 缺测试、压测、数据库工程、异步任务、可观测性 |
| AI 应用工程师 | 已达加分线 | 链路完整，有 Agent/RAG/语音/记忆 |
| AI Agent 工程师 | 有基础但不强 | 需要补 tool 可靠性、评测、状态持久化、多 Agent |
| 全栈工程师 | 较有竞争力 | 前后端和产品闭环完整 |
| 开源展示项目 | 有吸引力但需打磨 | 缺 Docker、演示视频、示例数据、配置模板 |

综合判断：

```text
AI 应用亮点：8/10
后端工程化：5.5/10
系统设计表达：6.5/10
简历吸引力：7/10
当前社招竞争力：P5+ 到 P6- 之间
补齐测试 + PostgreSQL + Celery + 用户级 RAG 后：可接近 P6 入门水平
```

## 15. GitHub / 开源社区吸引力

当前项目对 GitHub 有一定吸引力，因为“AI 角色 + 实时语音 + RAG + 长期记忆”这个组合本身有展示价值。

但开源吸引力目前受这些问题影响：

- 没有 Docker 一键启动；
- 依赖 DashScope，海外用户或非阿里云用户复现成本较高；
- 缺 `.env.example`；
- 缺截图、GIF、演示视频；
- 缺 demo 数据；
- 缺测试 badge；
- 缺架构图；
- 缺 Roadmap 和 Known Limitations 的正式 README 章节；
- 自定义音色、用户 RAG 等亮点尚未产品化。

建议 README 增加：

- 架构图；
- 实时语音链路图；
- 本地启动步骤；
- `.env.example`；
- 截图/GIF；
- 功能矩阵；
- Roadmap；
- Known Limitations；
- 贡献指南。

## 16. 是否达到“AI 岗位加分项目”标准

结论：**达到 AI 岗位加分项目标准，但还不是强加分项目。**

已经达到的原因：

- 有 Agent；
- 有 RAG；
- 有长期记忆；
- 有语音输入输出；
- 有流式交互；
- 有前后端闭环；
- 有部署路径；
- 已开始工程化修正。

还不是强加分的原因：

- RAG 不是用户级；
- 无测试；
- 无异步任务；
- 无模型效果评估；
- 无成本治理；
- 无压测数据；
- 无结构化可观测性；
- 无 Docker/CI。

面试时最稳的定位：

> 这是一个我独立完成的 AI 应用工程项目，核心目标是打通真实产品中的多模态 AI 交互链路。目前 Agent、RAG、语音、长期记忆和部署已经完成；我也清楚它距离生产级系统还差测试、数据库迁移、异步任务、可观测性和用户级 RAG，这些已经按优先级进入下一阶段路线图。

这个表达比硬说“生产级”更能打动 Tech Lead，因为它体现了技术判断力和自我校准能力。

## 17. 最终优先级建议

如果只做一件事：**写测试。**

如果做三件事：

1. 补 auth / friend / character 的 pytest 测试；
2. 把 `SECRET_KEY`、`DEBUG`、URL、模型名全部环境变量化；
3. Docker Compose + PostgreSQL + Redis。

如果做一个月：

```text
第 1 周：安全配置 + health check + 基础测试
第 2 周：PostgreSQL + Docker Compose + 索引
第 3 周：Celery + Redis + Memory 异步化
第 4 周：用户文档上传 RAG 最小闭环
```

如果目标是 Java 后端：

> 增加一个 Spring Boot 3 的 RAG 文档管理或额度管理服务，比重写整个项目更划算。

如果目标是 AI 应用工程师：

> 优先做用户级 RAG、评测集、Prompt 版本管理和成本统计。

