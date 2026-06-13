# AI Friends 项目技术 Review（Codex）

> 视角：资深后端架构师 / AI 应用面试官  
> 目标岗位：Java 后端 / AI 应用工程师  
> 评估依据：你提供的功能说明 + 对当前仓库的代码扫描，包括 Django models/views、LangGraph、SSE、ASR/TTS、前端 token 与音频流实现。

## 0. 总体判断

AI Friends 是一个 **AI 虚拟角色聊天平台**：用户创建 AI 角色，与角色建立好友关系，通过文本或语音进行实时对话。系统集成了 LLM、Agent Tool Calling、RAG、长期记忆、ASR、TTS、JWT 登录和前后端部署。

一句话评价：

> 这是一个“AI 应用方向亮点很强，但工程化成熟度还不足”的个人项目。  
> 对 AI 应用岗位有明显加分，对 Java 后端岗位也能体现学习能力和系统整合能力；但如果要冲高级后端，需要补测试、日志、异步任务、数据库迁移、可观测性和压测数据。

当前项目最强的不是 CRUD，而是这条链路：

```text
浏览器 VAD → ASR WebSocket → LLM Agent → RAG / Memory → SSE 流式文本 → TTS WebSocket → MSE 流式播放
```

这条链路很适合在简历和面试中讲。

---

## 1. 项目亮点：最适合写进简历的内容

### P0：实时语音 + AI Agent 双流式链路

最值得写。

项目实现了 **LLM 文本流 + TTS 音频流** 的并发输出，后端在 [chat.py](D:/MyProjects/AiFriends/backend/web/views/friend/message/chat/chat.py:97) 中通过 `StreamingHttpResponse` 返回 SSE，同时用后台线程 + `asyncio.gather()` 协调 LLM token 流和 DashScope TTS WebSocket。

简历可写：

> 基于 Django + LangGraph 实现 AI 角色对话 Agent，通过 SSE 推送 LLM 流式文本，并并发调用 DashScope TTS WebSocket 生成音频流，实现文本与语音的实时双通道输出。

### P0：完整语音交互闭环

前端 [Microphone.vue](D:/MyProjects/AiFriends/frontend/src/components/character/chat_field/input_field/Microphone.vue:1) 使用浏览器端 VAD 捕获语音结束，转 PCM16 后调用 ASR；前端 [InputField.vue](D:/MyProjects/AiFriends/frontend/src/components/character/chat_field/input_field/InputField.vue:1) 使用 Media Source Extensions 播放 TTS 音频流。

简历可写：

> 实现浏览器端 VAD、PCM16 编码、ASR 识别、LLM 推理、TTS 合成、MSE 流式播放的端到端实时语音交互链路，并支持用户语音打断 AI 输出。

### P0：LangGraph Agent + Tool Calling + RAG

[graph.py](D:/MyProjects/AiFriends/backend/web/views/friend/message/chat/graph.py:1) 中实现了 LangGraph `StateGraph`，包含 `agent -> tools -> agent` 的循环，并绑定 `get_time` 与 `search_knowledge_base` 工具。

简历可写：

> 基于 LangGraph 构建支持工具调用的 Chat Agent，集成 LanceDB 向量知识库检索，实现角色对话中的 RAG 增强回答。

### P1：长期记忆机制

[memory/update.py](D:/MyProjects/AiFriends/backend/web/views/friend/message/memory/update.py:1) 中每 10 条消息触发 Memory Agent，总结对话并写入 `Friend.memory`。

简历可写：

> 设计对话长期记忆机制，周期性调用独立 Memory Agent 对历史消息进行摘要压缩，并注入后续系统提示词，提升多轮对话连续性。

### P1：JWT 双 Token + 前端无感刷新

前端 [api.js](D:/MyProjects/AiFriends/frontend/src/js/http/api.js:1) 实现了 access token 内存存储、refresh token httpOnly cookie、401 并发刷新队列。

这是很像真实业务系统的点。尤其是 subscriber queue 避免多个 401 同时刷新 token，这个细节面试官会认可。

---

## 2. 项目体现出的工程能力与架构能力

### 已体现的能力

