# AI Friends 项目 Review 报告（Codex 2026-05-31）

> 角色视角：资深后端架构师 / AI 应用技术面试官  
> 评估目标：从技术深度、系统设计能力、工程能力、求职竞争力角度，判断该项目当前在社招 Java 后端 / AI 应用工程师岗位中的含金量。  
> 本次基于当前仓库代码、README、Docker Compose、后端测试结果，以及上一版 `项目Review报告(Codex-2026-05-22).md` 对比分析。

---

## 0. 本次结论摘要

相比 2026-05-22 版本，本项目已经有明显升级：**用户个人 RAG 文档上传、Celery + Redis 异步任务、PostgreSQL + pgvector 检索、Request-ID 日志链路、Health Check、99 个后端自动化测试** 都已经进入代码。这些变化使项目从“AI 聊天 Demo”进一步接近“可讲工程闭环的 AI 应用项目”。

但如果从真实互联网公司 Tech Lead / 面试官视角看，当前仍没有完全达到生产级项目。主要短板集中在：**部署与配置不够干净、成本/限流/风控缺失、流式聊天链路缺少取消与背压、RAG 没有引用来源与效果评估、Memory 任务存在 backlog 场景的数据遗漏风险、README 与代码状态不同步**。

总体判断：

| 维度 | 当前评分 | 说明 |
|---|---:|---|
| AI 应用完整度 | 8.5 / 10 | 多模态聊天、RAG、长期记忆、语音链路已具备，产品形态完整 |
| 后端工程能力 | 7.5 / 10 | 引入异步任务、测试、日志、健康检查，明显比上一版扎实 |
| 系统设计能力 | 7.3 / 10 | 已有分层和异步化意识，但容量、治理、可观测性还不完整 |
| RAG 工程深度 | 7.0 / 10 | 已从预置知识库升级到用户文档 RAG，但缺 citation、eval、召回策略 |
| 生产化成熟度 | 6.3 / 10 | 配置、部署、监控、限流、告警、任务运维仍偏弱 |
| Java 后端岗位匹配度 | 6.5 / 10 | 后端思维能体现，但主实现为 Django；需补 Java/Spring 侧表达 |
| AI 应用工程师加分度 | 8.0 / 10 | 已达到“强加分项目”门槛，但还可继续拔高 |

一句话评价：**现在已经不是普通 CRUD + LLM 包装项目，而是一个有工程链路的 AI 应用项目；但距离“高级后端工程化项目”还差治理、稳定性、评估和部署闭环。**

---

## 1. 本次相较上一版的关键提升

### 1.1 用户个人 RAG 已经落地

当前新增了 `UserDocument` / `DocumentChunk` 模型、文档上传接口、文档列表接口、删除接口、文档异步处理任务，以及前端知识库页面。

最值得写进简历的点：

- 支持用户上传 `txt / md / pdf` 文档构建个人知识库。
- 使用 `pgvector` 存储 1024 维 embedding，并通过向量距离进行检索。
- 检索时按 `owner_id IS NULL OR owner_id = 当前用户` 做全局知识库 + 个人知识库混合召回。
- 文档处理包含 loader、chunker、embedding、bulk insert、状态机。
- 支持文档处理状态：`pending / processing / completed / failed`。

这比上一版“管理员后台预置 RAG”更有招聘价值。原因是面试官更关心你有没有处理真实用户数据生命周期，而不是只把几段固定文本塞进向量库。

优先级评价：**P0 级提升，简历必须重点写。**

---

### 1.2 Celery + Redis 异步任务进入项目

当前已经把两个明显耗时链路异步化：

- 用户文档解析 / embedding / 入库：`process_document_task`
- 长期记忆摘要：`update_memory_task`

这体现了后端工程能力中的关键意识：**不要在请求线程里做不可控耗时的大模型调用和文档处理**。

当前 Celery 配置也有一些工程化细节：

- `CELERY_TASK_ACKS_LATE = True`
- `CELERY_WORKER_PREFETCH_MULTIPLIER = 1`
- 任务超时配置
- 对部分 API 异常做重试区分

这部分比单纯“我用了 Celery”更好，因为你开始考虑任务可靠性、worker 资源争抢和失败补偿。

优先级评价：**P0 级提升，适合突出“异步任务解耦高延迟 AI 链路”。**

---

### 1.3 测试覆盖有明显进步

本次我实际运行了后端测试：

```text
99 passed in 3.39s
```

覆盖范围包括：

- JWT 登录 / 注册 / 刷新 / 登出
- 角色创建 / 查询 / 更新 / 删除权限
- 好友关系
- 聊天 SSE 基础流
- LangGraph tool routing
- ASR WebSocket mock
- RAG tool 查询
- 文档上传校验
- 文档 owner 隔离
- 文档异步处理
- PDF / Markdown / TXT loader
- Memory Agent 触发与失败补偿
- Health Check
- Request-ID

