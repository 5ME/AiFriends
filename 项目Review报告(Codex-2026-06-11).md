# AI Friends 项目 Review 报告（Codex 2026-06-11）

> 角色视角：资深后端架构师 / AI 应用技术面试官  
> 评估目标：从技术深度、系统设计能力、工程能力、求职竞争力角度，判断项目在 Java 后端 / AI 应用工程师社招中的竞争力。  
> 对比基线：`项目Review报告(Codex-2026-05-22).md`、`项目Review报告(Codex-2026-05-31).md`。  
> 本次验证：后端 `147 passed, 3 deselected`；前端 `npm run build` 通过，存在 chunk size warning。

---

## 0. 总体结论

这轮迭代质量很高。项目已经从 5 月底的“有工程雏形的 AI 应用项目”，进一步升级为“具备生产化治理雏形的 AI 应用后端项目”。上次报告中 P0/P1 提到的多个问题已经被正面处理：

- README 从旧状态更新到基本符合当前功能。
- Docker Compose 去掉了硬编码密码和个人绝对路径。
- 生产 `SECRET_KEY` 缺失时会 fail-fast。
- CORS、Redis、媒体地址等配置进一步环境化。
- Redis 限流中间件已接入。
- API usage 模型与记录工具已接入 LLM / embedding / TTS / ASR / Memory 等链路。
- RAG 检索加入来源标记、distance、RetrievalTrace 落库。
- Chat SSE 能发送 citations 事件。
- Memory backlog 游标问题已修复。
- `Message.input` 已从 JSON 字符串改回原生 JSON。
- 文档处理增加 Celery task id、投递失败处理、删除时 revoke、系统知识库增量 embedding。
- Health Check 从只查 DB 扩展到 DB + Redis + Celery。
- Django Admin 注册文档与 chunk。
- GitHub Actions 已有后端测试流水线。
- 后端测试从上次 99 个常规测试扩展到 147 个常规测试。

但需要保持客观：当前还不能称为完整生产级系统。主要原因是：

- 成本治理仍是“记录 + 限流”，还没有用户配额、计费聚合、预算熔断和后台报表。
- RAG citation 后端链路已具备，但前端聊天界面尚未消费和展示 `citations`。
- RetrievalTrace 记录的是检索命中，但还没有 RAG eval 指标体系。
- Health Check 把 Celery worker 纳入同一个 `/api/health/`，适合 readiness，但不适合作为简单 liveness。
- SSE/TTS 仍缺少真正的服务端取消、bounded queue、背压和纯文本降级。
- ASR usage 记录存在 `User.id` 与 `UserProfile.id` 混用风险。
- 自定义音色目前只有底层 API wrapper，没有接入 URL、权限、前端上传流程和 Voice 归属模型，不能算完整功能。

综合判断：

| 维度 | 2026-05-31 | 2026-06-11 | 评价 |
|---|---:|---:|---|
| AI 应用完整度 | 8.5 | 8.7 | 核心形态完整，RAG citation/trace 增强明显 |
| 后端工程能力 | 7.5 | 8.2 | 限流、CI、Admin、任务可靠性、测试覆盖显著提升 |
| 系统设计能力 | 7.3 | 7.9 | 已开始覆盖治理、可观测性、任务状态、成本数据 |
| RAG 工程深度 | 7.0 | 7.7 | 有来源、trace、增量导入，但 eval 和前端展示未闭环 |
| 生产化成熟度 | 6.3 | 7.1 | 从配置/部署/health/limit/CI 多处提升，但仍缺监控和压测 |
| Java 后端岗位匹配度 | 6.5 | 7.0 | 后端工程素材更丰富，但仍需 Java/Spring 表达承接 |
| AI 岗位加分度 | 8.0 | 8.5 | 已是强加分项目，继续补 eval/压测/治理可成为主打项目 |

一句话评价：

> 当前项目已经具备“AI 应用工程师强加分项目”的水准，并开始体现高级后端工程化意识；但如果要冲击更高级别后端岗位，还需要用压测、成本配额、监控告警、RAG eval 和完整部署闭环来证明生产级能力。

---

## 1. 本轮相较上一版的关键提升

### 1.1 成本治理从“待补”变成“已起步”

新增 `APIUsage` 模型和 `record_api_usage()` 工具，并接入：

- Chat LLM token usage
- Memory Agent usage
- Embedding usage
- TTS 字符数/耗时
- ASR 音频采样点/耗时