| 能力            | 体现                                                         |
| --------------- | ------------------------------------------------------------ |
| 全栈交付能力    | Django + Vue + 部署文档 + 前后端联调                         |
| AI 应用整合能力 | LLM、LangGraph、RAG、ASR、TTS、Embeddings 串联               |
| 流式系统意识    | SSE、WebSocket、MSE、队列缓冲、`X-Accel-Buffering: no`       |
| 数据建模能力    | UserProfile、Character、Voice、Friend、Message、SystemPrompt 关系清晰 |
| 认证安全意识    | access token 不落 localStorage，refresh token 使用 httpOnly cookie |
| 产品闭环意识    | 角色创建、好友关系、聊天历史、首页探索、个人空间基本闭环     |

### 尚未充分体现的能力

| 短板               | 影响                                      |
| ------------------ | ----------------------------------------- |
| 缺少测试           | 面试官会认为项目偏 Demo                   |
| 缺少日志与可观测性 | 生产问题无法定位                          |
| SQLite 仍是主库    | 不利于证明并发与生产意识                  |
| 异常处理过粗       | 多处裸 `except:`，排障和错误语义不足      |
| 无异步任务队列     | Memory 总结、文档向量化、语音任务都应解耦 |
| 缺少压测数据       | 很难支撑“高并发”“性能优化”叙事            |

---

## 3. 最能体现“高级后端工程师”能力的设计

优先讲这几个。

### 1. SSE + WebSocket 的流式编排

这是最有后端技术含量的部分。难点在于：

- LLM token 是流式产生的；
- TTS WebSocket 需要边接收文本边返回音频；
- 前端需要边收 SSE 边播放音频；
- 用户可能中断输出；
- Nginx 默认可能缓冲 SSE，需要关闭代理缓冲。

这不是普通 CRUD，属于真实的 I/O 编排问题。

### 2. Token 刷新并发队列

前端不是简单地“401 就刷新”，而是处理了多个请求同时 401 的场景。这个点能体现你对竞态条件的理解。

### 3. Agent 与 Memory 分离

Chat Agent 负责实时对话，Memory Agent 负责摘要压缩。虽然实现还简单，但方向是对的：**不同任务使用不同模型、不同链路、不同成本策略**。

### 4. Character.profile 的“双用途约定”

`Character.profile` 第一行用于公开展示，全文用于系统提示词。这个设计体现了产品和模型上下文之间的折中，但也建议后续拆成 `public_intro` 和 `system_prompt`，避免长期维护混乱。

---

## 4. 当前项目不足与短板

### P0：工程化短板明显

仓库中 [backend/web/tests.py](D:/MyProjects/AiFriends/backend/web/tests.py:1) 基本为空，没有 API 测试、Agent 测试、认证测试。对社招来说，这是最容易被质疑的地方。

建议最低补齐：

- 登录 / 注册 / refresh token 测试；
- 角色 CRUD 权限测试；
- 好友关系权限测试；
- Chat SSE 事件格式测试；
- RAG tool mock 测试；
- Memory update mock 测试。

### P0：异常处理不合格

多个 view 使用裸 `except:`，例如角色创建、好友列表、登录注册等。这会导致：

- 真实异常被吞；
- 日志不可见；
- 前端只能看到“系统异常”；
- 面试官会认为你缺少生产排障意识。

建议改为：

```python
except Character.DoesNotExist:
    return Response({"message": "角色不存在"}, status=404)
except ValidationError as e:
    return Response({"message": str(e)}, status=400)
except Exception:
    logger.exception("create character failed")
    return Response({"message": "系统异常"}, status=500)
```

### P0：数据库仍停留在 Demo 级

SQLite 适合开发，不适合你用来讲“生产部署”和“并发”。尤其聊天消息、记忆更新、用户上传文件、向量索引都会产生写入。

建议迁移 PostgreSQL，并补充：

- 索引设计；
- 慢查询分析；
- 连接池；
- 事务边界；
- 消息表按用户/时间查询优化。

### P1：同步 Memory 更新会拖慢聊天请求

当前聊天结束后，如果消息数达到 10，会同步调用 `update_memory(friend)`。这会把额外一次 LLM 调用挂在聊天请求尾部。

更合理的设计：

```text
Chat API 写入消息
       ↓
投递 Celery / Redis 任务
       ↓
Memory Worker 异步总结
       ↓
更新 Friend.memory
```

### P1：RAG 还不是真正的用户级知识库

当前 RAG 更像管理员预置知识库，且 [search_knowledge_base](D:/MyProjects/AiFriends/backend/web/views/friend/message/chat/graph.py:26) 每次查询连接固定 LanceDB 表。面试官会追问：

