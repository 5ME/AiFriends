# Celery + Redis 异步任务实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Memory Agent 从聊天 SSE 尾部同步调用改为 Celery 异步任务，消除 2-5s 阻塞；同时新增 `last_summarized_count` 修复摘要失败导致的消息丢失。

**Architecture:** Celery app 通过 `backend/celery.py` 初始化，配置从 Django settings 以 `CELERY_` namespace 注入，Redis 作为 broker。chat.py 投递 `.delay()` 后立即返回，Worker 独立进程中执行 LangGraph LLM 调用。失败重试 1 次 + `last_summarized_count` 补偿机制防止消息遗漏。

**Tech Stack:** Celery 5.5.x, Redis 7-alpine (Docker), redis-py (via celery[redis])

**Branch:** `feature/gqyin/celery-redis-async`

---

## File Map

| 文件 | 操作 | Task |
|------|------|------|
| `backend/requirements.txt` | Modify — 加 `celery[redis]` | 1 |
| `backend/.env` | Modify — 加 broker URL | 1 |
| `backend/.env.example` | Modify — 加 broker URL | 1 |
| `backend/backend/celery.py` | Create | 2 |
| `backend/backend/settings.py` | Modify — 加 CELERY_* 配置 | 2 |
| `backend/web/models/friend.py` | Modify — 加 `last_summarized_count` | 3 |
| `backend/web/views/friend/message/memory/tasks.py` | Create | 4 |
| `backend/web/views/friend/message/memory/update.py` | Modify — 清理已迁移函数 | 4 |
| `backend/web/views/friend/message/chat/chat.py` | Modify — `update.update_memory` → `.delay()` | 5 |
| `backend/web/tests/test_memory_agent.py` | Modify — 适配 + 新增测试 | 6 |
| `docker-compose.yml` | Create — PG + Redis | 7 |
| `服务器部署.md` | Modify — 加 Celery Worker 启动 | 8 |

---

### Task 1: Dependencies & Environment Variables

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/.env`
- Modify: `backend/.env.example`

- [ ] **Step 1: 添加 celery[redis] 依赖**

在 `backend/requirements.txt` 末尾追加：

```
celery[redis]>=5.5,<5.6
```

- [ ] **Step 2: 安装依赖**

```bash
conda activate py312
pip install "celery[redis]>=5.5,<5.6"
```

- [ ] **Step 3: 添加 CELERY_BROKER_URL 到 .env**

在 `backend/.env` 末尾追加：

```shell
CELERY_BROKER_URL=redis://localhost:6379/0
```

- [ ] **Step 4: 添加 CELERY_BROKER_URL 到 .env.example**

在 `backend/.env.example` 末尾追加：

```shell
# Celery broker（异步任务队列）
CELERY_BROKER_URL=redis://localhost:6379/0
```

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt backend/.env backend/.env.example
git commit -m "chore: add celery[redis] dependency and broker env vars

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: Celery App + Django Settings

**Files:**
- Create: `backend/backend/celery.py`
- Modify: `backend/backend/settings.py`

- [ ] **Step 1: 创建 Celery app**

新建 `backend/backend/celery.py`：

```python
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

app = Celery('backend')

# namespace='CELERY' → settings 中所有 CELERY_ 开头的配置自动注入
app.config_from_object('django.conf:settings', namespace='CELERY')

# 自动扫描所有 INSTALLED_APPS 中的 tasks.py
app.autodiscover_tasks()
```

- [ ] **Step 2: 验证 Celery app 可加载**

```bash
cd backend && conda activate py312
# 只加载 Celery app 对象，不启动 Worker
python -c "from backend.celery import app; print(app.main)"
```
Expected: 输出 `backend`（Celery app 名称），无 ImportError

- [ ] **Step 3: 在 settings.py 添加 Celery 配置**

在 `backend/backend/settings.py` 末尾追加：

```python
# Celery — Redis broker（异步任务队列）
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')

# 任务完成后才 ack — Worker 崩溃时未完成的任务自动回到队列
CELERY_TASK_ACKS_LATE = True

# 长任务场景，每次只取一个任务避免并发 LLM 调用争抢资源
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# 软超时 120s / 硬超时 180s（LLM 调用通常 3-8s）
CELERY_TASK_SOFT_TIME_LIMIT = 120
CELERY_TASK_TIME_LIMIT = 180
```

- [ ] **Step 4: Commit**

```bash
git add backend/backend/celery.py backend/backend/settings.py
git commit -m "feat: add Celery app and broker configuration

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: Friend Model — last_summarized_count

