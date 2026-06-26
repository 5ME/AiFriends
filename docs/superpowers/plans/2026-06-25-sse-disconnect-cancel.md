# P1-C2: SSE 客户端断连检测 + 后端取消 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 前端关闭聊天窗口后，后端停止 TTS（省钱），LLM 自然完成后保存完整回复。

**Architecture:** generator `try/finally` 检测客户端断连（WSGI/ASGI 通用），`threading.Event` 通知 worker 线程停 TTS 不停 LLM，`_output_buffer` 始终收集完整输出。

**Tech Stack:** Python `threading.Event` + `@microsoft/fetch-event-source` AbortController + Django `StreamingHttpResponse`

---

### Task 1: 前端 — streamApi.js 支持 AbortController signal

**Files:**
- Modify: `frontend/src/js/http/streamApi.js` — 接受 signal 参数

- [ ] **Step 1: 给 `streamApi` 函数添加 `signal` 参数支持**

```javascript
// streamApi.js  — 在 fetchEventSource 调用中添加 signal 参数
// 变更位置: options.signal 传递给 fetchEventSource

export default async function streamApi(url, options = {}) {
  const userStore = useUserStore();

  const startFetch = async () => {
    return await fetchEventSource(BASE_URL + url, {
      method: options.method || 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${userStore.accessToken}`,
        ...options.headers,
      },
      body: JSON.stringify(options.body || {}),
      signal: options.signal,  // ← 新增：支持 AbortController

      openWhenHidden: true,
      // ... onopen, onmessage, onerror, onclose 不变 ...
    });
  };

  return await startFetch();
}
```

- [ ] **Step 2: 前端 build 验证**

```bash
cd frontend && npm run build
```
Expected: build 成功，无新增错误。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/js/http/streamApi.js
git commit -m "feat: streamApi 支持 AbortController signal 参数"
```

---

### Task 2: 前端 — InputField 创建 AbortController + onUnmounted 清理

**Files:**
- Modify: `frontend/src/components/character/chat_field/input_field/InputField.vue`

- [ ] **Step 1: 创建 AbortController，onUnmounted 中 abort，传给 streamApi**

在 `InputField.vue` 的 `<script setup>` 中：

```javascript
// 在 import 区域已有 useVoiceToggle, streamApi 等，在变量声明区新增：

let abortController = null  // SSE 断连控制器

// 修改 handleSend 中的 streamApi 调用，传入 signal:
// 在 streamApi('/api/friend/message/chat/', { ... }) 之前：
abortController = new AbortController()

await streamApi('/api/friend/message/chat/', {
  body: { friend_id: props.friendId, message: content },
  signal: abortController.signal,  // ← 新增
  onmessage(data, isDone) { ... },
  onerror(err) { ... },
})

// 修改 onUnmounted — 加入 abort:
onUnmounted(() => {
  if (abortController) {
    abortController.abort()  // ← 通知后端客户端已断开
    abortController = null
  }
  audioPlayer.pause()
  audioPlayer.src = ''
})
```

- [ ] **Step 2: 前端 build 验证**

```bash
cd frontend && npm run build
```
Expected: build 成功。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/character/chat_field/input_field/InputField.vue
git commit -m "feat: InputField onUnmounted 时 abort SSE 连接"
```

---

### Task 3: 后端 — event_stream generator finally 断连检测

**Files:**
- Modify: `backend/web/views/friend/message/chat/chat.py` — `event_stream()` 方法

- [ ] **Step 1: 改写 event_stream — mq.get(timeout=1) + try/finally**

将当前 `while True: msg = mq.get()` 改为 timeout 轮询，并将主逻辑包入 `try/finally`：

```python
def event_stream(self, app, inputs, friend, message):
    start_time = time.time()
    mq = queue.Queue(maxsize=500)
    cancel_event = threading.Event()            # ← 新增
    logger.info('Chat Agent 开始, friend_id=%s', friend.id)
    voice_id = friend.character.voice.voice_id if friend.character.voice else ''
    user_id = friend.user_profile_id
    thread = threading.Thread(
        target=self.work,
        args=(app, inputs, mq, voice_id, user_id, cancel_event, friend, message, inputs),  # ← 加参数（inputs 用于断连路径 Message.input 序列化）
        daemon=True,
    )
    thread.start()

    full_output = []
    full_usage = {}
    has_error = False
    error_message = ''
    try:                                        # ← 新增：finally 检测断连
        while True:
            try:
                msg = mq.get(timeout=1)         # ← 从 mq.get() 改为 timeout
            except queue.Empty:                 # ← 新增
                continue                        # 不检查 request.is_disconnected()

            if msg is None:
                break
            if msg.get('citations', None):
                yield f'data: {json.dumps({"citations": msg["citations"]}, ensure_ascii=False)}\n\n'
            if msg.get('error', None):
                has_error = True
                error_message = msg['error']
                yield f'data: {json.dumps({"error": error_message}, ensure_ascii=False)}\n\n'
            if msg.get('content', None):
                full_output.append(msg['content'])
                yield f'data: {json.dumps({'content': msg['content']}, ensure_ascii=False)}\n\n'
            if msg.get('audio', None):
                yield f'data: {json.dumps({'audio': msg['audio']}, ensure_ascii=False)}\n\n'
            if msg.get('usage', None):
                full_usage = msg['usage']
    finally:                                    # ← 新增：generator 退出时设置 cancel_event
        # 正常结束 或 客户端断连（GeneratorExit）均触发
        # 断连时 generator 直接退出（排空由 work() 线程完成），不需 disconnected 变量
        # 正常结束 或 客户端断连（GeneratorExit）均触发
        # WSGI/ASGI 通用 — 不依赖 request.is_disconnected()
        cancel_event.set()

    # 正常路径：event_stream 消费完 mq，保存 Message
    yield 'data: [DONE]\n\n'
    # ... LLM usage 记录 (不变) ...
    record_api_usage(
        user_id=user_id, api_type='llm',
        model_name='deepseek-v4-flash',
        token_count=full_usage.get('total_tokens', 0),
        duration_ms=int((time.time() - start_time) * 1000),
        success=not has_error,
        error_message=error_message,
    )
    Message.objects.create(
        friend=friend,
        user_message=message[:5000],
        output=''.join(full_output)[:5000],
        ...
    )
