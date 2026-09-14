<script setup lang="ts">
import { useVoiceToggle } from '@/composables/useVoiceToggle.js'
import SpeakerIcon from '@/components/character/icons/SpeakerIcon.vue'

const { voiceEnabled, toggle } = useVoiceToggle()
</script>

<template>
  <button type="button"
          class="chat-icon-btn-solid chat-focus h-10 w-10 rounded-full
                 flex items-center justify-center cursor-pointer
                 transition-colors shrink-0 outline-none"
          :title="voiceEnabled ? '语音已开启' : '语音已关闭'"
          :aria-label="voiceEnabled ? '关闭语音播报' : '开启语音播报'"
          :aria-pressed="voiceEnabled"
          @click="toggle">
    <SpeakerIcon :enabled="voiceEnabled" />
  </button>
</template>

<style scoped>
</style>