**Files:**
- Modify: `backend/web/models/friend.py`

- [ ] **Step 1: 添加字段**

在 `Friend` 模型的 `updated_at` 字段之后追加：

```python
    # 记录上一次成功摘要时的消息总数
    # 失败重试时 create_human_message 从此位置取消息，不会遗漏
    last_summarized_count = models.IntegerField(default=0)
```

完整位置（`friend.py` 第 13 行后）：

```python
class Friend(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    character = models.ForeignKey(Character, on_delete=models.CASCADE)
    memory = models.TextField(default='', max_length=5000, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # 记录上一次成功摘要时的消息总数
    # 失败重试时 create_human_message 从此位置取消息，不会遗漏
    last_summarized_count = models.IntegerField(default=0)
```

- [ ] **Step 2: 生成 migration**

```bash
cd backend && conda activate py312
python manage.py makemigrations web --name add_last_summarized_count
```

- [ ] **Step 3: 运行 migration**

```bash
python manage.py migrate
```

- [ ] **Step 4: Commit**

```bash
git add backend/web/models/friend.py backend/web/migrations/*last_summarized_count*.py
git commit -m "feat: add Friend.last_summarized_count for failure compensation

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: Memory Task + update.py Cleanup

**Files:**
- Create: `backend/web/views/friend/message/memory/tasks.py`
- Modify: `backend/web/views/friend/message/memory/update.py`

- [ ] **Step 1: 创建 tasks.py**

新建 `backend/web/views/friend/message/memory/tasks.py`：

```python
"""Memory Agent 异步任务 — Celery Worker 中执行，不阻塞聊天请求"""
import logging

from django.utils.timezone import now
from langchain_core.messages import SystemMessage, HumanMessage
from backend.celery import app

from web.models.friend import Friend, Message, SystemPrompt
from web.views.friend.message.memory.graph import MemoryGraph

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

    # 从上次摘要位置开始取 — 失败重试时不会遗漏消息
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

注意：`from backend.celery import app` 直接引用 celery.py 中创建的 Celery 实例。`@app.task` 装饰器在模块被导入时注册任务，无需依赖 `autodiscover_tasks`（该机制仅扫描各 app 顶层 `tasks.py`）。

- [ ] **Step 2: 清理 update.py**

`update.py` 中原有的 `create_system_message`、`create_human_message`、`update_memory` 三个函数已迁至 `tasks.py`。替换 update.py 的全部内容为：

```python
"""Memory 更新逻辑已迁至 memory/tasks.py — Celery 异步任务"""

# create_system_message / create_human_message / update_memory
# 已迁移到 web.views.friend.message.memory.tasks
```

- [ ] **Step 3: 验证 module 可导入**

```bash
cd backend && conda activate py312
python -c "from web.views.friend.message.memory.tasks import update_memory_task, create_human_message; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/web/views/friend/message/memory/tasks.py backend/web/views/friend/message/memory/update.py
git commit -m "feat: extract Memory Agent to Celery task with failure compensation

create_human_message now reads from last_summarized_count instead of
hardcoded recent-10, preventing message loss when summarization fails.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: chat.py — Hook Up Async Task

**Files:**
- Modify: `backend/web/views/friend/message/chat/chat.py`

- [ ] **Step 1: 替换同步调用为异步投递**

改两处：import 行（文件顶部区域）和调用行（约第 205 行）。

在 `chat.py` 顶部 import 区域，替换 `import web.views.friend.message.memory.update as update`：

```python
# Before（约第 25 行附近）：
import web.views.friend.message.memory.update as update

# After：
from web.views.friend.message.memory.tasks import update_memory_task
```

找到 import 的实际位置：

```bash
cd backend && grep -n "import.*memory.*update" web/views/friend/message/chat/chat.py
```

在调用位置（约第 205 行），替换 `update.update_memory(friend)`：

```python
# Before：
            update.update_memory(friend)

# After：
            update_memory_task.delay(friend.id)
```

- [ ] **Step 2: 验证 import 链正确**

```bash
cd backend && conda activate py312
python -c "from web.views.friend.message.chat.chat import update_memory_task; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/web/views/friend/message/chat/chat.py
git commit -m "refactor: dispatch memory update as async Celery task

Replace sync update.update_memory(friend) with
update_memory_task.delay(friend.id) — eliminates 2-5s blocking
at the tail of SSE stream completion.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: Test Adaptation + New Coverage

**Files:**
- Modify: `backend/web/tests/test_memory_agent.py`

