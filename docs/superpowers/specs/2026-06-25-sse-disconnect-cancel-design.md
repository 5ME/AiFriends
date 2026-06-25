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

- 前端关闭聊天窗口后，**≤1 秒**内后端停止 LLM + TTS 调用
- 不改变正常流（用户未离开时行为不变）
- 不引入新的外部依赖
- 兼容 C1 的 TTS 降级逻辑

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
│  event_stream()                                                          │
│  while True:                                                             │
│    msg = mq.get(timeout=1)  ← 每秒醒来                                    │
│    if timeout:                                                            │
│      if request.is_disconnected(): ← Django 6.0+                         │
│        stop_event.set() ──────────────────────────┐                      │
│        break                                      │                      │
│    ...                                            │                      │
│                                                   ▼                      │
│  work() 线程 ←────────────────────── stop_event.is_set()                 │
│    if stop_event.is_set(): return                                    │
│                                                                          │
│  tts_sender() [asyncio]                                                  │
│    async for msg in app.astream():                                       │
│      if stop_event.is_set(): break  ← 提前退出 LLM 循环                   │
│      if not tts_dead: await ws.send(...)                                 │
│      mq.put_nowait(content)                                              │
└──────────────────────────────────────────────────────────────────────────┘
```

### 取消信号选型

| 方案 | 描述 | 采用？ | 理由 |
|------|------|:---:|------|
| A. `threading.Event` | `event_stream` set，`work`/`tts_sender` 轮询 `is_set()` | ✅ | 标准库为此而生，跨线程零开销，不串数据流 |
| B. 队列毒丸 | 新增反向队列传 `'STOP'` | ❌ | 用队列模拟信号旗，多一层数据结构，无额外收益 |
| C. 等 asyncio 自然结束 | 不传取消信号，等 LLM 自然 yield 完 | ❌ | 与 C2 节省费用的目标矛盾，每个断连白烧 2-5s token |

### 前端 abort 触发点选型

| 方案 | 描述 | 采用？ | 理由 |
|------|------|:---:|------|
| A. `handleClose()` 回调 | dialog `@close` 事件中 abort | ❌ | 只覆盖显式关闭，漏掉路由跳转等路径 |
| B. `onUnmounted` 生命周期 | 组件卸载时自动 abort | ✅ | 覆盖所有卸载路径（关闭/路由/销毁），Vue 清理副作用的正确位置 |
| C. 两者都挂 | 防御性双重 abort | ❌ | B 已全覆盖，C 只增重复 abort 的噪音日志 |

### 后端断连检测方式

使用 `mq.get(timeout=1)` 轮询替代 `mq.get()` 阻塞等待。理由：

- **timeout 只在队列空时才触发** — 正常流中 token 推送频繁，`mq.get()` 立即返回，不触发 timeout
- **纳秒级开销** — `try/except queue.Empty` 约 100ns vs LLM 调用 100-500ms，6 个数量级差距
- **timeout 不是截止时间** — 只是"醒来检查一下用户还在不在"的闹钟，不影响 LLM token 间隔
- **等待中检查断连** — 断连后 ≤1s 停止烧钱

## 四、改动范围

### 前端

| 文件 | 改动 | 说明 |
|------|------|------|
| `src/js/http/streamApi.js` | 接受 `signal` 参数，传给 `fetchEventSource` | `@microsoft/fetch-event-source` 原生支持 |
| `src/components/character/chat_field/input_field/InputField.vue` | 创建 `AbortController`，`onUnmounted` 中 `abort()` | 生命周期清理 |

### 后端

| 文件 | 改动 | 说明 |
|------|------|------|
| `web/views/friend/message/chat/chat.py` | `event_stream()`: `mq.get(timeout=1)` + `request.is_disconnected()` + 创建 `threading.Event` | 断连检测 |
| | `work()`: 接收 `stop_event`，循环头检查 `is_set()` | 线程级取消 |
| | `tts_sender()`: 循环内检查 `stop_event.is_set()` | `app.astream()` 提前退出 |

## 五、关键设计细节

### 5.1 `stop_event` 传递路径

```
event_stream() 创建 stop_event = threading.Event()
  → 传给 work(app, inputs, mq, voice_id, user_id, stop_event)
    → 传给 run_tts_task(..., stop_event)
      → 传给 tts_sender(..., stop_event)
```

不需要传给 `tts_receiver` —— WebSocket 关闭会在 `async for msg in ws` 抛出异常，C1 已处理。

### 5.2 断连 vs 正常结束

`work()` 正常结束时也会 `mq.put(None)`，队列消费者收到 `None` break，**此时不 `set()` stop_event**：

```
正常结束:
  work() → mq.put(None) → event_stream 收到 None → break → 正常返回

断连:
  event_stream timeout → is_disconnected() → stop_event.set() → break
  → work(): tts_sender 检测到 stop_event.is_set() → break
  → work() finally: mq.put(None)
      → 队列未被消费，但不会阻塞（队列未满，maxsize=500 远大于残存消息数）
      → 线程退出，None 随队列 GC 释放
```

无需改动 `mq.put(None)` 调用方式 — 现有 `block=True` 在 disconnect 场景下不会阻塞（队列远未达到 maxsize）。

### 5.3 `openWhenHidden`

当前 `@microsoft/fetch-event-source` 设置了 `openWhenHidden: true` —— 这意味着切换浏览器标签页不会断开 SSE。这是有意为之（用户可能切出去看别的再回来继续听语音）。

保持此行为不变。本功能只在**关闭聊天窗口**时 abort，不在**切标签页**时 abort。

### 5.4 与 C1 的兼容

C1 的 `tts_dead` 和 C2 的 `stop_event` 在 `tts_sender` 循环内并列检查：

```python
async for msg in app.astream():
    if stop_event.is_set():   # C2: 用户走了，全停
        break
    if msg.content:
        if not tts_dead:      # C1: TTS 已坏，只推文字
            try: await ws.send(...)
            except: tts_dead = True
        mq.put_nowait(content)
```

互不干扰 —— C2 是全停（用户走了什么都没意义），C1 是部分降级（TTS 坏了文字还要）。

## 六、变更记录

| # | 时间 | 变更 | 原因 |
|---|------|------|------|
| 1 | 2026-06-25 | 初版 | P1-C2 设计启动 |