这回应了上次报告里“AI 成本治理是 P0”的建议。它最适合在面试中表达为：

> 我没有只做模型调用，而是开始记录每类 AI API 的调用类型、模型、token/字符/音频量、耗时、成功失败状态，为后续用户配额、成本看板和预算熔断提供数据基础。

但注意：当前还只是 usage 采集，不是完整成本治理。还缺：

- 每用户每日/每月额度。
- 余额或套餐。
- API 单价映射。
- 成本聚合任务。
- 超预算熔断。
- 管理后台统计图。

优先级评价：**P0 已部分完成，下一步应补配额和报表。**

---

### 1.2 Redis 限流中间件已接入

新增 `RateLimitMiddleware`，使用 Redis Sorted Set + Lua 实现 Sliding Window Log，规则覆盖：

- login：5/min
- register：3/min
- chat：20/min
- asr：10/min
- upload：10/min
- default write API：60/min

这个点对后端面试很有价值，因为你可以讲清楚：

- 为什么只限制写请求。
- 为什么登录/注册/AI 接口单独设规则。
- 为什么用 Redis Lua 保证原子性。
- fail-open 为什么是有意设计。
- Windows + WSL Docker 下 `localhost` IPv6 超时如何排查。

尤其是 `docs/troubleshooting/2026-06-07-test-performance-fix.md` 里“测试从 23 分钟降到 3.7 秒”的排障，非常适合面试讲 STAR 案例。

短板：

- 限流规则仍硬编码在 settings，不能运行时动态调整。
- 只有请求次数限制，不是 token/金额维度限额。
- fail-open 能保护可用性，但 Redis 故障时成本保护失效，需要监控告警。

优先级评价：**P0 完成基础版，P1 补动态配置和成本维度。**

---

### 1.3 RAG citation 与 RetrievalTrace 已落地

`search_knowledge_base` 现在通过 JOIN 查询拿到：

- document title
- chunk_index
- distance

并返回：

```text
[来源1: xxx.pdf 第3段]
```

同时写入 `RetrievalTrace`，记录用户、query、document、chunk_index、distance。

这比上次“只拼接 chunk 内容”有明显进步。它已经具备 RAG 可解释性和后续评估的数据地基。

但目前存在一个闭环缺口：后端 SSE 会发送 `citations` 事件，测试也覆盖了；前端 `InputField.vue` 目前只处理 `data.error / data.content / data.audio`，没有消费 `data.citations`，`Message.vue` 也没有展示引用来源。因此用户视角仍看不到引用。

建议下一步：

- 前端消息结构增加 `citations` 字段。
- `InputField` 收到 `data.citations` 后挂到当前 AI 消息。
- `Message.vue` 在 AI 回复下方展示“参考来源”。
- 历史消息可选择保存 citations 或通过 RetrievalTrace 时间窗口回查。

优先级评价：**P1，后端已强，前端展示未闭环。**

---

### 1.4 文档处理可靠性明显增强

本轮新增：

- `UserDocument.celery_task_id`
- 上传后保存 Celery task id
- Celery 投递失败时文档标记 failed
- 处理完成或永久失败时清空 task id
- 删除 pending/processing/retry 文档时尝试 revoke task
- revoke 失败不阻断删除
- 测试覆盖以上边界

这是很好的后端工程信号。它说明你开始处理异步任务生命周期，而不是只把任务丢进队列。

仍需注意：

- `revoke()` 默认不能杀掉已经在执行的任务，只能阻止未执行任务；如要终止执行中任务，需要 `terminate=True`，但这又有资源释放和一致性风险。
- worker 已经加载 doc 对象后，用户删除文档仍可能出现竞态，需要在任务关键阶段检查文档是否仍存在。
- 文档 media 文件保存成功但 DB 创建失败、DB 创建成功但响应失败等边界仍可进一步事务化/补偿化。

优先级评价：**P1 完成度高，但仍不是完整任务一致性方案。**

---

### 1.5 系统知识库增量导入减少 embedding 浪费

`insert_documents.py` 从全量删除/全量 embedding，升级为基于 `content_hash` 的增量更新：

- 内容不变的 chunk 原地保留。
- 新增或变更的 chunk 才重新 embedding。
- 多余旧 chunk 被删除。
- 历史 `content_hash=''` 数据会重新 embedding 兜底。

这是真正贴近 AI 应用成本优化的工程点。比“我做了 RAG”更有含金量，因为它展示了你关心 embedding API 成本、重复计算和数据更新策略。

