# Celery + Redis 异步任务设计

> **Date:** 2026-05-27 | **Scope:** Memory Agent 异步化 + 摘要失败补偿

**Goal:** 将 Memory Agent 从聊天 SSE 流尾部同步调用改为 Celery 异步任务，消除 2-5s 阻塞；同时修复摘要失败导致的历史消息丢失问题。

---

## 1. 技术栈选择

| 组件 | 版本 | 用途 | 选型原因 |
|------|------|------|----------|
| Celery | `>=5.5,<5.6` | 分布式任务队列 | 最新稳定版，原生支持 Python 3.12，Django 集成自 3.1 起内置 |
| Redis | `7-alpine` | 消息 broker | 官方推荐 broker，alpine 镜像仅 15MB，开发/生产均可 |
| redis-py | 通过 `celery[redis]` | 客户端 | Celery 团队维护，与 Celery 版本联动测试 |
| django-celery-results | 不引入 | — | Memory 是 best-effort 操作，fire-and-forget 即可；P2-2 文档 embedding 时再加 |

**选型理由：**
- 不用 RabbitMQ — 复用 Redis，不引入第二个基础设施
- 不用 `django-celery-beat` — 无定时任务需求
- alpine vs debian — 轻量、攻击面小，开发/测试无 glibc 依赖问题

---

## 2. 架构概览

```
chat.py (Django 请求线程)                Celery Worker (独立进程)
    │                                           │
    │ update_memory_task.delay(friend_id)       │
    ▼                                           ▼
┌──────┐    push    ┌─────────┐    pull    ┌──────────────┐
│Redis │ ◄──────── │  Redis  │ ────────► │  Worker      │
│Queue │           │ (broker)│           │  LangGraph   │
└──────┘           └─────────┘           │  LLM 调用    │
                                         └──────┬───────┘
                                                │ 成功
                                                ▼
                                         Friend.memory = 摘要
                                         Friend.last_summarized_count = N
                                                │ 失败
                                                ▼
                                         logger.exception
                                         retry × 1（10s 后）
                                         再失败 → 放弃，等下次触发
```

---

## 3. 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/backend/celery.py` | Create | Celery app 初始化 |
| `backend/backend/settings.py` | Modify | 追加 CELERY_* 配置 |
| `backend/web/models/friend.py` | Modify | 新增 `last_summarized_count` |
| `backend/web/views/friend/message/memory/tasks.py` | Create | 异步 task + helper 函数（从 update.py 迁移） |
| `backend/web/views/friend/message/memory/update.py` | Modify | 删除 `update_memory` 函数（逻辑迁至 tasks.py） |
| `backend/web/tests/test_memory_agent.py` | Modify | 适配异步改动 |
| `backend/web/views/friend/message/chat/chat.py` | Modify | 1 行：`update_memory()` → `.delay()` |
| `backend/requirements.txt` | Modify | 追加 `celery[redis]>=5.5,<5.6` |
| `backend/.env` / `.env.example` | Modify | 追加 `CELERY_BROKER_URL` |
| `docker-compose.yml` | Create | PG + Redis 一键启动，替代单独的 docker-run 脚本 |
| `服务器部署.md` | Modify | 追加 Celery Worker 启动步骤 |

---

## 4. 各模块设计

### 4.1 Celery app（`backend/backend/celery.py`）

```python
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

app = Celery('backend')

# namespace='CELERY' → settings 中所有以 CELERY_ 开头的配置
# 都会被自动注入 Celery app
app.config_from_object('django.conf:settings', namespace='CELERY')

# 自动扫描所有 INSTALLED_APPS 中的 tasks.py
app.autodiscover_tasks()
```

### 4.2 Settings 配置（settings.py 追加）

```python
# Celery — Redis broker（异步任务队列）
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')

# 任务完成后才 ack——Worker 崩溃时未完成的任务自动回到队列
CELERY_TASK_ACKS_LATE = True

# 每次只取一个任务，适合 LLM 长调用
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# 软超时 120s / 硬超时 180s（LLM 调用通常 3-8s）
CELERY_TASK_SOFT_TIME_LIMIT = 120
CELERY_TASK_TIME_LIMIT = 180
```

