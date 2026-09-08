# 聊天改版 Phase 3 —— 输入与语音 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成聊天输入与语音交互（停止生成、语音状态机、Microphone 受控化、识别回填确认、错误态/重试、音量波形），并清理 PR #35 遗留的 `rendered` 死代码。

**Architecture:** 语音交互实现为「InputField 持有状态 + Microphone 受控组件只出事件」：纯函数 `voiceReducer`（LD §6 转移表）单测锁定状态流转，InputField 按状态切换输入栏三区域（🎤/textarea/波形区），Microphone 通过 `getStream` 注入让 VAD 与 AnalyserNode 波形共用同一条麦克风流。

**Tech Stack:** Vue 3 Composition API + vitest + jsdom（沿用 Phase 2 引入的测试基建）；`@ricky0123/vad-web@0.0.30`（支持 `getStream` 注入，已核实 d.ts）；后端零改动。

---

> 状态：待执行
> 前置：PR #35 已合并 master（`32c4841`）；本计划从 master 切 `feature/gqyin/chat-ui-redesign-phase3`
> 事实源：`2026-09-07-chat-ui-redesign-spec-for-llm.md`（spec §5.3/§9/§11/§13）+ `2026-09-07-chat-ui-redesign-logic-design.md`（LD §3.8/§3.9/§6/§9.2）+ PR #35 复审遗留项（rendered 死代码）
> 范围拍板（本计划内的边界决策）：
> 1. **停止生成按钮**：spec Phase 2 断言 6 后半未交付、PR #35 已声明移入本 Phase，纳入本计划（Task 3）。
> 2. **`rendered` 死代码**：PR #35 两轮 review 登记「随 Phase 3 清理」，纳入本计划（Task 3）。
> 3. **自动发送开关（800ms 定时器 + ⚙ UI + useChatSettings）**：**不在本计划**——LD Phase 4 表把 `useChatSettings.js` 与 WindowHeader ⚙ 设置弹层归入 Phase 4；Phase 3 只实现 spec 断言 4「默认不自动发送」（confirm 仅回填）。
> 4. **不引入** `@vue/test-utils`（LD §9.1：仅在组件级用例需要时引入——本轮纯函数单测 + 手工验收足够）；停止生成/真实麦克风流程按 LD §9.3 归为手工验收。
> 5. E6 与 LD §6 的冲突拍板：`transcribing` 期间 🎤 按钮 **disabled**（E6，防并发 ASR）；Esc 仍可 CANCEL（LD §6 表 transcribing+CANCEL→idle 行保留）。
> 6. Microphone emits 偏离声明：LD §3.9 清单（started/speechEnded/transcript/error/cancel）之外**增加 `speechStart`**——LD §6 表「SPEECH_START → 打断 TTS（现状保留）」需要该信号，spec 清单是最小集而非封闭集，属必要的补全。
> 7. CANCEL 后的迟到结果丢弃：取消聆听/识别后，in-flight ASR 的 `transcript`/`error` 事件必须在 InputField 侧按当前态守卫丢弃（LD §6「transcribing+CANCEL → idle，忽略结果」）。

---

## Task 0：分支准备

**Files:**
- 无

- [ ] **Step 1：切分支**

Run:

```bash
cd /d/MyProjects/AiFriends   # 仓库根
git checkout master
git pull origin master       # 应已在 32c4841（PR #35 合并提交）
git checkout -b feature/gqyin/chat-ui-redesign-phase3
```

Expected: 新分支基于 `32c4841`，工作树与 master 一致。

- [ ] **Step 2：确认基线**

Run: `git log --oneline -1 && npm --prefix frontend run test:unit`
Expected: `32c4841 Merge pull request #35 ...`；`28 passed`（既有测试不受影响）。

---

## Task 1：`voiceState.js` 纯 reducer + 单测（TDD）

**Files:**
- Create: `frontend/src/utils/voiceState.js`
- Test: `frontend/src/utils/__tests__/voiceState.test.js`

- [ ] **Step 1：写失败测试**