这已经显著超过个人 Demo 的常见水平。尤其是权限隔离、异步任务、RAG 工具、ASR mock 都有测试，会让面试官更愿意相信你不是只跑通了 happy path。

但 README 仍写“51 个测试”，已经落后于代码。这个会影响项目可信度。

优先级评价：**P0 级提升，但 README 必须同步。**

---

### 1.4 Request-ID + Health Check 是生产意识加分项

新增 `RequestIdMiddleware`，日志 formatter 中包含 `{request_id}`，响应头也返回 `X-Request-ID`。这说明你开始考虑线上排障链路。

新增 `/api/health/`，当前检查 DB 可用性，失败返回 degraded / 503。这是部署、负载均衡、监控接入的基础。

从面试角度，这两个点不炫，但很像真实项目。

优先级评价：**P1 级提升，是“工程味”很强的加分项。**

---

### 1.5 PostgreSQL + pgvector 已经替代 SQLite / LanceDB 主链路

当前 settings 中已经使用 PostgreSQL，文档 chunk 使用 `pgvector.django.VectorField`，迁移中创建 `vector` 扩展，并添加 HNSW index。

这对后端岗位很重要，因为它把项目从“本地文件型 Demo 存储”推进到“关系数据库 + 向量检索统一建模”。

不过 README / AGENTS 中仍有部分 LanceDB 或旧描述残留，`chat/graph.py` 注释也还写“LanceDB”。这些要清掉，否则面试官看代码会觉得演进过程没有收口。

优先级评价：**P0 级提升，文档一致性需修复。**

---

## 2. 当前最适合写进简历的项目亮点

### 2.1 AI 虚拟角色多模态交互平台

推荐描述：

> 设计并实现 AI 虚拟角色聊天平台，支持角色创建、好友关系、文本/语音双模态输入输出、SSE 流式回复、DashScope ASR/TTS WebSocket 实时语音链路。

加分理由：

- 不是单轮 chat completion，而是有完整产品闭环。
- 同时涉及文本、语音、前端播放、后端流式响应。
- 对 AI 应用工程师岗位非常相关。

优先级：**P0**

---

### 2.2 基于 LangGraph 的 Agent 编排

推荐描述：

> 基于 LangGraph 构建 Chat Agent 与 Memory Agent，支持 LLM 工具调用、知识库检索、时间工具、长期记忆摘要与会话上下文注入。

加分理由：

- LangGraph 比普通 LangChain chain 更容易体现 agentic workflow。
- Chat Agent / Memory Agent 分离，说明你理解不同任务的职责边界。
- 有 tool routing 测试，能支撑面试追问。

优先级：**P0**

---

### 2.3 用户级 RAG 知识库

推荐描述：

> 实现用户文档 RAG：支持 txt/md/pdf 上传、异步解析切分、DashScope embedding、pgvector 向量存储、HNSW 索引、按用户隔离的全局 + 个人知识库混合召回。

加分理由：

- 用户文档上传比预置知识库更贴近真实业务。
- owner 隔离是多租户系统的基础能力。
- pgvector + PostgreSQL 对后端岗位比本地向量文件更有说服力。

优先级：**P0**

---

### 2.4 异步任务解耦高延迟链路

推荐描述：

> 使用 Celery + Redis 将文档 embedding 入库和长期记忆摘要异步化，避免大模型调用阻塞请求线程，并通过任务状态、重试、超时、late ack 提升任务可靠性。

加分理由：

- 体现了高延迟外部 API 的工程治理。
- 能自然引出 MQ、重试、幂等、任务状态机等后端面试话题。

优先级：**P0**

---

### 2.5 JWT 双令牌认证与前端静默刷新

推荐描述：

> 实现 JWT access/refresh 双令牌认证，refresh token 使用 httpOnly cookie，前端通过 Axios 拦截器处理 401 并发刷新队列，避免多请求重复刷新。

加分理由：

- 比简单 token localStorage 更安全。
- 并发刷新队列表明你考虑了真实前端并发场景。

优先级：**P1**

---

### 2.6 自动化测试覆盖核心链路

推荐描述：

> 编写 99 个 pytest 测试，覆盖认证、角色权限、好友关系、SSE 聊天、ASR mock、LangGraph 工具路由、RAG 检索、文档上传校验、异步文档处理、Memory 失败补偿、健康检查等核心链路。

加分理由：

- 这是从 Demo 项目向工程项目升级的核心证据。
- 99 个测试如果能在 CI 里跑，会更有说服力。

优先级：**P0**

---

## 3. 项目中体现出的工程能力与架构能力

### 3.1 分层意识

当前项目已经有明显分层：

- `models`：用户、角色、好友、消息、系统提示词、文档、chunk
- `views`：API endpoint
- `documents/loaders`：按文件类型处理文档
- `documents/services`：embedding、chunking
- `views/document/tasks.py`：异步文档处理
- `views/friend/message/chat`：聊天 agent
- `views/friend/message/memory`：记忆 agent

这说明你已经从“把所有逻辑写进 view”往服务化方向迁移。

