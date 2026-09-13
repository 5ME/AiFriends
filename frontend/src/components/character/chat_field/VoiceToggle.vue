<script setup lang="ts">
import { useVoiceToggle } from '@/composables/useVoiceToggle.js'
import SpeakerIcon from '@/components/character/icons/SpeakerIcon.vue'

const { voiceEnabled, toggle } = useVoiceToggle()
</script>

<template>
  <button type="button"
          class="h-10 w-10 rounded-full bg-black/50
                 flex items-center justify-center cursor-pointer
                 hover:bg-black/60 transition-colors shrink-0
                 focus-visible:ring-2 ring-white/40 outline-none"
          :title="voiceEnabled ? '语音已开启' : '语音已关闭'"
          :aria-label="voiceEnabled ? '关闭语音播报' : '开启语音播报'"
          :aria-pressed="voiceEnabled"
          @click="toggle">
    <SpeakerIcon :enabled="voiceEnabled" />
  </button>
</template>

<style scoped>
</style>
