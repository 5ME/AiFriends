<script setup lang="ts">
import { useVoiceToggle } from '@/composables/useVoiceToggle.js'
import SpeakerIcon from '@/components/character/icons/SpeakerIcon.vue'

const { voiceEnabled, toggle } = useVoiceToggle()
</script>

<template>
  <div class="h-10 w-10 rounded-full bg-black/50
              flex items-center justify-center cursor-pointer
              hover:bg-black/60 transition-colors shrink-0"
       :title="voiceEnabled ? '语音已开启' : '语音已关闭'"
       @click="toggle">
    <SpeakerIcon :enabled="voiceEnabled" />
  </div>
</template>

<style scoped>
</style>
