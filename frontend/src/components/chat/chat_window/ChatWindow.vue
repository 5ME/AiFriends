<script setup lang="ts">
import { onBeforeUnmount, ref, useTemplateRef, watch } from 'vue'
import WindowHeader from '@/components/chat/chat_window/WindowHeader.vue'
import ChatHistory from '@/components/character/chat_field/chat_history/ChatHistory.vue'
import InputField from '@/components/character/chat_field/input_field/InputField.vue'
import { useChatSettings } from '@/composables/useChatSettings.js'

const props = defineProps(['friend', 'overlayK', 'userBubbleBg'])
const { simpleBackground } = useChatSettings()
const emits = defineEmits(['closed', 'openDrawer'])

// history 数组所有权在 ChatWindow（D-L1）：每个会话一个实例，:key 重建即隔离
const history = ref([])
const isStreaming = ref(false)
const thinking = ref(false)

const chatHistoryRef = useTemplateRef('chat-history-ref')
const inputFieldRef = useTemplateRef('input-field-ref')

// RAG 引用原文浮层：状态上移到 ChatWindow，浮层在舞台根内居中（与角色之窗同轴）
const activeCitation = ref(null)

function openCitation(c) {
  activeCitation.value = c
}

function closeCitation() {
  activeCitation.value = null
}

function onKeydown(e) {
  if (e.key === 'Escape') closeCitation()
}

watch(activeCitation, (v) => {
  if (v) window.addEventListener('keydown', onKeydown)
  else window.removeEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

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
  <!-- 单根容器：absolute 铺满舞台，内部 flex 居中窗口
       （修复：原多根组件导致窗口在 main 的 flex 布局中未真正居中） -->
  <div class="chat-stage-root absolute inset-0 flex items-center justify-center"
       :style="{ '--overlay-k': overlayK, '--user-bubble-bg': userBubbleBg }">
    <!-- 舞台（桌面端：同图模糊压暗延展；移动端无舞台；简约模式 → base-200 纯色） -->
    <div class="absolute inset-0 overflow-hidden hidden lg:block">
      <template v-if="!simpleBackground">
        <div class="absolute -inset-[10%] bg-cover bg-center stage-blur"
             :style="{ backgroundImage: `url(${friend.character.background_image})` }"></div>
        <div class="absolute inset-0 stage-dim"></div>
      </template>
      <div v-else class="absolute inset-0 bg-base-200"></div>
    </div>

    <!-- 角色之窗（3:5，桌面居中 / 移动端全屏，纯 CSS 尺寸公式） -->
    <div class="chat-window relative flex flex-col" :class="{ 'chat-simple': simpleBackground }">
    <!-- 窗口背景 + 渐变蒙层（单层，停点随 --overlay-k 过渡；spec §6.3/§6.5） -->
    <template v-if="!simpleBackground">
      <div class="absolute inset-0 bg-cover bg-center"
           :style="{ backgroundImage: `url(${friend.character.background_image})` }"></div>
      <div class="absolute inset-0 window-scrim"></div>
    </template>

    <!-- 内容列（flex column，杜绝 absolute 堆叠） -->
    <div class="relative z-10 flex flex-col h-full">
      <WindowHeader :character="friend.character" @close="emits('closed')" @openDrawer="emits('openDrawer')" />
      <ChatHistory ref="chat-history-ref"
                   :friendId="friend.id"
                   :character="friend.character"
                   :history="history"
                   :thinking="thinking"
                   @pushFrontMessage="pushFrontMessage"
                   @quickSend="sendMessage"
                   @openCitation="openCitation" />
      <InputField ref="input-field-ref"
                  :friendId="friend.id"
                  @pushBackMessage="pushBackMessage"
                  @appendToLastMessage="appendToLastMessage"
                  @streamState="handleStreamState" />
    </div>
  </div>

    <!-- RAG 引用原文浮层：覆盖舞台根、flex 居中面板 → 与角色之窗同轴，盖在其上方 -->
    <div v-if="activeCitation"
         class="absolute inset-0 z-20 flex items-center justify-center p-4"
         role="dialog" aria-modal="true" aria-label="引用原文"
         @click="closeCitation">
      <div class="flex flex-col overflow-hidden rounded-xl border border-white/10
                  bg-neutral-900/95 backdrop-blur-xl shadow-2xl
                  w-[min(92vw,420px)] max-h-[70%]"
           @click.stop>
        <div class="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-white/10 shrink-0">
          <p class="text-sm font-medium text-white/90 truncate">
            《{{ activeCitation.title || '系统知识库' }}》 第{{ activeCitation.chunk_index + 1 }}段
          </p>
          <button type="button"
                  class="btn btn-xs btn-ghost text-white/70 shrink-0"
                  aria-label="关闭引用浮层"
                  @click="closeCitation">✕</button>
        </div>
        <div v-if="activeCitation.content"
             class="overflow-y-auto max-h-[40vh] px-4 py-3 text-sm leading-relaxed
                    text-white/80 whitespace-pre-wrap break-words">
          {{ activeCitation.content }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
</style>
