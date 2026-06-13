# AI Friends 项目后续任务路线图

> 基于 Claude 和 Codex 两份 Review 报告（2026-05-31）的综合规划
> 策略：均衡推进，兼顾面试价值、工程质量、功能完整

---

## 背景

2026-05-31 完成两轮独立 Review：
- **Claude Review**：99 测试通过，技术深度均分 7.4/10，识别了 5 个仍待解决问题 + 5 个新问题
- **Codex Review**：综合评价 7.3-8.0/10，识别了 Memory backlog bug、RAG eval 缺失、成本治理缺失等关键短板

两份报告在 README 过期、docker-compose 不可移植、SECRET_KEY 弱 fallback、缺 CI/CD、缺成本治理/限流 五个问题上完全一致。

## 总体策略

**均衡推进**：每个 Phase 同时包含面试价值项、工程质量项、功能完整项，按性价比排序。每项标注 P0/P1/P2 与两份报告对齐。

---

## Phase 0：可信度修复（半天）

**目标**：修掉"面试官第一眼"扣分项，让项目看起来维护良好。

| # | 任务 | 时间 | 类型 | 优先级 |
|---|------|------|------|--------|
| 0.1 | **README 全面更新**：测试数量 51→99、新增知识库上传功能、Celery 异步任务、健康检查、Request ID、docker-compose 启动说明、架构图 | 30min | 面试价值 | P0 |
| 0.2 | **docker-compose 可移植**：密码改 `${POSTGRES_PASSWORD}`、volume 改 named volume、`.env` 驱动 | 20min | 工程质量 | P0 |
| 0.3 | **SECRET_KEY 去弱 fallback**：非 DEBUG 模式缺环境变量时 `raise ImproperlyConfigured` 拒绝启动 | 10min | 安全 | P0 |
| 0.4 | **Memory Agent backlog bug**：`last_summarized_count` 只推进到 `skip + actual_take`，防止积压超 30 条时数据丢失；如果仍有 backlog 继续投递下一轮任务 | 30min | Bug 修复 | P0 |
| 0.5 | **清理 LanceDB 旧注释**：`chat/graph.py`、README 等处的 LanceDB 残留描述 | 15min | 工程质量 | P0 |
| 0.6 | **Message.input JSONField 修复**：改存原生 list/dict 而非 JSON 字符串；如需截断，加 `truncated` 标记字段 | 20min | 数据建模 | P2 |
| 0.7 | **Photo.vue 去重**：抽取公共 composable `useImageCropper`，两处 Photo.vue 共享逻辑 | 30min | 工程质量 | P2 |

**验收标准**：
- README 测试数量显示 99，功能列表包含知识库/Celery/健康检查
- docker-compose.yml 无硬编码路径和明文密码
- 非 DEBUG 模式无 `DJANGO_SECRET_KEY` 时启动报错退出
- Memory Agent 超过 30 条积压消息时不会丢失中间消息
- `git grep -i lancedb` 无结果
- `Message.input` 存储 Python list/dict，`json.dumps` 调用移除
- `Photo.vue` 两个副本通过共享 composable 消重

---

## Phase 1：工程基础闭环（2 天）

**目标**：项目能被别人 `git clone` → `docker compose up -d` 一键跑起来，有 CI 自动验证。

| # | 任务 | 时间 | 类型 | 优先级 |
|---|------|------|------|--------|
| 1.1 | **GitHub Actions CI**：`.github/workflows/test.yml`，PostgreSQL service container，pytest 99 测试，PR 触发 | 30min | 工程质量 | P0 |
| 1.2 | **应用 Dockerfile**：backend（Python 多阶段）+ frontend（Node build stage）+ nginx 配置 | 2-3h | DevOps | P0 |
| 1.3 | **docker-compose 全链路**：`web`、`celery-worker`、`frontend`、`nginx` 服务，`docker compose up -d` 一键启动 | 1-2h | DevOps | P0 |
| 1.4 | **请求耗时 middleware**：`RequestIdMiddleware` 中加 `time.time()` 记录 method/path/status/duration_ms，INFO 级别输出到日志 | 30min | 可观测性 | P1 |
| 1.5 | **`.env.example` 补齐**：`MEDIA_URL`、`CORS_ALLOWED_ORIGINS`、生产部署变量说明 | 15min | 工程质量 | P1 |
| 1.6 | **platform 环境自动切换**：通过 Vite build mode（`--mode production`）或环境变量自动切换，不再手动改 `config.js` | 30min | DevOps | P1 |