优先级评价：**P1，简历可作为 RAG 工程优化点。**

---

### 1.6 配置、部署、CI 可信度提升

这轮修复了上一版几个明显扣分项：

- `docker-compose.yml` 不再写死个人路径和明文强密码。
- `SECRET_KEY` 在 `DEBUG=False` 时缺失会直接抛 `ImproperlyConfigured`。
- `DJANGO_CORS_ORIGINS` 环境变量化。
- `REDIS_URL` 和 `CELERY_BROKER_URL` 默认改为 `127.0.0.1`，避免 Windows + WSL Docker 的 IPv6 超时。
- README 更新了本地 4 进程启动方式。
- `.github/workflows/test.yml` 已加入后端测试。

仍不足：

- Docker Compose 只有 Postgres + Redis，不包含 Django web、Celery worker、frontend/nginx。
- README 的“已知限制”仍写“无速率限制和成本治理”，与当前已有基础限流/usage 不一致。
- README 项目结构中 `components/knowledge` 放在 `frontend/` 根下，实际在 `frontend/src/components/knowledge/`。

优先级评价：**P0 扣分项大幅修复，P1 继续补完整一键启动。**

---

### 1.7 测试体系进一步增强

本次实际运行：

```text
collected 150 items / 3 deselected / 147 selected
147 passed, 3 deselected in 8.15s
```

新增测试覆盖：

- Admin 注册与搜索。
- health DB/Redis/Celery 降级。
- Redis 限流正常/超限/fail-open/跳过路径。
- RAG 来源标记。
- RetrievalTrace 落库。
- SSE citations 事件。
- 多层 SystemMessage 顺序。
- 文档 task id、revoke、投递失败。
- 系统知识库增量导入和 content_hash。

这已经明显超过普通个人项目。对招聘方来说，测试数量不是唯一重点，关键是你覆盖了权限、异步、外部 API mock、限流、RAG、任务可靠性这些高风险点。

优先级评价：**P0 强加分。**

---

## 2. 项目亮点：最适合写进简历的点

### P0：多模态 AI 虚拟角色平台

推荐简历描述：

> 设计并实现 AI 虚拟角色互动平台，支持角色创建、好友关系、文本/语音双模态聊天、DashScope ASR/TTS WebSocket、SSE 流式文本与音频返回、长期记忆和个人知识库 RAG。

理由：

- 产品形态完整。
- AI 应用链路覆盖文本、语音、RAG、记忆。
- 比普通 ChatGPT wrapper 更有复杂度。

---

### P0：LangGraph Agent 编排与工具调用

推荐简历描述：

> 基于 LangGraph 构建 Chat Agent 与 Memory Agent，支持 LLM tool-calling、知识库检索、长期记忆摘要、历史上下文注入，并通过分层 SystemMessage 控制工具规则、角色性格与平台级行为约束。

理由：

- 有 agent graph、tool routing、Memory Agent，不是简单 prompt。
- 新增 tool-calling slow 评估脚本，可作为“我验证过模型是否会调工具”的证据。

---

### P0：用户级 RAG + pgvector + 引用追踪

推荐简历描述：

> 实现用户文档 RAG：支持 txt/md/pdf 上传、异步解析分块、DashScope embedding、PostgreSQL pgvector HNSW 检索、用户级数据隔离、引用来源标记与 RetrievalTrace 落库。

理由：

- 有用户上传数据生命周期。
- 有 owner 隔离。
- 有 trace 数据，能继续做评估。
- pgvector 对后端岗位更容易讲数据库、索引和 SQL。

---

### P0：AI 成本治理基础

推荐简历描述：

> 引入 Redis Sliding Window Log 限流与 APIUsage 用量记录，按接口区分登录、注册、聊天、ASR、文档上传等频率限制，并记录 LLM / embedding / TTS / ASR 的 token、字符数、耗时和失败状态，为用户配额与成本分析提供数据基础。

理由：

- 这是 AI 应用后端最现实的生产问题。
- 很多个人项目没有成本意识。

注意不要写成“完整计费系统”，当前只是基础治理。

---

### P0：Celery 异步任务与任务生命周期治理

推荐简历描述：

> 使用 Celery + Redis 将文档解析/embedding 和长期记忆摘要异步化，设计任务状态机、失败重试、task id 跟踪、删除时 revoke、投递失败补偿，避免高延迟 AI 调用阻塞请求线程。

理由：