不足是：很多业务逻辑仍在 `views` 目录内，例如文档任务、聊天任务、memory 任务都位于 view 层路径下。面试官可能会追问：为什么任务逻辑属于 views？如果继续工程化，建议迁移为更清晰的结构：

```text
web/
  services/
    rag/
    chat/
    memory/
    voice/
  tasks/
    document_tasks.py
    memory_tasks.py
  api/
    document_views.py
```

优先级：**P2**

---

### 3.2 异步化与任务状态机

用户上传文档后不直接在 HTTP 请求中解析和 embedding，而是创建 `UserDocument` 记录并投递 Celery 任务。前端通过轮询展示处理状态。

这已经具备真实产品常见的异步任务模式：

```text
upload request
  -> save file
  -> create UserDocument(pending)
  -> enqueue Celery task
  -> worker processing
  -> chunk + embedding + insert
  -> completed / failed
  -> frontend polling
```

这比同步处理文档成熟很多。

短板是：

- task enqueue 失败时，文档会停留在 pending。
- 删除文档与正在处理任务之间存在竞态。
- 没有任务进度百分比、任务 ID、重试次数、失败类型。
- 没有 Celery worker 健康检查和积压监控。

优先级：**P1**

---

### 3.3 多租户数据隔离意识

RAG 查询使用：

```sql
WHERE owner_id IS NULL OR owner_id = 当前用户
```

这体现了全局知识库 + 用户私有知识库的隔离意识。测试也覆盖了只能查看/删除自己的文档。

这是后端面试中很重要的点，因为 AI 应用一旦允许用户上传私有资料，权限隔离就是底线。

可继续加强：

- 检索结果返回 `document_id / title / chunk_index / source_page`。
- 支持用户选择哪些文档参与某个角色的对话。
- 支持角色级知识库，而不只是用户级知识库。
- 增加“不能通过 prompt injection 读取其他用户文档”的安全说明和测试。

优先级：**P1**

---

### 3.4 可观测性开始起步

Request-ID、日志文件、health endpoint 是生产意识的体现。

但当前只是起步。真实生产环境还会要求：

- structured JSON logs
- request latency
- LLM latency
- TTS latency
- embedding latency
- token usage
- per user cost
- Celery queue length
- task failure count
- RAG hit rate
- SSE disconnect rate

优先级：**P1**

---

### 3.5 测试意识明显增强

99 个后端测试是当前项目工程能力最有说服力的部分之一。

尤其加分的测试：

- 角色非作者访问返回 404
- 文档 owner 隔离
- 文档上传格式与魔数校验
- 文档异步处理 mock embedding
- Memory 失败后不更新 `last_summarized_count`
- LangGraph 工具路由
- ASR WebSocket mock

这说明你不仅写了功能，还在防回归。

短板是：

- 没看到 CI 配置。
- 前端缺少组件测试 / e2e。
- RAG 质量没有评估集。
- SSE + TTS 的真实断连、取消、异常恢复测试不足。

优先级：**P1**

---

## 4. 哪些设计最能体现“高级后端工程师”能力

### 4.1 高延迟 AI 调用异步化

把 Memory Agent 和文档 embedding 从请求线程剥离，这是高级后端思维。因为 AI API 的延迟、失败率、限流都不可控，直接占用 web worker 会导致吞吐下降和尾延迟恶化。

面试时可以这样讲：

> 我把用户可等待的链路和不可等待的链路做了拆分。聊天首 token 需要流式返回，所以仍走 SSE；文档解析和长期记忆摘要不需要阻塞用户当前请求，因此用 Celery + Redis 异步执行，并通过状态字段和轮询反馈任务结果。

这是能打动面试官的表达。

优先级：**P0**

---

### 4.2 RAG 多租户隔离建模

你没有把所有 chunk 混在一个“公共知识库”里，而是引入了：

- `UserDocument.owner`
- `DocumentChunk.owner`
- `DocumentChunk.document`
- `metadata`
- `chunk_index`

这说明你已经考虑了文档归属、权限、来源追踪和后续扩展。

优先级：**P0**

---

### 4.3 pgvector + HNSW 索引

迁移中创建 `vector` 扩展并添加 HNSW index，这是非常好的工程信号。它比“我用了向量数据库”更后端，因为你能讲清楚：

- embedding 维度
- 存储模型
- 向量距离
- 索引类型
- SQL 过滤条件
- 多租户过滤与 ANN 检索的关系

面试官可能追问：`owner_id` 过滤和 HNSW index 的执行计划是什么？当数据量到百万级时如何优化？

优先级：**P0**

---

### 4.4 JWT 刷新并发控制

前端 Axios 刷新队列是一个真实工程细节。很多 Demo 项目会在多个请求同时 401 时打爆 refresh endpoint，你这里用了 `isRefreshing + subscribers` 避免重复刷新。

优先级：**P1**

---

### 4.5 自动化测试覆盖关键风险