**验收标准**：
- GitHub Actions 在 PR 时自动跑 99 个测试并全部通过
- `docker compose up -d` 后浏览器 `http://localhost` 可访问完整应用
- 日志中每条请求包含 `duration_ms` 字段
- `.env.example` 覆盖所有必需环境变量（含 MEDIA_URL、CORS_ALLOWED_ORIGINS）
- `npm run build` 自动使用 production 配置，无需手动改代码

---

## Phase 1.5：成本治理基础（1-2 天）★新增

**目标**：让项目从"能跑"升级到"能放心跑"。两份报告都将成本治理列为求职价值最高的 P0 项。

| # | 任务 | 时间 | 类型 | 优先级 |
|---|------|------|------|--------|
| 1.5.1 | **Redis 限流中间件**：token bucket / sliding window，登录 5/min、聊天 20/min、上传 10/min，超限返回 429 + `Retry-After` header | 3-4h | 安全/治理 | P0 |
| 1.5.2 | **API usage 统计**：`APIUsage` 模型记录 LLM/Embedding/ASR/TTS 调用的 token 数、耗时、用户、接口类型；Celery 任务异步写入 | 3-4h | 治理 | P0 |
| 1.5.3 | **MEDIA_URL / CORS 环境变量化**：生产 `MEDIA_URL` 从 `DJANGO_MEDIA_URL` 读取，`CORS_ALLOWED_ORIGINS` 从环境变量解析（逗号分隔） | 20min | 安全 | P1 |

**验收标准**：
- 超过限流阈值时返回 429 + `Retry-After` header
- `APIUsage` 表记录每次 AI API 调用的 token 数和耗时
- 生产环境配置无硬编码 IP/域名

---

## Phase 2：RAG 工程深度（1-2 周）

**目标**：RAG 从"能召回"升级到"可溯源、可评估、可运维"。

| # | 任务 | 时间 | 类型 | 优先级 |
|---|------|------|------|--------|
| 2.1 | **前端 toast 基础设施**：统一 notification 组件。先在聊天消息中展示 RAG 引用来源时引入 toast，后续 Phase 3.5 再做全局替换 | 2-3h | 工程质量 | P2 |
| 2.2 | **RAG 引用来源 + retrieval trace 落库**：`search_knowledge_base` 返回结构化结果 `{document_id, title, chunk_index, content, score}`；每次检索命中 chunk 写入 `RetrievalTrace` 表，用于排查和评估；前端聊天展示"📎 参考来源：xxx文档 第N段" | 5-6h | 功能完整 | P1 |
| 2.3 | **健康检查增强**：增加 Redis 连通性、Celery worker 状态检测，返回 `{"db":"ok","redis":"ok","celery":"ok"}` | 1h | 可观测性 | P1 |
| 2.4 | **Django Admin 注册**：`UserDocument` + `DocumentChunk` 注册 Admin，支持搜索 title/owner、过滤 status/file_type、展示 chunks_count/error_message | 30min | 运维 | P2 |
| 2.5 | **文档处理可靠性增强**：task enqueue 失败时 doc 标记 failed（而非永久 pending）；删除文档时检查并撤销正在处理的 Celery 任务 | 1-2h | 工程质量 | P1 |
| 2.6 | **系统知识库增量更新**：`insert_documents.py` 从全量删除+全量插入改为 hash 对比增量更新（`content_hash` 字段），避免重复 embedding 浪费 | 2-3h | 工程质量 | P2 |

> **执行顺序**：2.1（toast 基础设施）→ 2.2（RAG citation 接入 toast 展示）→ 2.3-2.6 可并行

**验收标准**：
- 聊天中 AI 引用知识库时前端展示"参考来源：xxx文档"
- `RetrievalTrace` 表记录每次检索的命中 chunk 和 score
- Admin 可查看/搜索/过滤文档，展示 chunks_count 和 error_message
- 健康检查返回 `{"db":"ok","redis":"ok","celery":"ok"}`
- 系统知识库重复导入不产生重复 chunk

---

## Phase 3：技术深度加固（2-3 周）

**目标**：补齐流式链路稳定性、RAG 评估体系，让项目达到"高级后端工程师"深度。