- 如何支持用户上传文档？
- 如何隔离不同用户的数据？
- 如何处理文档删除后的向量删除？
- 如何做 chunk 版本管理？
- 如何处理 embedding 失败重试？

### P1：配置和部署方式偏手工

[config.js](D:/MyProjects/AiFriends/frontend/src/js/config/config.js:1) 中直接切 `platform = 'cloud'`，后端 [settings.py](D:/MyProjects/AiFriends/backend/backend/settings.py:23) 中 `SECRET_KEY`、`ALLOWED_HOSTS`、IP 也比较硬编码。真实公司更希望看到环境变量、Docker Compose、CI/CD 和分环境配置。

### P2：代码/文档存在编码乱码

仓库多处中文注释、README 输出为乱码。这不一定影响运行，但对开源展示和面试代码审查有负面影响。建议统一 UTF-8，重新保存 README、注释和提示词种子数据。

---

## 5. 面试官视角：还缺少哪些真正有含金量的内容

按求职价值排序：

1. **测试体系**：这是区分 Demo 和工程项目的第一道线。
2. **PostgreSQL + Redis + Celery**：证明你理解生产级后端基本盘。
3. **用户级 RAG 上传与异步向量化**：这是 AI 应用岗位非常吃香的内容。
4. **可观测性**：结构化日志、request_id、LLM token 消耗、ASR/TTS 延迟、错误率。
5. **压测与优化报告**：例如聊天接口并发 20/50/100 时的首 token 延迟、总耗时、失败率。
6. **模型效果评估**：RAG 命中率、回答忠实度、Prompt 版本、回归样例集。
7. **限流与成本控制**：防止用户刷爆 LLM、TTS、ASR 成本。

---

## 6. 哪些地方像 Demo，哪些地方接近生产项目

### 像 Demo 的地方

| 点                     | 原因                                                         |
| ---------------------- | ------------------------------------------------------------ |
| SQLite                 | 不能支撑你讲生产并发                                         |
| 无测试                 | 个人 Demo 常见问题                                           |
| 裸 `except:`           | 缺少生产排障能力                                             |
| 无日志                 | 出问题无法定位                                               |
| 手动部署               | 缺少 CI/CD、Docker                                           |
| RAG 仅管理员预置       | 还不是完整用户产品能力                                       |
| 自定义音色仅有工具函数 | [voice/custom](D:/MyProjects/AiFriends/backend/web/views/create/character/voice/custom/create_voice.py:1) 有封装，但还没有形成完整产品链路 |
| 配置写死 IP            | 不利于多环境部署                                             |
| 中文乱码               | 降低项目专业度                                               |

### 接近生产的地方

| 点                        | 原因                           |
| ------------------------- | ------------------------------ |
| JWT access/refresh 分离   | 认证设计方向正确               |
| refresh 并发队列          | 处理了真实竞态问题             |
| SSE 响应头                | 考虑了 Nginx 缓冲              |
| MSE 音频队列              | 处理了浏览器 SourceBuffer 状态 |
| Agent / Memory 分离       | 有任务边界意识                 |
| 角色、好友、消息模型      | 业务模型基本清晰               |
| Gunicorn + Nginx 部署文档 | 至少完成了服务器落地           |

---

## 7. 冲击 Java 后端 / AI 应用工程师，还应该补哪些能力

### Java 后端方向

| 优先级 | 能力               | 建议                                                         |
| ------ | ------------------ | ------------------------------------------------------------ |
| P0     | Spring Boot 3      | 用 Java 重写一个 Chat Gateway 或用户/RAG 管理服务            |
| P0     | PostgreSQL / MySQL | 索引、事务、慢查询、连接池必须能讲                           |
| P0     | Redis              | 限流、缓存、任务状态、分布式锁                               |
| P0     | MQ                 | Celery 是 Python 方案；Java 面试建议理解 Kafka/RabbitMQ/RocketMQ |
| P1     | 高并发压测         | JMeter/Locust 压测并输出优化报告                             |
| P1     | JVM 基础           | GC、线程池、CompletableFuture、虚拟线程                      |
| P1     | 微服务设计         | 网关、鉴权、服务拆分、幂等、重试、降级                       |

### AI 应用工程师方向