后端项目能把权限、异步任务、外部 API mock、RAG 查询都纳入测试，这是高级工程师比普通 Demo 作者更强的地方。

优先级：**P0**

---

## 5. 当前不足与短板

### 5.1 Docker Compose 暴露硬编码密码与本机路径

当前 `docker-compose.yml` 中存在：

- 明文 `POSTGRES_PASSWORD`
- `/home/ygq/...` 绝对路径
- 只包含 postgres / redis，不包含 web / worker / frontend / nginx

这在开源项目和面试项目中是明显扣分点。面试官会认为部署方案还停留在个人机器脚本状态。

建议：

- 密码改为 `${POSTGRES_PASSWORD}`。
- 使用 `.env`。
- 使用 named volume 或相对目录。
- 增加 `web`、`celery-worker`、`celery-beat`、`nginx` 服务。
- 提供 `docker compose up -d` 一键本地启动。

优先级：**P0**

---

### 5.2 README 与真实代码不同步

README 仍写：

- “知识库目前为全局预置，暂不支持用户自行上传文档”
- “Memory Agent 当前在聊天请求线程内同步执行”
- “未做 Docker 容器化”
- “51 个测试”

但代码已经支持用户上传文档、Memory 异步、Docker Compose 基础设施、99 个测试。

这会造成一个非常现实的问题：**招聘方第一眼看 README，会低估项目；如果继续看代码，又会觉得项目维护不严谨。**

建议马上更新 README，把当前新增能力写清楚。

优先级：**P0**

---

### 5.3 Memory Agent backlog 场景存在摘要遗漏风险

当前 `create_human_message` 只取：

```python
take = min(total_msgs - skip, 30)
messages_raw = ...[skip:skip + take]
```

但 `update_memory_task` 成功后设置：

```python
friend.last_summarized_count = msg_count
```

如果 worker 堆积或任务失败后积累了超过 30 条未摘要消息，那么本次实际只喂给 LLM 30 条，却把 `last_summarized_count` 推进到全部消息数，可能导致中间消息永远没有进入记忆摘要。

这是一个面试官会非常敏感的问题，因为它涉及异步任务、幂等、进度游标和数据一致性。

建议：

- 成功后只推进到 `skip + take`。
- 如果仍有 backlog，继续投递下一轮 memory task。
- 或者按窗口循环摘要直到 backlog 清空。

优先级：**P0**

---

### 5.4 RAG 没有 citation 与可解释性

当前检索结果只把 chunk 内容拼接进工具返回：

```text
内容片段：1
...
```

但没有把文档标题、页码、chunk index、source metadata 返回给最终用户。

真实 RAG 项目中，用户和面试官都会关心：

- 答案来自哪个文档？
- 文档第几页 / 第几段？
- 是否可以点击查看原文？
- 如果回答错了，怎么定位召回问题还是生成问题？

建议：

- 工具返回结构化结果：`document_id/title/page/chunk_index/content/score`
- 前端展示引用来源
- 保存每次检索命中的 chunk，用于排查和评估

优先级：**P1**

---

### 5.5 RAG 缺少效果评估

当前有功能测试，但没有 RAG eval。面试官会追问：

- 你怎么知道召回质量好？
- chunk size 为什么这么设？
- topK 为什么是 3？
- embedding 模型为什么选这个？
- 混合召回要不要 BM25？
- 如何处理长文档、表格、扫描件？

建议做一个小型评估集：

```text
question, expected_doc, expected_keywords, answer_rubric
```

然后统计：

- hit@1 / hit@3
- MRR
- answer faithfulness
- citation accuracy
- no-answer 判断准确率

优先级：**P1**

---

### 5.6 缺少成本、限流与风控

AI 应用真实生产中，成本治理是核心问题。当前项目还缺：

- 每用户每日 token 限额
- 每用户文档上传数量 / 总大小限制
- embedding 成本统计
- TTS 调用次数限制
- ASR 音频时长限制
- IP / user rate limit
- 恶意上传和滥用保护

面试官会问：如果有人脚本调用语音聊天接口，一晚上刷掉几千块 API 费用怎么办？

建议优先实现：

- Redis token bucket / sliding window 限流
- 用户配额表
- API usage 表
- 超限返回 429
- 后台统计成本

优先级：**P0**

---

### 5.7 SSE + TTS 流式链路仍有生产风险

当前聊天流式实现中，后端起线程运行 async TTS + LangGraph，使用 `queue.Queue` 推给 Django streaming response。

这能跑通，但生产级还缺：

- 客户端断开时取消后台 LLM/TTS 任务
- queue 大小限制和背压
- TTS 失败时降级为纯文本
- LLM 成功但 TTS 失败的错误边界
- 每个请求一个线程的容量评估
- gunicorn worker / thread / timeout 配置说明

面试官可能追问：如果 100 个用户同时语音聊天，会创建多少线程？WebSocket 连接数怎么控制？客户端断开后外部 API 还会继续计费吗？