```js
// frontend/src/utils/__tests__/voiceState.test.js
import { describe, it, expect } from 'vitest'
import { voiceReducer, VOICE_STATES, VOICE_EVENTS } from '../voiceState'

const S = VOICE_STATES, E = VOICE_EVENTS

describe('voiceReducer（LD §6 转移表全行）', () => {
  it('idle + CLICK_MIC → listening', () => {
    expect(voiceReducer(S.IDLE, E.CLICK_MIC)).toBe(S.LISTENING)
  })
  it('listening + SPEECH_START → listening（打断 TTS 不换态）', () => {
    expect(voiceReducer(S.LISTENING, E.SPEECH_START)).toBe(S.LISTENING)
  })
  it('listening + SPEECH_END → transcribing', () => {
    expect(voiceReducer(S.LISTENING, E.SPEECH_END)).toBe(S.TRANSCRIBING)
  })
  it('listening + CANCEL → idle（Esc/✕/再点🎤）', () => {
    expect(voiceReducer(S.LISTENING, E.CANCEL)).toBe(S.IDLE)
  })
  it('listening + VAD_INIT_FAILED → vad_failed', () => {
    expect(voiceReducer(S.LISTENING, E.VAD_INIT_FAILED)).toBe(S.VAD_FAILED)
  })
  it('listening + MIC_PERMISSION_DENIED → mic_denied', () => {
    expect(voiceReducer(S.LISTENING, E.MIC_PERMISSION_DENIED)).toBe(S.MIC_DENIED)
  })
  it('transcribing + TRANSCRIPT_TEXT → confirm', () => {
    expect(voiceReducer(S.TRANSCRIBING, E.TRANSCRIPT_TEXT)).toBe(S.CONFIRM)
  })
  it('transcribing + TRANSCRIPT_EMPTY → asr_failed', () => {
    expect(voiceReducer(S.TRANSCRIBING, E.TRANSCRIPT_EMPTY)).toBe(S.ASR_FAILED)
  })
  it('transcribing + ASR_ERROR → asr_failed', () => {
    expect(voiceReducer(S.TRANSCRIBING, E.ASR_ERROR)).toBe(S.ASR_FAILED)
  })
  it('transcribing + CANCEL → idle（丢弃结果）', () => {
    expect(voiceReducer(S.TRANSCRIBING, E.CANCEL)).toBe(S.IDLE)
  })
  it('confirm + SEND → idle', () => {
    expect(voiceReducer(S.CONFIRM, E.SEND)).toBe(S.IDLE)
  })
  it('confirm + CLICK_MIC → listening（覆盖重录）', () => {
    expect(voiceReducer(S.CONFIRM, E.CLICK_MIC)).toBe(S.LISTENING)
  })
  it('confirm + EDIT_TEXT → confirm', () => {
    expect(voiceReducer(S.CONFIRM, E.EDIT_TEXT)).toBe(S.CONFIRM)
  })
  it.each([S.VAD_FAILED, S.MIC_DENIED, S.ASR_FAILED])('%s + RETRY → listening', (state) => {
    expect(voiceReducer(state, E.RETRY)).toBe(S.LISTENING)
  })
  it.each([S.IDLE, S.VAD_FAILED, S.MIC_DENIED, S.ASR_FAILED])('%s + SEND → idle（错误态可正常打字发送）', (state) => {
    expect(voiceReducer(state, E.SEND)).toBe(S.IDLE)
  })
  it('未知事件 → 原状态（no-op）', () => {
    expect(voiceReducer(S.IDLE, 'NOPE')).toBe(S.IDLE)
    expect(voiceReducer(S.CONFIRM, 'NOPE')).toBe(S.CONFIRM)
  })
  it('未知状态 → 原状态（no-op）', () => {
    expect(voiceReducer('ghost', E.SEND)).toBe('ghost')
  })
})
```

- [ ] **Step 2：运行确认失败**

Run: `cd frontend && npm run test:unit`
Expected: FAIL——`Failed to resolve import "../voiceState"`（文件不存在）。

- [ ] **Step 3：实现 reducer**

```js
// frontend/src/utils/voiceState.js
// 语音输入状态机纯 reducer（LD §6 转移表）。副作用（start/pause/ASR/回填）由 InputField 承担，
// 本模块只做状态流转，便于单测锁定。
export const VOICE_STATES = {
  IDLE: 'idle',
  LISTENING: 'listening',
  TRANSCRIBING: 'transcribing',
  CONFIRM: 'confirm',
  VAD_FAILED: 'vad_failed',
  MIC_DENIED: 'mic_denied',
  ASR_FAILED: 'asr_failed',
}

export const VOICE_EVENTS = {
  CLICK_MIC: 'CLICK_MIC',
  SPEECH_START: 'SPEECH_START',
  SPEECH_END: 'SPEECH_END',
  TRANSCRIPT_TEXT: 'TRANSCRIPT_TEXT',
  TRANSCRIPT_EMPTY: 'TRANSCRIPT_EMPTY',
  ASR_ERROR: 'ASR_ERROR',
  VAD_INIT_FAILED: 'VAD_INIT_FAILED',
  MIC_PERMISSION_DENIED: 'MIC_PERMISSION_DENIED',
  CANCEL: 'CANCEL',
  SEND: 'SEND',
  EDIT_TEXT: 'EDIT_TEXT',
  RETRY: 'RETRY',
}

const TRANSITIONS = {
  [VOICE_STATES.IDLE]: {
    [VOICE_EVENTS.CLICK_MIC]: VOICE_STATES.LISTENING,
    [VOICE_EVENTS.SEND]: VOICE_STATES.IDLE,
  },
  [VOICE_STATES.LISTENING]: {
    [VOICE_EVENTS.SPEECH_START]: VOICE_STATES.LISTENING,
    [VOICE_EVENTS.SPEECH_END]: VOICE_STATES.TRANSCRIBING,
    [VOICE_EVENTS.VAD_INIT_FAILED]: VOICE_STATES.VAD_FAILED,
    [VOICE_EVENTS.MIC_PERMISSION_DENIED]: VOICE_STATES.MIC_DENIED,
    [VOICE_EVENTS.CANCEL]: VOICE_STATES.IDLE,
  },
  [VOICE_STATES.TRANSCRIBING]: {
    [VOICE_EVENTS.TRANSCRIPT_TEXT]: VOICE_STATES.CONFIRM,
    [VOICE_EVENTS.TRANSCRIPT_EMPTY]: VOICE_STATES.ASR_FAILED,
    [VOICE_EVENTS.ASR_ERROR]: VOICE_STATES.ASR_FAILED,
    [VOICE_EVENTS.CANCEL]: VOICE_STATES.IDLE,
  },
  [VOICE_STATES.CONFIRM]: {
    [VOICE_EVENTS.SEND]: VOICE_STATES.IDLE,
    [VOICE_EVENTS.CLICK_MIC]: VOICE_STATES.LISTENING,
    [VOICE_EVENTS.EDIT_TEXT]: VOICE_STATES.CONFIRM,
  },
  [VOICE_STATES.VAD_FAILED]: {
    [VOICE_EVENTS.RETRY]: VOICE_STATES.LISTENING,
    [VOICE_EVENTS.SEND]: VOICE_STATES.IDLE,
  },
  [VOICE_STATES.MIC_DENIED]: {
    [VOICE_EVENTS.RETRY]: VOICE_STATES.LISTENING,
    [VOICE_EVENTS.SEND]: VOICE_STATES.IDLE,
  },
  [VOICE_STATES.ASR_FAILED]: {
    [VOICE_EVENTS.RETRY]: VOICE_STATES.LISTENING,
    [VOICE_EVENTS.SEND]: VOICE_STATES.IDLE,
  },
}

export function voiceReducer(state, event) {
  return TRANSITIONS[state]?.[event] ?? state
}
```

