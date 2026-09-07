<script setup lang="ts">
import Message from "@/components/character/chat_field/chat_history/message/Message.vue";
import api from "@/js/http/api";
import {nextTick, onBeforeUnmount, onMounted, ref, useTemplateRef} from "vue";

const props = defineProps(['friendId', 'character', 'history', 'thinking'])
const emits = defineEmits(['pushFrontMessage', 'quickSend'])

const scrollRef = useTemplateRef('scroll-ref')
const sentinelRef = useTemplateRef('sentinel-ref')

async function scrollToBottom() {
  await nextTick()
  scrollRef.value.scrollTop = scrollRef.value.scrollHeight
}

// rAF 节流滚动（D-L6）：每帧最多一次
let scrollPending = false
function scheduleScroll() {
  if (scrollPending) return
  scrollPending = true
  requestAnimationFrame(() => {
    scrollPending = false
    scrollToBottom()
  })
}

const loadError = ref('')
const initialLoading = ref(true)
let isLoading = false
let hasMessages = true
let lastMessageId = 0

// 判断哨兵是否能被看到
function checkSentinelVisible() {
  if (!sentinelRef.value)
    return false
  const sentinelRect = sentinelRef.value.getBoundingClientRect()
  const scrollRect = scrollRef.value.getBoundingClientRect()
  return sentinelRect.top < scrollRect.bottom && sentinelRect.bottom > scrollRect.top
}

async function loadMore() {
  if (isLoading || !hasMessages) {
    return
  }
  isLoading = true

  let newMessages = []
  try {
    const response = await api.get('/api/friend/message/get_history/', {
      params: {
        last_message_id: lastMessageId,
        friend_id: props.friendId
      }
    })
    const data = response.data
    newMessages = data.messages
    loadError.value = ''
  } catch (e) {
    console.log(e)
    loadError.value = '加载失败，请稍后重试'
  } finally {
    isLoading = false
    initialLoading.value = false
    if (newMessages.length === 0) {
      hasMessages = false
    } else {
      const oldHeight = scrollRef.value.scrollHeight
      const oldTop = scrollRef.value.scrollTop

      for (const m of newMessages) {
        emits('pushFrontMessage', {
          role: 'ai',
          content: m.output,
          id: crypto.randomUUID(),
          // Q3 拍板后端批次后，历史消息将携带 created_at/citations（Phase 2 消费）
          time: m.created_at,
          citations: m.citations,
        })
        emits('pushFrontMessage', {
          role: 'user',
          content: m.user_message,
          id: crypto.randomUUID(),
          time: m.created_at,
        })
        lastMessageId = m.id
      }

      await nextTick()

      const newHeight = scrollRef.value.scrollHeight
      // 防止视窗内容自动上滑（现有算法保留，F3）
      scrollRef.value.scrollTop = oldTop + newHeight - oldHeight

      if (checkSentinelVisible()) {
        await loadMore()
      }
    }
  }
}

// 错误重试：重置失败标记后重放 loadMore
function retry() {
  loadError.value = ''
  hasMessages = true
  loadMore()
}

// Phase 1 分组：仅按 role 变化切组（时间差 >5min 与日期分隔为 Phase 2）
function showHeaderFor(index) {
  if (index === 0) return true
  return props.history[index].role !== props.history[index - 1].role
}

let observer = null
onMounted(async () => {
  await loadMore()
  observer = new IntersectionObserver(
      (entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            loadMore()
          }
        })
      },
      {root: null, rootMargin: '2px', threshold: 0}
  )
  observer.observe(sentinelRef.value)
})

onBeforeUnmount(() => {
  observer?.disconnect()
})

defineExpose({
  scrollToBottom,
  scheduleScroll,
})
</script>

<template>
  <div ref="scroll-ref" class="flex-1 min-h-0 overflow-y-auto no-scrollbar px-4 py-3">
    <!-- 首次加载骨架（2 组左右交替 shimmer 气泡） -->
    <template v-if="initialLoading && history.length === 0">
      <div v-for="pair in 2" :key="pair">
        <div class="flex justify-start my-2">
          <div class="w-3/5 h-10 rounded-2xl skeleton-shimmer"></div>
        </div>
        <div class="flex justify-end my-2">
          <div class="w-2/5 h-10 rounded-2xl skeleton-shimmer"></div>
        </div>
      </div>
    </template>

    <!-- 加载失败（错误态 + 重试） -->
    <div v-if="loadError" class="flex flex-col items-center justify-center gap-3 py-8">
      <p class="text-center text-sm text-red-300">{{ loadError }}</p>
      <button type="button" class="btn btn-sm btn-neutral" @click="retry">点击重试</button>
    </div>

    <!-- 哨兵 -->
    <div ref="sentinel-ref" class="h-2"></div>

    <!-- 聊天消息 -->
    <Message v-for="(message, index) in history"
             :key="message.id"
             :message="message"
             :character="character"
             :show-header="showHeaderFor(index)"
    />

    <!-- 思考中指示（首 token 前） -->
    <div v-if="thinking" class="flex justify-start my-2">
      <div class="msg-bubble msg-bubble-ai flex items-center gap-1">
        <span class="loading loading-dots loading-sm"></span>
      </div>
    </div>
  </div>
</template>

<style scoped>
</style>
