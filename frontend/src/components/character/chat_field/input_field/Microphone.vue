<script setup lang="ts">
import KeyboardIcon from "@/components/character/icons/KeyboardIcon.vue";
import {onActivated, onDeactivated, onBeforeUnmount, onMounted, ref} from "vue";
import {MicVAD} from "@ricky0123/vad-web";
import api from "@/js/http/api";
import CONFIG_API from "@/js/config/config";

const isSpeaking = ref(false)
const vadReady = ref(false)

const emits = defineEmits(["close", "send", "stop"])

let vadInstance = null;
let componentActive = false;

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
      onSpeechStart: () => {
        isSpeaking.value = true;
        emits("stop")
      },
      onSpeechEnd: (audio) => {
        isSpeaking.value = false;
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

    if (componentActive && vadInstance) {
      await vadInstance.start();
    }
    vadReady.value = true;
  } catch (e) {
    console.error("VAD 初始化失败:", e);
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

// 将音频发送到后端
const sendToBackend = async (arrayBuffer) => {
  const blob = new Blob([arrayBuffer], {type: "audio/pcm"})
  const formData = new FormData();
  formData.append("audio", blob, "voice.pcm")
  try {
    const response = await api.post("/api/friend/message/asr/asr/", formData)
    const data = response.data
    // console.log("===> ", data)
    if (data.message === "success") {
      emits("send", null, data.text)
    }
  } catch (e) {
    console.log(e)
  }
};

onMounted(() => {
  componentActive = true;
  initVAD();
})

onActivated(() => {
  componentActive = true;
  if (vadInstance) {
    vadInstance.start();
  }
});

onDeactivated(() => {
  componentActive = false;
  if (vadInstance) {
    vadInstance.pause();
  }
});

onBeforeUnmount(() => {
  componentActive = false;
  if (vadInstance) {
    vadInstance.destroy();
    vadInstance = null;
  }
})
</script>

<template>
  <div class="absolute bottom-4 left-2 h-12 w-86 flex items-center bg-black/30 backdrop-blur rounded-md">
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
    <!--音浪动效-->
    <div v-else-if="isSpeaking" class="flex items-center justify-center gap-1 h-6 flex-1">
      <div
          v-for="i in 32" :key="i"
          class="w-0.5 bg-blue-400 rounded-full animate-wave"
          :style="{ animationDelay: `${i * 0.1}s` }"
      ></div>
    </div>
    <!--待机-->
    <div v-else class="text-white/50 text-base w-full text-center">
      语音输入
    </div>
    <div @click="emits('close')"
         class="absolute right-2 w-8 h-8 flex justify-center items-center cursor-pointer">
      <KeyboardIcon/>
    </div>
  </div>
</template>

<style scoped>
.animate-wave {
  height: 4px;
  animation: wave-animation 0.6s ease-in-out infinite alternate;
}

@keyframes wave-animation {
  0% {
    height: 4px;
    opacity: 0.3;
  }
  100% {
    height: 20px;
    opacity: 1;
  }
}

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