<script setup lang="ts">
import { useVoiceToggle } from '@/composables/useVoiceToggle.js'
import SpeakerIcon from '@/components/character/icons/SpeakerIcon.vue'

const { voiceEnabled, toggle } = useVoiceToggle()
</script>

<template>
  <!-- Phase 4 无障碍：原为 <div @click>，键盘不可达（Tab 聚焦不到）→ 改真按钮 -->
  <button type="button"
          class="h-10 w-10 rounded-full bg-black/50
                 flex items-center justify-center cursor-pointer
                 hover:bg-black/60 transition-colors shrink-0
                 focus-visible:ring-2 ring-white/40"
          :aria-label="voiceEnabled ? '关闭语音' : '开启语音'"
          :title="voiceEnabled ? '语音已开启' : '语音已关闭'"
          @click="toggle">
    <SpeakerIcon :enabled="voiceEnabled" />
  </button>
</template>

<style scoped>
</style>
