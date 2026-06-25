# P1-C2: SSE 客户端断连检测 + 后端取消 设计文档

> 状态：✅ 已确认 | 2026-06-25

## 一、问题

用户关闭聊天窗口 / 切换路由 / 关浏览器标签页后，后端不知道客户端已离开，继续跑 LLM + TTS + 写 DB，白白消耗 API 费用。

**当前链路无取消机制：**

```
前端 ChatField 关闭        后端 event_stream
─────────────────         ─────────────────
dialog.close()             while True:
组件卸载                      msg = mq.get()     ← 阻塞，不知客户端已走
                              if msg is None: break
                              
                           work() 线程
                           ├── app.astream()    ← 继续生成 token 🔥💰
                           ├── TTS WebSocket    ← 继续合成语音 🔥💰
                           └── Message.objects.create() ← 写无意义的 DB 记录
```

## 二、目标

- 前端关闭聊天窗口后，停止 TTS（不再合成语音），LLM 自然完成后保存完整回复
- 不改变正常流（用户未离开时行为不变）
- 不引入新的外部依赖
- 兼容 C1 的 TTS 降级逻辑
- **部署环境无关** — WSGI (gunicorn) 和 ASGI (daphne/uvicorn) 均有效

### 行为语义：让 AI 说完，不浪费 tokens

断连后的处理有两种选择：

| 方案 | 描述 | 采用？ | 理由 |
|------|------|:---:|------|
| 1. 立刻终止 | 断连即 stop LLM + TTS，半截句子入库 | ❌ | 聊天历史残留"半截句子"，用户下次打开看到像 bug |
| 2. 让 LLM 说完 | 断连即停 TTS，LLM 自然完成，完整消息入库 | ✅ | 用户关闭窗口 = 放弃**收听**，不等同于放弃**回复**；完整消息的聊天历史更干净，额外 LLM 成本极低 |

## 三、架构

```
┌─ 前端 ─────────────────────── 后端 ─────────────────────────────────────┐
│                                                                        │
│  InputField.vue                                                        │
│  onUnmounted()                                                         │
│    → abortController.abort()                                           │
│         │                                                              │
│         │  HTTP 连接断开                                                │
│         ▼                                                              │
│  event_stream() generator                                              │
│  try:                                                                  │
│    while True:                                                         │
│      msg = mq.get(timeout=1)                                          │
│      if msg is None: break                                            │
│      yield SSE ─────────→ 客户端收到                                   │
│  finally:  ←── GeneratorExit when client disconnects                  │
│    cancel_event.set() ────────────────────────┐                        │
│    # generator 退出，mq 不再被消费               │                        │
│                                                ▼                        │
│  tts_sender() [asyncio]  ←── cancel_event.is_set()                     │
│    async for msg in app.astream():                                     │
│      if msg.content:                                                   │
│        self._output_buffer.append(content)  ← 始终收集完整输出          │
│        if not cancel_event.is_set():                                   │
│          mq.put_nowait(content)   ← 正常：推 mq + TTS                  │
│          await ws.send(...)                                            │
│        # 断连：只写 buffer，不推 mq，不送 TTS                          │
│    → LLM 自然完成 → tts_sender 退出                                    │
│                                                                        │
│  work() [线程]                                                         │
│    asyncio.run(run_tts_task(...))                                      │
│    finally:                                                            │
│      if cancel_event.is_set():                                         │
│        # 断连路径：从 _output_buffer（完整输出）保存消息 + 记录 usage   │
│        Message.objects.create(output=''.join(self._output_buffer))     │
│        record_api_usage(api_type='llm', ...)                           │
│      mq.put(None)  ← 正常路径被 event_stream 消费，断连路径无害        │
└────────────────────────────────────────────────────────────────────────┘
```

**核心设计：Python generator `finally` 作为断连检测点**