```

`queue.Empty` 不需要 `import queue.Empty` — `queue.Empty` 是 `import queue` 后自动可用的。

- [ ] **Step 2: 运行后端测试**

```bash
cd backend && python -m pytest web/tests/ -v --tb=short
```
Expected: 197 passed, 3 deselected。

- [ ] **Step 3: Commit**

```bash
git add backend/web/views/friend/message/chat/chat.py
git commit -m "feat: event_stream generator finally 断连检测 + mq.get(timeout=1)"
```

---

### Task 4: 后端 — tts_sender 始终收集 _output_buffer + cancel_event 控制 TTS/mq

**Files:**
- Modify: `backend/web/views/friend/message/chat/chat.py` — `tts_sender()` 方法

- [ ] **Step 1: tts_sender 签名加 cancel_event，_output_buffer 始终收集**

```python
async def tts_sender(
        self, ws, task_id: str,
        app: CompiledStateGraph, inputs, mq: queue.Queue, user_id: int,
        cancel_event: threading.Event,  # ← 新增参数
):
    start = time.time()
    total_chars = 0
    success = True
    error_message = ''
    tts_dead = False
    self._output_buffer = []   # ← 始终收集完整输出
    self._output_usage = {}    # ← 始终记录 usage
    self._has_error = False    # ← 供 work() 断连路径使用
    try:
        async for msg, metadata in app.astream(inputs, stream_mode="messages"):
            if isinstance(msg, ToolMessage) and msg.name == "search_knowledge_base":
                citations = []
                for m in CITATION_RE.finditer(msg.content):
                    citations.append({...})
                if citations and not cancel_event.is_set():  # ← 断连时不推 mq
                    mq.put_nowait({'citations': citations})

            elif isinstance(msg, BaseMessageChunk):
                if msg.content:
                    total_chars += len(msg.content)
                    self._output_buffer.append(msg.content)  # ← 始终收集
                    if not cancel_event.is_set():             # ← 正常路径
                        mq.put_nowait({'content': msg.content})
                        if not tts_dead:
                            try:
                                await ws.send(json.dumps({...}))
                            except Exception:
                                logger.warning('TTS WS 发送失败，降级纯文本')
                                tts_dead = True
                if hasattr(msg, 'usage_metadata') and msg.usage_metadata:
                    self._output_usage = msg.usage_metadata   # ← 始终记录
                    if not cancel_event.is_set():             # ← 正常路径推 mq
                        mq.put_nowait({'usage': msg.usage_metadata})
        # finish-task：始终发送以解锁 tts_receiver
        if not tts_dead:                                     # ← 去掉 cancel_event 守卫
            try:
                await ws.send(json.dumps({...}))  # finish-task
            except Exception:
                pass
    except Exception as e:
        self._has_error = True                               # ← 供 work() 用
        success = False
        error_message = str(e)[:500]
        logger.exception('Chat Agent LLM 流异常, task_id=%s', task_id)
    finally:
        duration_ms = int((time.time() - start) * 1000)
        final_success = success and not tts_dead
        self._tts_usage = {
            'user_id': user_id, 'api_type': 'tts',
            'model_name': 'cosyvoice-v3-flash',
            'token_count': total_chars, 'duration_ms': duration_ms,
            'success': final_success,
            'error_message': error_message if not final_success else '',
        }
