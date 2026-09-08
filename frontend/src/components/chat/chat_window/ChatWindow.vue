<script setup lang="ts">
import { ref, useTemplateRef } from 'vue'
import WindowHeader from '@/components/chat/chat_window/WindowHeader.vue'
import ChatHistory from '@/components/character/chat_field/chat_history/ChatHistory.vue'
import InputField from '@/components/character/chat_field/input_field/InputField.vue'

const props = defineProps(['friend'])
const emits = defineEmits(['closed', 'openDrawer'])

// history 数组所有权在 ChatWindow（D-L1）：每个会话一个实例，:key 重建即隔离
const history = ref([])
const isStreaming = ref(false)
const thinking = ref(false)

const chatHistoryRef = useTemplateRef('chat-history-ref')
const inputFieldRef = useTemplateRef('input-field-ref')

function pushBackMessage(msg) {
  history.value.push(msg)
  scheduleScroll()
}

function pushFrontMessage(msg) {
  history.value.unshift(msg)
}

function appendToLastMessage(delta) {
  const last = history.value[history.value.length - 1]
  if (!last) return
  if (typeof delta === 'object') {
    if (delta.citations) {
      last.citations = delta.citations
    }
    if (delta.rendered) {
      last.rendered = true  // D-L5：isDone 后标记，触发 markdown 渲染
    }
  } else {
    last.content += delta
  }
  scheduleScroll()
}

// 发送统一入口（D-L3）：空态示例问题（Phase 2 quickSend）与外部调用都走这里
function sendMessage(text) {
  if (isStreaming.value || !text?.trim()) return
  inputFieldRef.value?.handleSend(text)
}

// InputField 上抛的流式状态 → 驱动窗口级 isStreaming / thinking
function handleStreamState({ streaming, thinking: thk }) {
  isStreaming.value = streaming
  thinking.value = thk
}

// rAF 节流滚动（D-L6）
let scrollPending = false
function scheduleScroll() {
  if (scrollPending) return
  scrollPending = true
  requestAnimationFrame(() => {
    scrollPending = false
    chatHistoryRef.value?.scrollToBottom()
  })
}

</script>

<template>
  <!-- 舞台（桌面端：同图模糊压暗延展；移动端无舞台） -->
  <div class="absolute inset-0 overflow-hidden hidden lg:block">
    <div class="absolute -inset-[10%] bg-cover bg-center stage-blur"
         :style="{ backgroundImage: `url(${friend.character.background_image})` }"></div>
    <div class="absolute inset-0 stage-dim"></div>
  </div>

  <!-- 角色之窗（3:5，桌面居中 / 移动端全屏，纯 CSS 尺寸公式） -->
  <div class="chat-window relative mx-auto flex flex-col">
    <!-- 窗口背景 + 渐变蒙层 -->
    <div class="absolute inset-0 bg-cover bg-center"
         :style="{ backgroundImage: `url(${friend.character.background_image})` }"></div>
    <div class="absolute inset-0 window-scrim"></div>

    <!-- 内容列（flex column，杜绝 absolute 堆叠） -->
    <div class="relative z-10 flex flex-col h-full">
      <WindowHeader :character="friend.character" @close="emits('closed')" @openDrawer="emits('openDrawer')" />
      <ChatHistory ref="chat-history-ref"
                   :friendId="friend.id"
                   :character="friend.character"
                   :history="history"
                   :thinking="thinking"
                   @pushFrontMessage="pushFrontMessage"
                   @quickSend="sendMessage" />
      <InputField ref="input-field-ref"
                  :friendId="friend.id"
                  @pushBackMessage="pushBackMessage"
                  @appendToLastMessage="appendToLastMessage"
                  @streamState="handleStreamState" />
    </div>
  </div>
</template>

<style scoped>
</style>
