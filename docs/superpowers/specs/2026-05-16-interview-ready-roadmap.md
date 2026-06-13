# AI Friends 求职面试导向：待办优先级路线图

> 视角：面试官会追问什么 → 按追问概率和扣分力度排序
> 日期：2026-05-16
> 目标岗位：Java 后端 / AI 应用工程师（社招）
> 当前状态：25 项 review 发现项中 14 项已修复，11 项待处理

---

## 一、当前进度总览

### 1.1 已修复（14/25）— 面试时可以说"已处理"

| 修复项 | 面试价值 |
|--------|---------|
| 裸 `except:` 全局替换为 `except Exception` + `logger.exception()` | 证明你发现了并修复了反模式 |
| Django LOGGING 配置（console + rotating file, 10MB×5） | 证明你有排障意识 |
| HTTP 状态码规范化（200/400/401/404/409/500） | 证明你理解 REST 语义 |
| ASR/Chat/Memory/Embeddings 全链路异常处理 | 证明你有链路思维 |
| SSE 错误流（角色已删除 → 前端显示错误气泡） | 证明你考虑了跨用户影响 |
| 角色删除确认弹窗 + 实时好友数 | 证明你考虑了产品安全 |
| 前端主路径错误提示（auth、CRUD） | 证明你有用户感知 |
| 创建/编辑角色取消按钮 | 产品细节 |
| `print()` 调试语句清理 | 代码整洁 |
| LangGraph agent 关键节点日志 | 排障能力 |
| `.env` 加入 `.gitignore` | 安全意识 |

### 1.2 未修复（11/25）— 面试官会追问

按"面试被问概率 × 答不好扣分力度"排序：

| 排名 | 问题 | 追问概率 | 答不好扣分 | 当前状态 |
|------|------|---------|-----------|---------|
| **1** | 零测试 | 95% | 直接质疑工程素养 | `tests.py` 仍为 3 行模板 |
| **2** | SQLite 跑生产 | 90% | 被归为 Demo | 无 PostgreSQL |
| **3** | SECRET_KEY 硬编码 | 80% | 安全意识到位了吗 | `settings.py:23` 硬编码 |
| **4** | .env 密钥仍在磁盘 | 70% | 安全治理不及格 | 文件存在，需轮换 |
| **5** | 无 Docker | 60% | "给别人跑得起来吗" | 无 Dockerfile |
| **6** | Memory Agent 同步阻塞 | 55% | 异步解耦意识不够 | chat.py 内联调用 |
| **7** | 无 Celery/Redis | 50% | 缺一个关键后端技能 | 项目中零使用 |
| **8** | 无健康检查 | 45% | "怎么接入 LB？" | 无 `/api/health/` |
| **9** | 无 request_id | 40% | "出问题怎么排查？" | 日志无 trace 字段 |
| **10** | 无限流 | 35% | "成本怎么控制？" | 无 DRF throttle |
| **11** | 配置硬编码 | 30% | "多环境怎么部署？" | IP/URL/模型名硬编码 |

---

## 二、分阶段执行计划

### 阶段 0：安全止血（1-2 天，本周末可完成）

面试时这关不过，后面的都白谈。

| # | 任务 | 工时 | 面试话术 |
|---|------|------|---------|
| 0.1 | `SECRET_KEY` 改为 `os.getenv('DJANGO_SECRET_KEY')` | 0.5h | "我把所有敏感配置都环境变量化了" |
| 0.2 | `DEBUG`、`ALLOWED_HOSTS`、`MEDIA_URL` 环境变量化 | 0.5h | 同上 |
| 0.3 | 创建 `.env.example`（只有 key 名，无真实值） | 0.5h | "新人 clone 后 `cp .env.example .env` 就能跑" |
| 0.4 | 到阿里云控制台轮换 DashScope API Key、OSS AK/SK | 1h | "安全治理：密钥定期轮换，不入 git 历史" |

**阶段 0 产出：** 项目不再有硬编码密钥，`.env.example` 降低新人门槛。

---

### 阶段 1：测试 + 数据库（2-3 周，面试最加分）

这是投入产出比最高的阶段。面试官 95% 会问测试，90% 会问数据库。

#### 1.1 测试（~1.5 周）

按面试追问概率排序：

| 测试范围 | 工时 | 为什么写这个 |
|---------|------|-------------|
| `test_auth.py` — 登录成功/失败、注册重复用户、Token 刷新 | 1.5d | 认证是最基础的，没测说不过去 |
| `test_friend.py` — 添加好友、重复添加、删除好友、角色删除后好友状态 | 1.5d | 边界条件多，容易出 bug，面试能讲 |
| `test_character.py` — 创建/编辑/删除角色、权限校验（非作者不能删） | 1d | 权限测试是高级话题 |
| `test_chat_agent.py` — Mock LLM，验证 SSE 事件格式、Tool calling 路由 | 2d | 这是项目最有技术含量的部分，能讲出彩 |
| `test_memory.py` — Mock LLM，验证摘要写入、10 条触发逻辑 | 0.5d | Memory Agent 是架构亮点 |

