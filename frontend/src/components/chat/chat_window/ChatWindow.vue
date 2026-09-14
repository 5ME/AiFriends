<script setup lang="ts">
import { computed, onBeforeUnmount, ref, useTemplateRef, watch } from 'vue'
import WindowHeader from '@/components/chat/chat_window/WindowHeader.vue'
import ChatHistory from '@/components/character/chat_field/chat_history/ChatHistory.vue'
import InputField from '@/components/character/chat_field/input_field/InputField.vue'
import { useChatBg } from '@/composables/useChatBg.js'

const props = defineProps(['friend'])
const emits = defineEmits(['closed', 'openDrawer'])

// 4B：简约背景按角色记忆（D4B-3）；:key 重建保证切换角色即换状态
const { simpleOn, toggleSimple } = useChatBg(props.friend.character.id)

// E2/E3：无背景图（空串）或图片加载失败时不渲染背景图层，避免 url(undefined) 与破图。
// ⚠️ 必须用 Image 预探测：监听器挂在用 :style 设 CSS background-image 的 <div> 上时，
// `error` 事件**不会触发**（评审 R-5 实测）——那样写 bgFailed 永远是 false，是死代码。
const bgFailed = ref(false)
const hasBg = computed(() => !!props.friend.character.background_image && !bgFailed.value)

watch(
  () => props.friend.character.background_image,
  (url) => {
    bgFailed.value = false
    if (!url) return
    const probe = new Image()
    probe.onerror = () => { bgFailed.value = true }
    probe.src = url
  },
  { immediate: true },
)

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
  <div class="absolute inset-0 flex items-center justify-center">
    <!-- 舞台（桌面端：沉浸=同图模糊压暗；简约=纯色 #e7e5e4；无图=深色兜底） -->
    <div class="chat-stage-root absolute inset-0 overflow-hidden hidden lg:block"
         :class="{ 'stage-simple': simpleOn, 'no-bg': !hasBg }">
      <div v-if="hasBg"
           class="absolute -inset-[10%] bg-cover bg-center stage-blur"
           :style="{ backgroundImage: `url(${friend.character.background_image})` }"></div>
      <div class="absolute inset-0 stage-dim"></div>
    </div>

    <!-- 角色之窗（3:5，桌面居中 / 移动端全屏，纯 CSS 尺寸公式） -->
    <div class="chat-window relative flex flex-col"
         :class="{ 'chat-simple': simpleOn, 'no-bg': !hasBg }">
    <!-- 窗口背景 + 渐变蒙层（无图时不渲染，避免 url(undefined) 与破图；E2/E3） -->
    <div v-if="hasBg"
         class="absolute inset-0 bg-cover bg-center"
         :style="{ backgroundImage: `url(${friend.character.background_image})` }"></div>
    <div v-if="hasBg" class="absolute inset-0 window-scrim"></div>
    <!-- 纯色窗底：沉浸模式为 transparent（图铺满），简约模式为 #fafaf9 -->
    <div class="chat-window-bg absolute inset-0"></div>

    <!-- 内容列（flex column，杜绝 absolute 堆叠） -->
    <div class="relative z-10 flex flex-col h-full">
      <WindowHeader :character="friend.character"
                    :simple-bg="simpleOn"
                    @close="emits('closed')"
                    @openDrawer="emits('openDrawer')"
                    @toggleSimpleBg="toggleSimple" />
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
      <!-- 引用浮层（浅色下变浅底深字）。逐处映射：
           面板底/描边：chat-modal ← bg-neutral-900/95 + border-white/10（专属 token，不用 --cbg-surface）
           标题：chat-text      ← text-white/90
           正文：chat-text-2    ← text-white/80
           关闭键：chat-text-2  ← text-white/70（它是 daisyUI .btn，故用 chat-text-2 而非 chat-focus） -->
      <div class="flex flex-col overflow-hidden rounded-xl border chat-modal
                  backdrop-blur-xl shadow-2xl
                  w-[min(92vw,420px)] max-h-[70%]"
           @click.stop>
        <div class="flex items-center justify-between gap-3 px-4 py-2.5 border-b chat-modal shrink-0">
          <p class="text-sm font-medium chat-text truncate">
            《{{ activeCitation.title || '系统知识库' }}》 第{{ activeCitation.chunk_index + 1 }}段
          </p>
          <button type="button"
                  class="btn btn-xs btn-ghost chat-text-2 shrink-0"
                  aria-label="关闭引用浮层"
                  @click="closeCitation">✕</button>
        </div>
        <div v-if="activeCitation.content"
             class="overflow-y-auto max-h-[40vh] px-4 py-3 text-sm leading-relaxed
                    chat-text-2 whitespace-pre-wrap break-words">
          {{ activeCitation.content }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
</style>
