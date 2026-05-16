# Chat Agent 和 Memory Agent 异常处理与日志增强 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 Chat Agent 后台线程和 Memory Agent 添加异常处理和日志，消除 SSE 核心链路中异常静默丢失的盲区。

**Architecture:** 后端 2 个文件（chat.py + memory/update.py）添加 logger 和 try/except，chat.py 的 `work()` 方法增加 SSE 错误事件推送。前端 1 个文件（InputField.vue）增加 `data.error` 显示支持。改动约 25 行，不改变现有业务流程。

**Tech Stack:** Django 6.0 + Python logging + Vue 3

**注意：** 在 `feature/gqyin/optimize-bare-except-and-logging` 分支上操作，不在 master 上改动。

---

### Task 1: 切到 feature 分支

**Files:** 无

- [ ] **Step 1: 切换到 feature 分支**

```bash
git checkout feature/gqyin/optimize-bare-except-and-logging
```
Expected: `Switched to branch 'feature/gqyin/optimize-bare-except-and-logging'`

---

### Task 2: chat.py — 添加 logger

**Files:**
- Modify: `backend/web/views/friend/message/chat/chat.py`

- [ ] **Step 1: 在 imports 区域后添加 logger**

在 `from web.views.friend.message.memory import update`（第 23 行）之后插入：

```python
import logging

logger = logging.getLogger(__name__)
```

- [ ] **Step 2: 验证 import**

```bash
cd backend && conda run -n py312 python -c "
import django; import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()
from web.views.friend.message.chat import chat
print('OK')
"
```
Expected: `OK`

- [ ] **Step 3: 提交**

```bash
git add backend/web/views/friend/message/chat/chat.py
git commit -m "feat: add logger to chat.py for SSE stream observability

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: chat.py — `work()` 加异常捕获 + SSE 错误事件

**Files:**
- Modify: `backend/web/views/friend/message/chat/chat.py`

- [ ] **Step 1: 在 `work()` 方法中加 except 子句**

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

- [ ] **Step 2: 在 `event_stream()` 的消息处理循环中添加 error 分支**

在消息处理循环中，`if msg.get('content', None):`（当前第 152 行）之前插入：

```python
            if msg.get('error', None):
                yield f'data: {json.dumps({"error": msg["error"]}, ensure_ascii=False)}\n\n'
```

完整顺序变为：
1. `msg.get('error', None)` → yield SSE error event
2. `msg.get('content', None)` → yield content
3. `msg.get('audio', None)` → yield audio
4. `msg.get('usage', None)` → store usage

- [ ] **Step 3: 验证 import**

```bash
cd backend && conda run -n py312 python -c "
import django; import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()
from web.views.friend.message.chat import chat
print('OK')
"
```
Expected: `OK`

- [ ] **Step 4: 提交**

```bash
git add backend/web/views/friend/message/chat/chat.py
git commit -m "fix: add exception handling and SSE error event in chat work() thread

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: chat.py — 核心链路日志

**Files:**
- Modify: `backend/web/views/friend/message/chat/chat.py`

- [ ] **Step 1: 在 `event_stream()` 开始处加日志**

在 `mq = queue.Queue()` 之后插入：

```python
        logger.info('Chat Agent 开始, friend_id=%s', friend.id)
```

- [ ] **Step 2: 在消息保存后加完成日志**

在 `Message.objects.create(...)` 之后、`if Message.objects.filter(...) % 10 == 0:` 之前（第 175 行附近），插入：

```python
        logger.info('Chat Agent 完成, friend_id=%s, tokens: in=%d out=%d total=%d',
                    friend.id, input_tokens, output_tokens, total_tokens)
```

- [ ] **Step 3: 在 Memory 触发前加日志**

在 `update.update_memory(friend)` 前插入：

```python
            logger.info('触发 Memory 更新, friend_id=%s, message_count=%d',
                        friend.id, Message.objects.filter(friend=friend).count())
```

- [ ] **Step 4: 在 TTS WebSocket 连接后加日志**

在 `run_tts_task()` 中，`await ws.send(json.dumps({...}))` 发送 run-task 消息之后、`async for msg in ws:` 等待 task-started 循环之前（第 227 行代替），插入：

```python
            logger.info('TTS WebSocket 已连接, task_id=%s, voice_id=%s', task_id, voice_id)
```

- [ ] **Step 5: 验证 import**

```bash
cd backend && conda run -n py312 python -c "
import django; import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()
from web.views.friend.message.chat import chat
print('OK')
"
```
Expected: `OK`

- [ ] **Step 6: 提交**

```bash
git add backend/web/views/friend/message/chat/chat.py
git commit -m "feat: add key checkpoint logging to chat SSE stream

Chat start, complete (with token counts), TTS connect, memory trigger.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: memory/update.py — 加异常处理

**Files:**
- Modify: `backend/web/views/friend/message/memory/update.py`

- [ ] **Step 1: 读取文件后重写 `update_memory()` 函数**

当前 `update_memory()` 函数（第 1-37 行，不含 imports 和两个 helper 函数），将其包裹 try/except。完整的新文件内容：

在现有 imports 之后添加：

```python
import logging

logger = logging.getLogger(__name__)
```

将 `update_memory()` 函数体包裹 try/except：

```python
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

`create_system_message()` 和 `create_human_message()` 两个辅助函数保持不变。

- [ ] **Step 2: 验证 import**

```bash
cd backend && conda run -n py312 python -c "
import django; import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()
from web.views.friend.message.memory import update
print('OK')
"
```
Expected: `OK`

- [ ] **Step 3: 提交**

```bash
git add backend/web/views/friend/message/memory/update.py
git commit -m "fix: add exception handling and logger to memory agent

Memory update failure no longer crashes the SSE stream.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: 前端 InputField.vue — 支持 SSE error 事件

**Files:**
- Modify: `frontend/src/components/character/chat_field/input_field/InputField.vue`

- [ ] **Step 1: 在 `onmessage` 回调中添加 error 处理**

在 `handleSend` 函数的 `onmessage(data, isDone)` 回调中（第 146-157 行），`if (data.content)` 之前添加：

```javascript
        if (data.error) {
          emits('appendToLastMessage', data.error)
        }
```

完整顺序变为：
1. `processId !== curId` → 中断检查
2. `data.error` → append error text to last message
3. `data.content` → append text
4. `data.audio` → play audio

- [ ] **Step 2: 验证前端构建**

```bash
cd frontend && npm run build 2>&1 | tail -5
```
Expected: `✓ built in X.XXs`

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/character/chat_field/input_field/InputField.vue
git commit -m "feat: display SSE error events in chat bubble

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: 最终验证

- [ ] **Step 1: Django system check**

```bash
cd backend && conda run -n py312 python manage.py check
```
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 2: 确认无裸 except**

```bash
grep -rn "except:" backend/web/views/friend/message/
```
Expected: 空（chat.py 只有 `except Exception:`，memory/update.py 只有 `except Exception:`）

- [ ] **Step 3: 确认 logger 存在**

```bash
grep -rn "logger" backend/web/views/friend/message/chat/chat.py backend/web/views/friend/message/memory/update.py | wc -l
```
Expected: > 0

- [ ] **Step 4: 前端构建**

```bash
cd frontend && npm run build 2>&1 | grep "built"
```
Expected: `✓ built in X.XXs`

- [ ] **Step 5: 检查工作树清洁**

```bash
git status
```
