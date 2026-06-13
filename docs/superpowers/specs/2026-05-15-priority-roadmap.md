# AI Friends — 下一步优先级路线图

> 评估日期：2026-05-15
> 基准：`feature/gqyin/character-delete-confirmation` 分支
> 依据：Claude Review 报告 + Codex Review 报告 + 实际代码状态

## 已修复（master + 当前分支）

| 问题 | 来源报告 | 状态 |
|------|----------|------|
| 裸 `except:` → `except Exception as e:` + logging | 两份报告 P0 | ✅ master |
| 无日志系统 → Python logging（console + 文件轮转） | 两份报告 P0 | ✅ master |
| HTTP 状态码混乱（失败返回 200） | 两份报告 P0 | ✅ master |
| 前端 `console.log(e)` 吞错误 | Claude 报告 | ✅ master + 当前分支 |
| 角色删除无确认/无提示 | 本分支新增 | ✅ 当前分支 |
| 好友侧删除后沉默失败/500 | 本分支新增 | ✅ 当前分支 |
| 创建/编辑角色无取消按钮 | 本分支新增 | ✅ 当前分支 |

---

## 尚未修复 — 按优先级排列

### Tier 0：致命 — 必须先修，否则有安全/法律风险

| # | 问题 | 严重程度 | 复杂度 | 文件/范围 |
|---|------|----------|--------|-----------|
| 1 | **SECRET_KEY 硬编码** + **`.env` 含生产 API Key 已提交 Git** | 致命 | 低 | `settings.py:23`, `.gitignore`, DashScope 控制台轮换 |

**行动：**
- [ ] 阿里云 DashScope 控制台轮换所有 API Key
- [ ] `SECRET_KEY` 改为 `os.getenv('DJANGO_SECRET_KEY')`
- [ ] `.env` 确认在 `.gitignore` 中

**工作量：** 30 分钟（操作 + 代码改动 1 行）

---

### Tier 1：面试第一道分界线 — 测试

| # | 问题 | 严重程度 | 复杂度 | 文件/范围 |
|---|------|----------|--------|-----------|
| 2 | **零测试** — 两份报告都列为首要短板 | 严重 | 中-高 | 项目级新增 |

两份报告原话：
> "面试官的第一句话往往就是'你写测试了吗'。没有测试 = 工程素养存疑。"
> "这是区分 Demo 和工程项目的第一道线。"

**建议从最小集开始：**

| 测试文件 | 覆盖 | 复杂程度 |
|----------|------|----------|
| `tests/test_auth.py` | 登录成功/失败、注册、Token 刷新、登出 | 低 — 纯 HTTP 测试 |
| `tests/test_friend.py` | 好友创建/删除、权限校验、get_or_create | 低 — CRUD + 权限 |
| `tests/test_character_crud.py` | 角色创建/编辑/删除权限、图片上传 | 中 — 涉及文件上传 |
| `tests/test_chat_agent.py` | Agent 工具调用（mock LLM）、SSE 事件格式 | 中-高 — 需要 mock |

**策略：** 先写 auth + friend 两个测试文件（投入产出比最高），chat agent 测试后续再补。

**工作量：** auth 测试 2h + friend 测试 2h ≈ 半天

---

### Tier 2：生产级基础 — 小改动，大信号

| # | 问题 | 严重程度 | 复杂度 | 文件/范围 |
|---|------|----------|--------|-----------|
| 3 | **无健康检查端点** | 重要 | 极低 | 新增 1 文件 |
| 4 | **硬编码 IP/URL/模型名** | 重要 | 低 | `settings.py`, `config.js`, `graph.py` |

**行动：**
- [ ] 添加 `GET /api/health/` — 返回 DB 连接状态
- [ ] 关键配置环境变量化（DashScope model name, BASE_URL 等）

**工作量：** 1-2 小时

---

### Tier 3：生产级架构 — 高价值、中-高复杂度

| # | 问题 | 严重程度 | 复杂度 | 说明 |
|---|------|----------|--------|------|
| 5 | **Docker 化** | 重要 | 中 | `Dockerfile` + `docker-compose.yml`（Django + PostgreSQL + Redis） |
| 6 | **PostgreSQL 迁移** | 重要 | 中-高 | 从 SQLite 迁移，含索引设计、连接池 |
| 7 | **Celery + Redis 异步任务** | 重要 | 中-高 | Memory Agent 异步化，解决 SSE 线程阻塞 |
| 8 | **SSE 线程中 Django ORM 不安全** | 严重 | 中-高 | 改为 ASGI 或独立 DB session |

**依赖关系：** Docker → PostgreSQL → Celery/Redis（Docker 是其他改动的基础平台）

**工作量：** Docker 1-2 天 → PostgreSQL 1-2 天 → Celery 1-2 天 ≈ 总计 1-2 周

---

### Tier 4：锦上添花

| # | 问题 | 说明 |
|---|------|------|
| 9 | 速率限制（DRF throttling） | 防止 API 滥用，但面试验证意义有限 |
| 10 | CI/CD（GitHub Actions） | 依赖测试先完善 |
| 11 | LanceDB 连接改为单例 | 性能优化 |
| 12 | 方案 B/C 软删除 | 产品决策 + 1-5 天，不直接影响面试评估 |

---

## 关于方案 B/C（软删除）的位置

方案 B 和 C 放在 Tier 4 的原因：

- 从求职角度，软删除不会成为面试的加分或扣分点——面试官大概率不会问"你有没有做软删除"
- 面试官会更关心"你有没有测试、有没有 Docker、有没有异步任务队列"
- 方案 A 已经把用户可见的体验问题修好了（弹窗 + 错误提示）
- 方案 B/C 更多的是产品完善，而非工程能力证明

等 Tier 0-3 完成后再做 B/C 不迟。

---

## 推荐执行顺序

```
第一轮（本周，1-2 天）：
  Tier 0: SECRET_KEY 环境变量化 + 轮换 Key
  Tier 2: Health check + 配置环境变量化

第二轮（2-3 天）：
  Tier 1: auth 测试 + friend 测试

第三轮（1-2 周）：
  Tier 3: Docker → PostgreSQL → Celery

第四轮（后续）：
  Tier 1 剩余: chat agent 测试
  Tier 3 剩余: SSE 线程安全
  Tier 4: 速率限制、CI/CD、软删除 B/C
```

---

## 如果只能做一件事

**写测试。** 两份独立 review 报告不约而同把"零测试"列为第一短板。这不是巧合。

当前项目的 AI 应用亮点（Agent、RAG、语音链路）已经足够通过简历筛选。但面试官问"你写测试了吗"时，如果你能说"我写了 auth 和 friend 管理的测试，chat agent 的测试因为需要 mock LLM 正在补"，这个回答本身就是工程素养的证明。

反之，如果零测试 + SQLite + 裸 except 三个问题都没修，面试官会把你归类为 Demo 写手。