当前 3 个测试需要适配：`test_memory_triggered_at_10`、`test_memory_field_updated` 从 `update` 改为从 `tasks` 导入，Mock 路径也相应调整。`test_memory_agent_graph` 直接测 MemoryGraph，无需改动。新增 1 个失败补偿测试。

- [ ] **Step 1: 重写 test_memory_agent.py**

替换 `backend/web/tests/test_memory_agent.py` 全部内容：

```python
import pytest
from unittest.mock import patch, MagicMock

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from web.models.friend import Friend, Message
from web.views.friend.message.memory import tasks


class TestMemoryTrigger:
    """记忆触发时机测试"""

    def test_memory_triggered_at_10(self, friend):
        """第 10 条消息后 update_memory_task 写入 Friend.memory"""
        for i in range(9):
            Message.objects.create(
                friend=friend,
                user_message=f"msg {i}",
                input="{}",
                output=f"reply {i}",
            )

        with patch.object(tasks, "MemoryGraph") as mock_graph_class:
            mock_app = MagicMock()
            mock_app.invoke.return_value = {
                "messages": [AIMessage(content="Summary of conversation")]
            }
            mock_graph_class.create_app.return_value = mock_app

            # Total messages is 9, add the 10th
            Message.objects.create(
                friend=friend,
                user_message="msg 9",
                input="{}",
                output="reply 9",
            )

            # 直接调用 task 函数（同步执行，不经过 broker）
            tasks.update_memory_task(friend.id)
            friend.refresh_from_db()
            assert friend.memory == "Summary of conversation"

    def test_memory_not_triggered_at_5(self, friend):
        """5 条消息时 count % 10 != 0"""
        for i in range(5):
            Message.objects.create(
                friend=friend,
                user_message=f"msg {i}",
                input="{}",
                output=f"reply {i}",
            )
        count = Message.objects.filter(friend=friend).count()
        assert count == 5
        assert count % 10 != 0


class TestMemoryField:
    """记忆字段更新测试"""

    def test_memory_field_updated(self, friend):
        """Friend.memory 被写入新值"""
        with patch.object(tasks, "MemoryGraph") as mock_graph_class:
            mock_app = MagicMock()
            mock_app.invoke.return_value = {
                "messages": [AIMessage(content="Updated summary")]
            }
            mock_graph_class.create_app.return_value = mock_app

            tasks.update_memory_task(friend.id)
            friend.refresh_from_db()
            assert friend.memory == "Updated summary"
            assert friend.updated_at is not None


class TestMemoryGraph:
    """Memory Agent 图逻辑测试"""

    @patch("web.views.friend.message.memory.graph.ChatOpenAI")
    def test_memory_agent_graph(self, mock_llm_class):
        """Mock LLM → 图返回摘要 AIMessage"""
        from web.views.friend.message.memory.graph import MemoryGraph

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content="记忆摘要: 用户讨论了天气")
        mock_llm_class.return_value = mock_llm

        app = MemoryGraph.create_app()
        result = app.invoke({
            "messages": [
                SystemMessage(content="你是一个记忆摘要助手"),
                HumanMessage(content="user: 今天天气真好\nai: 是啊"),
            ]
        })

        assert len(result["messages"]) >= 2
        last = result["messages"][-1]
        assert isinstance(last, AIMessage)
        assert "记忆摘要" in last.content


class TestMemoryFailureCompensation:
    """失败补偿：last_summarized_count 机制"""

    def test_last_summarized_count_not_updated_on_failure(self, friend):
        """LLM 失败时 last_summarized_count 保持不变 → 下次重试覆盖遗漏"""
        from celery.exceptions import Retry

        # 创建 10 条消息
        for i in range(10):
            Message.objects.create(
                friend=friend,
                user_message=f"msg {i}",
                input="{}",
                output=f"reply {i}",
            )

        assert friend.last_summarized_count == 0

        with patch.object(tasks, "MemoryGraph") as mock_graph_class:
            mock_app = MagicMock()
            mock_app.invoke.side_effect = RuntimeError("LLM service unavailable")
            mock_graph_class.create_app.return_value = mock_app

            # 直接调用 → retry() 抛出 Retry 异常
            try:
                tasks.update_memory_task(friend.id)
            except Retry:
                pass

            friend.refresh_from_db()
            # memory 未更新
            assert friend.memory == "" or friend.memory is None
            # last_summarized_count 未递增（失败不更新）
            assert friend.last_summarized_count == 0

            # 第二次触发 — 成功
            mock_app.invoke.side_effect = None
            mock_app.invoke.return_value = {
                "messages": [AIMessage(content="Summary of 10 messages")]
            }
            # 直接调用 task 函数（同步执行，不走 broker）
            tasks.update_memory_task(friend.id)
            friend.refresh_from_db()
            assert "10 messages" in friend.memory
            assert friend.last_summarized_count == 10

    def test_create_human_message_respects_last_summarized_count(self, friend):
        """create_human_message 从 last_summarized_count 位置取消息"""
        # 创建 15 条消息
        for i in range(15):
            Message.objects.create(
                friend=friend,
                user_message=f"msg {i}",
                input="{}",
                output=f"reply {i}",
            )

        friend.last_summarized_count = 10
        friend.save()

        msg = tasks.create_human_message(friend)
        content = msg.content

        # 应包含 msg 10-14（5 条增量），不包含 msg 0-9
        assert "msg 10" in content
        assert "msg 14" in content
        assert "msg 0" not in content
```