- [ ] **Step 4：运行确认通过**

Run: `cd frontend && npm run test:unit`
Expected: `voiceState.test.js` 全绿，总计 `28 + 17 = 45 passed`（17 = 上表用例数：13 it + it.each 展开 4 + 3 内层 → 实际按运行输出为准，全部 passed）。

- [ ] **Step 5：提交**

```bash
git add frontend/src/utils/voiceState.js frontend/src/utils/__tests__/voiceState.test.js
git commit -m "feat(chat): 语音状态机纯 reducer voiceReducer + 转移表单测（LD §6）"
```

---

## Task 2：`inputKey.js` 纯函数 + 单测（TDD）

**Files:**
- Create: `frontend/src/utils/inputKey.js`
- Test: `frontend/src/utils/__tests__/inputKey.test.js`

- [ ] **Step 1：写失败测试**

```js
// frontend/src/utils/__tests__/inputKey.test.js
import { describe, it, expect } from 'vitest'
import { shouldSendOnEnter } from '../inputKey'

describe('shouldSendOnEnter（spec §5.3 / E8 硬性）', () => {
  it('普通 Enter → true', () => {
    expect(shouldSendOnEnter({ key: 'Enter', isComposing: false, keyCode: 13, shiftKey: false })).toBe(true)
  })
  it('非 Enter 键 → false', () => {
    expect(shouldSendOnEnter({ key: 'a', isComposing: false, keyCode: 65, shiftKey: false })).toBe(false)
  })
  it('IME 组合中（isComposing）→ false', () => {
    expect(shouldSendOnEnter({ key: 'Enter', isComposing: true, keyCode: 13, shiftKey: false })).toBe(false)
  })
  it('IME 组合中（keyCode 229）→ false', () => {
    expect(shouldSendOnEnter({ key: 'Enter', isComposing: false, keyCode: 229, shiftKey: false })).toBe(false)
  })
  it('Shift+Enter（换行）→ false', () => {
    expect(shouldSendOnEnter({ key: 'Enter', isComposing: false, keyCode: 13, shiftKey: true })).toBe(false)
  })
  it('缺事件对象 → false（防御）', () => {
    expect(shouldSendOnEnter(null)).toBe(false)
  })
})
```

- [ ] **Step 2：运行确认失败**

Run: `cd frontend && npm run test:unit`
Expected: FAIL——`Failed to resolve import "../inputKey"`。

- [ ] **Step 3：实现**

```js
// frontend/src/utils/inputKey.js
// Enter 发送判定（E8 硬性：中文输入法候选状态下 Enter 一律不发送）
export function shouldSendOnEnter(e) {
  if (!e || e.key !== 'Enter') return false
  if (e.isComposing || e.keyCode === 229) return false
  if (e.shiftKey) return false
  return true
}
```

- [ ] **Step 4：运行确认通过**

Run: `cd frontend && npm run test:unit`
Expected: `inputKey.test.js` 全绿，总计 `45 + 6 = 51 passed`。

- [ ] **Step 5：提交**

```bash
git add frontend/src/utils/inputKey.js frontend/src/utils/__tests__/inputKey.test.js
git commit -m "feat(chat): shouldSendOnEnter 纯函数 + IME 单测（E8）"
```

---

## Task 3：停止生成按钮 + `rendered` 死代码清理 + inputKey 接入

**Files:**
- Modify: `frontend/src/components/character/chat_field/input_field/InputField.vue`
- Modify: `frontend/src/components/chat/chat_window/ChatWindow.vue:48-62`
- Modify: `frontend/src/components/character/chat_field/chat_history/ChatHistory.vue:62-80`

- [ ] **Step 1：InputField 接入 `shouldSendOnEnter`**

`InputField.vue` 顶部 import 增加：

```js
import { shouldSendOnEnter } from "@/utils/inputKey";
```

`handleKeydown` 替换为：

```js
// Enter 发送 / Shift+Enter 换行 / IME 组合中 Enter 不发送（E8 硬性，逻辑收口到 inputKey 纯函数）
function handleKeydown(e) {
  if (!shouldSendOnEnter(e)) return
  e.preventDefault()
  handleSend()
}
```

- [ ] **Step 2：isDone 分支删除 `rendered` 死 emit**

`InputField.vue` 中：

```js
        if (isDone) {
          // 流式结束（D-L5 修订：markdown 已边流边渲染，无需渲染触发；
          // rendered 标志已无消费方，Phase 3 状态机重构时清理）
          emits('appendToLastMessage', {rendered: true})
          setStreamState(false, false)
          return
        }
```

替换为：

```js
        if (isDone) {
          // 流式结束（D-L5：markdown 边流边渲染，无需 rendered 触发；PR #35 review 死代码已清）
          setStreamState(false, false)
          return
        }
```

- [ ] **Step 3：新增 `stopGenerate()`**

在 `stopAudio` 定义之后增加：

```js
// 停止生成（spec Phase 2 断言 6 后半 / Phase 3 断言 3）：
// abort → 后端断连路径落库（服务端保留完整输出）；前端已生成文本保留在 history，不再追加
function stopGenerate() {
  if (!abortController) return
  abortController.abort()
  abortController = null
  stopAudio()
  setStreamState(false, false)  // 随后的 onerror 幂等清理（同 processId，无副作用）
}
```

- [ ] **Step 4：发送/停止按钮改造**

`InputField.vue` 模板中现有发送按钮（`type="submit"` + SendIcon，注释「发送（48px 圆形；流式期间变 ■ 停止；空内容禁用）」）替换为：