优先级：**P1**

---

### 5.8 `Message.input` 使用 JSONField 但存入 JSON 字符串

当前保存消息时：

```python
input=json.dumps([...], ensure_ascii=False)[:50000]
```

如果模型字段是 JSONField，更合理的是保存 list/dict，而不是保存 JSON 字符串。当前做法会降低后续查询、审计、调试能力。

建议：

- JSONField 保存原生 list。
- 如需截断，设计结构化字段，如 `input_snapshot` / `truncated` / `message_count`。

优先级：**P2**

---

### 5.9 配置仍有硬编码

当前 settings 中仍有：

- 生产 `MEDIA_URL` 写死 IP
- CORS 只写 localhost
- `SECRET_KEY` 有默认 fallback

建议：

- `MEDIA_URL` 来自 `DJANGO_MEDIA_URL`。
- `CORS_ALLOWED_ORIGINS` 来自环境变量。
- 非 DEBUG 且缺少 `DJANGO_SECRET_KEY` 时直接启动失败。

优先级：**P1**

---

### 5.10 Admin / 运维入口未完善

`UserDocument` / `DocumentChunk` 当前没有注册到 Django Admin。对于调试文档状态、查看失败原因、人工删除异常数据来说不方便。

建议：

- 注册 `UserDocumentAdmin`
- 搜索 title / owner
- 过滤 status / file_type
- readonly 展示 chunks_count / error_message

优先级：**P2**

---

## 6. 从面试官视角：还缺哪些真正有含金量的内容

### P0：成本与限流系统

这是 AI 应用最现实的问题。没有成本控制，项目很难说是生产级。

建议实现：

- Redis 限流中间件
- 用户级每日 token / ASR / TTS / embedding 配额
- usage 表记录每次调用
- 管理页展示成本趋势

面试价值：非常高。能把项目从“会调模型”提升到“懂 AI 商业化系统”。

---

### P0：部署闭环与 CI

建议补：

- GitHub Actions 跑 pytest
- Docker Compose 一键启动 Postgres / Redis / Django / Celery / Frontend
- `.env.example` 完整化
- README 更新到真实现状

面试价值：高。招聘方会明显提高对项目可信度的判断。

---

### P1：RAG 引用来源 + 评估集

建议补：

- 答案展示引用
- 命中 chunk 记录
- RAG eval 脚本
- topK / chunk size 参数对比实验

面试价值：高。能体现 AI 应用深度，不只是集成。

---

### P1：流式链路稳定性治理

建议补：

- 客户端断开检测
- LLM/TTS cancel
- bounded queue
- TTS failover
- 并发压测报告

面试价值：高。尤其适合后端岗位。

---

### P1：任务系统可靠性

建议补：

- 任务幂等 key
- 重试次数和错误类型落库
- worker health check
- 队列积压指标
- 文档删除与任务处理竞态处理

面试价值：中高。能讲 MQ、幂等、补偿、最终一致性。

---

## 7. 哪些地方像 Demo，哪些接近真实生产项目

### 更接近真实生产项目的部分

- JWT access/refresh 双令牌认证
- 前端 access token 内存存储
- 401 并发刷新队列
- PostgreSQL + pgvector
- 用户文档 RAG 上传和异步处理
- Celery + Redis 异步任务
- Request-ID 日志链路
- Health Check
- 99 个后端自动化测试
- 文档 owner 隔离和删除权限测试
- HNSW index 迁移
- SSE 流式返回和 TTS 音频同步播放

这些部分可以放心写进简历。

---

### 仍显得像 Demo 的部分

- Docker Compose 只覆盖基础设施，且写死个人路径和密码。
- README 与代码状态明显不同步。
- 没有 CI/CD。
- 没有成本治理。
- 没有限流。
- 没有监控告警。
- RAG 没有引用来源和评估。
- SSE 断连、取消、背压没有处理。
- 文档处理缺少任务运维视图。
- UserDocument 没有 admin 管理。
- 前端知识库功能可用，但交互仍偏基础，没有文档详情、引用回溯、重新处理等能力。

这些不一定会否定项目，但会让面试官判断它还没有经历真实线上压力。

---

## 8. 如果冲击 Java 后端 / AI 应用工程师岗位，还应补哪些能力

### 8.1 Java 后端方向

你上一份工作是 Java 后端，这个项目用 Python/Django 实现 AI 应用是合理的，但面试 Java 岗时需要把能力翻译成 Java 技术语言。

建议补：

- Spring Boot / Spring Security / Spring Data JPA 或 MyBatis Plus 的同类设计表达
- Redis 限流、缓存、分布式锁
- MQ 可靠消息、幂等、重试、死信队列
- MySQL/PostgreSQL 索引与 SQL 执行计划
- JVM 线程池、连接池、GC 基础
- 高并发下的容量估算和压测报告

建议做一个小扩展：把“配额/限流/usage 统计”作为独立 Java Spring Boot 服务，供 Django AI 服务调用。这会非常适合你的背景：