| 优先级 | 能力       | 建议                                                         |
| ------ | ---------- | ------------------------------------------------------------ |
| P0     | RAG 工程化 | 文档上传、解析、切分、embedding、索引、召回、重排、权限隔离  |
| P0     | Agent 设计 | Tool schema、状态管理、失败重试、工具权限、Human-in-the-loop |
| P0     | 流式体验   | 首 token 延迟、TTS 首包延迟、取消任务、断线处理              |
| P1     | PromptOps  | Prompt 版本、评测集、A/B、回归测试                           |
| P1     | 成本治理   | token 统计、用户限额、模型路由、小模型摘要                   |
| P1     | 多模型适配 | OpenAI-compatible provider 抽象，支持 DashScope/OpenAI/DeepSeek 切换 |

---

## 8. 最值得扩展的功能方向：按求职价值排序

### 1. 用户上传文档构建个人 RAG

最高价值。因为它能覆盖后端、AI、异步任务、权限、文件处理、向量库全链路。

建议设计：

```text
用户上传文档
  → 文件落 OSS / 本地存储
  → 创建 Document 记录
  → Celery 异步解析
  → chunk 切分
  → embedding
  → LanceDB 写入 user_id / document_id / chunk_id
  → Chat Agent 按 friend/user 权限检索
```

### 2. Celery + Redis 异步任务系统

把 Memory 更新、文档向量化、音色创建、长耗时任务都放入任务队列。这个对后端岗位非常加分。

### 3. PostgreSQL 迁移 + 索引优化

必须做。你想冲社招，这个比加新 UI 更重要。

### 4. 日志、监控、错误追踪

加结构化日志：

- request_id；
- user_id；
- friend_id；
- model；
- input/output tokens；
- ASR/TTS 耗时；
- RAG 命中文档；
- 异常堆栈。

### 5. 自定义角色音色

已有工具函数，适合继续补齐。但求职价值低于 RAG 和工程化，属于产品亮点。

### 6. Java Spring Boot 辅助服务

如果你主投 Java 后端，可以加一个小型 Java 服务，例如：

- RAG 文档管理服务；
- 音频任务管理服务；
- 用户额度/计费服务；
- API Gateway。

不建议重写整个项目，投入产出比低。

---

## 9. 高级工程化路线图

### 第 1 阶段：止血与专业化，1 周

- 修复中文乱码；
- `SECRET_KEY`、IP、模型名、URL 全部环境变量化；
- 替换裸 `except:`；
- 增加 Python logging；
- 修正 HTTP 状态码；
- 清理 `console.log` / `print`；
- 增加 `/api/health/`。

### 第 2 阶段：测试与数据库，2-3 周

- 引入 `pytest-django`；
- 补认证、角色、好友、聊天历史测试；
- mock LLM / ASR / TTS；
- SQLite 迁移 PostgreSQL；
- 为 `Friend`、`Message`、`Character` 查询加索引；
- 增加 Docker Compose：Django + PostgreSQL + Redis。

### 第 3 阶段：异步化与可观测性，3-5 周

- 引入 Celery + Redis；
- Memory Agent 改异步任务；
- 文档向量化改异步任务；
- 增加任务状态表；
- 增加结构化日志；
- 增加 Sentry 或类似错误追踪；
- 记录 token 成本、首 token 延迟、TTS 首包延迟。

### 第 4 阶段：AI 工程深化，4-8 周

- 用户上传文档构建个人 RAG；
- chunk 元数据与权限隔离；
- RAG 召回评测集；
- Prompt 版本管理；
- Agent tool 调用失败重试；
- 支持多个模型 provider；
- 压测并输出性能优化报告。

---

## 10. 简历包装建议

### 项目名称

**AI Friends：基于 LangGraph 的实时语音 AI 角色聊天平台**

### 一句话描述

独立设计并实现一个支持 AI 角色创建、文本/语音实时对话、RAG 知识检索和长期记忆的全栈 AI 应用，完成前端、后端、Agent 编排、语音链路和服务器部署。

### 推荐简历 bullets

- 基于 **Django REST Framework + Vue 3** 实现 AI 角色聊天平台，支持角色创建、好友关系、聊天历史、JWT 登录认证与首页角色探索。
- 基于 **LangGraph** 构建 Chat Agent，支持 Tool Calling，集成 `get_time` 与 LanceDB 知识库检索工具，实现 RAG 增强回答。
- 设计 **长期记忆机制**，每 10 条消息触发 Memory Agent 对历史对话进行摘要压缩，并注入后续系统提示词提升多轮对话连续性。
- 实现 **SSE + DashScope TTS WebSocket** 的实时双流输出，单次聊天请求同时推送 LLM 文本增量与 base64 音频块，前端通过 MSE 流式播放。
- 实现浏览器端 **VAD → ASR → LLM → TTS → MSE** 语音闭环，支持用户语音输入、AI 语音回复与语音打断。
- 设计 JWT 双 Token 认证方案，access token 存于内存，refresh token 存于 httpOnly cookie，并在前端通过 subscriber queue 解决并发 401 刷新问题。
- 基于 Gunicorn + Nginx 完成服务器部署，并针对 SSE 配置 `X-Accel-Buffering: no`，避免代理缓冲影响实时输出。