- 体现 MQ、重试、幂等、最终一致性思维。
- 比只写 `delay()` 有深度。

---

### P1：测试与 CI

推荐简历描述：

> 编写 147 个后端常规测试，覆盖认证、权限、SSE、ASR mock、RAG、RetrievalTrace、限流、Health Check、Admin、Celery 文档任务、Memory Agent 等核心链路，并接入 GitHub Actions 自动测试。

理由：

- 个人项目中非常有说服力。
- 能证明项目可维护，不只是能跑。

---

### P1：真实工程排障案例

推荐简历描述：

> 排查 Windows + WSL Docker 下 Redis `localhost` IPv6 解析导致测试卡顿的问题，将全量测试耗时从 23 分钟优化到 8 秒内，并通过 pytest marker 排除真实 API slow 测试、mock 限流中间件降低测试环境外部依赖。

理由：

- 这是很好的面试故事。
- 能体现定位问题、分析根因、改配置和测试工程能力。

---

## 3. 项目中体现出的工程能力与架构能力

### 3.1 工程化闭环能力

当前项目不再只是功能堆叠，而是有一套工程闭环：

```text
功能实现
  → 异步化
  → 任务状态
  → 权限隔离
  → 测试覆盖
  → 日志/Request-ID
  → Health Check
  → CI
  → README 同步
```

这对求职非常重要。招聘方会更相信你能把一个功能从“跑通”推进到“可维护”。

---

### 3.2 高延迟 AI 服务治理意识

项目里有多类外部 AI 服务：

- LLM
- embedding
- TTS
- ASR
- voice enrollment wrapper

你已经开始做：

- 异步任务隔离。
- usage 记录。
- 限流。
- retry。
- fail-safe trace。
- 测试 mock。

这说明你理解 AI 应用不同于传统 CRUD：外部 API 延迟、成本、限流、失败率都是核心问题。

---

### 3.3 数据隔离与审计意识

RAG 通过 `owner_id IS NULL OR owner_id = 当前用户` 进行全局 + 个人文档混合召回，文档列表/删除也只允许 owner 操作。新增 RetrievalTrace 后，后续可以追踪：

- 用户问了什么。
- 命中了哪个文档。
- 命中第几段。
- distance 是多少。

这对 RAG 调试和审计是很好的基础。

---

### 3.4 任务可靠性意识

新增 `celery_task_id`、投递失败补偿、revoke、retry task id 保留、永久失败清空 task id，这些都说明你开始处理异步任务的真实生命周期。

不过还没有做到严格幂等和强一致性。比如 worker 已经执行中的任务，revoke 不一定能终止；删除和处理仍可能竞态。

---

### 3.5 测试工程能力

147 个常规测试覆盖面较广，且对 slow 真实 API 测试做了 marker 隔离。这个设计很成熟：

- 常规 CI 不依赖真实 API key。
- slow 测试可在需要时手动评估 tool-calling。
- 限流中间件在普通测试中 mock，专门测试中单独覆盖。

这说明你开始理解“测试要快、稳定、隔离外部依赖”。

---

## 4. 最能体现高级后端工程师能力的设计

### 4.1 Redis + Lua Sliding Window 限流

高级点在于：

- 不是用内存计数，而是 Redis 集中式限流。
- 不是 Fixed Window，而是 Sliding Window Log。
- 使用 Lua 保证 trim、count、add、expire 原子性。
- 按登录/注册/chat/asr/upload 分规则。

面试官可能会继续追问：

- Redis 挂了为什么 fail-open？
- fail-open 下成本风险怎么兜底？
- 如果从单机扩展到多实例，这套限流是否仍准确？
- Sorted Set 的内存占用如何估算？
- 如果 QPS 很高，Sliding Window Log 是否还合适？

你需要能回答：当前流量较低，精确限流优先；大规模下可改 Sliding Window Counter 或 Token Bucket。

---

### 4.2 RAG trace 数据地基

RetrievalTrace 的设计有明显后续价值：

- 可以统计 hit document。
- 可以看 distance 分布。
- 可以做用户查询日志。
- 可以构建 eval dataset。
- 可以排查“检索错了还是生成错了”。

这是 AI 应用从功能到质量工程的关键一步。

---

### 4.3 Memory backlog 修复

上一版的问题是最多只摘要 30 条，但成功后推进到总消息数，可能跳过中间未摘要消息。当前已经改为：

```python
friend.last_summarized_count = skip + take
```