`StreamingHttpResponse` 的 generator 在客户端断开时被框架 `close()` → 触发 `GeneratorExit` → `finally` 块执行。这是 Python generator 标准行为，**WSGI 和 ASGI 服务器均适用**，无需 `request.is_disconnected()`（ASGI-only）。

### 为什么不用 `request.is_disconnected()`

| 方式 | WSGI | ASGI | 复杂度 | 结论 |
|------|:---:|:---:|--------|------|
| `request.is_disconnected()` | ❌ 永远 False | ✅ | 低 | **不可用** — 生产环境 gunicorn WSGI 失效 |
| generator `finally` | ✅ | ✅ | 低 | **选用** — Python 标准行为，部署环境无关 |

`finally` 的检测延迟取决于 `yield` 间距。`yield` 在 `mq.get(timeout=1)` 拿到数据时触发（正常流中频繁 yield），或 timeout 后再次循环时触发（idle 时 ≤1s），因此断连后 ≤1s 内 `finally` 执行。性能特征与 timeout 轮询方案完全一致。

### 取消信号选型

`cancel_event` 的语义：**客户端已离开 → 停止 TTS + 停止推 mq，LLM 继续**。

| 方案 | 描述 | 采用？ | 理由 |
|------|------|:---:|------|
| A. `threading.Event` | `event_stream` finally set，`tts_sender` 轮询 `is_set()` | ✅ | 标准库为此而生，跨线程零开销，不串数据流 |
| B. 队列毒丸 | 新增反向队列传 `'STOP'` | ❌ | 用队列模拟信号旗，多一层数据结构，无额外收益 |

### 前端 abort 触发点选型

| 方案 | 描述 | 采用？ | 理由 |
|------|------|:---:|------|
| A. `handleClose()` 回调 | dialog `@close` 事件中 abort | ❌ | 只覆盖显式关闭，漏掉路由跳转等路径 |
| B. `onUnmounted` 生命周期 | 组件卸载时自动 abort | ✅ | 覆盖所有卸载路径（关闭/路由/销毁），Vue 清理副作用的正确位置 |
| C. 两者都挂 | 防御性双重 abort | ❌ | B 已全覆盖，C 只增重复 abort 的噪音日志 |

## 四、改动范围

### 前端

| 文件 | 改动 | 说明 |
|------|------|------|
| `src/js/http/streamApi.js` | 接受 `signal` 参数，传给 `fetchEventSource` | `@microsoft/fetch-event-source` 原生支持 |
| `src/components/character/chat_field/input_field/InputField.vue` | 创建 `AbortController`，`onUnmounted` 中 `abort()` | 生命周期清理 |

### 后端

| 文件 | 改动 | 说明 |
|------|------|------|
| `web/views/friend/message/chat/chat.py` | `event_stream()`: `mq.get(timeout=1)` + `try/finally` 检测断连 + 排空模式 | generator finally 作为断连检测点 |
| | `work()`: 接收 `cancel_event`，finally: 断连时本地保存 Message | 断连路径的 DB 写入 + usage |
| | `tts_sender()`: 检查 `cancel_event.is_set()` → 停 TTS + 切本地 buffer | 停 TTS，不停 LLM |

## 五、关键设计细节

### 5.1 精确函数签名变更

**`event_stream()`**:

```python
def event_stream(self, app, inputs, friend, message):
    start_time = time.time()
    mq = queue.Queue(maxsize=500)
    cancel_event = threading.Event()
    # ... existing setup ...
    thread = threading.Thread(
        target=self.work,
        args=(app, inputs, mq, voice_id, user_id, cancel_event, friend, message),
        daemon=True,
    )
    thread.start()

    full_output = []
    full_usage = {}
    has_error = False
    error_message = ''

    try:
        while True:
            msg = mq.get(timeout=1)  # ← 从 mq.get() 改为带超时
            # ... 处理 msg，收集 full_output/full_usage，yield SSE ...
    finally:
        # generator 退出 = 正常结束 或 客户端断连
        cancel_event.set()
        # LLM usage 在 work() 中记录（断连路径），此处不再记录
```

