# AiFriends 项目 Java 技术栈重写：调研分析报告

> 撰写日期：2026-05-16 | 目标读者：Java 后端开发工程师

---

## 一、项目现状总结

### 1.1 现有技术栈

| 层 | 技术 | 评价 |
|----|------|------|
| **后端框架** | Django 6.0 + DRF | 成熟，开发效率高 |
| **数据库** | SQLite | 不适合生产 |
| **ORM** | Django ORM（6个模型） | 简洁，自动迁移 |
| **认证** | SimpleJWT（access 2h + refresh 7d） | 轮换+黑名单，设计良好 |
| **AI 编排** | LangGraph（chat agent + memory agent） | 核心资产，架构优秀 |
| **向量存储** | LanceDB | 轻量，但生态小 |
| **语音** | DashScope TTS/ASR WebSocket | 流式并行，设计精巧 |
| **前端** | Vue 3 + Vite 7 + Pinia + daisyUI 5 | 组件化良好，UI 现代化 |
| **CSS** | Tailwind CSS 4 + daisyUI 5 | 开发效率高 |
| **部署** | Gunicorn + Nginx | 标准 Python 部署 |

### 1.2 架构亮点（必须保留）

1. **LangGraph Agent 架构** — Chat agent 用 tool-calling loop（`agent → tools → agent`），Memory agent 为线性总结图，模型可独立切换
2. **SSE 并行流式输出** — 同一条 SSE 连接交错推送 LLM 文本增量 + TTS base64 音频，前端 MediaSource API 实时播放
3. **JWT 无感刷新** — 请求拦截器 + 并发订阅队列，避免刷新风暴；access 仅存内存，refresh 存 httpOnly cookie
4. **浏览器端 VAD** — Silero VAD (ONNX) 在浏览器运行，语音端点检测零服务端成本
5. **SystemPrompt 可配置** — 数据库表管理 prompt 模板，按 order_number 拼接，非代码硬编码
6. **Character.profile 双角色** — 首行为用户可见简介，全文为 LLM system prompt，一个字段两种用途
7. **HTTP 状态码规范** — 200=成功，400=参数错，401=认证，404=不存在，409=冲突，500=服务端异常
8. **统一错误处理** — `logger.exception()` 捕获全链路异常，无 bare `except:`

### 1.3 已知不足（用户 + Review 报告共识）

**功能层面：**
- 无管理员后台（仅 Django Admin，功能单一）
- 无用户级 RAG（仅全局知识库 `Bailian_Overview.txt`）
- 不支持用户自定义音色上传
- 聊天 UI 简单（daisyUI chat bubble），非微信电脑端双栏布局
- 仅对接 DashScope 单一 AI 供应商

**工程层面：**
- SQLite 不适合并发生产
- 零测试（无 pytest，无前端测试）
- `.env` 含密钥被 git 追踪
- 无结构化日志（无 request_id，无 trace context）
- 无可观测性（无指标/链路追踪/面板）
- 无尽流/成本控制
- 聊天链路全同步（Django 线程阻塞等待 LLM + TTS）
- 长期记忆存为纯文本 `Friend.memory` 字段，未向量化
- 文件存本地磁盘，未落 OSS
- 无 Redis、无消息队列

---

## 二、Java 技术栈选型分析

### 2.1 总体推荐：Spring Boot 3.x 单体 + 按需拆分

当前项目规模（约 20 个 API 端点、6 个数据模型、单一用户场景）远未到需要微服务拆分的程度。推荐 **Spring Boot 单体** 作为起点，通过模块化分包为未来的拆分预留空间。待用户量/功能增长后，可渐进式拆分为微服务。

### 2.2 逐组件对比选型

#### 2.2.1 Web 框架：Spring Boot 3.x + Spring MVC

| 对比项 | Django | Spring Boot |
|--------|--------|-------------|
| REST API | DRF APIView | `@RestController` + `@RequestMapping` |
| 请求/响应 | `request.data` / `Response(dict)` | `@RequestBody` / `ResponseEntity<T>` |
| 文件上传 | `request.FILES` | `@RequestParam MultipartFile` |
| 中间件 | Django Middleware | `Filter` / `HandlerInterceptor` |
| 全局异常处理 | `except Exception` 手动 | `@ControllerAdvice` 统一 |
| 参数校验 | 手动 if-else | `@Valid` + Bean Validation |

**选型建议：Spring Boot 3.4.x（最新稳定版）**。Spring Boot 的 `@ControllerAdvice` 可以很好地统一 HTTP 状态码规范，`Bean Validation` 替换手写空值检查。

#### 2.2.2 ORM & 数据库：PostgreSQL + JPA + Hibernate + Flyway

| 对比项 | Django + SQLite | Spring Boot + PostgreSQL |
|--------|-----------------|--------------------------|
| 模型定义 | `models.Model` class | `@Entity` + `@Table` |
| 迁移 | `makemigrations` / `migrate` | Flyway / Liquibase |
| 查询 | Django ORM QuerySet | Spring Data JPA Repository / JPQL |
| 关系 | `ForeignKey` / `OneToOneField` | `@ManyToOne` / `@OneToOne` |
| JSON 字段 | `TextField` 存 JSON 字符串 | `@Column(columnDefinition = "jsonb")` |
| 全文搜索 | 无（使用 `icontains`） | PostgreSQL `tsvector` + GIN 索引 |
| 向量检索 | LanceDB（独立进程） | pgvector 扩展，同库内查询 |

**选型建议：PostgreSQL 16 + pgvector**。原因：
- pgvector 将向量和业务数据放在同一数据库，简化运维，避免 LanceDB 额外进程
- JSONB 字段天然适合 Message 的 input/output JSON 存储
- 支持全文搜索（未来角色搜索场景）
- MySQL 8.x 也是可选方案，但 pgvector 优势明显

**ORM 建议：Spring Data JPA + QueryDSL**。JPA 的 `@Entity` 注解体系是 Java 标准，QueryDSL 提供类型安全的动态查询（替代 Django ORM 的链式 filter）。

#### 2.2.3 认证鉴权：Spring Security + jjwt

| 功能 | Django SimpleJWT | Java 等价方案 |
|------|-----------------|--------------|
| access/refresh token 生成 | SimpleJWT 内置 | jjwt 0.12.x fluent API 手动签发 |
| refresh 自动轮换 | `ROTATE_REFRESH_TOKENS` | 手动实现（生成新 token 对 + 旧 token 入黑名单） |
| 黑名单 | `BlacklistMixin` | Redis `SETEX token_id` |
| httpOnly cookie | `Response.set_cookie()` | `ResponseCookie` 构建 |
| 权限装饰器 | `permission_classes = [IsAuthenticated]` | `@PreAuthorize` / `SecurityFilterChain` |

**选型建议：Spring Security 6.x + jjwt 0.12.x**。