```html
    <!-- 发送/停止（48px 圆形；流式期间变 ■ 停止；空内容或语音聆听/识别中禁用；aria-label 无障碍） -->
    <button v-if="streaming"
            type="button"
            class="w-12 h-12 shrink-0 rounded-full flex items-center justify-center text-white cursor-pointer
                   bg-[var(--accent)] focus-visible:ring-2 ring-white/40 tooltip tooltip-top"
            aria-label="停止生成"
            data-tip="停止"
            @click="stopGenerate">
      ■
    </button>
    <button v-else
            type="submit"
            class="w-12 h-12 shrink-0 rounded-full flex items-center justify-center text-white cursor-pointer
                   transition-opacity focus-visible:ring-2 ring-white/40 tooltip tooltip-top"
            :class="message.trim() ? 'bg-[var(--accent)]' : 'bg-neutral-700 opacity-50'"
            :disabled="!message.trim()"
            aria-label="发送消息"
            data-tip="发送">
      <SendIcon/>
    </button>
```

> 说明：语音状态导致的 disable（listening/transcribing）在 Task 5 接入状态机时再合并进 `:disabled`。

- [ ] **Step 5：ChatWindow 删除 `rendered` 分支**

`ChatWindow.vue` `appendToLastMessage` 中：

```js
    if (delta.rendered) {
      last.rendered = true  // D-L5：isDone 后标记，触发 markdown 渲染
    }
```

整段删除（保留 citations 分支与字符串追加分支）。

- [ ] **Step 6：ChatHistory 删除 `rendered` 字段**

`ChatHistory.vue` `loadMore` 中两处 `rendered: true,` 删除，并把注释 `// 历史消息挂载即 rendered（D-L5）；time/citations 消费 Step A 新字段` 改为 `// 历史消息挂载即渲染（D-L5 边流边渲染）；time/citations 消费 Step A 新字段`。

- [ ] **Step 7：全局校验**

Run:

```bash
cd frontend && npm run test:unit
npm run build
```

Expected: `51 passed`；`✓ built in ...s`（exit 0，仅既有 daisyUI/chunk 警告）。

- [ ] **Step 8：手工验证（断言 3 前置冒烟）**

本地起前后端（`npm run dev` + Django `:8000`），发一条消息，流式中点击 ■：
Expected: 发送键变回 ➤；最后一条 AI 消息保留已生成文本且不再增长；可立即发新消息；刷新后历史正常。

- [ ] **Step 9：提交**

```bash
git add frontend/src/components/character/chat_field/input_field/InputField.vue frontend/src/components/chat/chat_window/ChatWindow.vue frontend/src/components/character/chat_field/chat_history/ChatHistory.vue
git commit -m "feat(chat): 停止生成按钮（保留已生成文本）+ 清理 rendered 死代码（PR #35 review）+ inputKey 接入"
```

---

## Task 4：Microphone 受控化 + AnalyserNode 音量波形

**Files:**
- Modify（重写 script/template/style）: `frontend/src/components/character/chat_field/input_field/Microphone.vue`

- [ ] **Step 1：重写为受控组件（完整代码替换）**

以下为完整新文件内容（保留：VAD Cache API 缓存、PCM16 转换、ASR 请求；新增：`getStream` 注入共用流、错误映射、AnalyserNode 波形、`start/pause/destroy/retry` 暴露、`transcript/error/cancel` emits）：