**`work()`** — 新增参数 + 断连保存逻辑:

```python
def work(self, app, inputs, mq, voice_id, user_id,
         cancel_event, friend, message):
    tts_allowed, _, _ = check_quota(user_id, 'tts')
    try:
        asyncio.run(self.run_tts_task(
            app, inputs, mq, voice_id, user_id, tts_allowed, cancel_event
        ))
    except Exception:
        logger.exception('Chat Agent 执行异常')
    finally:
        if cancel_event.is_set():
            # 断连路径：从 _output_buffer（始终收集，完整输出）保存消息
            output = ''.join(getattr(self, '_output_buffer', []))
            if output:
                Message.objects.create(
                    friend=friend,
                    user_message=message[:5000],
                    output=output[:5000],
                    ...
                )
            # 记录 LLM usage（token 数从 _output_usage 取，has_error 由 tts_sender 设置）
            usage = getattr(self, '_output_usage', {})
            record_api_usage(
                user_id=user_id,
                api_type='llm',
                model_name='deepseek-v4-flash',
                token_count=usage.get('total_tokens', 0),
                success=not getattr(self, '_has_error', False),
            )
        mq.put(None)  # 正常路径被消费，断连路径无害

    # TTS usage（C1 已覆盖，不变）
    if hasattr(self, '_tts_usage'):
        record_api_usage(**self._tts_usage)
```

**`run_tts_task()`** — 新增 `cancel_event` 参数:

```python
async def run_tts_task(self, app, inputs, mq, voice_id, user_id,
                        tts_allowed=True, cancel_event=None):
```

**`tts_sender()`** — 新增参数 + 双路径推内容:

```python
async def tts_sender(self, ws, task_id, app, inputs, mq, user_id, cancel_event):
    self._output_buffer = []  # 始终收集完整输出（正常 + 断连两用）
    self._output_usage = {}   # usage_metadata（正常 mq 走，断连靠这个）
    tts_dead = False
    try:
        async for msg, metadata in app.astream(inputs, stream_mode="messages"):
            if isinstance(msg, ToolMessage) ...:
                # citations（断连时不推 mq — 客户端已走，无意义）
                if not cancel_event.is_set() and citations:
                    mq.put_nowait({'citations': citations})
            elif isinstance(msg, BaseMessageChunk):
                if msg.content:
                    total_chars += len(msg.content)
                    self._output_buffer.append(msg.content)  # ← 始终收集，保完整输出
                    if not cancel_event.is_set():
                        # 正常路径：推 mq + TTS
                        mq.put_nowait({'content': msg.content})
                        if not tts_dead:
                            try: await ws.send(...)
                            except: tts_dead = True
                    # 断连路径：只写 buffer，不推 mq，不送 TTS
                if hasattr(msg, 'usage_metadata') and msg.usage_metadata:
                    self._output_usage = msg.usage_metadata       # ← 始终记录
                    if not cancel_event.is_set():
                        mq.put_nowait({'usage': msg.usage_metadata})
        # finish-task：始终发送以解锁 tts_receiver，避免 asyncio.gather 挂起
        if not tts_dead:
            try: await ws.send(finish_task)
            except: pass
    except Exception as e:
        self._has_error = True   # ← work() 断连路径用
        error_message = str(e)[:500]
        logger.exception('Chat Agent LLM 流异常, task_id=%s', task_id)
    finally:
        # TTS usage（C1 逻辑，不变）
        ...
```

### 5.2 正常结束 vs 断连（排空模式）

