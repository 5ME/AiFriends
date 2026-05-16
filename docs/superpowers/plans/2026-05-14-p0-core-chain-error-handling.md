# P0 核心链路异常处理和日志增强 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 ASR、Chat 入参、Chat DB 写入、Embedding API 四个 P0 盲区加异常处理和日志，防止核心链路崩溃。

**Architecture:** 3 个文件独立修改，互不依赖。每个文件遵循相同模式：加 `import logging` + `logger`，关键操作包裹 `try/except Exception` + `logger.exception()`。前端无影响。

**Tech Stack:** Django 6.0 + Python logging + LangChain

**分支:** `feature/gqyin/optimize-bare-except-and-logging`

---

### Task 1: ASR — 加异常处理和日志

**Files:**
- Modify: `backend/web/views/friend/message/asr/asr.py`

- [ ] **Step 1: 删除死代码**

删除第 7 行 `from openai import api_key`

- [ ] **Step 2: 添加 logger**

在 `import uuid`（第 4 行）之后插入：
```python
import logging

logger = logging.getLogger(__name__)
```

- [ ] **Step 3: 包装 `post()` 方法**

将 `post()` 方法体包裹 try/except。替换第 17-24 行：

```python
    def post(self, request):
        try:
            audio = request.FILES.get('audio')
            if not audio:
                return Response({'message': '音频不存在'},
                                status=status.HTTP_400_BAD_REQUEST)
            logger.info('ASR 开始')
            pcm_data = audio.read()
            text = asyncio.run(self.run_asr_task(pcm_data))
            logger.info('ASR 完成, text_length=%d', len(text))
            return Response({'message': 'success', 'text': text})
        except Exception:
            logger.exception('ASR 执行异常')
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

- [ ] **Step 4: `run_asr_task` 中添加 WebSocket 连接日志**

在 `async with websockets.connect(...)` 之后、`await ws.send(...)` 之前（约第 32 行之后）插入：
```python
            logger.info('ASR WebSocket 已连接, task_id=%s', task_id)
```

- [ ] **Step 5: 修复 `task-failed` 静默返回空字符串**

在 `asr_receiver` 中，将 `elif event in ['task-finished', 'task-failed']:`（第 98 行）改为：
```python
            elif event == 'task-finished':
                break
            elif event == 'task-failed':
                raise Exception('ASR task failed')
```

- [ ] **Step 6: 验证 import**

```bash
cd backend && conda run -n py312 python -c "
import django; import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()
from web.views.friend.message.asr import asr
print('OK')
"
```
Expected: `OK`

- [ ] **Step 7: 提交**

```bash
git add backend/web/views/friend/message/asr/asr.py
git commit -m "fix: add exception handling and logger to ASR pipeline

Wrap post() in try/except, log key checkpoints, handle task-failed
by raising exception instead of silently returning empty string.
Remove dead openai api_key import.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: Chat — 入参校验 + Voice 空值保护 + DB 写入保护

**Files:**
- Modify: `backend/web/views/friend/message/chat/chat.py`

- [ ] **Step 1: 入参改用 `.get()` + 空值校验**

替换第 103-104 行：
```python
        friend_id = request.data["friend_id"]
        message = request.data["message"].strip()
```

为：
```python
        friend_id = request.data.get("friend_id")
        message = (request.data.get("message") or "").strip()
        if not friend_id or not message:
            return Response({"message": "参数不完整"},
                            status=status.HTTP_400_BAD_REQUEST)
```

- [ ] **Step 2: Voice 空值保护**

找到 `event_stream` 调用中访问 `friend.character.voice.voice_id` 的地方（约第 141 行），将其提取为局部变量并加空值保护。替换：
```python
        thread = threading.Thread(target=self.work, args=(app, inputs, mq, friend.character.voice.voice_id))
```

为：
```python
        voice_id = friend.character.voice.voice_id if friend.character.voice else ''
        thread = threading.Thread(target=self.work, args=(app, inputs, mq, voice_id))
```

- [ ] **Step 3: `Message.objects.create()` 包裹 try/except**

在第 170-181 行的 `Message.objects.create(...)` 外加保护：

```python
        try:
            Message.objects.create(
                friend=friend,
                user_message=message[:5000],
                input=json.dumps(
                    [m.model_dump() for m in inputs['messages']],
                    ensure_ascii=False
                )[:50000],
                output=''.join(full_output)[:5000],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            )
        except Exception:
            logger.exception('聊天消息保存失败, friend_id=%s', friend.id)
```

- [ ] **Step 4: 验证 import**

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

- [ ] **Step 5: 提交**

```bash
git add backend/web/views/friend/message/chat/chat.py
git commit -m "fix: add input validation and DB write protection in chat view

- Use .get() instead of [] for request.data to prevent KeyError 500
- Add null guard for character voice attribute
- Wrap Message.objects.create() in try/except to prevent silent data loss

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: CustomEmbeddings — 加异常处理和 logger

**Files:**
- Modify: `backend/web/documents/utils/custom_embeddings.py`

- [ ] **Step 1: 添加 logger**

在第 5 行（`from openai import OpenAI` 之后）插入：
```python
import logging

logger = logging.getLogger(__name__)
```

- [ ] **Step 2: `embed_documents()` 中 API 调用包裹 try/except**

将第 34-39 行：
```python
            response = self.client.embeddings.create(
                model="text-embedding-v4",
                input=batch,
                dimensions=1024
            )
            all_embeddings.extend([data.embedding for data in response.data])
```

改为：
```python
            try:
                response = self.client.embeddings.create(
                    model="text-embedding-v4",
                    input=batch,
                    dimensions=1024
                )
                all_embeddings.extend([data.embedding for data in response.data])
            except Exception:
                logger.exception('Embedding API 调用失败, batch_index=%d, batch_size=%d',
                                 i // batch_size, len(batch))
                raise
```

- [ ] **Step 3: `embed_query()` 包装 try/except**

将第 48 行：
```python
        return self.embed_documents([text])[0]
```

改为：
```python
        try:
            return self.embed_documents([text])[0]
        except Exception:
            logger.exception('Embedding 查询向量化失败, text_length=%d', len(text))
            raise
```

- [ ] **Step 4: 验证 import**

```bash
cd backend && conda run -n py312 python -c "
import django; import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()
from web.documents.utils.custom_embeddings import CustomEmbeddings
print('OK')
"
```
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/web/documents/utils/custom_embeddings.py
git commit -m "fix: add exception handling and logger to custom embeddings

Wrap embedding API calls in try/except to prevent RAG crashes.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: 最终验证

- [ ] **Step 1: Django system check**

```bash
cd backend && conda run -n py312 python manage.py check
```
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 2: 确认改动的文件无裸 except**

```bash
grep -rn "except:" backend/web/views/friend/message/asr/asr.py backend/web/views/friend/message/chat/chat.py backend/web/documents/utils/custom_embeddings.py
```
Expected: 空（所有 except 都是 `except Exception`）

- [ ] **Step 3: 确认 logger 引用存在**

```bash
grep -rn "logger" backend/web/views/friend/message/asr/asr.py backend/web/documents/utils/custom_embeddings.py
```
Expected: 均有输出

- [ ] **Step 4: 检查工作树清洁**

```bash
git status
```