**面试话术：**
> "我采用的是 pytest-django，对 auth、friend、character CRUD 和 Chat Agent 的 SSE 事件格式都写了测试。Chat Agent 我 mock 了 LLM 响应，验证了 tool-calling 的路由逻辑和 SSE 事件顺序。"

#### 1.2 PostgreSQL 迁移（~1 周）

| 任务 | 工时 |
|------|------|
| Docker Compose 启动 PostgreSQL + pgvector | 0.5d |
| `settings.py` 切换 `django.db.backends.postgresql` | 0.5d |
| 添加索引：`Message(friend, created_at)`、`Character(author)` | 0.5d |
| Friend 添加 `unique_together(user_profile, character)` | 0.5d |
| 数据迁移脚本（SQLite → PostgreSQL dump/load） | 1d |
| 验证所有 API 正常工作 | 0.5d |

**面试话术：**
> "我主动把 SQLite 迁移到了 PostgreSQL。加上了核心索引——Message 按好友+时间、Character 按作者。Friend 加了唯一约束防止重复关系。迁移过程写了脚本，可以在 Docker Compose 里一键启动。"

---

### 阶段 2：工程化基础设施（2-3 周）

#### 2.1 Docker 化（~3 天）

| 任务 | 工时 |
|------|------|
| `Dockerfile`（Django + Gunicorn） | 1d |
| `docker-compose.yml`（PostgreSQL + Redis + Django + Nginx） | 1d |
| `.env.example` 对齐 Docker 环境变量 | 0.5d |
| README 更新一键启动步骤 | 0.5d |

**面试话术：**
> "我把整个项目 Docker 化了——`docker compose up` 就能跑起来。包含 PostgreSQL、Redis、Django、Nginx 四个服务。环境变量通过 `.env.example` 管理，新人 clone 后复制一份填自己的 API Key 就行。"

#### 2.2 Celery + Redis 异步任务（~1 周）

| 任务 | 工时 |
|------|------|
| Redis 集成到 Django Cache + Celery Broker | 0.5d |
| Celery 配置（`celery.py`、worker、beat） | 1d |
| Memory Agent 异步化：`update_memory.delay(friend_id)` | 1d |
| 添加 `MemoryTask` 模型记录任务状态（pending/running/done/failed） | 1d |
| Chat 完成后不阻塞，投递任务即返回 | 0.5d |

**面试话术：**
> "我把 Memory 更新从同步改成了 Celery 异步任务。聊天 SSE 完成后投递 `update_memory.delay(friend_id)` 就返回，不阻塞用户。任务状态写入 `MemoryTask` 表，失败自动重试。这是 AI 应用的标准工程化做法——长耗时推理任务必须异步。"

#### 2.3 健康检查 + 结构化日志（~3 天）

| 任务 | 工时 |
|------|------|
| `/api/health/` 端点（检查 DB + Redis + Celery 连接） | 1d |
| 日志中间件注入 `request_id`（`uuid4` → MDC/threading.local） | 1d |
| 日志格式增加 `user_id`、`endpoint`、`latency` 字段 | 0.5d |
| 响应头回传 `X-Request-ID` 给前端 | 0.5d |

**面试话术：**
> "我加了 `/api/health/` 端点，检查 PostgreSQL、Redis、Celery 的连接状态。日志层面引入了 `request_id`——每个请求生成 UUID，贯穿整个链路，出问题时能按 ID 追踪。响应头也回传给前端，用户报 bug 时可以直接给 `X-Request-ID`。"

---

### 阶段 3：安全与可靠性（1-2 周）

#### 3.1 限流（~3 天）

| 任务 | 工时 |
|------|------|
| 登录/注册限流：`AnonRateThrottle`（5 次/分钟/IP） | 0.5d |
| 聊天限流：`UserRateThrottle`（20 次/分钟/用户） | 0.5d |
| ASR 限流 + 音频文件大小限制（≤ 10MB, ≤ 60s） | 0.5d |
| TTS 字符数限流（≤ 500 字/次, ≤ 5000 字/天） | 0.5d |

**面试话术：**
> "我做了分层限流——登录注册用 IP 限流防暴力破解，聊天和 ASR/TTS 按用户限流。ASR 还限制了音频大小和时长，TTS 限制了每日字符数。这些都是付费的外部 API，不做限流成本会失控。"

#### 3.2 CI/CD + 前端残留清理（~3 天）

| 任务 | 工时 |
|------|------|
| GitHub Actions：`pytest` + `npm run build` on PR | 1d |
| 前端残留 `console.log(e)` 替换为 toast/user-facing error | 0.5d |
| 配置硬编码值环境变量化（模型名、API URL 等） | 1d |

---

### 阶段 4：功能亮点（4-8 周，可选）

这些不是面试"必答题"，但能让你从"有工程素养"进阶到"技术亮点突出"。

