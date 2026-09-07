<script setup lang="ts">
import CharacterPhotoField from '@/components/character/chat_field/character_photo_field/CharacterPhotoField.vue'
import VoiceToggle from '@/components/character/chat_field/VoiceToggle.vue'

defineProps(['character'])
const emits = defineEmits(['close'])
</script>

<template>
  <div class="h-14 shrink-0 px-3 flex items-center justify-between gap-2
              bg-black/40 backdrop-blur">
    <!-- 头像 + 名字 pill（点击开详情，复用现有能力） -->
    <CharacterPhotoField :character="character" />

    <div class="flex items-center gap-2">
      <VoiceToggle />
      <button type="button"
              class="btn btn-sm btn-circle btn-ghost text-white"
              aria-label="关闭对话"
              data-tip="关闭"
              @click="emits('close')">
        ✕
      </button>
    </div>
  </div>
</template>

<style scoped>
</style>