```text
Vue
  -> Django AI Service
      -> Java Quota/Billing Service
      -> PostgreSQL / Redis
      -> DashScope / pgvector
```

优先级：**P1**

---

### 8.2 AI 应用工程师方向

建议补：

- RAG eval
- prompt versioning
- tool call tracing
- agent memory 策略对比
- embedding 模型选型说明
- chunking 参数实验
- hallucination 处理
- citation 与 grounded answer
- 多租户知识库安全

优先级：**P0**

---

### 8.3 实时语音交互方向

建议补：

- 音频格式、采样率、VAD 参数说明
- ASR/TTS 延迟分解
- 首字延迟 / 首音频延迟指标
- 异常降级策略
- WebSocket 连接管理
- 客户端断连后的取消机制

优先级：**P1**

---

## 9. 最值得扩展的功能方向（按求职价值排序）

### 1. AI 成本治理与限流系统

求职价值：**最高**

实现内容：

- 用户级 API 调用配额
- token / ASR 秒数 / TTS 字符数统计
- Redis 限流
- 超限返回 429
- 后台 cost dashboard

为什么值钱：

AI 应用公司最关心成本失控。你能讲清楚这个，立刻区别于普通模型调用者。

---

### 2. RAG 引用来源 + 评估集

求职价值：**极高**

实现内容：

- 检索结果返回文档标题、页码、chunk index、score
- 前端展示引用来源
- 保存 retrieval trace
- 建立 20-50 条 QA eval dataset
- 输出 hit@k / MRR / faithfulness

为什么值钱：

RAG 岗位最怕“只会调接口”。评估和可解释性是高级 AI 应用工程能力。

---

### 3. Docker Compose 全链路 + CI

求职价值：**高**

实现内容：

- web / worker / redis / postgres / frontend / nginx 全部容器化
- GitHub Actions 自动跑测试
- README 一键启动
- `.env.example` 完整

为什么值钱：

招聘方能直接跑起来，GitHub 吸引力会显著提升。

---

### 4. SSE / TTS 生产级稳定性

求职价值：**高**

实现内容：

- 客户端断开取消 LLM/TTS
- bounded queue
- TTS 失败降级纯文本
- 并发压测报告
- latency metrics

为什么值钱：

实时语音交互系统比普通聊天系统更有技术壁垒。

---

### 5. Java 配额服务 / 管理后台服务

求职价值：**高，尤其对 Java 后端岗位**

实现内容：

- Spring Boot 实现用户配额、usage、billing mock
- Redis 限流
- PostgreSQL 持久化
- REST API 被 Django 调用

为什么值钱：

能把你的 Java 背景和 AI 项目连接起来，避免面试官认为你偏离 Java 主线。

---

### 6. 文档处理增强

求职价值：**中高**

实现内容：

- docx 支持
- 表格解析
- OCR
- 重新处理
- 文档详情页
- 文档级启用/禁用

为什么值钱：

能提高产品完整度，但不如成本治理和 RAG eval 对面试冲击大。

---

## 10. 高级工程化路线图

### 阶段一：先修掉“可信度扣分项”（1 周）

目标：让招聘方第一眼觉得项目靠谱。

任务：

- 更新 README：功能、架构、测试数、已知限制、启动方式。
- 修复 Docker Compose：去掉硬编码密码和个人路径。
- `.env.example` 补齐 `MEDIA_URL / CORS_ALLOWED_ORIGINS / PG / Redis`。
- 修复 Memory backlog 摘要遗漏风险。
- 清理 LanceDB 旧注释和旧文档描述。
- 注册 UserDocument / DocumentChunk 到 Django Admin。

优先级：**P0**

---

### 阶段二：补 AI 应用生产治理（2-3 周）

目标：从“功能完整”升级为“可运营”。

任务：

- Redis 限流中间件。
- usage 表记录 token、embedding、ASR、TTS。
- 用户配额。
- 成本统计接口。
- RAG citation。
- retrieval trace 落库。
- RAG eval 脚本和报告。

优先级：**P0 / P1**

---

### 阶段三：补实时链路稳定性（2 周）

目标：让语音聊天成为技术亮点，而不是风险点。

任务：

- SSE 客户端断连检测。
- 后台 LLM/TTS 任务取消。
- queue 设置 maxsize。
- TTS 失败降级文本。
- 并发压测：10 / 50 / 100 并发。
- 统计首 token、首音频、总响应时间。

优先级：**P1**

---

### 阶段四：部署与开源体验（1-2 周）

目标：让 GitHub 项目能被陌生人跑起来。

任务：

- Docker Compose 全链路。
- GitHub Actions。
- seed data。
- demo account。
- 架构图。
- API 文档。
- 截图 / GIF。
- Roadmap。

优先级：**P1**

---

### 阶段五：Java 后端能力对齐（可选，2-4 周）

目标：为 Java 后端岗位建立强关联。

任务：