```vue
<script setup lang="ts">
import KeyboardIcon from "@/components/character/icons/KeyboardIcon.vue";
import {onBeforeUnmount, ref} from "vue";
import {MicVAD} from "@ricky0123/vad-web";
import api from "@/js/http/api";
import CONFIG_API from "@/js/config/config";

// 受控组件（LD §3.9）：InputField 通过 ref 调 start/pause/destroy/retry，
// 本组件只出事件（started/speechStart/speechEnded/transcript/error/cancel），
// 状态由 InputField 的 voiceReducer 持有。
const emits = defineEmits(["started", "speechStart", "speechEnded", "transcript", "error", "cancel"])

const vadReady = ref(false)
const mode = ref<'wave' | 'transcribing'>('wave')  // 波形区视觉：音浪 / 识别中三点
const bars = ref(new Array(32).fill(8))            // 32 根柱高（px），AnalyserNode 实时驱动

let vadInstance = null
let streamRef = null          // getUserMedia 流：VAD 与 Analyser 共用（getStream 注入）
let audioContext = null
let analyser = null
let rafId = 0
let active = false            // 组件是否处于工作期（start 后 true，pause/destroy 后 false）
const preferReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches

const VAD_CACHE = 'vad-assets-v1';
const VAD_PATH = '/static/frontend/vad/';

// 缓存策略：MicVAD.new() 内部通过 fetch() 加载 WASM/ONNX 文件，
// 临时包装 window.fetch，对 /vad/ 路径的请求走 Cache API（跨页面会话持久化），
// 其他请求透传。initVAD 完成后在 finally 中恢复原始 fetch。
const makeCachedFetch = (origFetch) => {
  return async (input, init) => {
    const url = typeof input === 'string' ? input
      : input instanceof URL ? input.href
      : input.url;
    if (url && url.includes(VAD_PATH)) {
      const cache = await caches.open(VAD_CACHE);
      const match = await cache.match(url);
      if (match) return match.clone();
      const resp = await origFetch(input, init);
      if (resp.ok) cache.put(url, resp.clone());
      return resp;
    }
    return origFetch(input, init);
  };
};

const initVAD = async () => {
  const baseUrl = CONFIG_API.VAD_URL;
  const origFetch = window.fetch;
  window.fetch = makeCachedFetch(origFetch);
  try {
    // getStream 注入：VAD 复用外部 getUserMedia 的流（与 AnalyserNode 同源）
    vadInstance = await MicVAD.new({
      baseAssetPath: baseUrl,
      startOnLoad: false,
      getStream: async () => streamRef,
      onSpeechStart: () => {
        emits("speechStart")   // 说话开始 → InputField 打断 TTS（现状保留）
      },
      onSpeechEnd: (audio) => {
        mode.value = 'transcribing'
        stopWave()
        emits("speechEnded")
        const pcm16 = float32ToInt16(audio);
        sendToBackend(pcm16);
      },
      ortConfig: (ort) => {
        ort.env.wasm.wasmPaths = baseUrl;
        ort.env.logLevel = "error";
      },
      positiveSpeechThreshold: 0.8,
      negativeSpeechThreshold: 0.65,
      minSpeechFrames: 5,
      redemptionFrames: 5,
    });
    vadReady.value = true;
  } catch (e) {
    console.error("VAD 初始化失败:", e);
    emits("error", "vad_init_failed")
  } finally {
    window.fetch = origFetch;
  }
};

// 将 Float32 转 PCM 16-bit
const float32ToInt16 = (float32Array) => {
  const buffer = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i++) {
    let s = Math.max(-1, Math.min(1, float32Array[i]));
    buffer[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return buffer.buffer;
};

// ASR：成功且有文本 → transcript(text)（InputField 回填，D6）；空文本/异常 → asr_failed
const sendToBackend = async (arrayBuffer) => {
  const blob = new Blob([arrayBuffer], {type: "audio/pcm"})
  const formData = new FormData();
  formData.append("audio", blob, "voice.pcm")
  try {
    const response = await api.post("/api/friend/message/asr/asr/", formData)
    const text = (response.data?.text || '').trim()
    if (text) emits("transcript", text)
    else emits("error", "asr_failed")
  } catch (e) {
    console.log(e)
    emits("error", "asr_failed")
  }
};

// ==== AnalyserNode 实时波形（spec §5.3：替换 CSS 定时器动画；reduced-motion 柱高固定 8px）====
function setupAnalyser() {
  if (!streamRef || analyser) return
  audioContext = new AudioContext()
  analyser = audioContext.createAnalyser()
  analyser.fftSize = 128
  audioContext.createMediaStreamSource(streamRef).connect(analyser)
}

function startWave() {
  if (!analyser || rafId) return
  const data = new Uint8Array(analyser.frequencyBinCount)
  const tick = () => {
    if (!active || !analyser) return
    analyser.getByteTimeDomainData(data)
    const next = []
    for (let i = 0; i < 32; i++) {
      const v = Math.abs(data[i * 2] - 128) / 128
      next.push(preferReduced ? 8 : Math.round(4 + v * 16))   // 4~20px（spec §5.3）
    }
    bars.value = next
    rafId = requestAnimationFrame(tick)
  }
  rafId = requestAnimationFrame(tick)
}

function stopWave() {
  if (rafId) {
    cancelAnimationFrame(rafId)
    rafId = 0
  }
}

// ==== 受控 API ====
async function start() {
  active = true
  mode.value = 'wave'
  try {
    if (!streamRef) {
      streamRef = await navigator.mediaDevices.getUserMedia({audio: true})
      setupAnalyser()
    }
    if (!vadInstance) {
      await initVAD()
    }
    await vadInstance.start()
    startWave()
    emits("started")
  } catch (e) {
    // 权限被拒（NotAllowedError/SecurityError）→ mic_denied（E9）；其余 → vad_init_failed
    const denied = e && ['NotAllowedError', 'PermissionDeniedError', 'SecurityError'].includes(e.name)
    emits("error", denied ? "mic_permission_denied" : "vad_init_failed")
  }
}

async function pause() {
  active = false
  stopWave()
  if (vadInstance) {
    try { await vadInstance.pause() } catch (e) { console.error('VAD pause 失败:', e) }
  }
}

async function destroy() {
  active = false
  stopWave()
  if (vadInstance) {
    try { await vadInstance.destroy() } catch (e) { console.error('VAD destroy 失败:', e) }
    vadInstance = null
  }
  if (streamRef) {
    streamRef.getTracks().forEach(t => t.stop())
    streamRef = null
  }
  if (audioContext) {
    try { await audioContext.close() } catch (e) { console.error('AudioContext close 失败:', e) }
    audioContext = null
    analyser = null
  }
  vadReady.value = false
}

async function retry(kind) {
  // vad/权限类：全量重建（重新 getUserMedia + 重新 initVAD）；asr_failed：仅重启监听
  if (kind === 'vad_init_failed' || kind === 'mic_permission_denied') {
    await destroy()
  }
  await start()
}

onBeforeUnmount(() => {
  destroy()
})

defineExpose({start, pause, destroy, retry})
</script>

<template>
  <!-- 波形区（受控：仅渲染视觉，状态由 InputField 决定显隐）。
       h-12/rounded-xl/bg-black/35 与文字输入框一致，容器内切换无跳变 -->
  <div class="relative w-full h-12 flex items-center bg-black/35 backdrop-blur rounded-xl">
    <!--初始化中-->
    <div v-if="!vadReady" class="flex items-center justify-center gap-1.5 flex-1">
      <span class="w-1 h-1 bg-blue-400 rounded-full animate-pulse-dot"
            :style="{ animationDelay: '0s' }"></span>
      <span class="w-1 h-1 bg-blue-400 rounded-full animate-pulse-dot"
            :style="{ animationDelay: '0.2s' }"></span>
      <span class="w-1 h-1 bg-blue-400 rounded-full animate-pulse-dot"
            :style="{ animationDelay: '0.4s' }"></span>
      <span class="text-white/40 text-sm ml-2">语音初始化中...</span>
    </div>
    <!--音浪（AnalyserNode 实时音量驱动）-->
    <div v-else-if="mode === 'wave'" class="flex items-center justify-center gap-1 h-6 flex-1" aria-hidden="true">
      <div v-for="(h, i) in bars" :key="i"
           class="w-0.5 bg-blue-400 rounded-full"
           :style="{ height: h + 'px' }"></div>
    </div>
    <!--识别中（transcribing）-->
    <div v-else class="flex items-center justify-center gap-1.5 flex-1">
      <span class="w-1 h-1 bg-blue-400 rounded-full animate-pulse-dot"
            :style="{ animationDelay: '0s' }"></span>
      <span class="w-1 h-1 bg-blue-400 rounded-full animate-pulse-dot"
            :style="{ animationDelay: '0.2s' }"></span>
      <span class="w-1 h-1 bg-blue-400 rounded-full animate-pulse-dot"
            :style="{ animationDelay: '0.4s' }"></span>
      <span class="text-white/40 text-sm ml-2">识别中...</span>
    </div>
    <div @click="emits('cancel')"
         class="absolute right-2 w-8 h-8 flex justify-center items-center cursor-pointer"
         aria-label="取消语音输入">
      <KeyboardIcon/>
    </div>
  </div>
</template>

<style scoped>
.animate-pulse-dot {
  animation: pulse-dot 1.2s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 80% {
    opacity: 0.2;
    transform: scale(1);
  }
  40% {
    opacity: 1;
    transform: scale(1.8);
  }
}
</style>
```