### 4.3 Friend 模型（`web/models/friend.py` 追加）

```python
# 记录上一次成功摘要时的消息总数
# 失败重试时 create_human_message 从此位置取消息，不会遗漏
last_summarized_count = models.IntegerField(default=0)
```

一条 migration。

### 4.4 异步 Task（`web/views/friend/message/memory/tasks.py`）

```python
from django.utils.timezone import now
from langchain_core.messages import SystemMessage, HumanMessage
from backend.celery import app
from web.models.friend import Friend, Message, SystemPrompt
from web.views.friend.message.memory.graph import MemoryGraph
import logging

logger = logging.getLogger(__name__)


def create_system_message() -> SystemMessage:
    system_prompts = SystemPrompt.objects.filter(
        title=SystemPrompt.Title.MEMORY
    ).order_by('order_number')
    prompts = [sp.prompt for sp in system_prompts]
    return SystemMessage(content="".join(prompts))


def create_human_message(friend: Friend) -> HumanMessage:
    """构造 Memory Agent 输入：原始记忆 + 上次摘要之后的增量对话"""
    prompts = [f'【原始记忆】\n{friend.memory}\n', f'【最近对话】\n']
    total_msgs = Message.objects.filter(friend=friend).count()

    # 从上次摘要位置开始取——失败重试时不会遗漏消息
    skip = friend.last_summarized_count
    take = min(total_msgs - skip, 30)  # 30 条兜底，防 LLM 上下文溢出

    messages_raw = Message.objects.filter(friend=friend).order_by('id')[skip:skip + take]
    for m in messages_raw:
        prompts.append(f'user: {m.user_message}\n')
        prompts.append(f'ai: {m.output}\n')
    return HumanMessage(content="".join(prompts))


@app.task(max_retries=1)
def update_memory_task(friend_id: int):
    """异步更新好友记忆摘要。失败由下一次触发自然重试。"""
    try:
        friend = Friend.objects.get(id=friend_id)
        msg_count = Message.objects.filter(friend=friend).count()
        logger.info('Memory 任务开始, friend_id=%d, msg_count=%d', friend_id, msg_count)

        app_graph = MemoryGraph.create_app()
        inputs = {
            'messages': [create_system_message(), create_human_message(friend)]
        }
        res = app_graph.invoke(inputs)
        friend.memory = res['messages'][-1].content

        # 在 task 内部重新计数而非传参：Worker 处理时用户可能已发新消息
        friend.last_summarized_count = Message.objects.filter(friend=friend).count()
        friend.updated_at = now()
        friend.save()

        logger.info('Memory 任务完成, friend_id=%d, memory_len=%d',
                    friend_id, len(friend.memory))
    except Exception as exc:
        logger.exception('Memory 任务失败, friend_id=%d', friend_id)
        # 10s 后重试一次；两次都失败则放弃，等下一个 10 条触发
        raise update_memory_task.retry(exc=exc, countdown=10)
```

### 4.5 chat.py 改动（1 行）

```python
# Before:
import web.views.friend.message.memory.update as update
# ...
update.update_memory(friend)

# After:
from web.views.friend.message.memory.tasks import update_memory_task
# ...
update_memory_task.delay(friend.id)
```

### 4.6 update.py 清理

原有 `update_memory` 函数已不直接调用，逻辑迁至 `tasks.py`。`create_system_message` 和 `create_human_message` 两个 helper 也一并迁走，`update.py` 中只保留对旧调用方的兼容引用（如测试文件迁移后可删除）。

---

## 5. 失败处理与重试

