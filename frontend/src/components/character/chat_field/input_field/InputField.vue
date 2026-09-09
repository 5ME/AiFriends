<script setup lang="ts">

import MicIcon from "@/components/character/icons/MicIcon.vue";
import SendIcon from "@/components/character/icons/SendIcon.vue";
import StopIcon from "@/components/character/icons/StopIcon.vue";
import streamApi from "@/js/http/streamApi";
import {computed, nextTick, onUnmounted, ref, useTemplateRef, watch} from "vue";
import Microphone from "@/components/character/chat_field/input_field/Microphone.vue";
import {useVoiceToggle} from "@/composables/useVoiceToggle.js";
import {shouldSendOnEnter} from "@/utils/inputKey";
import { voiceReducer, VOICE_STATES, VOICE_EVENTS, acceptTranscript, acceptMicError } from "@/utils/voiceState";

const props = defineProps(['friendId'])
const emits = defineEmits(['pushBackMessage', 'appendToLastMessage', 'streamState'])

const inputRef = useTemplateRef('input-ref')
const message = ref('')
let processId = 0

let abortController = null  // SSE 客户端断连控制器

let mediaSource = null;
let sourceBuffer = null;
let audioPlayer = new Audio(); // 全局播放器实例
let audioQueue = [];           // 待写入 Buffer 的二进制队列
let isUpdating = false;        // Buffer 是否正在写入

const { voiceEnabled } = useVoiceToggle()

// 流式状态（thinking：发送后首 content 前；streaming：content 到达后）
const thinking = ref(false)
const streaming = ref(false)

// ===== 语音状态机（LD §6）：状态由 InputField 持有，Microphone 只出事件 =====
const micRef = useTemplateRef('mic-ref')
const micState = ref(VOICE_STATES.IDLE)
const micErrorKind = ref('')   // 错误态类型：vad_init_failed / mic_permission_denied / asr_failed
let micSeqCounter = 0          // 会话令牌计数：每次 start/retry 递增
const activeMicSeq = ref(0)    // 当前会话令牌：transcript/error 迟到结果按 seq 丢弃

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
  // 复审修复：仅错误态可重试（否则 micRef.retry→start 会启动无 UI 指示的录音）
  if (![VOICE_STATES.VAD_FAILED, VOICE_STATES.MIC_DENIED, VOICE_STATES.ASR_FAILED].includes(micState.value)) return
  const KINDS = { [VOICE_STATES.VAD_FAILED]: 'vad_init_failed', [VOICE_STATES.MIC_DENIED]: 'mic_permission_denied' }   // 统一 kind 字符串族（vad/mic 对称）
  const k = KINDS[kind] || kind
  const seq = ++micSeqCounter
  activeMicSeq.value = seq
  micErrorKind.value = ''
  transition(VOICE_EVENTS.RETRY)
  micRef.value?.retry(k, seq)
}

// 打断 TTS + 冻结当前流 UI 更新（原 handleStop 语义，抽取共用）。触发时机两处：
// ① 点击 🎤 进入聆听时（用户拍板 2026-09-09：按下即静音 AI，免 VAD 检测延迟窗口）；
// ② 说话开始（LD §6 现状保留，兜底迟到帧）
function interruptTts() {
  ++processId
  stopAudio()
  setStreamState(false, false)
}

