# P0 核心链路异常处理和日志增强

> 设计日期：2026-05-14 | 状态：待实施

## 背景

third-round review 发现 4 个核心链路文件存在"无 try/except、无 logger"的盲区，任一网络/数据异常都会导致 500 错误或静默数据丢失。

## 目标

- `asr/asr.py` — 加异常处理 + logger，ASR 链路不再裸奔
- `chat/chat.py` — 修复 3 处入参/空值/DB 写入崩溃点
- `custom_embeddings.py` — embedding API 调用加保护 + logger

## 详细设计

### 改动 1 — asr/asr.py

1. 删除死代码 `from openai import api_key`（第 7 行）
2. 添加 `import logging` + `logger = logging.getLogger(__name__)`
3. `post()` 包裹 try/except Exception：
```python
def post(self, request):
    try:
        audio = request.FILES.get('audio')
        if not audio:
            return Response({'message': '音频不存在'}, status=status.HTTP_400_BAD_REQUEST)
        logger.info('ASR 开始')
        pcm_data = audio.read()
        text = asyncio.run(self.run_asr_task(pcm_data))
        logger.info('ASR 完成, text_length=%d', len(text))
        return Response({'message': 'success', 'text': text})
    except Exception:
        logger.exception('ASR 执行异常')
        return Response({'message': '系统异常'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```
4. `run_asr_task()` 内加日志：WebSocket 连接成功后记录 task_id；转录完成后记录文本长度
5. `task-failed`（第 98 行）改为抛异常而非返回空字符串：`raise Exception('ASR task failed')`，由外层 except 捕获并返回 500

### 改动 2 — chat/chat.py

1. **入参改用 `.get()`**（第 103-104 行）：
```python
friend_id = request.data.get("friend_id")
message = (request.data.get("message") or "").strip()
if not friend_id or not message:
    return Response({"message": "参数不完整"}, status=status.HTTP_400_BAD_REQUEST)
```
2. **Voice 空值保护**（第 145 行附近）：
```python
voice_id = friend.character.voice.voice_id if friend.character.voice else None
```
传递给 `self.work()` 时若 voice_id 为 None，TTS 连接自然跳过（现有逻辑中 ws.send 传空 voice 会出错；更安全的做法是在 `run_tts_task` 中加判断：voice_id 为空则跳过 TTS，仅走 LLM 文本流）
3. **Message 写入加保护**（第 170-181 行）：
```python
try:
    Message.objects.create(
        friend=friend,
        user_message=message[:5000],
        ...existing fields...
    )
except Exception:
    logger.exception('聊天消息保存失败, friend_id=%s', friend.id)
```

### 改动 3 — custom_embeddings.py

1. 添加 `import logging` + `logger = logging.getLogger(__name__)`
2. `embed_documents()` 的 API 调用包裹 try/except，记录 batch 序号和错误后 re-raise：
```python
try:
    response = self.client.embeddings.create(model=..., input=batch, dimensions=1024)
except Exception:
    logger.exception('Embedding API 调用失败, batch_index=%d, batch_size=%d', i // batch_size, len(batch))
    raise
```
3. `embed_query()` 同理：
```python
def embed_query(self, text):
    try:
        return self.embed_documents([text])[0]
    except Exception:
        logger.exception('Embedding 查询向量化失败, text_length=%d', len(text))
        raise
```

## 影响范围

| 文件 | 改动类型 |
|------|----------|
| `backend/web/views/friend/message/asr/asr.py` | +logger +try/except +日志点 +删死代码 |
| `backend/web/views/friend/message/chat/chat.py` | 入参校验 +Voice 空值保护 +DB 写入保护 |
| `backend/web/documents/utils/custom_embeddings.py` | +logger +try/except |

前端无影响。

## 不改变

- 不引入重试机制
- 不引入细粒度异常分类
- 不影响现有 API 契约（Response 格式不变）