- [ ] **Step 2：构建校验**

Run: `cd frontend && npm run build`
Expected: exit 0。注意：此阶段 Microphone 新 emits 尚无消费方（InputField 还是旧接线），构建不报错即可；Task 5 完成接线。

- [ ] **Step 3：提交**

```bash
git add frontend/src/components/character/chat_field/input_field/Microphone.vue
git commit -m "refactor(chat): Microphone 受控化（start/pause/destroy/retry + 错误映射 + AnalyserNode 波形）"
```

---

## Task 5：InputField 语音状态机接入（核心）

**Files:**
- Modify: `frontend/src/components/character/chat_field/input_field/InputField.vue`

- [ ] **Step 1：script 头部接线**

`InputField.vue` import 增加（同时把 vue import 补上 `computed`：`import {computed, nextTick, onUnmounted, ref, useTemplateRef, watch} from "vue"`）：

```js
import { voiceReducer, VOICE_STATES, VOICE_EVENTS } from "@/utils/voiceState";
```

删除 `const showMic = ref(false)`；新增：

```js
// ===== 语音状态机（LD §6）：状态由 InputField 持有，Microphone 只出事件 =====
const micRef = useTemplateRef('mic-ref')
const micState = ref(VOICE_STATES.IDLE)
const micErrorKind = ref('')   // 错误态类型：vad_init_failed / mic_permission_denied / asr_failed

const ERROR_COPY = {
  vad_init_failed: '语音初始化失败，请重试',
  mic_permission_denied: '请允许使用麦克风后重试',
  asr_failed: '未听清，请重试',
}

const isTextMode = computed(() =>
  [VOICE_STATES.IDLE, VOICE_STATES.CONFIRM, VOICE_STATES.VAD_FAILED,
   VOICE_STATES.MIC_DENIED, VOICE_STATES.ASR_FAILED].includes(micState.value))

function transition(event) {
  micState.value = voiceReducer(micState.value, event)
}

function cancelMic() {
  transition(VOICE_EVENTS.CANCEL)
  micRef.value?.pause()
}

function retryMic(kind) {
  micErrorKind.value = ''
  transition(VOICE_EVENTS.RETRY)
  micRef.value?.retry(kind)
}

// 🎤 按钮：idle → 开麦；confirm → 覆盖重录（清空回填文本）；listening → 取消；
// transcribing → 禁用（E6 防并发 ASR）；错误态 → 重试
function handleMicClick() {
  if (micState.value === VOICE_STATES.IDLE) {
    micErrorKind.value = ''
    transition(VOICE_EVENTS.CLICK_MIC)
    micRef.value?.start()
  } else if (micState.value === VOICE_STATES.CONFIRM) {
    message.value = ''                        // 覆盖重录：清空回填文本（LD §6）
    micErrorKind.value = ''
    transition(VOICE_EVENTS.CLICK_MIC)
    micRef.value?.start()
  } else if (micState.value === VOICE_STATES.LISTENING) {
    cancelMic()
  } else if ([VOICE_STATES.VAD_FAILED, VOICE_STATES.MIC_DENIED, VOICE_STATES.ASR_FAILED]
             .includes(micState.value)) {
    retryMic(micErrorKind.value || micState.value)
  }
  // transcribing：no-op（E6）
}

// Microphone 事件 → 状态机
function onMicSpeechStart() {
  // 现状保留（旧 handleStop 语义）：说话开始打断 TTS + 冻结当前流 UI 更新
  ++processId
  stopAudio()
  setStreamState(false, false)
  transition(VOICE_EVENTS.SPEECH_START)
}

function onMicSpeechEnded() {
  transition(VOICE_EVENTS.SPEECH_END)
}

function onMicTranscript(text) {
  // 已取消（CANCEL 后 in-flight ASR 迟到）：丢弃结果（LD §6「忽略结果」，范围拍板 #7）
  if (micState.value !== VOICE_STATES.TRANSCRIBING) return
  message.value = text       // 回填 textarea（D6：不再识别即发送；watch(message) 自动 autoGrow）
  transition(VOICE_EVENTS.TRANSCRIPT_TEXT)
}

function onMicError(kind) {
  // 迟到错误同样丢弃：asr_failed 只在 transcribing 有效，vad/mic 错误只在 listening 有效
  const expectState = kind === 'asr_failed' ? VOICE_STATES.TRANSCRIBING : VOICE_STATES.LISTENING
  if (micState.value !== expectState) return
  micErrorKind.value = kind
  const eventMap = {
    vad_init_failed: VOICE_EVENTS.VAD_INIT_FAILED,
    mic_permission_denied: VOICE_EVENTS.MIC_PERMISSION_DENIED,
    asr_failed: VOICE_EVENTS.ASR_ERROR,
  }
  transition(eventMap[kind] || VOICE_EVENTS.ASR_ERROR)
}

// Esc：listening / transcribing 均可取消（LD §6 两行 CANCEL；E6 仅禁 🎤 不禁 Esc）
function onGlobalKeydown(e) {
  if (e.key === 'Escape' &&
      [VOICE_STATES.LISTENING, VOICE_STATES.TRANSCRIBING].includes(micState.value)) {
    cancelMic()
  }
}
watch(micState, (s) => {
  if ([VOICE_STATES.LISTENING, VOICE_STATES.TRANSCRIBING].includes(s)) {
    window.addEventListener('keydown', onGlobalKeydown)
  } else {
    window.removeEventListener('keydown', onGlobalKeydown)
  }
})
```