这是一个很好的“异步任务进度游标”修复案例。能体现你理解任务处理不应把“系统当前总量”误当成本次“实际处理量”。

---

### 4.4 系统知识库增量 embedding

通过 content hash 跳过未变化 chunk，可以减少重复 embedding 调用。这个点体现：

- 成本意识。
- 增量更新思维。
- 数据一致性思维。
- 测试覆盖边界情况。

如果能再补一份“重复导入节省多少 token / 耗时”的数据，会更适合写进简历。

---

### 4.5 CI + 本地测试性能优化

测试工程本身也是高级后端能力的一部分。你不仅写了测试，还处理了：

- Redis 连接超时导致测试慢。
- slow tests 与常规 tests 分离。
- 测试中自动 mock 限流。
- GitHub Actions 使用 pgvector postgres service。

这很像真实团队会遇到的问题。

---

## 5. 当前不足与短板

### P0：ASR usage 记录存在 User / UserProfile id 混用风险

`APIUsage.user` 外键指向 `UserProfile`，大部分链路传的是 `UserProfile.id`，例如 Chat、TTS、Memory、Embedding。

但 ASR 中：

```python
user_id = self.request.user.id
record_api_usage(user_id=user_id, api_type='asr', ...)
```

这里传的是 Django `User.id`。如果 `User.id` 与 `UserProfile.id` 不一致，`APIUsage.objects.create(user_id=...)` 可能写错归属或直接外键失败。因为 `record_api_usage()` 捕获异常，所以接口不会失败，但 ASR 成本数据会丢失或错账。

建议：

```python
user_id = self.request.user.userprofile.id
```

并补一个测试：创建 `User.id != UserProfile.id` 的场景，验证 ASR usage 正确落到 UserProfile。

优先级：**P0，因为它影响成本治理准确性。**

---

### P0：成本治理还没有“配额”和“预算熔断”

现在已经有 usage 和 rate limit，但还不是完整成本治理。

还缺：

- 用户每日 token 上限。
- 用户每日 TTS 字符上限。
- 用户每日 ASR 秒数上限。
- 文档上传总大小 / 总数量限制。
- embedding 总 token 上限。
- 成本单价配置。
- 额度消耗查询接口。
- 管理后台聚合报表。
- 超限时 429/402/业务提示。

面试时可以说“我已经完成成本治理的数据采集和入口限流基础”，不要说“已完成完整成本治理系统”。

优先级：**P0。**

---

### P1：RAG citation 前端展示未闭环

后端已经 emit `citations` SSE 事件，但前端没有处理：

- `InputField.vue` 未消费 `data.citations`。
- `Message.vue` 没有引用来源 UI。
- 历史消息也没有保存/回显 citations。

这会让面试官觉得“后端实现了，但用户不可见”。建议尽快补。

优先级：**P1。**

---

### P1：RAG 仍缺评估体系

RetrievalTrace 是数据基础，但还没有：

- QA 测试集。
- hit@1 / hit@3。
- MRR。
- faithfulness。
- citation accuracy。
- no-answer accuracy。
- chunk size / topK 参数实验。

如果投 AI 应用工程师岗位，RAG eval 是很有含金量的下一步。

优先级：**P1。**

---

### P1：Health Check 需要区分 liveness 与 readiness

当前 `/api/health/` 同时检查 DB、Redis、Celery。优点是能发现依赖故障；风险是如果 Celery worker 暂时没响应，Web 服务会返回 503。

真实生产中建议拆分：

- `/api/health/live/`：进程活着即可，给容器 liveness probe。
- `/api/health/ready/`：检查 DB/Redis/Celery，给流量接入 readiness probe。
- `/api/health/deps/`：更详细依赖状态，给监控。

优先级：**P1。**

---

### P1：SSE/TTS 仍缺服务端取消和背压

当前前端 `processId` 可以忽略旧响应、停止播放音频，但后端仍可能继续跑 LLM/TTS 调用。

风险：

- 用户关闭页面后外部 API 可能继续计费。
- `queue.Queue()` 无上限，极端情况下内存不可控。
- 每次聊天创建线程，高并发下线程数不可控。
- TTS 失败会导致整体 error，没有纯文本降级策略。

建议：

- 使用 `AbortController` 取消 fetch-event-source。
- 后端检测客户端断开。
- 给 queue 设置 `maxsize`。
- TTS 失败时保留 LLM 文本流。
- 做 10/50/100 并发压测，记录首 token、首音频、总耗时。

