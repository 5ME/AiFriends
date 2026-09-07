<script setup lang="ts">
import { computed } from 'vue'
import {useUserStore} from '@/stores/user';

const props = defineProps({
  message: Object,
  character: Object,
  showHeader: { type: Boolean, default: true },
})

const user = useUserStore()

const avatar = computed(() =>
  props.message.role === 'ai' ? props.character?.photo : user.photo
)
const name = computed(() =>
  props.message.role === 'ai' ? props.character?.name : user.username
)
</script>

<template>
  <div v-if="message.content" :class="showHeader ? 'mt-3' : 'mt-1'">
    <!-- 组首：头像 + 名字 pill（N1 底衬保证亮图可读） -->
    <div v-if="showHeader" class="flex items-center gap-2 mb-1"
         :class="message.role === 'user' ? 'flex-row-reverse' : ''">
      <div class="avatar shrink-0">
        <div class="w-9 rounded-full">
          <img :src="avatar" alt=""/>
        </div>
      </div>
      <span class="msg-name-pill">{{ name }}</span>
    </div>

    <!-- 气泡（spec §8.2：break-words、max-w 75%、圆角 16px 头像侧 4px） -->
    <div class="flex" :class="message.role === 'user' ? 'justify-end' : 'justify-start'">
      <div class="msg-bubble"
           :class="message.role === 'user' ? 'msg-bubble-user' : 'msg-bubble-ai'">
        {{ message.content }}
      </div>
    </div>

    <!--RAG 引用来源（Phase 1 保留现有 collapse，Phase 2 改为 chips）-->
    <div v-if="message.role === 'ai' && message.citations?.length"
         class="collapse collapse-arrow mt-0.5 w-fit max-w-80 rounded-box"
         :class="showHeader ? 'ml-12' : ''">
      <input type="checkbox" />
      <div class="collapse-title text-xs font-medium opacity-60 text-white/80 py-1">
        📖 {{ message.citations.length }} 条参考来源
      </div>
      <div class="collapse-content text-xs opacity-50 text-white/70">
        <p v-for="c in message.citations" :key="c.index" class="py-0.5">
          {{ c.index }}. {{ c.title || '系统知识库' }} 第{{ c.chunk_index + 1 }}段
        </p>
      </div>
    </div>
  </div>
</template>

<style scoped>
</style>