选择 jjwt 而非 Nimbus 的理由：
- **API 简洁**：jjwt 的 fluent builder 链式 API（`Jwts.builder().subject().issuedAt().signWith().compact()`）比 Nimbus 的显式构造更直观
- **国内社区活跃**：中文资料丰富，团队协作门槛低
- **Spring Boot 集成**：与 Spring Security 配合成熟，社区有大量最佳实践参考
- **功能充分**：0.12.x 版本已完整支持 JWT 标准（HS256/RS256、claims、expiration），完全覆盖项目所需

**JWT 设计要点：**

```java
// access token (2h TTL) — 返回在 response body
String accessToken = Jwts.builder()
    .subject(userId.toString())
    .claim("type", "access")
    .issuedAt(new Date())
    .expiration(new Date(System.currentTimeMillis() + 7200_000))
    .signWith(secretKey)   // HS256
    .compact();

// refresh token (7d TTL) — 设置在 httpOnly cookie
String refreshToken = Jwts.builder()
    .subject(userId.toString())
    .claim("type", "refresh")
    .issuedAt(new Date())
    .expiration(new Date(System.currentTimeMillis() + 604800_000))
    .signWith(secretKey)
    .compact();
```

前端 JWT 刷新逻辑无需改变（仍走 `/api/user/account/refresh_token/`），Spring Security 过滤器链可完美复刻当前认证模型。

#### 2.2.4 AI Agent & LangGraph：Hybrid 方案（Java + Python Sidecar）为主推荐

这是 **迁移最复杂的部分**。当前 LangGraph 的 tool-calling loop 是核心逻辑，Java 生态无直接等价物。

| 方案 | 优点 | 缺点 | 工期影响 |
|------|------|------|---------|
| **A. Hybrid（推荐）** | 100% 保留现有 LangGraph，风险最低，Python AI 生态完整 | 需维护双语言服务，增加运维复杂度 | 基准（25w） |
| **B. LangChain4j 全量迁移** | 纯 Java 统一技术栈，类型安全 | 缺乏有状态图编排（LangGraph StateGraph 无直接等价物），周边 Tool 生态不如 Python | +3~5w |
| **C. Spring AI + 手动实现 Agent Loop** | 利用 Spring AI 的多供应商抽象 | 需自行实现 tool-calling loop 和 state graph，工作量最大 | +5~8w |

**推荐方案：A（Hybrid）**。理由：
1. 当前 LangGraph Chat Agent + Memory Agent 代码已稳定运行，是经过验证的核心资产，不应冒重写风险
2. Python 在 AI/ML 生态的统治地位短期内不会改变，LangChain/LangGraph/LanceDB 等库的 Java 移植总是滞后的
3. Hybrid 架构在业界是主流做法（Uber、Netflix 均有 Python ML + Java 业务层的案例）
4. 服务边界清晰：Java 管业务（auth、CRUD、文件、限流、Admin），Python 管 AI（agent、embedding、TTS/ASR）
5. 未来可渐进式迁移：当 LangChain4j 生态足够成熟时，可逐个 agent 替换 Python 端点，无需一次性重写

