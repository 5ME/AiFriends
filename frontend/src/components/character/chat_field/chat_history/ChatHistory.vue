<script setup lang="ts">
import Message from "@/components/character/chat_field/chat_history/message/Message.vue";
import api from "@/js/http/api";
import {nextTick, onBeforeUnmount, onMounted, useTemplateRef} from "vue";

const props = defineProps(['friendId', 'character', 'history'])
const emits = defineEmits(['pushFrontMessage'])

const scrollRef = useTemplateRef('scroll-ref')
const sentinelRef = useTemplateRef('sentinel-ref')

async function scrollToBottom() {
  await nextTick()
  scrollRef.value.scrollTop = scrollRef.value.scrollHeight
}

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
    if (data.message === 'success') {
      newMessages = data.messages
    }
  } catch (e) {
    console.log(e)
  } finally {
    isLoading = false
    if (newMessages.length === 0) {
      hasMessages = false
    } else {
      const oldHeight = scrollRef.value.scrollHeight
      const oldTop = scrollRef.value.scrollTop

      for (const m of newMessages) {
        emits('pushFrontMessage', {
          role: 'ai',
          content: m.output,
          id: crypto.randomUUID()
        })
        emits('pushFrontMessage', {
          role: 'user',
          content: m.user_message,
          id: crypto.randomUUID()
        })
        lastMessageId = m.id
      }

      await nextTick()

      const newHeight = scrollRef.value.scrollHeight
      // 防止视窗内容自动上滑
      scrollRef.value.scrollTop = oldTop + newHeight - oldHeight

      if (checkSentinelVisible()) {
        await loadMore()
      }
    }
  }
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
  scrollToBottom
})
</script>

<template>
  <div ref="scroll-ref" class="absolute top-18 left-0 w-90 h-112 overflow-y-scroll no-scrollbar">
    <!--哨兵-->
    <div ref="sentinel-ref" class="h-2"></div>
    <!--聊天消息-->
    <Message v-for="message in history"
             :key="message.id"
             :message="message"
             :character="character"
    />
  </div>
</template>

<style scoped>
/* 隐藏 Chrome, Safari 和 Opera 的滚动条 */
.no-scrollbar::-webkit-scrollbar {
  display: none;
}

/* 隐藏 IE, Edge 和 Firefox 的滚动条 */
.no-scrollbar {
  -ms-overflow-style: none;
  /* IE and Edge */
  scrollbar-width: none;
  /* Firefox */
}
</style>