- [ ] **Step 2: 运行新测试，确认全部通过**

```bash
cd backend && conda activate py312
python -m pytest web/tests/test_memory_agent.py -v
```
Expected: 6 passed（3 原有 + 1 迁移 + 2 新增）

- [ ] **Step 3: 运行全量测试确认无回归**

```bash
cd backend && conda activate py312
python -m pytest web/tests/ -q
```
Expected: 75 passed

- [ ] **Step 4: Commit**

```bash
git add backend/web/tests/test_memory_agent.py
git commit -m "test: adapt memory tests for Celery task + failure compensation

- Switch imports from update to tasks module
- Add test_last_summarized_count_not_updated_on_failure
- Add test_create_human_message_respects_last_summarized_count
- Adapt existing tests to call tasks.update_memory_task directly

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: Docker Compose

**Files:**
- Create: `docker-compose.yml`（项目根目录）

- [ ] **Step 1: 创建 docker-compose.yml**

在项目根目录 `D:\MyProjects\AiFriends\docker-compose.yml` 新建：

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

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: add docker-compose.yml for PostgreSQL + Redis

Replace standalone docker-postgresql.sh with unified compose file.
Redis 7-alpine added as Celery broker for async memory summarization.
Uses docker compose (v2) with space separator, no legacy docker-compose.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 8: 部署文档更新

**Files:**
- Modify: `服务器部署.md`

- [ ] **Step 1: 更新 服务器部署.md**

在 `服务器部署.md` 的 "前置操作" 部分后、"部署操作" 部分前，插入以下内容：

```markdown
#### Docker 服务（PG + Redis）

在 WSL 中执行：

```bash
cd ~/ai-friends

# 启动 PostgreSQL + Redis
docker compose up -d

# 查看状态
docker compose ps

# 查看日志
docker compose logs -f
```

**Redis 说明：**
- 版本 `7-alpine`，仅约 15MB
- 数据持久化至 `/home/ygq/redis-data`（`--save 60 1`：每 60 秒至少 1 次写入时存盘）
- 连接：`redis://localhost:6379/0`
```

在 "启动 gunicorn" 步骤之后，追加 Celery Worker 启动步骤：

```markdown
7. 启动 Celery Worker（异步记忆摘要）

   - ```bash
     # 在 ~/ai-friends/backend/ 目录下执行
     celery -A backend worker -l info -c 1 &
     ```
     
     生产环境使用 systemd 管理进程，以下为示例 `celery-worker.service`：
     
     ```
     [Unit]
     Description=Celery Worker for AI Friends
     After=network.target
     
     [Service]
     Type=simple
     User=gqyin
     Group=gqyin
     WorkingDirectory=/home/gqyin/ai-friends/backend
     ExecStart=/home/gqyin/miniconda3/envs/py312/bin/celery -A backend worker -l info -c 1
     Restart=on-failure
     RestartSec=5s
     
     [Install]
     WantedBy=multi-user.target
     ```
```

原来的步骤 7 "浏览器访问" 改为步骤 8。

- [ ] **Step 2: Commit**

```bash
git add 服务器部署.md
git commit -m "docs: add Redis + Celery Worker deployment instructions

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Verification Checklist

```
[ ] 75 tests pass (pre-existing, no regression)
[ ] TestMemoryFailureCompensation: 2 new tests pass
[ ] Celery app loads: python -c "from backend.celery import app"
[ ] Tasks importable: python -c "from web.views.friend.message.memory.tasks import update_memory_task"
[ ] chat.py imports update_memory_task without error
[ ] docker compose up -d starts both PG and Redis
[ ] Migration runs: python manage.py migrate
```