// 🎤 按钮：idle → 开麦；confirm → 覆盖重录（清空回填文本）；listening → 取消；
// transcribing → 禁用（E6 防并发 ASR）；错误态 → 重试
function handleMicClick() {
  if (micState.value === VOICE_STATES.IDLE) {
    micErrorKind.value = ''
    // 用户拍板：点击 🎤 即打断——AI 播报/流式期间进入聆听立即停 TTS + 冻结文字流
    if (thinking.value || streaming.value) {
      interruptTts()
    }
    const seq = ++micSeqCounter
    activeMicSeq.value = seq
    transition(VOICE_EVENTS.CLICK_MIC)
    micRef.value?.start(seq)
  } else if (micState.value === VOICE_STATES.CONFIRM) {
    message.value = ''                        // 覆盖重录：清空回填文本（LD §6）
    micErrorKind.value = ''
    const seq = ++micSeqCounter
    activeMicSeq.value = seq
    transition(VOICE_EVENTS.CLICK_MIC)
    micRef.value?.start(seq)
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
  // 说话开始打断 TTS（LD §6 现状保留；点击进入聆听时已打断则此处幂等）
  interruptTts()
  transition(VOICE_EVENTS.SPEECH_START)
}

function onMicSpeechEnded() {
  transition(VOICE_EVENTS.SPEECH_END)
}

function onMicTranscript(text, seq) {
  // 迟到结果（CANCEL 后 in-flight ASR）或旧会话结果丢弃：状态 + seq 令牌双守卫（LD §6「忽略结果」）
  if (!acceptTranscript(micState.value, seq, activeMicSeq.value)) return
  message.value = text       // 回填 textarea（D6：不再识别即发送；watch(message) 自动 autoGrow）
  transition(VOICE_EVENTS.TRANSCRIPT_TEXT)
}

function onMicError(kind, seq) {
  // 迟到错误同样丢弃：asr_failed 只在 transcribing 有效，vad/mic 错误只在 listening 有效
  if (!acceptMicError(micState.value, kind, seq, activeMicSeq.value)) return
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

function setStreamState(thk, strm) {
  if (thinking.value !== thk || streaming.value !== strm) {
    thinking.value = thk
    streaming.value = strm
    emits('streamState', { thinking: thk, streaming: strm })
  }
}

const initAudioStream = () => {
  if (!voiceEnabled.value) return  // 语音关闭时不建立 MediaSource
  audioPlayer.pause();
  audioQueue = [];
  isUpdating = false;

  mediaSource = new MediaSource();
  audioPlayer.src = URL.createObjectURL(mediaSource);

  mediaSource.addEventListener('sourceopen', () => {
    try {
      sourceBuffer = mediaSource.addSourceBuffer('audio/mpeg');
      sourceBuffer.addEventListener('updateend', () => {
        isUpdating = false;
        processQueue();
      });
    } catch (e) {
      console.error("MSE AddSourceBuffer Error:", e);
    }
  });

  audioPlayer.play().catch(e => console.error("等待用户交互以播放音频"));
};

const processQueue = () => {
  if (isUpdating || audioQueue.length === 0 || !sourceBuffer || sourceBuffer.updating) {
    return;
  }

  isUpdating = true;
  const chunk = audioQueue.shift();
  try {
    sourceBuffer.appendBuffer(chunk);
  } catch (e) {
    console.error("SourceBuffer Append Error:", e);
    isUpdating = false;
  }
};

const stopAudio = () => {
  audioPlayer.pause();
  audioQueue = [];
  isUpdating = false;

  if (mediaSource) {
    if (mediaSource.readyState === 'open') {
      try {
        mediaSource.endOfStream();
      } catch (e) {
      }
    }
    mediaSource = null;
    sourceBuffer = null
  }

  if (audioPlayer.src) {
    URL.revokeObjectURL(audioPlayer.src);
    audioPlayer.src = '';
  }
};

// 停止生成（spec Phase 2 断言 6 后半 / Phase 3 断言 3）：
// fetch-event-source 2.0.1 外部 signal abort → 静默 resolve，不触发 onerror（fetch.js:43-46 已核实）；
// 后端断连路径落库（服务端保留完整输出）；前端已生成文本保留在 history，不再追加
function stopGenerate() {
  if (!abortController) return
  abortController.abort()
  abortController = null
  stopAudio()
  setStreamState(false, false)
}

const handleAudioChunk = (base64Data) => {  // 将语音片段添加到播放器队列中
  if (!voiceEnabled.value) return       // 语音关闭时不消费音频数据
  try {
    const binaryString = atob(base64Data);
    const len = binaryString.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }

    audioQueue.push(bytes);
    processQueue();
  } catch (e) {
    console.error("Base64 Decode Error:", e);
  }
};

onUnmounted(() => {
  if (abortController) {
    abortController.abort()  // 通知后端客户端已断开，停止 TTS
    abortController = null
  }
  audioPlayer.pause();
  audioPlayer.src = '';
  window.removeEventListener('keydown', onGlobalKeydown)
});

function focus() {
  inputRef.value.focus()
}

// ===== textarea 自动增高（LD §3.8：1 → 4 行，超过内部滚动） =====
const MAX_INPUT_HEIGHT = 116  // 4 行 × 24px(leading-6) + 上下 padding 20px

function autoGrow() {
  const el = inputRef.value
  if (!el) return
  el.style.height = 'auto'
  const h = Math.max(48, Math.min(el.scrollHeight, MAX_INPUT_HEIGHT))
  el.style.height = h + 'px'
  el.style.overflowY = el.scrollHeight > MAX_INPUT_HEIGHT ? 'auto' : 'hidden'
}

// 输入变化（含发送后清空）→ 下一帧重算高度
watch(message, () => nextTick(autoGrow))

// Enter 发送 / Shift+Enter 换行 / IME 组合中 Enter 不发送（E8 硬性，逻辑收口到 inputKey 纯函数）
function handleKeydown(e) {
  if (!shouldSendOnEnter(e)) return
  // 流式中 Enter 仍可打断发送（现状保留：processId 守卫即为此设计）
  e.preventDefault()
  handleSend()
}

async function handleSend(eventOrMsg?: Event | string, audioMsg?: string) {
  let content = ""

  // 逻辑优化：判断第一个参数是字符串（语音消息）还是事件对象
  if (typeof eventOrMsg === 'string') {
    content = eventOrMsg.trim()
  } else if (typeof audioMsg === 'string') {
    content = audioMsg.trim()
  } else {
    content = message.value.trim()
  }

  if (!content) {
    return
  }

  // 发送即回 idle（confirm→idle；错误态/常态语义不变）；同步暂停语音
  transition(VOICE_EVENTS.SEND)
  micErrorKind.value = ''   // 发送即清错误横幅（复审：SEND 后不残留错误提示）
  micRef.value?.pause()

  initAudioStream()

  const curId = ++processId
  message.value = ''

  emits('pushBackMessage', {
    role: 'user',
    content: content,
    id: crypto.randomUUID()
  })
  emits('pushBackMessage', {
    role: 'ai',
    content: '',
    id: crypto.randomUUID()
  })

  if (abortController) {
    abortController.abort()  // 中断上一个未完成的 SSE 流，避免服务端空跑
  }
  abortController = new AbortController()
  setStreamState(true, false)  // thinking：等待首个 token
  try {
    await streamApi('/api/friend/message/chat/', {
      signal: abortController.signal,  // 组件卸载时 abort → 断连检测
      body: {
        friend_id: props.friendId,
        message: content
      },
      onmessage(data, isDone) {
        if (processId !== curId) {
          // 实现输出打断
          return
        }
        if (isDone) {
          // 流式结束（D-L5：markdown 边流边渲染，无需 rendered 触发；PR #35 review 死代码已清）
          setStreamState(false, false)
          return
        }
        // citations 在 content 之前到达（后端保证时序），先挂载到消息上
        if (data.citations) {
          emits('appendToLastMessage', {citations: data.citations})
        }
        if (data.error) {
          emits('appendToLastMessage', data.error)
          stopAudio()
          setStreamState(false, false)
        }
        if (data.content) {
          if (streaming.value === false) {
            setStreamState(false, true)  // 首 token：thinking → streaming
          }
          emits('appendToLastMessage', data.content)
        }
        if (data.audio) {
          handleAudioChunk(data.audio)
        }
      },
      onerror(err) {
        console.log(err)
        if (processId !== curId) return   // 被新发送打断的旧流错误：不得清理新流状态（PR review 硬性 #2）
        // 错误消息统一由 catch 块展示，此处只做清理
        stopAudio()
        setStreamState(false, false)
      },
    })
  } catch (e) {
    console.log(e)
    if (processId !== curId) return   // 被新发送打断的旧流错误：不得清理新流状态（PR review 硬性 #2）
    emits('appendToLastMessage', e.message || '发送失败')
    stopAudio()
    setStreamState(false, false)
  }
}

defineExpose({focus, handleSend})
</script>

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
                  @speechStart="onMicSpeechStart"
                  @speechEnded="onMicSpeechEnded"
                  @transcript="onMicTranscript"
                  @error="onMicError"
                  @cancel="cancelMic" />
    </div>

    <!-- 发送/停止（48px 圆形；流式期间变 StopIcon 停止；空内容或语音聆听/识别中禁用） -->
    <button v-if="streaming"
            type="button"
            class="w-12 h-12 shrink-0 rounded-full flex items-center justify-center text-white cursor-pointer
                   bg-[var(--accent)] focus-visible:ring-2 ring-white/40 tooltip tooltip-top"
            aria-label="停止生成"
            data-tip="停止"
            @click="stopGenerate">
      <StopIcon class="w-4 h-4"/>
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
    <p class="text-red-300 text-xs flex-1"
       :title="micErrorKind === 'mic_permission_denied' ? '请允许使用麦克风' : ERROR_COPY[micErrorKind]">
      {{ ERROR_COPY[micErrorKind] }}
    </p>
    <button type="button" class="btn btn-xs btn-neutral shrink-0" @click="retryMic(micErrorKind)">
      重试
    </button>
  </div>
</template>

<style scoped>

</style>