`onUnmounted` 增加一行（保留现有逻辑）：

```js
  window.removeEventListener('keydown', onGlobalKeydown)
```

- [ ] **Step 2：发送路径并入状态机**

`handleSend` 开头（`if (!content) return` 之后）增加：

```js
  // 发送即回 idle（confirm→idle；错误态/常态不变语义）；同步 pause 语音
  micState.value = voiceReducer(micState.value, VOICE_EVENTS.SEND)
  micRef.value?.pause()
```

`handleKeydown` 内 send 前无需变化；textarea `@input` 增加 confirm 编辑事件：

```html
      <textarea class="flex-1 min-w-0 resize-none bg-black/35 backdrop-blur text-base text-white rounded-xl
                      px-3 py-2.5 leading-6 outline-none"
              placeholder="文本输入"
              aria-label="消息输入"
              ref="input-ref" v-model="message"
              rows="1"
              style="height: 48px; overflow: hidden;"
              @input="transition(VOICE_EVENTS.EDIT_TEXT)"
              @keydown="handleKeydown"></textarea>
```

> 说明：`EDIT_TEXT` 仅在 confirm 态有效（reducer 表），其他态 no-op，无需条件判断。

- [ ] **Step 3：删除旧语音接线**

删除以下整段（被状态机取代）：

```js
function closeMic() {
  ++processId
  showMic.value = false
  stopAudio()
}

function handleStop() {
  ++processId
  stopAudio()
  setStreamState(false, false)
}
```

`defineExpose` 更新为：

```js
defineExpose({focus, closeMic: cancelMic, handleSend})
```

（`closeMic` 名保留以兼容 ChatWindow/ChatIndex 潜在调用，语义 = 取消语音。）

- [ ] **Step 4：模板重构（输入栏三区域）**

将现有 `<form v-show="!showMic" ...>` 整块（含麦克风按钮、textarea、发送按钮）与 `<div v-if="showMic">`（KeepAlive + Microphone）**整体替换**为：

```html
<template>
  <form @submit.prevent="handleSend"
        class="shrink-0 px-2 pb-3 pt-1 flex gap-2 items-end">
    <!-- 麦克风入口（48px 圆形；listening/transcribing 高亮 accent，transcribing 禁用防并发 ASR） -->
    <button type="button"
            class="w-12 h-12 shrink-0 rounded-full flex items-center justify-center text-white cursor-pointer
                   hover:bg-black/20 transition-colors focus-visible:ring-2 ring-white/40
                   tooltip tooltip-top"
            :class="[VOICE_STATES.LISTENING, VOICE_STATES.TRANSCRIBING].includes(micState) ? 'bg-[var(--accent)]' : ''"
            :disabled="micState === VOICE_STATES.TRANSCRIBING"
            :aria-label="micState === VOICE_STATES.LISTENING || micState === VOICE_STATES.TRANSCRIBING ? '取消语音输入' : '语音输入'"
            :data-tip="micState === VOICE_STATES.LISTENING || micState === VOICE_STATES.TRANSCRIBING ? '取消' : '语音输入'"
            @click="handleMicClick">
      <MicIcon/>
    </button>

    <!-- 文字输入（idle/confirm/错误态显示；listening/transcribing 隐藏换波形区） -->
    <!-- textarea 自动增高：1 → 4 行，超过内部滚动；Enter 发送 / Shift+Enter 换行 / IME 组合中不发送 -->
    <textarea v-show="isTextMode"
              class="flex-1 min-w-0 resize-none bg-black/35 backdrop-blur text-base text-white rounded-xl
                      px-3 py-2.5 leading-6 outline-none"
              placeholder="文本输入"
              aria-label="消息输入"
              ref="input-ref" v-model="message"
              rows="1"
              style="height: 48px; overflow: hidden;"
              @input="transition(VOICE_EVENTS.EDIT_TEXT)"
              @keydown="handleKeydown"></textarea>

    <!-- 波形区（常驻挂载，v-show 切换——VAD 实例随 InputField 生命周期，KeepAlive 已移除） -->
    <div v-show="!isTextMode" class="flex-1 min-w-0">
      <Microphone ref="mic-ref"
                  @started="() => {}"
                  @speechStart="onMicSpeechStart"
                  @speechEnded="onMicSpeechEnded"
                  @transcript="onMicTranscript"
                  @error="onMicError"
                  @cancel="cancelMic" />
    </div>

    <!-- 发送/停止（48px 圆形；流式期间变 ■ 停止；空内容或语音聆听/识别中禁用） -->
    <button v-if="streaming"
            type="button"
            class="w-12 h-12 shrink-0 rounded-full flex items-center justify-center text-white cursor-pointer
                   bg-[var(--accent)] focus-visible:ring-2 ring-white/40 tooltip tooltip-top"
            aria-label="停止生成"
            data-tip="停止"
            @click="stopGenerate">
      ■
    </button>
    <button v-else
            type="submit"
            class="w-12 h-12 shrink-0 rounded-full flex items-center justify-center text-white cursor-pointer
                   transition-opacity focus-visible:ring-2 ring-white/40 tooltip tooltip-top"
            :class="message.trim() ? 'bg-[var(--accent)]' : 'bg-neutral-700 opacity-50'"
            :disabled="!message.trim() || micState === VOICE_STATES.LISTENING || micState === VOICE_STATES.TRANSCRIBING"
            aria-label="发送消息"
            data-tip="发送">
      <SendIcon/>
    </button>
  </form>

  <!-- 错误态内联提示（spec §9：红字 + 重试；不卡死、textarea 仍可用） -->
  <div v-if="micErrorKind && isTextMode" class="shrink-0 px-4 pb-2 flex items-center gap-3">
    <p class="text-red-300 text-xs flex-1">{{ ERROR_COPY[micErrorKind] }}</p>
    <button type="button" class="btn btn-xs btn-neutral shrink-0" @click="retryMic(micErrorKind)">
      重试
    </button>
  </div>
</template>
```

