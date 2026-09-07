<script setup lang="ts">

import MicIcon from "@/components/character/icons/MicIcon.vue";
import SendIcon from "@/components/character/icons/SendIcon.vue";
import streamApi from "@/js/http/streamApi";
import {nextTick, onUnmounted, ref, useTemplateRef, watch} from "vue";
import Microphone from "@/components/character/chat_field/input_field/Microphone.vue";
import {useVoiceToggle} from "@/composables/useVoiceToggle.js";

const props = defineProps(['friendId'])
const emits = defineEmits(['pushBackMessage', 'appendToLastMessage', 'error', 'streamState'])

const inputRef = useTemplateRef('input-ref')
const message = ref('')
let processId = 0

const showMic = ref(false)

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
  }

  if (audioPlayer.src) {
    URL.revokeObjectURL(audioPlayer.src);
    audioPlayer.src = '';
  }
};

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

// Enter 发送 / Shift+Enter 换行 / IME 组合中 Enter 不发送（E8 硬性）
function handleKeydown(e) {
  if (e.key !== 'Enter') return
  if (e.isComposing || e.keyCode === 229) return
  if (e.shiftKey) return
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
        // 错误消息统一由 catch 块展示，此处只做清理
        stopAudio()
        setStreamState(false, false)
      },
    })
  } catch (e) {
    console.log(e)
    if (processId === curId) {
      emits('appendToLastMessage', e.message || '发送失败')
    }
    stopAudio()
    setStreamState(false, false)
  }
}

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

defineExpose({focus, closeMic, handleSend})
</script>

<template>
  <form v-show="!showMic" @submit.prevent="handleSend"
        class="shrink-0 px-2 pb-3 pt-1 flex gap-2 items-end">
    <!-- 麦克风入口（48px 圆形，与输入框同高 → 单行恒居中、多行恒贴底且零位移；Phase 3 重构为输入栏内状态切换） -->
    <button type="button"
            class="w-12 h-12 shrink-0 rounded-full flex items-center justify-center text-white cursor-pointer
                   hover:bg-black/20 transition-colors focus-visible:ring-2 ring-white/40
                   tooltip tooltip-top"
            aria-label="语音输入"
            data-tip="语音输入"
            @click="showMic = true">
      <MicIcon/>
    </button>

    <!-- 输入框 -->
    <!-- 输入框（textarea 自动增高：1 → 4 行，超过内部滚动；Enter 发送 / Shift+Enter 换行 / IME 组合中不发送 -->
    <textarea class="flex-1 min-w-0 resize-none bg-black/35 backdrop-blur text-base text-white rounded-xl
                      px-3 py-2.5 leading-6 outline-none"
              placeholder="文本输入"
              aria-label="消息输入"
              ref="input-ref" v-model="message"
              rows="1"
              style="height: 48px; overflow: hidden;"
              @keydown="handleKeydown"></textarea>

    <!-- 发送（48px 圆形；流式期间变 ■ 停止；空内容禁用） -->
    <button type="submit"
            class="w-12 h-12 shrink-0 rounded-full flex items-center justify-center text-white cursor-pointer
                   transition-opacity focus-visible:ring-2 ring-white/40 tooltip tooltip-top"
            :class="message.trim() ? 'bg-[var(--accent)]' : 'bg-neutral-700 opacity-50'"
            :disabled="!message.trim()"
            aria-label="发送消息"
            data-tip="发送"
            @click="handleSend">
      <SendIcon/>
    </button>
  </form>

  <!--麦克风组件（KeepAlive 保持存活，避免重复加载 WASM；Phase 3 重构为受控组件）-->
  <div v-if="showMic" class="shrink-0 px-2 pb-3 pt-1">
    <KeepAlive>
      <Microphone
          @close="showMic=false"
          @send="handleSend"
          @stop="handleStop"
      />
    </KeepAlive>
  </div>
</template>

<style scoped>

</style>