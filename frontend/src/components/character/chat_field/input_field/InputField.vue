<script setup lang="ts">

import MicIcon from "@/components/character/icons/MicIcon.vue";
import SendIcon from "@/components/character/icons/SendIcon.vue";
import streamApi from "@/js/http/streamApi";
import {onUnmounted, ref, useTemplateRef} from "vue";
import Microphone from "@/components/character/chat_field/input_field/Microphone.vue";

const props = defineProps(['friendId'])
const emits = defineEmits(['pushBackMessage', 'appendToLastMessage'])

const inputRef = useTemplateRef('input-ref')
const message = ref('')
let processId = 0

const showMic = ref(false)

let mediaSource = null;
let sourceBuffer = null;
let audioPlayer = new Audio(); // 全局播放器实例
let audioQueue = [];           // 待写入 Buffer 的二进制队列
let isUpdating = false;        // Buffer 是否正在写入

const initAudioStream = () => {
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
  audioPlayer.pause();
  audioPlayer.src = '';
});

function focus() {
  inputRef.value.focus()
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

  try {
    await streamApi('/api/friend/message/chat/', {
      body: {
        friend_id: props.friendId,
        message: content
      },
      onmessage(data, isDone) {
        if (processId !== curId) {
          // 实现输出打断
          return
        }
        if (data.content) {
          emits('appendToLastMessage', data.content)
        }
        if (data.audio) {
          handleAudioChunk(data.audio)
        }
      },
      onerror(err) {
        console.log(err)
      },
    })
  } catch (e) {
    console.log(e)
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
}

defineExpose({focus, closeMic})
</script>

<template>
  <form v-if="!showMic" @submit.prevent="handleSend" class="absolute bottom-4 left-2 h-12 w-86 flex items-center">
    <input class="input bg-black/30 backdrop-blur text-base text-white w-full h-full rounded-md pr-20"
           type="text" placeholder="文本输入"
           ref="input-ref" v-model="message"/>
    <div class="absolute right-2 w-8 h-8 flex justify-center items-center cursor-pointer"
         @click="handleSend">
      <SendIcon/>
    </div>
    <div @click="showMic=true" class="absolute right-10 w-8 h-8 flex justify-center items-center cursor-pointer">
      <MicIcon/>
    </div>
  </form>
  <!--麦克风组件-->
  <Microphone v-else
              @close="showMic=false"
              @send="handleSend"
              @stop="handleStop"
  />
</template>

<style scoped>

</style>