<script setup lang="ts">
import CharacterPhotoField from '@/components/character/chat_field/character_photo_field/CharacterPhotoField.vue'
import VoiceToggle from '@/components/character/chat_field/VoiceToggle.vue'

defineProps(['character'])
const emits = defineEmits(['close', 'openDrawer'])
</script>

<template>
  <div class="h-14 shrink-0 px-3 flex items-center justify-between gap-2
              glass-bar">
    <!-- 头像 + 名字 pill（点击开详情，复用现有能力） -->
    <CharacterPhotoField :character="character" />

    <div class="flex items-center gap-2">
      <!-- 移动端会话抽屉入口（spec §4.2「头部菜单按钮」；lg:hidden = 桌面端列表常驻无需） -->
      <button type="button"
              class="lg:hidden btn btn-sm btn-circle btn-ghost chat-icon-btn"
              aria-label="打开会话列表"
              data-tip="会话"
              @click="emits('openDrawer')">
        ☰
      </button>
      <VoiceToggle />
      <button type="button"
              class="btn btn-sm btn-circle btn-ghost chat-icon-btn"
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