```

注意 `cancel_event` 参数位置 — 放在 `user_id` 之后，和 `run_tts_task` 签名保持一致。

- [ ] **Step 2: 运行后端测试**

```bash
cd backend && python -m pytest web/tests/ -v --tb=short
```
Expected: 197 passed, 3 deselected。

- [ ] **Step 3: Commit**

```bash
git add backend/web/views/friend/message/chat/chat.py
git commit -m "feat: tts_sender _output_buffer 始终收集 + cancel_event 控制路由"
```

---

### Task 5: 后端 — work() 断连路径保存 Message + run_tts_task 传参

**Files:**
- Modify: `backend/web/views/friend/message/chat/chat.py` — `work()` 和 `run_tts_task()` 方法

- [ ] **Step 1: work() 签名加 cancel_event/friend/message，断连路径保存**

```python
def work(self, app, inputs, mq, voice_id, user_id,
         cancel_event, friend, message,
         inputs_dict):  # ← 新增参数（用于断连时序列化 Message.input）
    tts_allowed, _, _ = check_quota(user_id, 'tts')
    if not tts_allowed:
        logger.warning('TTS 跳过：今日配额已用尽, user_id=%s', user_id)
    try:
        asyncio.run(self.run_tts_task(
            app, inputs, mq, voice_id, user_id,
            tts_allowed, cancel_event  # ← 新增参数
        ))
    except Exception:
        logger.exception('Chat Agent 执行异常')
    finally:
        if cancel_event.is_set():                    # ← 断连路径
            output = ''.join(getattr(self, '_output_buffer', []))
            if output:
                usage = getattr(self, '_output_usage', {})
                Message.objects.create(
                    friend=friend,
                    user_message=message[:5000],
                    input=[m.model_dump() for m in inputs_dict.get('messages', [])],
                    output=output[:5000],
                    input_tokens=usage.get('input_tokens', 0),
                    output_tokens=usage.get('output_tokens', 0),
                    total_tokens=usage.get('total_tokens', 0),
                )
            record_api_usage(
                user_id=user_id, api_type='llm',
                model_name='deepseek-v4-flash',
                token_count=usage.get('total_tokens', 0),
                duration_ms=0,
                success=not getattr(self, '_has_error', False),
                error_message='客户端断开连接',
            )
        mq.put(None)

    # TTS usage（C1 已覆盖）
    if hasattr(self, '_tts_usage'):
        record_api_usage(**self._tts_usage)
        del self._tts_usage
```

- [ ] **Step 2: run_tts_task() 签名加 cancel_event 参数**

```python
async def run_tts_task(
        self, app, inputs, mq, voice_id, user_id,
        tts_allowed: bool = True,
        cancel_event=None,  # ← 新增参数
):
    # ... 函数体不变，只需传递给 tts_sender ...
    await asyncio.gather(
        self.tts_sender(ws, task_id, app, inputs, mq, user_id, cancel_event),  # ← 加参数
        self.tts_receiver(ws, mq, task_id)
    )