- Spring Boot Quota Service。
- Redis rate limiter。
- usage billing mock。
- OpenAPI 文档。
- Django 调用 Java 服务。
- 写一篇 ADR：为什么拆分配额服务。

优先级：**P1**

---

## 11. 简历包装建议

### 11.1 项目名称建议

不要写：

> AI 聊天机器人项目

建议写：

> AI Friends：基于 LangGraph + pgvector 的多模态 AI 虚拟角色与个人知识库平台

这个名字能同时传达：AI 应用、Agent、RAG、多模态、平台化。

---

### 11.2 简历项目描述示例

```text
AI Friends 是一个 AI 虚拟角色互动平台，支持用户创建 AI 角色并进行文本/语音双模态聊天。系统基于 Django REST Framework + Vue 3 构建，使用 LangGraph 编排 Chat Agent / Memory Agent，集成 DashScope ASR/TTS WebSocket 实现语音输入与流式语音回复，并使用 PostgreSQL + pgvector 构建全局 + 用户个人知识库 RAG。
```

---

### 11.3 简历 bullet 推荐

可以写：

- 基于 LangGraph 设计 Chat Agent 与 Memory Agent，支持工具调用、长期记忆摘要、历史上下文注入和 SSE 流式输出。
- 实现用户个人 RAG 知识库，支持 txt/md/pdf 上传、异步解析切分、DashScope embedding、pgvector 向量检索与用户级数据隔离。
- 使用 Celery + Redis 将文档处理和记忆摘要异步化，避免高延迟 LLM / embedding 调用阻塞请求线程，并通过任务状态和重试机制提升可靠性。
- 设计 JWT access/refresh 双令牌认证，refresh token 使用 httpOnly cookie，前端 Axios 拦截器支持 401 静默刷新和并发请求排队。
- 实现 DashScope ASR/TTS WebSocket 语音链路，前端结合 VAD 检测语音结束，后端通过 SSE 同步返回文本 token 与音频 chunk。
- 引入 Request-ID、Health Check、PostgreSQL 测试库和 99 个 pytest 测试，覆盖认证、权限、RAG、ASR、异步任务、Memory Agent 等核心链路。

---

### 11.4 不建议夸大的说法

不建议写：

- “高并发 AI 语音系统”
- “生产级 RAG 平台”
- “企业级 Agent 平台”
- “完整 DevOps 自动化部署”

原因：

- 目前没有压测和容量数据。
- 没有成本治理、监控告警、CI/CD。
- Docker Compose 还不是完整应用部署。
- RAG 缺少 eval 和 citation。

更稳妥的表达：

- “具备生产化雏形”
- “完成核心工程链路”
- “围绕高延迟 AI 调用做了异步化改造”
- “覆盖核心业务链路的自动化测试”

---

## 12. 真实面试官视角

### 12.1 最能加分的地方

第一，项目不是只包了一层 LLM API，而是有角色、好友、记忆、RAG、语音、前端交互、认证和测试。完整度不错。

第二，用户文档 RAG + Celery 异步处理是本次最大加分点。这说明你开始处理真实 AI 应用的数据链路。

第三，99 个后端测试很有说服力。个人项目里能覆盖到 ASR mock、RAG tool、Memory failure compensation，不常见。

第四，JWT 双令牌、Request-ID、Health Check、PostgreSQL 测试库，都说明你有后端工程意识。

---

### 12.2 最容易被质疑的地方

第一，部署方案不干净。Docker Compose 暴露个人路径和密码，这是明显扣分项。

第二，README 过期。文档说不支持用户上传，但代码已经支持；这会让人怀疑项目维护质量。

第三，没有成本治理。AI 应用没有限流和配额，真实上线风险很大。

第四，RAG 没有评估。功能跑通不等于效果可靠。

第五，实时语音链路没有断连取消和背压，无法证明高并发下稳定。

---

### 12.3 我会追问的技术问题

RAG 方向：

- 为什么选择 pgvector，而不是独立向量数据库？
- HNSW 索引参数怎么调？数据量上来后查询计划是什么？
- `owner_id IS NULL OR owner_id = ?` 和向量索引结合时性能如何？
- chunk size / overlap 怎么确定？
- topK 为什么是 3？
- 如何判断召回结果质量？
- 如何防止用户 A 通过 prompt injection 读取用户 B 的文档？
- PDF 表格和扫描件怎么处理？

Agent 方向：

- LangGraph 相比直接调用 LLM 有什么收益？
- Tool 调用失败怎么处理？
- Memory Agent 的摘要策略如何避免遗忘关键信息？
- 如果 Memory 任务积压超过 30 条消息，你现在的游标是否会丢数据？
- 系统提示词如何版本化？

语音方向：

- VAD 在前端做有什么优缺点？
- ASR/TTS 的平均延迟是多少？
- SSE 和 WebSocket 为什么这样选？
- 客户端断开后，后端如何停止 TTS 计费？
- 多用户并发时线程和 WebSocket 连接如何控制？

后端工程方向：

