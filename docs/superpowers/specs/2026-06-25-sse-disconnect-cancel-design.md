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

- 前端关闭聊天窗口后，**≤1 秒**内停止 TTS（不再合成语音），LLM 自然完成后保存完整回复
- 不改变正常流（用户未离开时行为不变）
- 不引入新的外部依赖
- 兼容 C1 的 TTS 降级逻辑

### 行为语义：让 AI 说完，不浪费 tokens

断连后的处理有两种选择：

| 方案 | 描述 | 采用？ | 理由 |
|------|------|:---:|------|
| 1. 立刻终止 | 断连即 stop LLM + TTS，半截句子入库 | ❌ | 聊天历史残留"半截句子"，用户下次打开看到像 bug |
| 2. 让 LLM 说完 | 断连即停 TTS，LLM 自然完成，完整消息入库 | ✅ | 用户关闭窗口 = 放弃**收听**，不等同于放弃**回复**；完整消息的聊天历史更干净，额外 LLM 成本极低（deepseek-v4-flash 几分钱） |

## 三、架构

```
┌─ 前端 ──────────────────────────────────── 后端 ──────────────────────────┐
│                                                                          │
│  InputField.vue                                                          │
│  onUnmounted()                                                           │
│    → abortController.abort()                                             │
│         │                                                                │
│         │  HTTP 连接断开                                                  │
│         ▼                                                                │
│  event_stream()  ──── 正常路径 ────                                      │
│  while True:                                                             │
│    msg = mq.get(timeout=1)  ← 每秒醒来                                    │
│    if timeout:                                                            │
│      if request.is_disconnected():                                       │
│        disconnected = True                                               │
│        cancel_event.set() ──┐  ← 通知停止 TTS，不停 LLM                    │
│        continue (排空模式)   │                                            │
│    if msg is None: break    │                                            │
│    if not disconnected:     │                                            │
│      yield SSE              │  ← 断连后不再 yield，只收集 full_output      │
│                             │                                            │
│                             ▼                                            │
│  tts_sender() [asyncio]                                                  │
│    async for msg in app.astream():                                       │
│      if msg.content:                                                     │
│        mq.put_nowait(content)           ← 始终推 mq（event_stream 仍在消费）│
│        if not cancel_event.is_set():                                     │
│          await ws.send(...)             ← 断连后停止 TTS ✅              │
│      if hasattr(msg, 'usage_metadata'):                                  │
│        mq.put_nowait({'usage': ...})                                     │
│  → LLM 自然完成 → work() finally: mq.put(None)                           │
│  → event_stream 收到 None → break                                        │
│  → 完整消息入库 ✅                                                       │
└──────────────────────────────────────────────────────────────────────────┘
```

**核心设计：排空模式（Drain Mode）**

`event_stream` 检测到断连后不立即退出，而是继续消费 `mq` 队列等待 LLM 自然结束。这期间：
- 不再 `yield` SSE 数据（客户端已走，yield 无意义）
- 继续收集 `full_output` / `full_usage`（用于最后 DB 写入）
- `cancel_event` 告知 `tts_sender` 停止 TTS（省 TTS 费用），但不影响 LLM 继续生成

### 取消信号选型

`cancel_event` 的语义：**客户端已离开 → 停止 TTS，但不停止 LLM**。

| 方案 | 描述 | 采用？ | 理由 |
|------|------|:---:|------|
| A. `threading.Event` | `event_stream` set，`tts_sender` 轮询 `is_set()`，跳过 TTS | ✅ | 标准库为此而生，跨线程零开销，不串数据流 |
| B. 队列毒丸 | 新增反向队列传 `'STOP'` | ❌ | 用队列模拟信号旗，多一层数据结构，无额外收益 |

### 前端 abort 触发点选型

| 方案 | 描述 | 采用？ | 理由 |
|------|------|:---:|------|
| A. `handleClose()` 回调 | dialog `@close` 事件中 abort | ❌ | 只覆盖显式关闭，漏掉路由跳转等路径 |
| B. `onUnmounted` 生命周期 | 组件卸载时自动 abort | ✅ | 覆盖所有卸载路径（关闭/路由/销毁），Vue 清理副作用的正确位置 |
| C. 两者都挂 | 防御性双重 abort | ❌ | B 已全覆盖，C 只增重复 abort 的噪音日志 |

### 后端断连检测 + 排空机制

使用 `mq.get(timeout=1)` 轮询替代 `mq.get()` 阻塞等待。检测到断连后进入**排空模式**而非直接退出：

