# Chat Agent 和 Memory Agent 异常处理与日志增强

> 设计日期：2026-05-14 | 状态：待实施

## 背景

前两轮优化（裸 except + 日志系统、HTTP 状态码 + 前端错误处理）完成后，views 层的 CRUD 端点已全部具备异常处理和日志。但 SSE 聊天链路和 Memory Agent 仍有两个盲区：

1. `chat.py:186` — `work()` 后台线程中 `asyncio.run()` 的异常被 `finally` 静默吞掉，仅由 Python 线程默认输出到 stderr
2. `memory/update.py` — `update_memory()` 无 try/except 无日志，LLM 调用失败会穿透到 SSE 生成器导致连接异常断开
3. Chat Agent 核心链路（Agent 调用、TTS 连接、消息持久化）无运行日志

## 目标

- 后台线程异常不被静默吞掉：记录到日志文件 + 向前端发送 SSE 错误事件
- Memory Agent 失败不影响主聊天流程：静默记录日志，用户不受影响
- 关键运行节点可追踪：Agent 开始/完成、TTS 连接、Memory 触发

## 改动范围

仅 2 个文件：

| 文件 | 改动类型 |
|------|----------|
| `backend/web/views/friend/message/chat/chat.py` | 加 logger + 4 处日志 + 1 处异常处理 + 1 处 SSE 错误事件 |
| `backend/web/views/friend/message/memory/update.py` | 加 logger + 1 处异常处理 |

无需前端改动——SSE 错误事件使用现有 EventSource 解析，前端 catch 能捕获网络断开；`error` 类型事件可作为后续增强项在前端展示。

## 详细设计

### 改动 1 — chat.py：添加 logger

在 `chat.py` 顶部现有 imports 后添加：

```python
import logging

logger = logging.getLogger(__name__)
```

### 改动 2 — chat.py：`work()` 加异常捕获 + 错误事件

`work()` 方法当前代码（第 186-189 行）：

```python
        try:
            asyncio.run(self.run_tts_task(app, inputs, mq, voice_id))
        finally:
            mq.put_nowait(None)
```

改为：

```python
        try:
            asyncio.run(self.run_tts_task(app, inputs, mq, voice_id))
        except Exception:
            logger.exception('Chat Agent 执行异常')
            mq.put_nowait({'error': '系统异常，请稍后重试'})
        finally:
            mq.put_nowait(None)
```

`event_stream()` 中已有的消息处理循环（第 150-158 行）扩展一个 `elif` 分支处理 `error` 事件。在 `if msg.get('content', None):` 之前插入：

```python
            if msg.get('error', None):
                yield f'data: {json.dumps({"error": msg["error"]}, ensure_ascii=False)}\n\n'
```

处理顺序：先检查 error → 再检查 content/audio/usage。发送错误事件后继续循环（不 break），等待最终的 `None` 哨兵正常关闭流。

### 改动 3 — chat.py：核心链路日志

**Chat 开始** — 在 `event_stream()` 方法开头，`mq` 创建后插入：

```python
        logger.info('Chat Agent 开始, friend_id=%s', friend.id)
```

**Chat 完成** — 在 `Message.objects.create(...)` 之后、`update_memory()` 调用之前插入：

```python
        logger.info('Chat Agent 完成, friend_id=%s, tokens: in=%d out=%d total=%d',
                    friend.id, input_tokens, output_tokens, total_tokens)
```

**Memory 触发** — 在 `update_memory(friend)` 调用前插入：

```python
            logger.info('触发 Memory 更新, friend_id=%s, message_count=%d',
                        friend.id, Message.objects.filter(friend=friend).count())
```

**TTS 连接** — 在 `run_tts_task()` 中 WebSocket 连接成功后（第 202 行 `async with websockets.connect(...) as ws:` 内部，第 203 行 `await ws.send(...)` 之后、第 227 行 wait 循环之前）插入：

```python
        logger.info('TTS WebSocket 已连接, task_id=%s, voice_id=%s', task_id, voice_id)
```

### 改动 4 — memory/update.py：加异常保护

`update_memory()` 函数整体包裹 try/except，并添加 logger：

```python
import logging

logger = logging.getLogger(__name__)


def update_memory(friend: Friend):
    try:
        app = MemoryGraph.create_app()
        inputs = {
            'messages': [
                create_system_message(),
                create_human_message(friend)
            ]
        }
        res = app.invoke(inputs)
        friend.memory = res['messages'][-1].content
        friend.updated_at = now()
        friend.save()
    except Exception:
        logger.exception('Memory Agent 更新失败, friend_id=%s', friend.id)
```

## 验证方式

```bash
# 后端 import 校验
cd backend && conda run -n py312 python -c "
import django; import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()
from web.views.friend.message.chat import chat
from web.views.friend.message.memory import update
print('OK')
"

# 确认无裸 except
grep -rn "except:" backend/web/views/friend/message/
```

## 不变更

- 不修改前端——SSE 流断开时前端已有 `网络异常` 兜底提示
- 不修改 `ChatGraph`（`graph.py`）——Agent 逻辑本身是纯 LangGraph，异常会自然向上抛
- 不修改 `MemoryGraph`（`memory/graph.py`）——同理
