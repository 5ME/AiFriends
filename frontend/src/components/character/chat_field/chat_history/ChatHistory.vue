<script setup lang="ts">
import Message from "@/components/character/chat_field/chat_history/message/Message.vue";
import api from "@/js/http/api";
import {computed, nextTick, onBeforeUnmount, onMounted, ref, useTemplateRef} from "vue";
import { dateLabel, groupMessages } from "@/utils/chatFormat";

const props = defineProps(['friendId', 'character', 'history', 'thinking'])
const emits = defineEmits(['pushFrontMessage', 'quickSend', 'openCitation'])

const scrollRef = useTemplateRef('scroll-ref')
const sentinelRef = useTemplateRef('sentinel-ref')

async function scrollToBottom() {
  await nextTick()
  scrollRef.value.scrollTop = scrollRef.value.scrollHeight
}

const loadError = ref('')
const initialLoading = ref(true)
let isLoading = false
const hasMessages = ref(true)
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
  if (isLoading || !hasMessages.value) {
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
      hasMessages.value = false
    } else {
      const oldHeight = scrollRef.value.scrollHeight
      const oldTop = scrollRef.value.scrollTop

      for (const m of newMessages) {
        emits('pushFrontMessage', {
          role: 'ai',
          content: m.output,
          id: crypto.randomUUID(),
          // 历史消息挂载即 rendered（D-L5）；time/citations 消费 Step A 新字段
          time: m.created_at,
          citations: m.citations,
          rendered: true,
        })
        emits('pushFrontMessage', {
          role: 'user',
          content: m.user_message,
          id: crypto.randomUUID(),
          time: m.created_at,
          rendered: true,
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
  hasMessages.value = true
  loadMore()
}

// 空态示例问题（D7 文案）
const quickQuestions = ['介绍一下你自己吧', '讲个今天发生的故事', '和我聊聊最近的烦恼']

// Phase 2 分组（LD §9.2）：同 role 连续且时间差 ≤5min 一组；首条恒为组首
const groups = computed(() => groupMessages(props.history))
const groupHeadSet = computed(() => {
  const set = new Set()
  for (const g of groups.value) {
    set.add(g.startIndex)
  }
  return set
})

function showHeaderFor(index) {
  return groupHeadSet.value.has(index)
}

// 组首消息前的日期胶囊：与上一条消息跨天时出「今天/昨天/M月D日」
function dateLabelFor(index) {
  if (!groupHeadSet.value.has(index)) return null
  const prevTime = index > 0 ? props.history[index - 1]?.time : null
  return dateLabel(prevTime, props.history[index]?.time)
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
             :date-label="dateLabelFor(index)"
             @openCitation="emits('openCitation', $event)"
    />

    <!-- 空态：新会话 introduction + 示例问题（D7 文案；点击 quickSend 直达发送）。
         与错误态互斥（LD §5:300/301）：loadMore 失败时只显示「加载失败+重试」，不同屏双态 -->
    <div v-if="!initialLoading && !hasMessages && history.length === 0 && !loadError"
         class="h-full flex flex-col items-center justify-center gap-5 px-6 text-center">
      <p v-if="character?.introduction" class="text-white/90 text-lg leading-relaxed">
        {{ character.introduction }}
      </p>
      <div class="flex flex-col items-stretch gap-2.5 w-full max-w-60">
        <button v-for="q in quickQuestions" :key="q"
                type="button"
                class="bg-black/25 backdrop-blur text-white/90 rounded-full px-4 py-2 text-sm
                       cursor-pointer hover:bg-black/40 transition-colors
                       focus-visible:ring-2 ring-white/40"
                :aria-label="`发送示例问题：${q}`"
                @click="emits('quickSend', q)">
          {{ q }}
        </button>
      </div>
    </div>

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