同步删除模板内旧的「<!-- 输入框 -->\n<!-- 输入框（textarea 自动增高...）」重复注释行（合并为一条）。

- [ ] **Step 5：script 头部残留清理**

删除旧 `showMic` 相关引用（Step 1 已删 ref；确认模板中无 `showMic` 残留、`<KeepAlive>` 已随 Step 4 移除）；确认 `computed` 已加入 vue import（Step 1 已含）。

- [ ] **Step 6：构建 + 单测**

Run:

```bash
cd frontend && npm run test:unit
npm run build
```

Expected: `51 passed`（voiceState/inputKey 不受影响）；build exit 0。

- [ ] **Step 7：提交**

```bash
git add frontend/src/components/character/chat_field/input_field/InputField.vue
git commit -m "feat(chat): 语音状态机接入 InputField（聆听/识别/回填确认/错误重试/Esc 取消/覆盖重录）"
```

---

## Task 6：全局验证 + 手工验收清单 + 部署

**Files:**
- 无（后端零改动）

- [ ] **Step 1：全量单测 + 构建**

Run:

```bash
cd frontend && npm run test:unit
npm run build
```

Expected: `51 passed`；build exit 0。

- [ ] **Step 2：手工验收清单（对照 spec §13 Phase 3 断言 1~6 + Phase 2 断言 6 后半）**

本地前后端联调（`npm run dev` + Django `:8000`）：

| # | 验收项 | 预期 |
|---|--------|------|
| 1 | 断言 1：输入 200 字 | 无横向滚动条；超 4 行内部滚动（Phase 2 已实现，回归即可） |
| 2 | 断言 2：中文输入法候选状态按 Enter | 不发送（Phase 2 已实现，回归即可） |
| 3 | **断言 3 + Phase 2 断言 6 后半：流式中点 ■** | 已生成文本保留、流不再追加；按钮变回 ➤；可立即发送；TTS 停止 |
| 4 | 断言 4：🎤 说一句话 | 波形随音量起伏（静音≈4px、大声≈20px）；识别后文本**回填** textarea 可编辑，默认不自动发送；Enter/➤ 发送 |
| 5 | 断言 5：浏览器拒绝麦克风权限 | 内联"请允许使用麦克风后重试" + 重试按钮，不再卡"语音初始化中..."；允许权限后点重试 → 正常聆听 |
| 6 | 断言 6：说话太短/杂音导致 ASR 空文本 | 内联"未听清，请重试" |
| 7 | E6：识别中（transcribing）点 🎤 | 无效（禁用）；Esc 取消回 idle |
| 8 | 覆盖重录：confirm 态再点 🎤 | 回填文本被清空，重新进入聆听 |
| 9 | Esc 取消聆听 | 回 idle，音频丢弃，无发送 |
| 10 | 说话开始打断 TTS（现状保留） | AI 语音停止；流 UI 冻结；可发新消息 |
| 11 | reduced-motion | 系统开启"减弱动态效果"时柱高恒定 8px |
| 12 | 会话切换/关闭窗口 | 无控制台报错；麦克风指示消失；VAD 资源释放 |

- [ ] **Step 3：部署云服务器（验收用）**

按既有 registry 流程（后端零改动，仅前端进镜像）：

```bash
ACR_IMAGE=crpi-2ltqkeifvac3nlun.cn-shanghai.personal.cr.aliyuncs.com/gqyin-sh/gqyin-docker:latest ./deploy/build.sh
# 服务器（8.153.201.12）：cd /home/gqyin/source-code/ai-friends && ./deploy/server-deploy.sh
```

Expected: 健康检查 `{"status":"ok","db":"ok","redis":"ok","celery":"ok"}`；云上复验手工清单 3~11。

- [ ] **Step 4：提交（如有验收后修复则另开 fix commit）**

```bash
git add -A docs/superpowers/plans/
git commit -m "docs(chat): Phase 3 验收完成记录"
```

（仅当验收过程对计划/文档有修正时执行；无修正则跳过。）

---

## 风险与回滚

- **语音链路无自动化测试**（LD §9.3：真实麦克风权限流归手工）——Task 6 手工清单是合入门槛；若后续回归频繁，再评估引入 `@vue/test-utils` 对 Microphone 做 mock 级组件测试（非本期）。
- **`getStream` 注入与 vad-web 0.0.30 的兼容性**：已核实 `MicVAD.new(options: Partial<RealTimeVADOptions>)` 支持 `getStream`（`dist/real-time-vad.d.ts:33`）；若实机发现异常，回退方案 = 不自建 getUserMedia（恢复 vad-web 内部申请），波形改为 `onFrameProcessed` 概率驱动（近似音量），代价小。
- **停止生成的 abort 语义**：前端 abort → 后端断连路径落库（`work()` C2，已含 try/except 防护，PR #35 修复）——停止后服务端仍保留完整输出，前端仅显示已生成部分（与断言 3 一致）。
- 回滚 = revert Task 3~5 三个 commit；Phase 1/2 功能不受影响（改动仅限 InputField/Microphone/ChatWindow/ChatHistory 四文件）。