Hybrid 方案的详细设计见 [第四章 4.4 节](#44-hybrid-方案详细设计服务拆分与通信)。

**多 AI 供应商支持：** 在 Python Sidecar 侧通过 adapter 模式统一，或通过 Spring AI 在 Java 侧做供应商路由。推荐后者——Java 侧根据配置决定调用哪个 AI 供应商的 Sidecar，Python 侧保持对 DashScope 的专注。

#### 2.2.5 SSE 流式输出：Spring WebFlux + Reactor

| 功能 | Django | Java |
|------|--------|------|
| SSE 响应 | 手动 `StreamingHttpResponse` + `yield` | `Flux<ServerSentEvent<T>>` |
| 并行 TTS WebSocket | 单独线程 + `queue.Queue` | Reactor `Sinks.Many` + `Mono.zip` |
| 背压控制 | 无（手动队列） | Reactor 内置背压 |
| 超时/取消 | `processId` 递增丢弃 | `Flux.takeUntilOther()` / `Disposable` |

**选型建议：Spring WebFlux（响应式）**。当前 Django SSE 是手动线程+队列模式，WebFlux 的响应式编程模型天然适合 SSE 流式场景：
- `Flux<ServerSentEvent>` 直接映射到 SSE 输出
- `Sinks.Many` 替代 `queue.Queue`，线程安全且支持多订阅者
- `Flux.merge()` 实现 LLM 文本流与 TTS 音频流并行推送

#### 2.2.6 向量存储 & RAG

| 方案 | 适用场景 | 优劣势 |
|------|---------|--------|
| **pgvector** | 中小规模，希望一库多用 | 运维简单，SQL 兼容，向量检索性能中等 |
| **Milvus** | 大规模向量检索，生产级 | 性能极致，支持混合检索，需独立部署 |
| **Elasticsearch + 向量插件** | 需要全文+向量混合检索 | 功能全面但重 |

**推荐：pgvector（当前阶段）→ Milvus（未来扩展）**

pgvector 的 `ivfflat` 和 `hnsw` 索引在 10 万级向量下性能足够，且与业务数据同一数据库，简化事务和权限管理。用户级 RAG 的隐私隔离可以通过 `WHERE user_id = ?` 天然实现。

#### 2.2.7 消息队列 & 异步处理

| 场景 | 技术选型 | 说明 |
|------|---------|------|
| **消息队列** | RabbitMQ（传统企业首选）或 Apache Kafka（日志/流式） | 建议 RabbitMQ，管理界面友好，Spring AMQP 集成成熟 |
| **异步任务** | Spring `@Async` + 自定义线程池 或 RabbitMQ 消费 | 轻量异步用 @Async，重量级用消息队列 |
| **缓存** | Redis（Spring Data Redis） | JWT 黑名单、限流计数、会话缓存、临时数据 |

**需要异步化的链路：**
1. **聊天记忆更新**（当前：同步阻塞在 SSE 流末尾）→ 发消息到队列，异步消费
2. **RAG 文档预处理**（当前：不存在）→ 上传后异步 embedding + 入库
3. **TTS 音频生成**（当前：同步 WebSocket）→ 可保持流式，仅将日志落库异步化

#### 2.2.8 文件存储：阿里云 OSS

当前 `.env` 已有 OSS 配置（AccessKey、Bucket、Region），但代码未使用。Java 集成简单：

```java
// Aliyun OSS SDK for Java
OSS ossClient = new OSSClientBuilder().build(endpoint, accessKeyId, accessKeySecret);
ossClient.putObject(bucketName, objectName, inputStream);
```

需替换的范围：用户头像、角色头像、聊天背景图、用户级 RAG 文档。

#### 2.2.9 可观测性

| 维度 | 技术选型 | 对标当前 |
|------|---------|---------|
| **结构化日志** | Logback + JSON encoder + MDC（request_id, user_id） | 当前为纯文本日志 |
| **指标采集** | Micrometer + Prometheus | 当前无 |
| **链路追踪** | Micrometer Tracing + Brave/Zipkin | 当前无 |
| **可视化面板** | Grafana（对接 Prometheus + Loki） | 当前无 |
| **健康检查** | Spring Boot Actuator + `/health` | 当前无 |
| **LLM 可观测** | 自定义 Micrometer Timer（首 token 延迟、token 消耗、ASR/TTS 延迟） | 当前无 |

**关键指标：**
- `chat.first_token_latency` — 首 token 延迟（Histogram）
- `chat.total_tokens` — LLM token 消耗（Counter，按模型/用户标签）
- `tts.audio_latency` — TTS 音频延迟
- `asr.transcription_latency` — ASR 转录延迟
- `api.request.duration` — 各端点 P50/P99 延迟
- `rate_limit.exceeded` — 限流触发次数

#### 2.2.10 限流 & 成本控制

| 方案 | 适用场景 |
|------|---------|
| **Bucket4j**（本地令牌桶） | 单实例限流，轻量 |
| **Spring Cloud Gateway + Redis Rate Limiter** | 网关层限流，多实例 |
| **自定义 Redis 计数器** | 灵活，按用户/接口/时间窗口 |

**建议：** 先用 Redis 实现简单的计数限流：
- 每用户每小时 LLM 调用次数上限
- 每用户每天 TTS 字符数上限
- 每用户每天 ASR 调用次数上限
- 免费用户全局速率限制（如 10 次/分钟）

#### 2.2.11 测试框架

| 层 | 技术选型 |
|----|---------|
| **单元测试** | JUnit 5 + Mockito |
| **数据库集成测试** | `@DataJpaTest` + Testcontainers（PostgreSQL 容器） |
| **API 集成测试** | `@SpringBootTest` + MockMvc / TestRestTemplate |
| **前端测试** | Vitest（Vue）或 Jest（React） |
| **E2E 测试** | Playwright |
| **契约测试** | Spring Cloud Contract（未来微服务时需要） |

#### 2.2.12 管理员后台

| 方案 | 优点 | 缺点 |
|------|------|------|
| **自建 Admin API（推荐）** | 轻量，与业务模型一致，无侵入 | 需手写 CRUD 页面 |
| **若依 (RuoYi)** | 功能全面，开箱即用 | 侵入性强，自带用户/角色/菜单体系，与项目模型冲突 |
| **AdminForth** | 类 Django Admin，自动生成 CRUD | Java 生态不成熟 |

**推荐：自建 Admin API，拒绝引入若依。**

不选若依的理由：
- 若依不是库，是完整项目模板——自带 `sys_user`、`sys_role`、`sys_menu` 等几十张表。项目已有 `UserProfile` 和角色字段，两套用户体系要么合并（改造成本高），要么并存（数据割裂）
- 若依的代码组织与 feature-based 分包不兼容，硬塞会破坏项目结构
- 管理员后台需要的无非是用户管理、角色审核、操作日志——这几个 CRUD 接口 + Spring Security `ROLE_ADMIN` + 前端路由守卫即可覆盖，不值得引入一个框架

**自建方案：**
- 后端：`@PreAuthorize("hasRole('ADMIN')")` 保护的 AdminController，提供用户列表/禁用、角色管理、文件管理、操作日志查询等接口
- 前端：与用户侧共用同一 Vue 项目，通过路由 `meta: { requiresAdmin: true }` + `beforeEnter` 守卫区分管理区域
- 工作量：Phase 6 中 Admin 前端页面 1.5w（含用户管理、角色管理、文件管理、操作日志 4 个页面），Admin 后端接口 0.5w，合计 2w

### 2.3 前端选型分析（Vue 3 vs React）

| 维度 | 保留 Vue 3 | 改用 React |
|------|-----------|-----------|
| **迁移工作量** | 低（仅 UI 重设计） | 高（全部重写 ~50 组件） |
| **与 Java 生态契合度** | 一般 | 更好（React 在 Java 后端圈更主流） |
| **微信样式适应性** | daisyUI + Tailwind 即可 | 可用 shadcn/ui 或 Ant Design |
| **招聘友好度** | 国内 Vue 开发者多 | 全球 React 开发者更多 |
| **现有代码资产** | 可复用 ~70% 逻辑代码 | 零复用 |
| **SSE/MSE 处理** | 现有实现成熟，无缝迁移 | 需重新实现 |
| **Admin 后台** | 共用同一 Vue 项目，路由守卫区分 | 需独立 Admin SPA 或选择 React Admin 框架 |

**推荐：保留 Vue 3。** 理由：
1. 前端代码质量不错，SSE + MSE 音频管道 + JWT 刷新等核心逻辑是经过验证的资产
2. 重写后端 + 新功能开发已是巨大工作量，同时重写前端风险过高
3. Vue 3 组合式 API 与现代 React（Hooks）理念相同，未来切换没有认知鸿沟
4. Admin 后台与用户侧共用 Vue 项目，无需引入额外框架

前端主要工作量集中在 **UI 重设计为微信电脑端样式**（双栏布局：左侧好友列表 + 右侧聊天窗口），而非框架重写。

---

## 三、数据模型优化建议

### 3.1 当前模型问题

1. **`Message.input` / `Message.output`**：存完整 prompt/response JSON 字符串（最长 50000 字符），无索引，查询低效
2. **`Friend.memory`**：纯文本长期记忆，无法按语义检索，每次只取最近一条
3. **`Character.profile`**：双角色字段无文档化约束（首行为简介为约定，非数据库约束）
4. **`Voice` 模型**：仅存储 DashScope voice_id，扩展自定义音色后需新增字段（上传用户、音频文件路径、是否共享等）
5. **`SystemPrompt` 模型**：`title` 仅用两值（`'回复'`/`'记忆'`），靠代码约定而非枚举约束
6. **无 `updated_at` 的自动更新**：需手动设置

### 3.2 优化建议

```
User (Django/auth 内置)
  └── UserProfile (1:1)
       ├── name, photo, profile
       └── created_at, updated_at

Voice
  ├── name, voice_id, profile
  ├── type: ENUM('PRESET', 'CUSTOM')        ← 新增：区分预设/自定义
  ├── owner → UserProfile (nullable)         ← 新增：自定义音色归属
  ├── sample_audio_url (nullable)            ← 新增：样本音频 OSS URL
  ├── is_public: boolean                     ← 新增：是否共享到音色广场
  └── created_at, updated_at

Character
  ├── author → UserProfile
  ├── name, profile
  ├── introduction: varchar(500)             ← 新增：显式分离简介
  ├── system_prompt: text                    ← 新增：显式分离系统提示词
  ├── photo, background_image → OSS URL
  ├── voice → Voice
  ├── is_public: boolean (default true)
  └── created_at, updated_at

Friend
  ├── user_profile → UserProfile
  ├── character → Character
  ├── memory: text                               ← 保留：最近一次完整摘要的文本备份（兜底用）
  ├── last_memory_updated_at: timestamp          ← 新增：记忆更新时间
  └── created_at, updated_at

Message
  ├── friend → Friend
  ├── user_message: text
  ├── input_json: jsonb                      ← 改为：PostgreSQL JSONB
  ├── output_text: text
  ├── input_tokens, output_tokens, total_tokens
  └── created_at

MemoryVector                               ← 新模型：向量化长期记忆
  ├── friend → Friend
  ├── content: text                         ← 记忆内容摘要
  ├── embedding: vector(1024)               ← pgvector 向量
  ├── source_message_ids: integer[]         ← 来源消息 ID 列表
  └── created_at

UserDocument                               ← 新模型：用户 RAG 文档
  ├── owner → UserProfile
  ├── title: varchar(200)
  ├── file_url: varchar ← OSS URL
  ├── chunks_count: integer
  └── created_at

DocumentChunk                              ← 新模型：RAG 文档分块（可选，可用 pgvector 替代）
  ├── document → UserDocument
  ├── chunk_index: integer
  ├── content: text
  ├── embedding: vector(1024)
  └── created_at

RateLimitRecord                            ← 限流状态（仅存 Redis，不入库）
  ├── Key: rate_limit:{user_id}:{resource_type}:{window}
  ├── 值: 当前窗口计数
  ├── TTL: 自动过期 (Redis EXPIRE)
  └── 操作: INCR 原子递增

TokenUsageRecord                           ← 用量审计记录（异步落库，非限流控制）
  ├── user → UserProfile
  ├── resource_type: enum('LLM','TTS','ASR')
  ├── tokens_used: integer
  ├── recorded_at: timestamp
  └── 用途: 统计分析/成本核算，不用于实时限流判断
```

**限流设计原则：** 限流是高频写、短生命周期计数，必须全在 Redis。Key 设计 `rate_limit:{user_id}:{resource_type}:{window}`（如 `rate_limit:123:LLM:1h`），`INCR` + `EXPIRE` 原子操作，不落数据库。`TokenUsageRecord` 表仅用于异步审计/成本核算，与限流判断解耦。

### 3.3 关键改进

1. **Character 拆分 introduction / system_prompt**：消除"首行是简介"的隐式约定，数据库层面明确区分
2. **Memory 向量化 + 文本兜底**：`MemoryVector` 表（pgvector）实现语义检索，`Friend.memory` 保留为最近一次完整摘要的文本备份，两者职责不同且共存
3. **Message 使用 JSONB**：PostgreSQL JSONB 可建 GIN 索引，支持高效查询和部分更新
4. **Voice 扩展**：支持自定义音色的元数据存储
5. **文件 URL 化**：`photo`/`background_image` 等字段存 OSS URL 而非本地路径
6. **JPA Auditing**：`@CreatedDate` / `@LastModifiedDate` 自动管理时间戳
7. **限流状态 Redis 化**：限流计数全在 Redis（`INCR` + `EXPIRE`），不入库。仅用量审计数据异步落 `TokenUsageRecord` 表

---

## 四、架构设计

### 4.1 目标架构图（Hybrid 方案）

```
┌──────────────────────────────────────────────────────────────┐
│                     Nginx (反向代理)                           │
│  /          → Vue SPA static (含 Admin 路由守卫)               │
│  /api/*     → Spring Boot (8080)                             │
│  /grafana/* → Grafana (3000)                                  │
└──────────────────────────────────────────────────────────────┘
                          │
       ┌──────────────────┼──────────────────┐
       ▼                  ▼                  ▼
┌─────────────┐  ┌──────────────┐  ┌──────────────┐
│ Spring Boot  │  │  PostgreSQL  │  │    Redis     │
│  (业务主服务)  │  │  + pgvector  │  │  (缓存/限流)  │
│  :8080       │  │  :5432       │  │  :6379       │
└──────┬──────┘  └──────┬───────┘  └──────────────┘
       │                │
       │  HTTP REST     │  共享数据库（读）
       │  (同步调用)     │
       ▼                ▼
┌──────────────┐  ┌──────────────────────────────┐
│  RabbitMQ    │  │  Python FastAPI (AI Sidecar) │
│  (异步消息)   │  │  :8001                       │
│              │  │  ├── Chat Agent (LangGraph)  │
│              │  │  ├── Memory Agent (LangGraph)│
│              │  │  ├── RAG Embedding + Search  │
│              │  │  ├── TTS WebSocket Client    │
│              │  │  └── ASR WebSocket Client    │
└──────┬───────┘  └──────────────┬───────────────┘
       │                        │
       │   异步消费              │   外部 API 调用
       │   (记忆更新/RAG处理)     │   (DashScope)
       ▼                        ▼
┌──────────────────────────────────────────────────┐
│              外部服务                              │
│  DashScope API (LLM/Embedding/TTS/ASR)           │
│  阿里云 OSS (文件存储)                             │
│  Prometheus + Grafana (可观测性)                   │
└──────────────────────────────────────────────────┘
```

**关键通信路径：**

| 路径 | 方向 | 协议 | 场景 |
|------|------|------|------|
| ① 前端 → Java | → | HTTP REST | 所有 CRUD + 认证 |
| ② 前端 → Java | → | SSE (代理) | 聊天流式响应 |
| ③ Java → Python | → | HTTP REST (内网) | 触发聊天、ASR、自定义音色注册 |
| ④ Python → Java → 前端 | ← → | SSE (Java 代理) | LLM token + TTS 音频流 |
| ⑤ Java → RabbitMQ → Python | → | AMQP | 记忆更新、RAG 文档处理 |
| ⑥ Python → PostgreSQL | → | JDBC/psycopg | 写入 MemoryVector、DocumentChunk |
| ⑦ Python → DashScope | ⇄ | HTTPS + WSS | LLM/TTS/ASR/Embedding 调用 |

### 4.2 项目包结构（Feature-based Package 划分）

单体项目使用 package 划分领域，不做 Maven 多模块。真正需要独立部署时再拆。

```
backend-java/src/main/java/com/aifriends/
├── common/                    # 全局基础设施
│   ├── config/                #   SecurityConfig, WebClientConfig, RedisConfig, OssConfig
│   ├── exception/             #   GlobalExceptionHandler (@ControllerAdvice)
│   ├── dto/                   #   公共 DTO: ApiResponse<T>, PageRequest, PageResponse
│   └── util/                  #   工具类: RequestIdGenerator
│
├── auth/                      # 认证
│   ├── security/              #   JwtFilter, JwtTokenProvider (jjwt), SecurityConfig
│   ├── LoginController.java
│   ├── RegisterController.java
│   ├── RefreshTokenController.java
│   └── AuthService.java
│
├── user/                      # 用户
│   ├── UserProfile.java       #   JPA Entity
│   ├── UserProfileRepository.java
│   ├── UserController.java    #   get_user_info, update_profile
│   └── UserService.java
│
├── character/                 # 角色
│   ├── Character.java         #   JPA Entity
│   ├── Voice.java             #   JPA Entity
│   ├── CharacterRepository.java
│   ├── VoiceRepository.java
│   ├── CharacterController.java  # CRUD
│   ├── VoiceController.java      # get_list
│   └── CharacterService.java
│
├── friend/                    # 好友 & 聊天
│   ├── Friend.java            #   JPA Entity
│   ├── Message.java           #   JPA Entity
│   ├── FriendRepository.java
│   ├── MessageRepository.java
│   ├── FriendController.java  #   get_or_create, remove, list, get_count, is_friend
│   ├── ChatController.java    #   SSE 代理入口 → Python Sidecar
│   ├── HistoryController.java #   get_history
│   └── ChatService.java       #   SSE 代理: WebClient → Flux 转发
│
├── memory/                    # 长期记忆
│   ├── MemoryVector.java      #   JPA Entity (pgvector)
│   └── MemoryVectorRepository.java  #   向量查询: ORDER BY embedding <=> ?
│
├── rag/                       # 用户 RAG
│   ├── UserDocument.java      #   JPA Entity
│   ├── UserDocumentRepository.java
│   ├── DocumentController.java  # 上传 OSS + 发 RabbitMQ 消息
│   └── DocumentService.java
│
├── voice/                     # 语音（ASR/TTS 代理）
│   ├── AsrController.java     #   接收 PCM → 转发 Python Sidecar
│   ├── CustomVoiceController.java  # 自定义音色上传/管理
│   └── VoiceService.java      #   HTTP 客户端 → Python Sidecar
│
├── admin/                     # 管理员
│   └── AdminController.java   #   @PreAuthorize("hasRole('ADMIN')")
│
├── oss/                       # 文件存储
│   └── OssService.java        #   阿里云 OSS SDK
│
├── observability/             # 可观测性
│   ├── logging/
│   │   └── RequestIdFilter.java   # MDC 注入 request_id
│   ├── metrics/
│   │   └── ChatMetrics.java       # Micrometer Timer/Counter
│   └── health/
│       └── ExternalServiceHealthIndicator.java  # DB/Redis/RabbitMQ/Python Sidecar
│
└── ratelimit/                 # 限流
    ├── RateLimitInterceptor.java  # Redis INCR + EXPIRE
    └── RateLimitConfig.java       # 按 resource_type 配置阈值
```

**Hybrid 方案下 voice 包的定位：** 语音包不负责 TTS/ASR 的实际执行（全在 Python 侧），只做 HTTP 代理——接收前端请求 → 转发 Python Sidecar → 返回结果。`DashScope WebSocket Client` 不在 Java 侧，避免职责重叠。

### 4.3 异步任务设计（Hybrid 模式）

```
同步部分 (SSE 实时流):
  前端 (浏览器)
     │  POST /api/friend/message/chat/
     ▼
  Java ChatController
     ├── 验证 JWT (Spring Security Filter)
     ├── 验证好友关系 + 限流检查 (Redis)
     ├── 加载最近消息历史 (PostgreSQL, Java 写入故 Java 传)
     │
     │  HTTP POST → Python FastAPI /agent/chat/
     │  (只传 friend_id + user_message + recent_messages + enable_tts)
     ▼
  Python Chat Agent (LangGraph)
     ├── 自行从 PostgreSQL 加载: Character.system_prompt + SystemPrompt + MemoryVector 向量召回
     ├── LangGraph agent loop: agent → tools → agent (循环)
     ├── 工具: get_time(), search_knowledge_base() + search_user_rag() (用户级RAG)
     ├── 并行: LLM 文本流 + TTS WebSocket
     │
     │  SSE stream → Java WebClient 消费 → Flux<ServerSentEvent> → 前端
     ▼
  前端
     ├── onmessage: 文本增量渲染 + TTS 音频 MSE 播放
     └── [DONE] → 显示完成

异步部分 (消息队列消费):
  Java ChatController (SSE 流结束后)
     ├── 保存 Message 到 PostgreSQL (同步，需确认落库)
     └── 发布事件到 RabbitMQ:
           ├── exchange: "ai-friends.chat"
           ├── routing_key: "chat.completed"
           └── body: { friend_id, message_id, user_id }

  RabbitMQ → Python 消费者:
     ├── Queue "memory.update" → MemoryAgent
     │     ├── 摘要最近10条消息 + 旧记忆
     │     ├── 生成向量化长期记忆
     │     └── 写入 pgvector (MemoryVector 表)
     │
     ├── Queue "usage.record" → TokenUsageRecorder
     │     └── 写入 token_usage_records (PostgreSQL)
     │
     └── Queue "metrics.report" → MetricsCollector
           └── 上报 Micrometer 指标 (Prometheus 拉取)

  RAG 文档上传后 (异步):
    前端 → Java → OSS (同步上传文件)
    Java → RabbitMQ (routing_key: "rag.document.uploaded")
     │
    RabbitMQ → Python 消费者:
       Queue "rag.process":
         ├── 文档解析 (PDF/Word/TXT/Markdown)
         ├── RecursiveCharacterTextSplitter 分块
         ├── CustomEmbeddings (DashScope text-embedding-v4) 生成向量
         └── 写入 pgvector (DocumentChunk 表, 带 owner_id 隐私隔离)

  自定义音色注册 (异步):
    前端 → Java → OSS (同步上传样本音频)
    Java → RabbitMQ (routing_key: "voice.custom.register")
     │
    RabbitMQ → Python 消费者:
       Queue "voice.register":
         └── DashScope Voice Enrollment API 注册
              └── 结果回调: 更新 Voice 表状态
```

### 4.4 Hybrid 方案详细设计：服务拆分与通信

#### 4.4.1 服务边界

```
┌─── Java Spring Boot (业务主服务 :8080) ───┐
│                                            │
│  负责:                                      │
│  ✅ 用户认证 (Spring Security + jjwt)       │
│  ✅ 用户 CRUD (注册/登录/资料)               │
│  ✅ 角色 CRUD (创建/编辑/删除/列表)          │
│  ✅ 好友管理 (添加/删除/列表/计数)            │
│  ✅ 管理员后台 (自建 Admin API + 路由守卫)     │
│  ✅ 文件上传 → OSS (预签名 URL 直传)         │
│  ✅ 限流 (Redis 令牌桶)                      │
│  ✅ 可观测性 (Micrometer + Actuator)         │
│  ✅ SSE 代理 (接收 Python 流 → 转发前端)     │
│  ✅ RabbitMQ 生产者 (发布异步任务)            │
│  ✅ 消息历史查询 (PostgreSQL)                │
│                                            │
│  不负责:                                    │
│  ❌ LLM 调用 / Agent 编排                   │
│  ❌ TTS / ASR WebSocket                    │
│  ❌ Embedding 生成 / 向量检索               │
│  ❌ 文档分块 / 记忆摘要                      │
└────────────────────────────────────────────┘

┌─── Python FastAPI (AI Sidecar :8001) ───┐
│                                          │
│  负责:                                    │
│  ✅ LangGraph Chat Agent (tool-calling)  │
│  ✅ LangGraph Memory Agent (摘要)         │
│  ✅ TTS WebSocket 客户端 (cosyvoice)      │
│  ✅ ASR WebSocket 客户端 (gummy-realtime) │
│  ✅ Embedding API 调用 (text-embedding)   │
│  ✅ 向量检索 (pgvector 查询)              │
│  ✅ 文档分块 + embedding 生成             │
│  ✅ RabbitMQ 消费者 (异步任务)            │
│  ✅ 自定义音色 API 调用 (Voice Enrollment) │
│                                          │
│  不负责:                                  │
│  ❌ 用户认证 / 权限校验                    │
│  ❌ 业务 CRUD                              │
│  ❌ 文件存储                                │
│  ❌ 限流 / 监控                             │
└──────────────────────────────────────────┘
```

#### 4.4.2 通信协议选型

| 场景 | 协议 | 方向 | 理由 |
|------|------|------|------|
| **聊天请求** | HTTP REST (内网) | Java → Python | 简单、无状态、易于调试；一次请求一次响应 |
| **SSE 流式输出** | HTTP SSE (Java 代理) | Python → Java → 前端 | Java 掌控认证/限流，Python 专注于 AI 生成 |
| **异步记忆更新** | RabbitMQ (AMQP) | Java → Python | 解耦、持久化、支持重试、不阻塞主链路 |
| **异步 RAG 处理** | RabbitMQ (AMQP) | Java → Python | 文档处理耗时较长，必须异步 |
| **数据库读写** | PostgreSQL 连接 | 双向 | Java 读写业务表，Python 读写向量表 |
| **健康检查** | HTTP GET /health | Java ⇄ Python | 互相探测存活状态 |

#### 4.4.3 Java ↔ Python API 契约

**① 聊天（核心同步接口）**

Java 只传业务标识和用户消息，Python 自行从 PostgreSQL 读取配置（character、system_prompt、记忆向量）。减少接口体积，避免数据冗余。

```
POST http://localhost:8001/agent/chat/
Content-Type: application/json
Authorization: Bearer <internal-api-key>   ← 内网 API Key，非用户 JWT

Request:
{
  "request_id": "uuid",          ← 全链路追踪 ID
  "friend_id": 42,
  "user_message": "你好",
  "recent_messages": [            ← Java 从 Message 表加载，避免 Python 重复查
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "enable_tts": true,            ← 是否启用 TTS
  "model": "deepseek-v3.2"       ← 可选：覆盖默认模型
}

# Python 侧自行从 PostgreSQL 读取:
#   - Character.system_prompt  (friend_id → character_id → system_prompt)
#   - SystemPrompt 表 WHERE title='回复' ORDER BY order_number
#   - MemoryVector 表 WHERE friend_id=? ORDER BY embedding <=> query LIMIT 5

Response: text/event-stream (SSE)
data: {"type": "content", "data": "你好！今天"}     ← LLM 文本增量
data: {"type": "audio", "data": "<base64_mp3>"}     ← TTS 音频块
data: {"type": "usage", "data": {"input_tokens": 1234, "output_tokens": 56, "total_tokens": 1290}}
data: {"type": "error", "data": "错误消息"}          ← 异常时
data: [DONE]
```

**② ASR（语音识别）**

```
POST http://localhost:8001/agent/asr/
Content-Type: multipart/form-data

Request:
  audio: <PCM16 binary file>
  sample_rate: 16000

Response 200:
{
  "text": "你好，今天天气怎么样",
  "latency_ms": 850
}
```

**③ 自定义音色注册**

```
POST http://localhost:8001/agent/voice/enroll/
Content-Type: application/json

Request:
{
  "request_id": "uuid",
  "audio_oss_url": "https://oss/voices/user_123/xxx.wav",
  "prefix": "user_123_custom"
}

Response 200:
{
  "voice_id": "cosyvoice-v3-flash-xxx",
  "status": "registered"
}
```

**④ RAG 文档处理（由 RabbitMQ 触发）**

```
# Java 发布消息
rabbitTemplate.convertAndSend(
    "ai-friends.rag",
    "document.uploaded",
    {
      "request_id": "uuid",
      "document_id": 42,
      "owner_id": 123,
      "oss_url": "https://oss/documents/user_123/doc.pdf",
      "title": "我的知识库文档"
    }
)

# Python 消费 → 处理 → 写入 pgvector
# 完成后通过 RabbitMQ 回调通知 Java:
rabbitTemplate.convertAndSend(
    "ai-friends.rag",
    "document.processed",
    {
      "request_id": "uuid",
      "document_id": 42,
      "status": "completed",
      "chunks_count": 35
    }
)
```

#### 4.4.4 数据库共享策略

```
PostgreSQL 数据库: ai_friends

┌── Java 独占写入 ──┐          ┌── Python 独占写入 ──┐
│                    │          │                      │
│  user_profile      │          │  memory_vector       │
│  character         │          │  document_chunk      │
│  voice             │          │                      │
│  friend            │          └──────────────────────┘
│  message
│  system_prompt      │         ┌── 双方可读 ─────────┐
│  user_document      │         │                      │
│  rate_limit_record  │         │  全部表（Python 只读 │
│  token_usage_record │         │  业务表用于获取      │
│                     │         │  character/settings) │
└─────────────────────┘         └──────────────────────┘
```

**事务边界原则：**
- Java 掌管所有业务表的写入——用户、角色、好友、消息
- Python 掌管向量相关表的写入——MemoryVector、DocumentChunk（pgvector 类型字段）
- Python 需要读 Character.profile（system_prompt）、SystemPrompt.prompt 时，**直接读 PostgreSQL 从库或主库**，不走 Java API（避免循环依赖和内网延迟叠加）
- 两服务使用同一个 PostgreSQL 用户但不同 schema 权限，或简单信任内网隔离

#### 4.4.5 部署拓扑

```
                    ┌──────────┐
                    │  Nginx   │
                    │  :443    │
                    └────┬─────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
   ┌──────────┐  ┌────────────┐  ┌──────────┐
   │ Vue SPA  │  │ Spring Boot│  │ Grafana  │
   │ (静态)    │  │ :8080      │  │ :3000    │
   └──────────┘  └──┬────┬────┘  └──────────┘
                    │    │
        ┌───────────┘    └───────────┐
        ▼                            ▼
┌──────────────┐            ┌──────────────┐
│ Python       │            │  RabbitMQ    │
│ FastAPI      │            │  :5672       │
│ :8001        │            │  :15672 (UI) │
└──┬───────┬───┘            └──────────────┘
   │       │
   ▼       ▼
┌──────┐ ┌──────┐
│PostgreSQL│Redis│
│:5432 │:6379│
└──────┘ └──────┘
```

**Docker Compose 服务清单：**
```yaml
services:
  nginx:       # 反向代理
  postgres:    # PostgreSQL 16 + pgvector
  redis:       # Redis 7
  rabbitmq:    # RabbitMQ 3.13
  springboot:  # Java 业务主服务 :8080
  fastapi:     # Python AI Sidecar :8001
  grafana:     # 可观测面板 :3000
  prometheus:  # 指标采集 :9090
```

#### 4.4.6 SSE 代理的风险与应对

Hybrid 方案最大的工程风险是 **SSE 代理的延迟叠加和错误处理复杂度**。当前 Django 直接推 SSE 给前端，Hybrid 变成 `Python SSE → Java WebClient → 前端`，多了一跳内网中转。以下是关键风险点和应对策略：

**① 延迟叠加**

| 环节 | 延迟量级 | 应对 |
|------|---------|------|
| Python → Java WebClient 首包 | ~1-5ms (内网) | 可忽略，远小于 LLM 首 token 延迟 (~500ms+) |
| Java 反序列化 → 重新序列化 SSE | ~0.1ms | 直接透传 byte stream，不解析 JSON |
| 总体叠加 | < 10ms | 对用户体验无影响 |

**② 反压处理**

```
Python 生成快，前端消费慢（网络差/设备慢）→ 堆积在 Java 内存

应对:
- WebClient 读取 Python SSE → Sinks.Many 的缓冲区设置上限 (如 256 条)
- 缓冲区满时: 暂停从 Python 读取 (Reactor 自动背压)
- 前端断开时: 取消 Python 订阅 (WebClient 的 Disposable.dispose())
```

**③ Python 侧超时/异常时 Java 如何向前端报错**

```
场景                          Java 处理
────────────────────────────────────────────────
Python 连接拒绝 (未启动)        → 5xx + "AI 服务暂时不可用"
Python 返回 4xx (参数错)       → 透传错误信息
Python SSE 中途断开             → Flux.error("AI 服务连接中断")
Python 超过 60s 无数据          → 发送 data: {"type": "error", ...} 然后关闭流
```

**④ 连接断开时的资源清理**

```java
// ChatService.java SSE 代理核心逻辑
public Flux<ServerSentEvent<String>> proxyChatStream(ChatRequest req) {
    return webClient.post()
        .uri("http://fastapi:8001/agent/chat/")
        .bodyValue(req)
        .accept(MediaType.TEXT_EVENT_STREAM)
        .retrieve()
        .bodyToFlux(ServerSentEvent.class)
        .doOnCancel(() -> {
            // 前端主动断开 → 取消 Python 订阅
            logger.info("Client disconnected, request_id={}", req.requestId());
        })
        .doOnError(e -> {
            // Python 侧异常 → 日志 + 告警
            logger.error("Python sidecar error, request_id={}", req.requestId(), e);
            meterRegistry.counter("chat.sidecar.error").increment();
        })
        .timeout(Duration.ofSeconds(60))  // 60s 无数据则超时
        .onErrorResume(e -> Flux.just(
            ServerSentEvent.builder()
                .data("{\"type\":\"error\",\"data\":\"" + e.getMessage() + "\"}")
                .build()
        ));
}
```

**⑤ 前端 SSE 客户端改造**

当前 `streamApi.js` 从 Django 直接接收 SSE，改为从 Java 接收无需任何改造——SSE 协议格式不变（`data: {...}\n\n`，`[DONE]` 结束标记），前端对 Java 代理完全透明。

---

## 五、迁移成本估算

### 5.1 前提假设

- 1 名全栈开发（Java 主语言，懂 Vue）
- 标准工作时：5 天/周，8 小时/天
- 包含编码 + 自测时间，不含需求变更

### 5.2 分阶段估算

| 阶段 | 模块 | 人周 | 说明 |
|------|------|------|------|
| **Phase 0** | 项目基础设施 | **2w** | Spring Boot 脚手架、模块分层、CI/CD (GitHub Actions)、Docker Compose 开发环境 (PostgreSQL + Redis + RabbitMQ)、.env 管理、日志框架 |
| **Phase 1** | 数据模型 + 认证 | **3w** | JPA Entity 定义、Flyway 迁移脚本、Spring Security + JWT、登录/注册/刷新/登出 API、用户资料 CRUD |
| **Phase 2** | 角色 & 好友管理 | **2w** | Character CRUD、Voice API、Friend get_or_create/remove/list、首页角色列表、OSS 图片上传 |
| **Phase 3** | 聊天核心 | **4w** | **最复杂模块（纯 Java 方案）**：LangChain4j agent 定义、tool-calling loop、SSE 流式输出 (WebFlux)、并行 TTS 音频流、消息历史分页、记忆异步触发 |
| **Phase 4** | 语音管道 | **2w** | ASR WebSocket 客户端、TTS WebSocket 流式客户端、浏览器 VAD 不变、前后端联调 |
| **Phase 5** | RAG & 向量记忆 | **3w** | pgvector 初始化、文档上传/分块/embedding/入库、用户级隐私隔离、聊天时向量记忆召回 |
| **Phase 6** | 管理员后台 | **2w** | 自建 Admin API（后端 0.5w + 前端 1.5w）：用户管理、角色管理、文件管理、操作日志页面 |
| **Phase 7** | 可观测性 | **2w** | 结构化日志 (MDC request_id)、Micrometer 指标、Grafana 面板、健康检查、告警规则 |
| **Phase 8** | 限流 & 成本控制 | **1w** | Redis 令牌桶、按用户/资源类型限流、超限响应、使用量统计 |
| **Phase 9** | 前端重构 | **3w** | 微信电脑端双栏布局、聊天窗口改造（若保留 Vue） |
| **Phase 10** | 测试补全 | **3w** | 单元测试 + API 集成测试 + 核心链路 E2E |
| **Phase 11** | 部署上线 | **1w** | Docker 化、Nginx 配置、HTTPS、数据迁移脚本、灰度验证 |
| **合计** | | **28w** | **约 7.0 个月（单人）** |

### 5.3 风险缓冲区

- LangChain4j 与现有 LangGraph 逻辑差异 → +1~3w
- 前后端联调意外问题 → +1~2w
- SQLite → PostgreSQL 数据迁移边界情况 → +0.5w
- **建议总预算（纯 Java 方案）：30~34 人周（7.5~8.5 个月单人）**

### 5.4 Hybrid 方案成本明细（推荐方案）

将聊天 agent + 记忆 agent + RAG + 语音处理保留为 Python FastAPI Sidecar，Java 负责 Web 业务层和代理层：

| 模块 | 方案调整 | 人周 | 变化 |
|------|---------|------|------|
| Phase 3 (聊天核心) | Java 负责 SSE 代理（WebClient + Flux 转发、超时处理、错误传播）+ 元数据加载，Python 负责 Agent 编排 | 2w | **-2w** |
| Phase 4 (语音管道) | TTS/ASR WebSocket 客户端仍在 Python，Java 只做 HTTP 封装 | 1.5w | -0.5w |
| Phase 5 (RAG) | 文档处理/embedding/向量检索均在 Python，Java 只做上传+查询封装 | 1w | **-2w** |
| Phase 6 (管理员后台) | 自建 Admin API（Java @PreAuthorize + Vue 路由守卫） | 2w | 0 （与纯 Java 方案一致） |
| 新增：Python FastAPI Sidecar 搭建 | API 契约定义、Dockerfile、内网通信、health check | 1.5w | +1.5w |
| 新增：RabbitMQ 集成 | 消息定义、生产/消费、重试策略 | 1w | +1w |
| **总工期** | | **~26w** | **节省约 2w，约 6.5 个月** |

**Hybrid 方案的额外投入（约 2.5w）换来的收益：**
- 100% 保留已验证的 LangGraph Agent 代码，零 AI 逻辑重写风险
- Python AI 生态（LangChain/LangGraph/Embeddings）持续可用
- 未来 DashScope API 变更时，只需改 Python 侧，Java 侧不受影响
- 可渐进式迁移：先跑通 Hybrid，未来视 LangChain4j 成熟度逐步替换

---

## 六、前端改微信电脑端样式分析

微信电脑端布局核心特征：
- **左侧面板**：固定宽度（~280px），包含搜索 + 好友/对话列表
- **右侧面板**：弹性宽度，聊天窗口（顶部标题栏 + 中间消息区 + 底部输入区）
- **最小窗口限制**：~800px 宽

当前项目是移动端优先的单列布局（daisyUI drawer 侧边栏 + 对话框聊天）。改造为双栏需要：

### 6.1 Vue 3 改造要点

1. **路由重构**：`/friend/` 页面改为双栏布局，左侧好友列表 + 默认空状态/选中聊天
2. **ChatField 从 `<dialog>` 改为嵌入式组件**：不再弹窗，而是嵌入右侧面板
3. **响应式**：大屏双栏，小屏自动切换回全屏聊天（Tailwind `md:flex` 断点）
4. **布局组件**：新建 `SplitLayout.vue`（双栏容器）、`FriendListPanel.vue`（左侧）、`ChatPanel.vue`（右侧）
5. **状态管理**：新增 `chatStore` 管理当前选中好友、未读消息数等

### 6.2 React 改造要点

1. 全部重写 ~50 个 Vue 组件
2. 状态管理方案：Zustand（轻量）或 Redux Toolkit
3. UI 库选择：shadcn/ui（现代）或 Ant Design（企业级）
4. SSE/MSE 音频管道重新实现（约等于 Vue 版的 1.5x 工作量，因需要适配 React 生命周期）

**Vue 改造（仅改 UI）：~3w | React 改造（全重写）：~6~8w**

---

## 七、总结与行动建议

### 7.1 推荐技术栈（总览）

| 层 | 选型 | 替代候选 |
|----|------|---------|
| 后端框架 | Spring Boot 3.4 | Quarkus |
| 数据库 | PostgreSQL 16 + pgvector | MySQL 8 + Milvus |
| ORM | Spring Data JPA + QueryDSL + Flyway | MyBatis-Plus |
| 认证 | Spring Security 6 + **jjwt 0.12.x** | Nimbus JOSE |
| AI Agent | **Hybrid: Python FastAPI Sidecar** | LangChain4j (未来迁移) |
| AI 抽象层 | Spring AI (供应商路由) | 手动适配 |
| SSE | Spring WebFlux (Reactor) → 代理 Python SSE | Spring MVC + SseEmitter |
| 缓存 | Redis 7 | — |
| 消息队列 | RabbitMQ 3.13 (AMQP) | Kafka, Redis Streams |
| 文件存储 | 阿里云 OSS | MinIO |
| 管理员后台 | **自建 Admin API** | — |
| 可观测性 | Micrometer + Prometheus + Grafana | ELK |
| 前端框架 | **保留 Vue 3** | React |
| 测试 | JUnit 5 + Testcontainers + Playwright | — |

### 7.2 推荐的迁移策略

**分 3 个里程碑推进，每阶段产出可运行的软件：**

| 里程碑 | 范围 | 人周 | 产出 |
|--------|------|------|------|
| **M1: 核心可用** | Phase 0-3（基础 + 认证 + CRUD + 聊天核心） | 11w | 可聊天的 MVP，含 JWT 认证和 SSE 流式 |
| **M2: 增强体验** | Phase 4-5 + Phase 9（语音 + RAG + 前端重设计） | 8w | 全功能对齐当前 + RAG + 微信样式 |
| **M3: 生产就绪** | Phase 6-8 + Phase 10-11（Admin + 可观测性 + 限流 + 测试 + 部署） | 9w | 生产级完善，可替代当前系统上线 |

### 7.3 不做的事情（YAGNI）

- **微服务拆分**：当前规模不需要，模块化分包已为未来拆分预留空间
- **Kubernetes**：单机 Docker Compose 足够，待用户量 > 1000 DAU 再考虑
- **自建 AI 网关**：Spring AI 的多供应商抽象已足够，不重复造轮子
- **音色广场**：用户标注为低优先级，M3 后再议

### 7.4 最关键的决策点

> **方案已明确：Hybrid（Java Spring Boot 业务主服务 + Python FastAPI AI Sidecar）。**
>
> 服务边界：Java 管业务（auth/CRUD/Admin/OSS/限流/监控/SSE代理），Python 管 AI（LangGraph Agent/Embedding/向量检索/TTS/ASR）。
>
> Java ↔ Python 通信：同步走 HTTP REST（内网），异步走 RabbitMQ。
>
> 代价：多维护一个 Python 服务（Docker 容器），多约 2.5w 的 Sidecar + MQ 集成投入。收益：零 AI 逻辑重写风险，100% 保留现有 LangGraph 资产。
>
> 未来路径：当 LangChain4j 生态足够成熟，可逐 agent 替换 Python 端点，无需一次性重写。

---

## 附录：当前项目文件清单

### 后端核心文件（27 个视图/模型/配置文件）

```
backend/
├── backend/settings.py                          # Django 配置
├── backend/urls.py                              # 项目路由
├── web/models/
│   ├── user.py                                  # UserProfile (1 Entity)
│   ├── character.py                             # Character, Voice (2 Entities)
│   └── friend.py                                # Friend, Message, SystemPrompt (3 Entities)
├── web/views/
│   ├── index.py                                 # SPA 入口
│   ├── user/account/                            # login, register, logout, refresh, get_user_info
│   ├── user/profile/                            # update
│   ├── create/character/                        # create, remove, update, get_single, get_list, voice
│   ├── homepage/                                # index (角色列表)
│   ├── friend/                                  # get_count, is_friend, get_or_create, remove, get_list
│   ├── friend/message/chat/chat.py + graph.py  # SSE 聊天 + LangGraph agent
│   ├── friend/message/memory/graph.py + update.py # 记忆 agent + 触发
│   └── friend/message/asr/asr.py               # ASR WebSocket
└── web/documents/                               # LanceDB + 嵌入 + 文档插入
```

### 前端核心文件（~50 个 Vue/JS 文件）

```
frontend/src/
├── main.js, App.vue, router/index.js, stores/user.js, js/config/config.js
├── views/ (homepage, friend, create, user/account, user/profile, user/space, error)
├── components/character/ (Character, CharacterDetail, ChatField, ChatHistory, Message, InputField, Microphone)
├── components/navbar/ (NavBar, UserMenu, icons x8)
└── js/http/ (api.js Axios + JWT, streamApi.js SSE)
```
