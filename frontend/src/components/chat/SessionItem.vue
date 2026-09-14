<script setup lang="ts">
import { computed } from 'vue'
import { sessionTimeLabel } from '@/utils/chatFormat.js'

const props = defineProps(['session', 'active', 'preview'])
const emits = defineEmits(['select'])

// 本地乐观预览（刚发送/刚回完，还没被下一次 get_list 拉取覆盖）优先于服务端值
const previewText = computed(() => props.preview?.text || props.session.last_message || '')
const timeLabel = computed(
  () => sessionTimeLabel(props.preview?.at || props.session.last_message_at),
)
</script>

<template>
  <button type="button"
          class="w-full h-16 flex items-center gap-3 rounded-xl px-2 pl-1 text-left transition-colors cursor-pointer
                 hover:bg-base-300"
          :class="active ? 'session-active' : 'session-inactive'"
          :aria-current="active ? 'true' : undefined"
          @click="emits('select', session.character.id)">
    <div class="avatar shrink-0">
      <div class="w-10 rounded-full">
        <img :src="session.character.photo" alt="" />
      </div>
    </div>
    <div class="flex-1 min-w-0 flex flex-col gap-0.5">
      <div class="flex items-baseline gap-2">
        <span class="flex-1 min-w-0 text-base font-medium line-clamp-1 break-all">
          {{ session.character.name }}
        </span>
        <!-- 裸时间夹在可访问名称中间是噪音，对读屏隐藏（预览保留，它带信息量） -->
        <span v-if="timeLabel" aria-hidden="true" class="shrink-0 text-xs text-neutral-500">
          {{ timeLabel }}
        </span>
      </div>
      <p class="text-[13px] leading-tight line-clamp-1 break-all text-neutral-500">
        {{ previewText || '还没有消息' }}
      </p>
    </div>
  </button>
</template>

<style scoped>
</style>