| 排名 | 功能 | 工时 | 面试价值 |
|------|------|------|---------|
| 1 | **用户级 RAG**（文档上传 → 解析 → embedding → 向量检索） | 3-4w | 证明多租户 RAG 架构能力 |
| 2 | **自定义音色**（用户录音 → Voice Clone API → 绑定角色） | 1-2w | 产品感强，API 已有封装 |
| 3 | **微信电脑端 UI**（双栏布局） | 2-3w | 产品设计能力 |
| 4 | **压测报告**（Locust → Chat/ASR/Homepage） | 1w | 有数据支撑的性能叙事 |
| 5 | **Spring Boot 辅助服务**（如 RAG Document Service） | 2w | 证明 Java 后端能力 |

---

## 三、按周的冲刺计划

### 第 1 周：安全 + 测试起步
```
Mon-Tue:   阶段 0 全部（SECRET_KEY、.env.example、密钥轮换）
Wed-Fri:   test_auth.py + test_friend.py 编写和通过
```

### 第 2 周：测试收尾 + PostgreSQL
```
Mon-Wed:   test_character.py + test_chat_agent.py
Thu-Fri:   Docker Compose + PostgreSQL 迁移
```

### 第 3 周：Docker + Celery
```
Mon-Tue:   Dockerfile + docker-compose.yml 完善
Wed-Fri:   Redis + Celery 配置，Memory Agent 异步化
```

### 第 4 周：日志 + 限流
```
Mon-Tue:   健康检查 + request_id 日志中间件
Wed-Fri:   限流 + CI/CD + 前端残留清理
```

**4 周后产出：** 一个有测试、有 PostgreSQL、有 Docker、有异步任务、有 request_id、有健康检查、有限流的项目。面试时可以从容应对 90% 的技术追问。

---

## 四、每个阶段的"可以讲" vs "先不讲"

### 阶段 1 完成后

**可以讲：**
- "我写了 auth、friend、character、Chat Agent 的测试覆盖"
- "我把数据库迁移到了 PostgreSQL，加了核心索引和约束"
- "我做了 Docker Compose 一键启动"

**先不讲：**
- 不要说"测试覆盖率达到了 X%"（数字会引来更深的追问）

### 阶段 2 完成后

**可以讲：**
- "Memory 更新改成了 Celery 异步任务，解耦了聊天主链路"
- "日志引入 request_id，全链路可追踪"
- "有 `/api/health/` 端点，检查所有依赖服务"

**先不讲：**
- 不要说"高可用"（单机 Docker Compose 不叫高可用）

### 阶段 3 完成后

**可以讲：**
- "我做了分层限流，控制 LLM/TTS/ASR 成本"
- "GitHub Actions 跑 pytest 和 build"

---

## 五、面试模拟：每个阶段能回答到什么程度

### 面试官："你写测试了吗？"

| 当前（无测试） | 阶段 1 后 |
|---------------|----------|
| "还没，但在计划中" 😰 | "写了。auth 的登录/注册/刷新、friend 的权限和边界、character CRUD、Chat Agent 的 SSE 事件和 tool-calling 路由都有覆盖。Chat Agent 我 mock 了 LLM，验证了工具调用循环和 SSE 事件顺序。" ✅ |

### 面试官："为什么用 SQLite？"

| 当前 | 阶段 1 后 |
|------|----------|
| "开发方便..." 😰 | "已经迁移到 PostgreSQL 了。加了 Message 按好友+时间的索引，Friend 加了唯一约束。Docker Compose 启动可以选 SQLite 或 PostgreSQL。" ✅ |

### 面试官："Memory 更新为什么不异步？"

| 当前 | 阶段 2 后 |
|------|----------|
| "因为..."（解释原因反而暴露设计问题）😰 | "已经改成 Celery 异步了。聊天完成后投递任务到 Redis 队列，Worker 异步执行 LLM 摘要。任务状态写入 MemoryTask 表，失败自动重试。长耗时的 AI 推理必须异步，不能阻塞用户请求。" ✅ |

### 面试官："怎么排查一个用户说聊天很慢的问题？"

| 当前 | 阶段 2 后 |
|------|----------|
| "看日志..."（但日志没有 request_id）😰 | "日志里每个请求都有 request_id，从 Nginx → Django → Celery 一路透传。响应头也回传 X-Request-ID，用户报 bug 时可以直接按 ID 搜索。关键指标——首 token 延迟、token 消耗、TTS 首包延迟——都记录在日志里。" ✅ |

---

## 六、不在本次范围内的（YAGNI）

以下事项有意不列入当前路线图，理由如下：

| 事项 | 理由 |
|------|------|
| 微服务拆分 | 单体远未到瓶颈，拆了反而增加运维复杂度 |
| Kubernetes | Docker Compose 足够，用户量 < 1000 DAU 不需要 |
| GraphQL | REST 足够，当前 API 数量少 |
| 实时协作 / 群聊 | 产品方向未定，先聚焦单人对话 |
| 国际化 i18n | 当前用户全是中文 |
| PWA / 离线支持 | 聊天应用离线价值有限 |

---

*本路线图基于 2026-05-16 master 分支代码实际状态编写，已考虑 Claude review 报告、Codex 更新版 review 报告、docs/superpowers/specs/ 和 plans/ 中的历史迭代记录。*