```
send task → Redis 入队 → Worker 取任务 → LLM 调用
                                              │
                                    ┌─────────┴──────────┐
                                    ▼ 成功                ▼ 失败
                             写入 memory            1. log traceback
                             更新 last_count        2. 10s 后 retry
                             更新 updated_at              │
                                                    ┌─────┴──────┐
                                                    ▼ 成功       ▼ 失败
                                                 正常完成      放弃此批
                                                            下次 10 条
                                                            自然触发
```

**为什么只重试 1 次：**
- LLM API 临时波动（429 rate limit / 503 暂时不可用）→ 10s 后一般恢复
- 持久性错误（API key 过期 / 网络不通）→ 无限重试浪费资源，日志记录即可
- 即使放弃此批，下 10 条消息会触发新任务，且 `last_summarized_count` 保持不变，新任务会纳入遗漏的消息

### 丢失补偿机制

**失败前**（同步模式已有的问题，本次顺带修复）：

- 同步模式 `create_human_message` 硬编码取最近 10 条
- 一次 LLM 失败 → 那 10 条永远不在摘要中

**失败后**（`last_summarized_count` 补偿）：

- `last_summarized_count` 只在上次**成功**时更新
- 本次失败 → `last_summarized_count` 不变 → 下次 `create_human_message` 从此位置取
- 失败一次：带 20 条（两次触发范围）
- 连续失败：最多 30 条兜底（防止上下文字段溢出）

---

## 6. Docker Compose（替代旧脚本）

### `docker-compose.yml`（WSL `~/ai-friends/`）

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg17
    container_name: ai-friends-db
    environment:
      POSTGRES_PASSWORD: Kakarot001#
    ports:
      - "55432:5432"
    volumes:
      - /home/ygq/postgres-data:/var/lib/postgresql/data
      - /home/ygq/ai-friends/init.sql:/docker-entrypoint-initdb.d/init.sql
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    container_name: ai-friends-redis
    ports:
      - "6379:6379"
    volumes:
      - /home/ygq/redis-data:/data
    command: redis-server --save 60 1 --loglevel warning
    restart: unless-stopped
```

### 使用方式

```bash
cd ~/ai-friends

# 启动所有服务
docker compose up -d

# 查看状态
docker compose ps

# 查看日志
docker compose logs -f postgres
docker compose logs -f redis

# 停止
docker compose stop

# 停止并删除容器（数据卷保留）
docker compose down
```

### Windows 端启动

```bash
# 终端 1：Celery Worker（Windows 需 solo 模式）
conda activate py312
celery -A backend worker -l info -P solo

# 终端 2：Django
conda activate py312
python manage.py runserver

# 终端 3：Vite
cd frontend && npm run dev
```

---

## 7. 测试适配

`test_memory_agent.py` 当前直接调用 `update.update_memory(friend)`，改用 task 后：

- **单元测试：** 直接调 `tasks.update_memory_task(friend.id)` 验证逻辑（跳过 Celery 队列）
- **集成测试（可选）：** 设置 `CELERY_TASK_ALWAYS_EAGER = True`（本地同步执行，不经过 broker）
- **`last_summarized_count` 测试：** 模拟 Mock LLM 失败 → 验证字段值不变 → 下次 create_human_message 携带更多消息

---

## 8. 环境变量

### `.env` 追加

```shell
CELERY_BROKER_URL=redis://localhost:6379/0
```

### `.env.example` 追加

```shell
# Celery broker（异步任务队列）
CELERY_BROKER_URL=redis://localhost:6379/0
```

---

## 9. 影响分析

| 维度 | 说明 |
|------|------|
| **用户体验** | 聊天结束后不再有 2-5s 额外等待 |
| **数据安全** | `last_summarized_count` 补偿机制 → 反脆弱于同步模式 |
| **兼容性** | 现有 Message 的 `last_summarized_count` 默认 0，行为等同旧逻辑（从第 0 条取最近消息） |
| **运维** | 多一个 Redis 容器 + 一个 Celery Worker 进程 |
| **测试** | `test_memory_agent.py` 3 个测试需适配，新增 2 个失败补偿测试 |