| # | 任务 | 时间 | 类型 | 优先级 |
|---|------|------|------|--------|
| 3.1 | **SSE 稳定性治理**：`queue.Queue(maxsize=100)` 背压控制 + SSE 心跳（30s `': heartbeat\n\n'`）+ 客户端断开时取消后台 LLM/TTS 任务 + TTS 失败降级纯文本 + gunicorn worker/thread/timeout 配置文档 | 5-6h | 工程质量 | P1 |
| 3.2 | **RAG 评估体系**：建立 20-50 条 QA eval dataset（基于 retrieval trace 数据 + 人工标注），脚本统计 hit@1/hit@3、MRR、faithfulness；输出评估报告 | 5-6h | 功能完整 | P1 |
| 3.3 | **Chat Agent LLM 重试**：tenacity exponential backoff（max 2次），4xx 不重试 | 1-2h | 工程质量 | P1 |
| 3.4 | **压测报告**：Locust 对首页、聊天 SSE、文档上传做 10/50/100 并发，记录 QPS/P50/P99 延迟、错误率，输出简要压测报告 | 3-4h | 系统设计 | P1 |
| 3.5 | **前端全局 toast 替换**：用 Phase 2.2 建立的 toast 基础设施，替换各组件散落的 `uploadError`/`errorMessage` 模式 | 2-3h | 工程质量 | P2 |

**验收标准**：
- SSE 连接 30s 无数据时发送心跳，客户端断开后 5s 内取消后台 LLM/TTS 任务
- RAG eval 报告包含 hit@1、hit@3、MRR 三项指标
- Locust 报告包含 100 并发下首页 < 200ms P99、聊天首 token < 3s
- 前端所有错误提示使用统一 toast 组件

---

## Phase 4（可选）：Java 能力对齐（2-4 周）

**目标**：为 Java 后端岗位建立跨语言能力证据。AI 应用工程师岗位可跳过。

| # | 任务 | 时间 | 类型 | 优先级 |
|---|------|------|------|--------|
| 4.1 | **Spring Boot 配额/计费服务**：独立 Java 服务（用户配额 + Redis 限流 + usage billing mock），Django 通过 REST API 调用 | 1-2 周 | Java 能力 | P1 |
| 4.2 | **ADR 决策记录**：pgvector 选型、Memory Agent 拆分、SSE vs WebSocket、Celery vs RQ 等 3-5 篇 | 2-3h | 文档 | P2 |

---

## 里程碑总览

| 阶段 | 耗时 | 任务数 | 可交付成果 | 简历竞争力跃升 |
|------|------|--------|-----------|---------------|
| Phase 0 | 半天 | 7 | README/Compose/安全配置一致，2 个 bug 修复 | 消除减分项 |
| Phase 1 | 2 天 | 6 | `docker compose up -d` + CI badge + platform 自动切换 | GitHub 吸引力 ↑ |
| Phase 1.5 | 1-2 天 | 3 | 限流中间件 + usage 统计 + 配置环境变量化 | 面试可聊成本控制 ★ |
| Phase 2 | 1-2 周 | 6 | RAG citation/trace + 健康检查增强 + Admin + 增量更新 | "有生产意识"→"有生产治理" |
| Phase 3 | 2-3 周 | 5 | 压测报告 + RAG eval + SSE 降级 + 全局 toast | 面试主打项目级别 |
| Phase 4 | 2-4 周 | 2 | Java 服务 + ADR | Java 岗位竞争力 +1 档 |

---

## 覆盖度校对

| 两份报告的核心建议 | 映射到的任务 |
|-------------------|-------------|
| README 更新 (P0) | 0.1 |
| docker-compose 修复 (P0) | 0.2, 1.3 |
| SECRET_KEY fallback (P0) | 0.3 |
| CI/CD (P0) | 1.1 |
| 成本治理/限流 (P0) | 1.5.1, 1.5.2 |
| Memory backlog bug (P0) | 0.4 |
| RAG citation + trace (P1) | 2.1 |
| RAG eval (P1) | 3.2 |
| SSE 稳定性 (P1) | 3.1 |
| 压测报告 (P1) | 3.4 |
| LanceDB 清理 (P0) | 0.5 |
| Message.input JSONField (P2) | 0.6 |
| Photo.vue 去重 (P2) | 0.7 |
| platform 自动切换 (P1) | 1.6 |
| 请求耗时日志 (P1) | 1.4 |
| MEDIA_URL/CORS 环境变量 (P1) | 1.5.3 |
| 健康检查增强 (P1) | 2.3 |
| Django Admin (P2) | 2.4 |
| 文档处理可靠性 (P1) | 2.5 |
| 系统知识库增量更新 (P2) | 2.6 |
| 前端全局 toast (P2) | 3.5 |
| Chat Agent LLM 重试 (P1) | 3.3 |
| Java 配额服务 (P1) | 4.1 |
| ADR 决策记录 (P2) | 4.2 |

---

*Plan Date: 2026-05-31*
*Based on: 项目Review报告(Claude).md + 项目Review报告(Codex-2026-05-31).md*
*Review feedback incorporated: user's detailed spec review*
