<script setup lang="ts">
import CharacterPhotoField from '@/components/character/chat_field/character_photo_field/CharacterPhotoField.vue'
import VoiceToggle from '@/components/character/chat_field/VoiceToggle.vue'
import { onBeforeUnmount, ref, useTemplateRef, watch } from 'vue'
import { useChatSettings } from '@/composables/useChatSettings.js'

defineProps(['character'])
const emits = defineEmits(['close', 'openDrawer'])

const { simpleBackground, autoSendVoice, toggleSimple, toggleAutoSend } = useChatSettings()

// ⚙ 设置弹层（Q6）：简约背景 + 语音自动发送；点外部 / Esc 关闭
const settingsOpen = ref(false)
const settingsRef = useTemplateRef('settings-ref')

function onDocPointerDown(e) {
  if (!settingsRef.value?.contains(e.target)) settingsOpen.value = false
}

function onKeydown(e) {
  if (e.key === 'Escape') settingsOpen.value = false
}

watch(settingsOpen, (open) => {
  if (open) {
    document.addEventListener('pointerdown', onDocPointerDown)
    window.addEventListener('keydown', onKeydown)
  } else {
    document.removeEventListener('pointerdown', onDocPointerDown)
    window.removeEventListener('keydown', onKeydown)
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocPointerDown)
  window.removeEventListener('keydown', onKeydown)
})
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
      <div ref="settings-ref" class="relative">
        <button type="button"
                class="btn btn-sm btn-circle btn-ghost chat-icon-btn"
                aria-label="聊天设置"
                :aria-expanded="settingsOpen ? 'true' : 'false'"
                aria-haspopup="dialog"
                data-tip="设置"
                @click="settingsOpen = !settingsOpen">
          ⚙
        </button>

        <div v-if="settingsOpen"
             role="dialog"
             aria-label="聊天设置"
             class="absolute right-0 top-full mt-2 z-30 w-60 rounded-xl bg-base-100 text-base-content p-3 shadow-xl">
          <label class="flex items-center justify-between gap-3 py-1.5 cursor-pointer">
            <span class="text-sm">简约背景</span>
            <input type="checkbox"
                   class="toggle toggle-sm"
                   :checked="simpleBackground"
                   aria-label="简约背景"
                   @change="toggleSimple" />
          </label>
          <label class="flex items-center justify-between gap-3 py-1.5 cursor-pointer">
            <span class="text-sm">语音自动发送</span>
            <input type="checkbox"
                   class="toggle toggle-sm"
                   :checked="autoSendVoice"
                   aria-label="语音自动发送"
                   @change="toggleAutoSend" />
          </label>
          <p class="text-[11px] text-base-content/60 pt-1 leading-snug">
            看到背景图时已自动适配蒙层；如仍觉得花，可开简约背景。
          </p>
        </div>
      </div>
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