优先级：**P1。**

---

### P1：自定义音色还不能算已实现功能

仓库中已有 `create_voice / list_voice / delete_voice` 的 DashScope wrapper，但：

- 没接入 URL。
- 没有 DRF View。
- 没有权限模型。
- `Voice` 没有 owner 字段。
- 前端 `Voice.vue` 仍只是选择已有 voices。
- 没有音频上传、OSS URL、状态轮询、删除权限。

因此简历里不要写“已支持用户自定义音色”。最多写：

> 已预研 DashScope voice enrollment API，保留自定义音色扩展入口。

优先级：**P1，如果你想把语音方向做成主亮点。**

---

### P2：前端缺少自动化测试和部分交互闭环

前端 build 通过，但项目没有：

- component test
- e2e test
- Playwright/Cypress
- SSE citation UI 测试
- 上传失败 toast/e2e 测试

Vite build 还提示主 JS chunk 超过 500KB。不是严重问题，但后续可以考虑路由级 code splitting。

优先级：**P2。**

---

### P2：请求链路追踪没有跨线程/跨任务传播

Request-ID 在 Django 请求日志中有价值，但：

- Chat 子线程日志不一定携带同一个 request_id。
- Celery task 日志没有从请求传入 correlation id。
- RetrievalTrace、APIUsage 没有 request_id 字段。

如果要进一步生产化，建议：

- Request-ID 放入 Celery task kwargs 或 headers。
- APIUsage / RetrievalTrace 增加 request_id。
- 结构化 JSON 日志。

优先级：**P2。**

---

## 6. 哪些地方更像生产项目，哪些仍像 Demo

### 更接近生产项目的部分

- PostgreSQL + pgvector + HNSW index。
- 用户文档 RAG 与 owner 隔离。
- Celery + Redis 异步任务。
- 文档 task id 与删除 revoke。
- Redis 限流。
- API usage 数据采集。
- Request-ID + 请求耗时日志。
- DB/Redis/Celery health check。
- GitHub Actions。
- 147 个后端常规测试。
- RAG RetrievalTrace。
- 系统知识库增量 embedding。
- `.env.example` 和 README 明显改善。

这些都可以作为简历/面试主材料。

---

### 仍显得像 Demo 的部分

- Docker Compose 还不是全应用一键启动。
- 成本治理没有配额/报表/熔断。
- RAG citations 未前端展示。
- RAG 没有 eval。
- SSE 断连取消不完整。
- 没有压测数据。
- 没有 Prometheus/Grafana/Sentry 等监控告警。
- 自定义音色只有底层 wrapper。
- 前端缺少测试。
- README “已知限制”有少量过期描述。

这些是下一轮最值得补的点。

---

## 7. 面试官视角

### 7.1 最加分的地方

第一，项目完整度高。它不是简单 AI chat，而是角色、好友、文本、语音、RAG、记忆、认证、文档上传、异步任务组合成完整产品。

第二，这轮补了真实 AI 应用后端最关键的治理能力：限流、usage、trace、health、CI。

第三，测试质量明显超过多数个人项目。147 个常规测试覆盖了很多高风险场景。

第四，RAG 从“能搜”走向“可追踪”，这比只会接向量库更有深度。

第五，有可讲的排障案例：Redis `localhost` IPv6 导致测试卡顿。

---

### 7.2 最容易被质疑的地方

第一，成本治理尚未闭环。usage 记录不等于配额系统。

第二，RAG citation 用户不可见。后端有事件，前端没展示。

第三，没有压测，不能讲高并发。

第四，自定义音色 README 里仍列为限制，代码里有 wrapper，状态容易让面试官追问“到底实现到哪一步”。

第五，ASR usage id 混用是一个细节 bug，会让面试官质疑成本数据准确性。

---

### 7.3 我会追问的问题

后端工程：

- 你的限流为什么选择 Sliding Window Log，而不是 Token Bucket？
- Redis 挂了 fail-open，如何避免成本失控？
- 如何从 APIUsage 做每日用户配额？
- Celery task revoke 能否终止正在执行的任务？
- 文档删除和 worker 正在处理发生竞态怎么办？
- Health check 为什么同时检查 Celery？如何区分 liveness/readiness？
- Request-ID 如何跨 Celery 和后台线程传播？

RAG：