- Celery 任务如何保证幂等？
- 文档上传成功但任务投递失败怎么办？
- 文档删除时 worker 正在处理怎么办？
- 为什么不用 DRF Serializer？
- JSONField 为什么保存 JSON 字符串？
- 如何做限流、成本控制和审计？
- 线上如何查看某个请求的完整链路？

Java 岗位方向：

- 如果用 Spring Boot 重构，你会怎么拆模块？
- Redis 在这个项目里可以承担哪些职责？
- MQ 可靠消息和 Celery retry 有什么异同？
- 如何设计一个 usage billing 服务？
- PostgreSQL 连接池、事务边界、索引优化怎么做？

---

### 12.4 项目体现出的技术深度

当前项目技术深度可以分为三层：

第一层：AI 应用集成。包括 LLM、ASR、TTS、embedding、RAG。这一层已经比较完整。

第二层：后端工程闭环。包括 JWT、异步任务、日志、健康检查、测试、PostgreSQL。这一层已经开始扎实，但部署和治理还欠缺。

第三层：生产级治理。包括限流、成本、监控、压测、RAG eval、SSE 稳定性。当前这一层还比较薄。

所以我会判断：**项目已经有中级偏上的 AI 应用工程深度，但高级后端系统深度还需要继续补。**

---

### 12.5 社招竞争力判断

如果投 AI 应用工程师、AI 产品后端、LLM 应用开发岗位：

> 竞争力：较强。  
> 只要 README 和部署修好，这个项目可以明显加分。

如果投 Java 后端开发岗位：

> 竞争力：中等偏强。  
> 它能证明你有后端工程和 AI 应用能力，但需要在面试表达中主动补 Java/Spring/Redis/MQ/并发/数据库优化。

如果投高级 Java 后端岗位：

> 竞争力：中等。  
> 项目本身亮点足够，但还缺压测、成本治理、监控告警、分布式服务拆分等高级后端硬证据。

---

### 12.6 GitHub / 开源社区吸引力判断

当前吸引力：**中等偏上，但还没完全释放。**

有吸引力的原因：

- 主题明确：AI 虚拟角色 + 语音 + RAG。
- 功能完整：不是一个最小 Demo。
- 技术栈新：LangGraph、pgvector、DashScope、Vue 3。
- 测试较多。

影响 Star / 复现的原因：

- README 过期。
- Docker Compose 不可移植。
- 缺截图 / GIF。
- 缺一键启动。
- 缺 demo data。
- 缺架构图。

如果你补齐 README、Docker Compose、截图和 demo 数据，这个项目在 GitHub 上会比普通 AI chat repo 更有吸引力。

---

### 12.7 是否达到“AI 岗位加分项目”标准

判断：**已经达到，而且比上一版更稳。**

理由：

- 有真实 AI 应用形态，而不是 prompt demo。
- 有 Agent 编排。
- 有用户文档 RAG。
- 有语音输入输出。
- 有长期记忆。
- 有异步任务。
- 有测试。

但是否达到“强竞争力 AI 项目”，还取决于下一步是否补：

- RAG citation / eval
- 成本治理
- 稳定性压测
- 部署闭环

当前状态可以作为简历强项目；如果再补上述四项，可以成为面试主打项目。

---

## 13. 建议立即修复清单

### P0：马上做

- 修复 `docker-compose.yml` 中的明文密码和个人绝对路径。
- 更新 README，把用户文档 RAG、Celery、99 tests、Docker Compose 现状写准。
- 修复 Memory backlog 超过 30 条时可能遗漏摘要的问题。
- 清理 LanceDB 旧描述和旧注释。
- 增加 GitHub Actions 跑后端测试。

### P1：下一轮做

- 加 Redis 限流和 usage 统计。
- RAG 返回 citation。
- 保存 retrieval trace。
- Health Check 增加 Redis / Celery。
- SSE 断连取消和 TTS 失败降级。
- `.env.example` 补齐媒体地址和 CORS。

### P2：锦上添花

- UserDocument / DocumentChunk 注册 Django Admin。
- 前端知识库增加文档详情、重新处理、引用回溯。
- 增加 docx / OCR。
- Java Spring Boot 配额服务。
- 写架构图和 ADR。

---

## 14. 最终判断

这个项目已经具备比较好的求职价值。它的最大优势不是“用了很多 AI 技术名词”，而是你已经开始把 AI 能力放进一个有用户、有权限、有异步处理、有测试、有日志、有数据库建模的后端系统里。

从招聘方视角，它现在最适合定位为：

> 一个具备生产化雏形的多模态 AI 应用后端项目。

不要把它包装成“高并发生产级平台”，那会被追问压测、限流、监控和成本时打穿。更好的策略是坦诚讲：

> 当前已经完成核心 AI 应用链路和关键工程化改造，下一步重点补成本治理、RAG 评估、流式链路稳定性和部署闭环。

这会显得真实、专业，也更像一个能持续把项目做深的后端工程师。