```
正常模式                         排空模式（disconnected = True）
────────                         ─────────────────────────────
msg = mq.get(timeout=1)         msg = mq.get(timeout=1)
if timeout:                      if timeout: continue  ← 已经知道断连，不用再检查
  if request.is_disconnected():  msg = mq.get() 拿到数据 → yield SSE？不
    disconnected = True          msg = mq.get() 拿到 None → break → 保存 Message
    cancel_event.set()           → event_stream 退出
    continue                     → work 线程自然结束，LLM tokens 记录完整 ✅
if msg is None: break
yield SSE → 客户端收到
```

排空模式的要点：
- `cancel_event` 的语义是"停 TTS"，不是"停一切"
- `event_stream` 继续消费 mq，但不再 yield SSE（客户端已走，yield 无意义）
- LLM 自然完成 → `work()` finally: `mq.put(None)` → `event_stream` 收到退出
- 完整 `full_output` 和 `full_usage` 正常收集 → 写入 DB

## 四、改动范围

### 前端

| 文件 | 改动 | 说明 |
|------|------|------|
| `src/js/http/streamApi.js` | 接受 `signal` 参数，传给 `fetchEventSource` | `@microsoft/fetch-event-source` 原生支持 |
| `src/components/character/chat_field/input_field/InputField.vue` | 创建 `AbortController`，`onUnmounted` 中 `abort()` | 生命周期清理 |

### 后端

| 文件 | 改动 | 说明 |
|------|------|------|
| `web/views/friend/message/chat/chat.py` | `event_stream()`: `mq.get(timeout=1)` + `request.is_disconnected()` + 排空模式 + `try/finally` 保 LLM usage | 断连检测 + 完整回复入库 |
| | `work()`: 接收 `cancel_event` | 传给 tts_sender |
| | `tts_sender()`: 循环内检查 `cancel_event.is_set()` 跳过 TTS | 停 TTS，不停 LLM |

## 五、关键设计细节

### 5.1 `cancel_event` 传递路径

```
event_stream() 创建 cancel_event = threading.Event()
  → 传给 work(app, inputs, mq, voice_id, user_id, cancel_event)
    → 传给 run_tts_task(..., cancel_event)
      → 传给 tts_sender(..., cancel_event)
```

`tts_receiver` 不需要 `cancel_event` — WebSocket 关闭会在 `async for msg in ws` 抛出异常，C1 已处理。断连后 TTS 不再发送文本，receiver 端收到 `task-failed` 或连接关闭也会自然退出。

### 5.2 正常结束 vs 断连（排空模式）

```
正常结束:
  work() → mq.put(None) → event_stream 收到 None → break
  → yield [DONE] → 保存 Message → 正常返回

断连（排空模式）:
  event_stream timeout → is_disconnected() → disconnected = True
  → cancel_event.set() → 继续消费 mq（不再 yield SSE）
  → tts_sender 继续生成 LLM → mq.put_nowait(content) → 正常入队
  → tts_sender: ws.send() 跳过（cancel_event.is_set()）
  → LLM 完成 → tts_sender 退出 → work() finally: mq.put(None)
  → event_stream 收到 None → break
  → 保存完整 Message ✅
```

### 5.3 `openWhenHidden`

当前 `@microsoft/fetch-event-source` 设置了 `openWhenHidden: true` —— 这意味着切换浏览器标签页不会断开 SSE。这是有意为之（用户可能切出去看别的再回来继续听语音）。

保持此行为不变。本功能只在**关闭聊天窗口**时 abort，不在**切标签页**时 abort。

### 5.4 与 C1 的兼容

C1 的 `tts_dead` 和 C2 的 `cancel_event` 在 `tts_sender` 循环内并列检查：

```python
async for msg in app.astream():
    if msg.content:
        mq.put_nowait(content)           # 始终推 mq
        if not cancel_event.is_set():     # C2: 用户走了，停 TTS
            if not tts_dead:             # C1: TTS 已坏，只推文字
                try: await ws.send(...)
                except: tts_dead = True
```

互不干扰 —— C2 停 TTS 但不影响 LLM 生成和消息队列，C1 停 TTS 但不影响文本流。

## 六、变更记录

| # | 时间 | 变更 | 原因 |
|---|------|------|------|
| 1 | 2026-06-25 | 初版 | P1-C2 设计启动 |
| 2 | 2026-06-25 | 方案 1→2：立刻终止 → 排空模式 | 用户期望完整回复，非半截句子 |
| 3 | 2026-06-25 | `stop_event` 重命名为 `cancel_event` | 语义精确化：停 TTS 不停 LLM |
| 4 | 2026-06-25 | 架构重写为排空模式 | `event_stream` 断连后继续消费 mq 不 break |