注意：暂时不要写“高并发”“生产级”“企业级”，除非你补了压测、PostgreSQL、异步任务、日志和监控。

---

## 11. 真实面试官会怎么看

### 最加分的地方

1. **AI 应用链路完整**：不是只调一个 Chat API，而是 Agent、RAG、Memory、ASR、TTS 都打通了。
2. **实时流式体验有技术难度**：SSE + WebSocket + MSE 是真实复杂度。
3. **学习能力强**：Java 背景能独立完成 Python + Vue + AI 工程，说明迁移能力不错。
4. **有部署意识**：不是停留在 localhost。

### 最容易被质疑的地方

1. 为什么没有测试？
2. 为什么还用 SQLite？
3. 为什么大量裸 `except:`？
4. Memory 为什么同步执行，不放任务队列？
5. 用户断开 SSE 后，LLM/TTS 调用如何取消？
6. RAG 如何支持用户私有知识库和权限隔离？
7. 项目中哪些是你自己设计的，哪些是照文档拼接的？
8. 有没有压测过首 token 延迟、并发连接数、TTS 延迟？

---

## 12. 我会追问的技术问题

1. 画一下你的 LangGraph 图，解释 `agent -> tools -> agent` 循环什么时候结束。
2. SSE 和 WebSocket 在你的项目中分别承担什么职责？为什么不全部用 WebSocket？
3. 如果 100 个用户同时语音聊天，当前架构瓶颈在哪里？
4. SQLite 在多 worker Gunicorn 下有什么问题？
5. Memory Agent 每 10 条消息总结一次，这个阈值怎么来的？如何评估摘要质量？
6. RAG chunk size 和 overlap 为什么这么设？如何评估召回效果？
7. 如果用户上传 100MB PDF，你如何异步处理、展示进度、失败重试？
8. Refresh token 存 httpOnly cookie 可以防 XSS 吗？如何防 CSRF？
9. 如果 TTS WebSocket 中途失败，前端体验如何降级？
10. 你会如何把这个项目拆成 Java 微服务？

---

## 13. 社招竞争力判断

| 场景            | 判断                                                        |
| --------------- | ----------------------------------------------------------- |
| Java 后端初中级 | 有加分，但需要把 Java 基础、数据库、Redis、MQ 补实          |
| Java 高级后端   | 当前还不够，主要缺工程化和高并发证据                        |
| AI 应用工程师   | 已达到加分项目标准                                          |
| AI Agent 工程师 | 有基础，但需要补多 Agent、评测、工具可靠性、状态持久化      |
| 全栈应用工程师  | 竞争力较好                                                  |
| 开源项目展示    | 有吸引力，但需要修乱码、Docker、README、Demo 视频和一键启动 |

综合评分：

```text
AI 应用亮点：8/10
后端工程化：5/10
系统设计表达：6.5/10
简历吸引力：7/10
当前社招竞争力：P5+ 到 P6- 之间
补齐工程化后：可接近 P6 入门水平
```

---

## 14. 是否达到“AI 岗位加分项目”标准

结论：**达到，但还不是强加分项目。**

它已经具备 AI 岗位加分项目的关键要素：

- Agent；
- RAG；
- 长期记忆；
- 流式输出；
- 语音交互；
- 前后端完整闭环；
- 可部署演示。

但距离“强加分”还差：

- 用户级 RAG；
- 异步任务；
- 测试；
- 日志监控；
- 模型效果评估；
- 成本控制；
- 压测数据。

最后给你一个很真实的建议：面试时不要把它包装成“生产级大系统”，而要包装成：

> 我基于真实产品目标独立完成了一个 AI 应用闭环，目前核心 AI 链路已经打通；我也清楚它距离生产级系统还差测试、异步化、数据库迁移、可观测性和压测，这些已经在我的下一阶段工程化路线图中。

这个表达会比硬夸项目更打动 Tech Lead，因为它体现的是技术判断力。