```

- [ ] **Step 3: 运行后端测试**

```bash
cd backend && python -m pytest web/tests/ -v --tb=short
```
Expected: 197 passed, 3 deselected。

- [ ] **Step 4: Commit**

```bash
git add backend/web/views/friend/message/chat/chat.py
git commit -m "feat: work() 断连路径从 _output_buffer 保存完整消息"
```

---

### Task 6: 后端测试 — test_chat_agent 扩写 tts_sender cancel_event 测试

**Files:**
- Modify: `backend/web/tests/test_chat_agent.py`

- [ ] **Step 1: 添加 `TestTtsSenderCancelEvent` 测试类**

```python
class TestTtsSenderCancelEvent:
    """P1-C2: tts_sender 断连取消行为测试"""

    def test_output_buffer_always_collects(self, mocker):
        """验证 _output_buffer 始终收集，无论 cancel_event 状态"""
        from web.views.friend.message.chat.chat import MessageChatView
        import threading
        import queue

        view = MessageChatView()
        cancel_event = threading.Event()
        mq = queue.Queue()

        # mock app.astream 返回 3 个 chunk
        async def mock_astream(*args, **kwargs):
            from langchain_core.messages import AIMessageChunk
            yield AIMessageChunk(content='hello '), {}
            yield AIMessageChunk(content='world'), {}
            yield AIMessageChunk(content='!'), {}

        mock_app = mocker.MagicMock()
        mock_app.astream = mock_astream
        mock_ws = mocker.AsyncMock()
        mock_ws.send = mocker.AsyncMock()

        # 模拟断连
        cancel_event.set()

        import asyncio
        asyncio.run(view.tts_sender(
            mock_ws, 'task-1', mock_app, {}, mq, user_id=1,
            cancel_event=cancel_event,
        ))

        assert view._output_buffer == ['hello ', 'world', '!']
        # mq 应该为空（断连时不推）
        assert mq.empty()

    def test_normal_path_pushes_to_mq(self, mocker):
        """验证正常路径推 mq + TTS"""
        from web.views.friend.message.chat.chat import MessageChatView
        import threading
        import queue

        view = MessageChatView()
        cancel_event = threading.Event()  # 未 set
        mq = queue.Queue()

        async def mock_astream(*args, **kwargs):
            from langchain_core.messages import AIMessageChunk
            yield AIMessageChunk(content='hi'), {}

        mock_app = mocker.MagicMock()
        mock_app.astream = mock_astream
        mock_ws = mocker.AsyncMock()
        mock_ws.send = mocker.AsyncMock()

        import asyncio
        asyncio.run(view.tts_sender(
            mock_ws, 'task-1', mock_app, {}, mq, user_id=1,
            cancel_event=cancel_event,
        ))

        assert view._output_buffer == ['hi']
        msg = mq.get_nowait()
        assert msg == {'content': 'hi'}

    def test_disconnect_skips_tts(self, mocker):
        """验证断连时跳过 ws.send"""
        from web.views.friend.message.chat.chat import MessageChatView
        import threading
        import queue

        view = MessageChatView()
        cancel_event = threading.Event()
        cancel_event.set()  # 断连
        mq = queue.Queue()

        async def mock_astream(*args, **kwargs):
            from langchain_core.messages import AIMessageChunk
            yield AIMessageChunk(content='x'), {}

        mock_app = mocker.MagicMock()
        mock_app.astream = mock_astream
        mock_ws = mocker.AsyncMock()
        mock_ws.send = mocker.AsyncMock()

        import asyncio
        asyncio.run(view.tts_sender(
            mock_ws, 'task-1', mock_app, {}, mq, user_id=1,
            cancel_event=cancel_event,
        ))

        # TTS 不应该被调用
        mock_ws.send.assert_not_called()

    def test_finish_task_sent_when_cancel_event_set(self, mocker):
        """验证 cancel_event 已 set 时 finish-task 仍发送（解锁 receiver）"""
        from web.views.friend.message.chat.chat import MessageChatView
        import threading
        import queue

        view = MessageChatView()
        cancel_event = threading.Event()
        cancel_event.set()  # 断连
        mq = queue.Queue()

        async def mock_astream(*args, **kwargs):
            from langchain_core.messages import AIMessageChunk
            yield AIMessageChunk(content='x'), {}
            # 没有 usage_metadata — 正常

        mock_app = mocker.MagicMock()
        mock_app.astream = mock_astream
        mock_ws = mocker.AsyncMock()
        mock_ws.send = mocker.AsyncMock()

        import asyncio
        asyncio.run(view.tts_sender(
            mock_ws, 'task-1', mock_app, {}, mq, user_id=1,
            cancel_event=cancel_event,
        ))

        # finish-task 应该被调用一次
        finish_calls = [c for c in mock_ws.send.call_args_list
                        if '"finish-task"' in str(c.args[0])]
        assert len(finish_calls) == 1
```

- [ ] **Step 2: 运行新测试验证失败（TDD）**

```bash
cd backend && python -m pytest web/tests/test_chat_agent.py::TestTtsSenderCancelEvent -v
```
Expected: 部分测试 PASS（如果 Task 4 已实现），部分可能因未加测试方法到类而需调整。

- [ ] **Step 3: 运行全部测试**

```bash
cd backend && python -m pytest web/tests/ -v --tb=short
```
Expected: 全部通过。

- [ ] **Step 4: Commit**

```bash
git add backend/web/tests/test_chat_agent.py
git commit -m "test: tts_sender cancel_event 行为测试（buffer/mq/TTS/finish-task）"
```

---

## Self-Review

**1. Spec coverage:**

| Spec 要求 | 对应 Task |
|-----------|----------|
| streamApi 支持 signal | Task 1 |
| InputField onUnmounted abort | Task 2 |
| generator finally 断连检测 | Task 3 |
| mq.get(timeout=1) | Task 3 |
| work() 断连路径保存 Message | Task 5 |
| tts_sender _output_buffer 始终收集 | Task 4 |
| cancel_event 控制 TTS/mq 路由 | Task 4 |
| finish-task 始终发送解锁 receiver | Task 4 |
| _has_error 实例属性传递 | Tasks 4+5 |
| C1 兼容（tts_dead 并列检查） | Task 4 |

**2. Placeholder scan:** 无 TBD/TODO，所有代码步骤包含具体实现。

**3. Type consistency:** `cancel_event` 类型 `threading.Event` 在所有函数中一致，`_output_buffer`/`_output_usage`/`_has_error` 命名一致。