- RetrievalTrace 如何用于 RAG eval？
- distance 阈值如何确定？
- topK 为什么是 3？
- owner 过滤和 pgvector HNSW 的执行计划是什么？
- 系统知识库和个人知识库混合召回是否需要重排序？
- 如何防止用户通过 prompt injection 获取其他用户文档？
- citation 如何保存到历史消息？

Agent：

- 分层 SystemMessage 的顺序为什么这么设计？
- Tool rule 放第一条会不会压过角色设定？
- slow tool-calling eval 的结果是多少？
- 模型从 `deepseek-v3.2` 换到 `deepseek-v4-flash` 的原因是什么？
- tool 调用失败时怎么降级？

语音：

- ASR/TTS 的延迟如何拆解？
- 前端停止播放时，后端 TTS 是否停止计费？
- 并发语音聊天时线程数、WebSocket 数如何控制？
- TTS 失败是否可以纯文本返回？

Java 岗位：

- 如果用 Spring Boot 重构限流和 usage，你会怎么设计？
- Celery 和 Java MQ 方案有什么异同？
- Redis 限流 Lua 在 Java 中怎么实现？
- PostgreSQL pgvector 查询如何在 Java 服务中封装？
- 你如何把这个 Python AI 服务和 Java 后端体系结合？

---

## 8. 社招竞争力判断

### AI 应用工程师

竞争力：**强**

理由：

- 有 Agent、RAG、语音、长期记忆。
- 有用户文档上传。
- 有治理雏形。
- 有测试和 CI。

如果补上 RAG eval、citation UI、压测和配额，项目可以成为主打项目。

---

### Java 后端工程师

竞争力：**中等偏强**

理由：

- 后端工程能力已经能体现：认证、限流、异步、数据库、测试、CI。
- 但主实现是 Django/Python，不是 Spring Boot。

建议简历表达时强调后端共通能力：

- Redis 限流
- PostgreSQL schema/index
- 异步任务可靠性
- API usage/cost governance
- CI/testing

并准备把 Celery 映射到 Java 里的 MQ、把 Django middleware 映射到 Spring interceptor/filter。

---

### 高级后端工程师

竞争力：**中等**

理由：

- 工程意识已经不错。
- 但缺少高级后端岗位常问的硬证据：压测、容量估算、监控告警、SLA、降级熔断、分布式部署、数据归档。

下一步最该补：

- 压测报告。
- Prometheus metrics。
- 用户配额。
- SSE 取消与背压。
- Docker Compose 全应用启动。

---

### GitHub / 开源吸引力

竞争力：**中等偏上**

相比上次，README、CI、Docker Compose 都有改善。继续提升 GitHub 吸引力，需要：

- 首页截图/GIF。
- 一键启动 demo。
- `.env.example` 说明更完整。
- seed data。
- 架构图更精致。
- 前端 citation UI 展示。
- Release/Roadmap。

---

## 9. 是否达到“AI 岗位加分项目”标准

判断：**已经达到强加分标准。**

原因：

- 不是单 API demo。
- 有 Agent 编排。
- 有 RAG 数据生命周期。
- 有语音双模态。
- 有长期记忆。
- 有异步任务。
- 有成本治理基础。
- 有限流。
- 有测试与 CI。

但还没有达到“生产级 AI 平台项目”标准。生产级还需要：

- 配额和预算控制。
- 监控告警。
- RAG eval。
- 压测。
- 完整部署。
- 断连取消。
- 安全审计。

---

## 10. 下一步高级工程化路线图

### Phase 1：补齐当前治理闭环（最高优先级）

目标：把已有基础能力从“有记录”变成“能治理”。

任务：

- 修复 ASR usage 的 `User.id` / `UserProfile.id` 问题。
- 增加用户每日配额：chat token、embedding token、TTS 字符、ASR 秒数、上传大小。
- 增加 quota check：调用前检查，超限返回 429。
- 增加 APIUsage 聚合接口。
- Admin 中展示 APIUsage。
- README 已知限制更新为“已有基础限流/usage，待补配额和报表”。

优先级：**P0**

---

### Phase 2：RAG 可解释性闭环

目标：让 citation 对用户可见，并能支撑评估。

任务：

- 前端展示 citations。
- 保存 AI 消息对应 citations。
- RetrievalTrace 关联 Message 或 request_id。
- 构建 30-50 条 QA eval。
- 输出 hit@k / MRR / citation accuracy。
- 加 distance threshold 和 no-answer 策略。

优先级：**P1**

---

### Phase 3：实时语音链路稳定性

目标：让语音聊天可讲并发和降级。

任务：

