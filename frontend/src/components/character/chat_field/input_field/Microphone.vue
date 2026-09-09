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
let streamRef = null          // getUserMedia 流：VAD 与 Analyser 共用（三覆盖保证不脱钩）
let audioContext = null
let analyser = null
let rafId = 0
let active = false            // 工作期标志：start 后 true；P1 竞态守卫依赖它
// 会话令牌：start() 递增来源在 InputField；ASR 迟到结果按 seq 丢弃（跨会话竞态修复）
let currentSeq = 0
const preferReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches

// 与 vad-web 默认 getUserMedia 约束一致（channelCount:1 + 回声消除/降噪/自动增益），
// 避免 VAD 误触发与音质回归
const AUDIO_CONSTRAINTS = {
  audio: {
    channelCount: 1,
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  }
}

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
    vadInstance = await MicVAD.new({
      baseAssetPath: baseUrl,
      startOnLoad: false,
      // 评审 P0：库默认 pauseStream 会 stop() 全部 track、默认 resumeStream 会自建新流——
      // 显式覆盖为空操作 + 返回自持流；track 生命周期完全归 pause()/destroy()，
      // 保证 VAD 与 Analyser 始终共用同一条流
      getStream: async () => streamRef,
      pauseStream: async () => {},
      resumeStream: async () => streamRef,
      onSpeechStart: () => {
        if (!active) return   // 暂停/销毁后的迟到帧不 emit speechStart（跨会话竞态守卫）
        emits("speechStart")   // 说话开始 → InputField 打断 TTS（现状保留）
      },
      onSpeechEnd: (audio) => {
        // 评审 P2-3（E6 网络层）：speechEnd 即暂停采集——PCM 已捕获、ASR 不依赖活动流，
        // transcribing 期间不会再触发第二个 speechEnd/ASR；录音指示随之熄灭
        const seq = currentSeq   // 捕获会话令牌：ASR 迟到结果在 InputField 按 seq 丢弃
        mode.value = 'transcribing'
        pause()
        emits("speechEnded")
        sendToBackend(float32ToInt16(audio), seq);
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
    // 注（v2 复审 P3-2）：失败后 start() 因 vadInstance 为 null 会再抛 TypeError → 双重 error emit；
    // InputField 状态守卫丢弃第二次，无害；第二次进入 start() 的 catch 并执行 teardown 兜底
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

// ASR：成功且有文本 → transcript(text, seq)（InputField 回填，D6）；空文本/异常 → asr_failed(seq)
const sendToBackend = async (arrayBuffer, seq) => {
  const blob = new Blob([arrayBuffer], {type: "audio/pcm"})
  const formData = new FormData();
  formData.append("audio", blob, "voice.pcm")
  try {
    const response = await api.post("/api/friend/message/asr/asr/", formData)
    const text = (response.data?.text || '').trim()
    // 空文本折叠为 asr_failed（LD §6 的 TRANSCRIPT('') 行保留在 reducer，组件侧统一走 error 事件）
    if (text) emits("transcript", text, seq)
    else emits("error", "asr_failed", seq)
  } catch (e) {
    console.log(e)
    emits("error", "asr_failed", seq)
  }
};

// ==== AnalyserNode 实时波形（spec §5.3；reduced-motion 柱高固定 8px）====
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

// 停流 + 清引用 + 关 analyser（P0 配套：track 生命周期唯一归属点）
function teardownStream() {
  stopWave()
  if (streamRef) {
    streamRef.getTracks().forEach(t => t.stop())
    streamRef = null
  }
  if (audioContext) {
    audioContext.close().catch(() => {})
    audioContext = null
    analyser = null
  }
}

// ==== 受控 API ====
async function start(seq = 0) {
  currentSeq = seq
  active = true
  mode.value = 'wave'
  try {
    // 每次录音重新申请流（P0：暂停即停流；已授权 origin 不重复弹权限框）；ended-track 检测为防御性兜底
    if (!streamRef || streamRef.getTracks().every(t => t.readyState === 'ended')) {
      streamRef = await navigator.mediaDevices.getUserMedia(AUDIO_CONSTRAINTS)
      setupAnalyser()
    }
    if (!active) { teardownStream(); return }   // P1：getUserMedia 期间被取消 → 停掉刚建的流
    if (!vadInstance) {
      await initVAD()
    }
    if (!active) { teardownStream(); return }   // P1：initVAD（WASM 下载）期间被取消
    await vadInstance.start()
    if (!active) { await pause(); return }      // P1：vad.start() 完成前被取消
    startWave()
    emits("started")
  } catch (e) {
    // 权限被拒（NotAllowedError/SecurityError）→ mic_denied（E9）；其余 → vad_init_failed
    // v2 复审 P3-1：vad_init_failed 路径流已存活 → 立即 teardown，避免错误态下「录音中」指示常亮
    active = false
    if (streamRef) teardownStream()
    const denied = e && ['NotAllowedError', 'PermissionDeniedError', 'SecurityError'].includes(e.name)
    emits("error", denied ? "mic_permission_denied" : "vad_init_failed")
  }
}

async function pause() {
  active = false
  if (vadInstance) {
    try { await vadInstance.pause() } catch (e) { console.error('VAD pause 失败:', e) }
  }
  teardownStream()
}

async function destroy() {
  active = false
  if (vadInstance) {
    try { await vadInstance.destroy() } catch (e) { console.error('VAD destroy 失败:', e) }
    vadInstance = null
  }
  teardownStream()
  vadReady.value = false
}

async function retry(kind, seq = 0) {
  // vad/权限类：全量重建（重新 getUserMedia + 重新 initVAD）；asr_failed：仅重启监听
  if (kind === 'vad_init_failed' || kind === 'mic_permission_denied') {
    await destroy()
  }
  await start(seq)
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
    <!--音浪（AnalyserNode 实时音量驱动）+「正在聆听…」文案（spec §9）-->
    <div v-else-if="mode === 'wave'" class="flex flex-col items-center justify-center gap-0.5 flex-1" aria-hidden="true">
      <div class="flex items-center gap-1 h-5">
        <div v-for="(h, i) in bars" :key="i"
             class="w-0.5 bg-blue-400 rounded-full"
             :style="{ height: h + 'px' }"></div>
      </div>
      <span class="text-white/40 text-[11px] leading-none">正在聆听…</span>
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
    <!--取消（✕ 语义，沿用 KeyboardIcon；role=button + 键盘可达）-->
    <div @click="emits('cancel')"
         role="button"
         tabindex="0"
         @keydown.enter.prevent="emits('cancel')"
         @keydown.space.prevent="emits('cancel')"
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