```
正常结束:
  work() → asyncio.run() 完成 → _output_buffer 有完整输出（和 mq 中的 full_output 等价）
  → finally: mq.put(None)
  → event_stream 收到 None → break → 从 full_output 保存 Message → 正常返回
  → finally: cancel_event.set() 无影响

断连（排空模式）:
  event_stream 在 yield 处 → client 断开 → GeneratorExit
  → finally: cancel_event.set()
  → generator 退出，mq 不再被消费
  → tts_sender: cancel_event.is_set() → 停 TTS/停 mq，_output_buffer 继续收集
  → LLM 完成 → tts_sender 退出
  → work() finally: cancel_event.is_set() → 从 self._output_buffer（完整输出）保存 Message
  → 记录 LLM usage → mq.put(None) 无害
```

`_output_buffer` 始终收集，因此 work() 断连时拿到的就是完整 LLM 输出——无前缀丢失。

### 5.3 正常路径中的 `cancel_event.set()`

正常结束时 generator `finally` 也会执行 `cancel_event.set()`。但此时 LLM 已自然完成、消息已保存，`set()` 是 no-op。不需要区分正常/断连 — `finally` 统一处理，简单可靠。

### 5.4 TTS usage 在断连时的语义

当 `cancel_event` 触发时，TTS 主动停止（WebSocket 仍健康），`tts_dead` 不设置，LLM 也没抛异常 → `final_success = True`。这意味着用量数据无法区分"完整 TTS"和"用户主动中断 TTS"。

不修复。操作上 `success=True` 正确（非故障），区分需求可通过 `error_message` 为空 + chat 消息未完整返回间接推断。如将来需要精确标记，可在 `tts_sender` finally 加 `self._tts_interrupted_by_client` 字段，不阻塞当前实现。

### 5.5 `openWhenHidden`

当前 `@microsoft/fetch-event-source` 设置了 `openWhenHidden: true` — 切换浏览器标签页不会断开 SSE。这是有意为之（用户可能切出去看别的再回来继续听语音）。

保持此行为不变。本功能只在**关闭聊天窗口**时 abort，不在**切标签页**时 abort。

### 5.6 与 C1 的兼容

C1 的 `tts_dead` 和 C2 的 `cancel_event` 在 `tts_sender` 循环内并列检查：

```python
async for msg in app.astream():
    if msg.content:
        self._output_buffer.append(content)  # 始终收集完整输出
        if not cancel_event.is_set():         # C2: 用户没走 → 推 mq + TTS
            mq.put_nowait(content)
            if not tts_dead:                 # C1: TTS 已坏 → 只推文字
                try: await ws.send(...)
                except: tts_dead = True
        # 用户走了：跳过 mq + TTS，buffer 已收集
```

互不干扰 — C2 控制 mq/TTS 路由，C1 降级 TTS；`_output_buffer` 始终完整。

## 六、变更记录

| # | 时间 | 变更 | 原因 |
|---|------|------|------|
| 1 | 2026-06-25 | 初版 | P1-C2 设计启动 |
| 2 | 2026-06-25 | 方案 1→2：立刻终止 → 排空模式（让 LLM 说完） | 用户期望完整回复 |
| 3 | 2026-06-25 | `stop_event`→`cancel_event` + 排空模式重写 | 语义精确化 |
| 4 | 2026-06-25 | 断连检测：`request.is_disconnected()` → generator `finally` | ASGI-only → WSGI/ASGI 通用 |
| 5 | 2026-06-25 | 新增 §5.1 精确函数签名 + `_drain_output` 本地 buffer | Review: 签名细节 + mq 断连后不可用 |
| 6 | 2026-06-25 | 新增 §5.4 TTS usage 语义说明 | Review: 主动中断 vs 故障中断的区分 |
| 7 | 2026-06-25 | `_drain_output`→`_output_buffer`：始终收集，不断连后才切 | Review: 断连时前缀丢失（event_stream.full_output 被 discard） |
| 8 | 2026-06-25 | `has_error`→`self._has_error`：通过实例属性在线程内传递 | Review: work() 中 has_error 变量未定义 |
| 9 | 2026-06-25 | `finish-task` 移除 `cancel_event` 守卫：始终发送以解锁 receiver | Review: 断连时 receiver 阻塞 asyncio.gather 30s |