- 前端 AbortController。
- 后端感知客户端断连。
- TTS 失败降级纯文本。
- queue maxsize。
- 并发压测脚本。
- 指标：首 token、首音频、总耗时、失败率。

优先级：**P1**

---

### Phase 4：部署和可观测性

目标：让项目能被陌生人稳定跑起来。

任务：

- Docker Compose 增加 web、worker、frontend/nginx。
- Prometheus metrics。
- structured JSON logging。
- request_id 传递到 Celery。
- `/health/live` 与 `/health/ready` 分离。
- Sentry 或等价错误追踪。

优先级：**P1**

---

### Phase 5：Java 后端能力承接

目标：把项目和你的 Java 背景连接起来。

建议做一个独立 Spring Boot 服务：

```text
Quota Service
  - 用户额度
  - APIUsage 聚合
  - Redis 限流
  - PostgreSQL 持久化
  - OpenAPI
```

Django AI 服务在调用 LLM/TTS/ASR 前请求 Java Quota Service。这样你面 Java 后端时就能把 AI 项目转化为 Java 系统设计案例。

优先级：**P1 / P2**

---

## 11. 简历包装建议

### 项目标题

建议：

> AI Friends：基于 LangGraph + pgvector 的多模态 AI 虚拟角色与个人知识库平台

---

### 项目简介

```text
AI Friends 是一个支持文本/语音双模态交互的 AI 虚拟角色平台。系统基于 Django REST Framework + Vue 3 构建，使用 LangGraph 编排 Chat Agent / Memory Agent，集成 DashScope ASR/TTS WebSocket 实现实时语音交互，基于 PostgreSQL + pgvector 构建全局与用户个人知识库 RAG，并通过 Celery + Redis、限流、usage 统计、RetrievalTrace、Health Check 和 CI 测试提升工程化能力。
```

---

### 推荐简历 bullet

- 基于 LangGraph 构建 Chat Agent 与 Memory Agent，支持 tool-calling、长期记忆摘要、分层 SystemMessage、历史上下文注入和 SSE 流式输出。
- 实现用户个人 RAG 知识库，支持 txt/md/pdf 上传、异步解析分块、DashScope embedding、PostgreSQL pgvector 检索、用户级权限隔离和 RetrievalTrace 落库。
- 使用 Celery + Redis 将文档处理和记忆摘要异步化，设计任务状态机、task id 跟踪、投递失败补偿、删除时 revoke 和失败重试策略。
- 引入 Redis Sliding Window Log 限流中间件，基于 Lua 保证限流检查原子性，覆盖登录、注册、聊天、ASR、文档上传等高风险接口。
- 设计 APIUsage 用量记录模型，采集 LLM、embedding、TTS、ASR 的 token/字符/音频量、耗时和失败状态，为后续用户配额与成本治理提供数据基础。
- 接入 Request-ID、DB/Redis/Celery Health Check、Django Admin、GitHub Actions，并编写 147 个后端常规测试覆盖认证、权限、RAG、ASR、限流、异步任务和 Agent 路由。
- 排查 Windows + WSL Docker 下 Redis `localhost` IPv6 连接超时导致测试卡顿的问题，将本地全量测试从分钟级优化到秒级。

---

### 避免过度包装

不建议写：

- “完整生产级成本治理”
- “高并发语音系统”
- “完整自定义音色功能”
- “企业级 RAG 平台”

更准确的说法：

- “具备成本治理基础”
- “完成实时语音交互核心链路”
- “RAG 已具备引用追踪数据基础”
- “具备生产化雏形”

---

## 12. 最终判断

这个项目现在已经很适合作为求职主项目，尤其适合 AI 应用工程师、LLM 应用后端、智能体平台后端方向。它比 5 月 22 日版本强了不止一个层级，也比 5 月 31 日版本更接近真实互联网后端项目。

从招聘视角看，当前项目最有价值的定位是：

> 一个具备多模态交互、用户级 RAG、Agent 编排、异步任务、限流、usage 统计、trace、health、CI 和较完整测试体系的 AI 应用后端项目。

下一轮最建议做的三件事：

1. 修复 ASR usage 用户 id 问题，并补用户配额。
2. 把 RAG citations 展示到前端，并开始做 RAG eval。
3. 做 SSE/TTS 断连取消、降级和压测。

做到这三点后，这个项目在 AI 应用工程师岗位里会非常有说服力；再补一个 Java Quota Service，就能更自然地承接你的 Java 后端背景。

