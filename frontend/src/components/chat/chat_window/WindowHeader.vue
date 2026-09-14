<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import CharacterPhotoField from '@/components/character/chat_field/character_photo_field/CharacterPhotoField.vue'
import VoiceToggle from '@/components/character/chat_field/VoiceToggle.vue'
import SettingsIcon from '@/components/character/icons/SettingsIcon.vue'

const props = defineProps(['character', 'simpleBg'])
const emits = defineEmits(['close', 'openDrawer', 'toggleSimpleBg'])

const settingsOpen = ref(false)
const popoverRef = ref(null)
const gearWrapRef = ref(null)   // 包裹层：仅用于「点外关闭」的 contains 判断
const gearBtnRef = ref(null)    // 触发器本体：焦点回归必须落在可聚焦的 <button> 上（评审 R-5）

const scopeLabel = computed(() => `仅对《${props.character?.name ?? '该角色'}》生效`)

function closeSettings() {
  settingsOpen.value = false
  gearBtnRef.value?.focus()       // 焦点回归触发器本体（B7）
}

function onDocClick(e) {
  if (!settingsOpen.value) return
  if (popoverRef.value?.contains(e.target) || gearWrapRef.value?.contains(e.target)) return
  closeSettings()
}

function onKeydown(e) {
  if (e.key === 'Escape' && settingsOpen.value) closeSettings()
}

watch(settingsOpen, (open) => {
  if (open) {
    document.addEventListener('click', onDocClick)
    document.addEventListener('keydown', onKeydown)
  } else {
    document.removeEventListener('click', onDocClick)
    document.removeEventListener('keydown', onKeydown)
  }
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <!-- relative + z-30：头部**自身建层叠上下文**，否则弹层的 z-30 出不去、会被气泡遮挡
       （PR #40 踩过的坑）。引用浮层是 z-20，弹层 z-30 天然盖住它，互不干扰。 -->
  <div class="relative h-14 shrink-0 px-3 flex items-center justify-between gap-2
              chat-surface z-30">
    <!-- 头像 + 名字 pill（点击开详情，复用现有能力） -->
    <CharacterPhotoField :character="character" />

    <div class="flex items-center gap-2">
      <!-- 移动端会话抽屉入口（spec §4.2「头部菜单按钮」；lg:hidden = 桌面端列表常驻无需） -->
      <button type="button"
              class="lg:hidden chat-icon-btn-solid chat-focus btn btn-sm btn-circle btn-ghost"
              aria-label="打开会话列表"
              data-tip="会话"
              @click="emits('openDrawer')">
        ☰
      </button>

      <!-- ⚙ 设置（4B：简约背景开关落点，D4B-4） -->
      <div ref="gearWrapRef" class="relative">
        <button ref="gearBtnRef"
                type="button"
                class="chat-icon-btn-solid chat-focus btn btn-sm btn-circle btn-ghost"
                aria-label="聊天设置"
                :aria-expanded="settingsOpen ? 'true' : 'false'"
                data-tip="设置"
                @click="settingsOpen = !settingsOpen">
          <SettingsIcon />
        </button>

        <div v-if="settingsOpen" ref="popoverRef"
             class="chat-modal absolute right-0 top-12 z-30 w-64 rounded-xl border
                    p-3 shadow-xl"
             role="dialog" aria-label="聊天设置">
          <div class="flex items-center justify-between gap-3">
            <span class="chat-text text-sm">简约背景</span>
            <button type="button" role="switch"
                    :aria-checked="simpleBg ? 'true' : 'false'"
                    aria-label="简约背景"
                    class="chat-switch-track relative h-5 w-9 shrink-0 rounded-full transition-colors cursor-pointer"
                    :class="{ on: simpleBg }"
                    @click="emits('toggleSimpleBg')">
              <span class="chat-switch-knob absolute top-0.5 h-4 w-4 rounded-full transition-all"
                    :style="{ left: simpleBg ? '18px' : '2px' }"></span>
            </button>
          </div>
          <!-- 生效范围说明：上一次被否的原因之一是"全局偏好但界面没说明"（D4B-3） -->
          <p class="chat-text-2 text-xs mt-1.5">{{ scopeLabel }}</p>
        </div>
      </div>

      <VoiceToggle />
      <button type="button"
              class="chat-icon-btn-solid chat-focus btn btn-sm btn-circle btn-ghost"
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
