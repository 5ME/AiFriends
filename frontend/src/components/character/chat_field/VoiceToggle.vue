<script setup lang="ts">
import { useVoiceToggle } from '@/composables/useVoiceToggle.js'
import SpeakerIcon from '@/components/character/icons/SpeakerIcon.vue'

const { voiceEnabled, toggle } = useVoiceToggle()
</script>

<template>
  <button type="button"
          class="h-10 w-10 rounded-full glass-panel chat-text
                 flex items-center justify-center cursor-pointer
                 chat-icon-hover transition-colors shrink-0 chat-ring"
          :aria-label="voiceEnabled ? '语音已开启，点击关闭' : '语音已关闭，点击开启'"
          :aria-pressed="voiceEnabled ? 'true' : 'false'"
          :title="voiceEnabled ? '语音已开启' : '语音已关闭'"
          @click="toggle">
    <SpeakerIcon :enabled="voiceEnabled" />
  </button>
</template>

<style scoped>
</style>
