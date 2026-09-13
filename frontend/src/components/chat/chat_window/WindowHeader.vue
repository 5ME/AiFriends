<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import CharacterPhotoField from '@/components/character/chat_field/character_photo_field/CharacterPhotoField.vue'
import VoiceToggle from '@/components/character/chat_field/VoiceToggle.vue'
import SettingsIcon from '@/components/character/icons/SettingsIcon.vue'
import MenuIcon from '@/components/character/icons/MenuIcon.vue'
import { useChatSettings } from '@/composables/useChatSettings'

defineProps(['character'])
const emits = defineEmits(['close', 'openDrawer'])

// ⚙ 设置弹层（LD §3.5 / Q6 落点）：点击外部关闭
const settingsOpen = ref(false)
const settingsRef = ref(null)
// 模块级单例：InputField 通过同一实例读取 autoSendVoice（LD D-L7）
const { simpleBackground, autoSendVoice, toggleSimple, toggleAutoSend } = useChatSettings()

function onDocClick(e) {
  if (settingsOpen.value && settingsRef.value && !settingsRef.value.contains(e.target)) {
    settingsOpen.value = false
  }
}
onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))
</script>

<template>
  <!-- Phase 4 修复（2026-09-13 验收反馈「设置弹层会被虚拟角色的气泡遮挡」）：
       本容器有 backdrop-blur → **自身即层叠上下文**，其内部弹层的 z-30 只在
       本上下文内有效，无法越过兄弟节点 ChatHistory 的 z-10。
       故给头部本身 z-20，使整个头部（含弹层）位于消息列表之上。 -->
  <div class="h-14 shrink-0 px-3 flex items-center justify-between gap-2
              bg-black/40 backdrop-blur relative z-20">
    <!-- 头像 + 名字 pill（点击开详情，复用现有能力） -->
    <CharacterPhotoField :character="character" />

    <div class="flex items-center gap-2">
      <!-- 移动端会话抽屉入口（spec §4.2「头部菜单按钮」；lg:hidden = 桌面端列表常驻无需）
           Phase 4 补：原为 emoji "☰"（字体字形，各平台形状不一）→ 改 SVG 图标 -->
      <button type="button"
              class="lg:hidden btn btn-sm btn-circle btn-ghost text-white"
              aria-label="打开会话列表"
              data-tip="会话"
              @click="emits('openDrawer')">
        <MenuIcon />
      </button>
      <VoiceToggle />
      <!-- 设置（简约背景 / 语音自动发送，spec §6.6 + D6；入口形态偏离 spec 原文，登记于 W6）
           Phase 4 补：原为 emoji "⚙" → 改 SVG 图标（SettingsIcon） -->
      <div ref="settingsRef" class="relative">
        <button type="button"
                class="btn btn-sm btn-circle btn-ghost text-white"
                aria-label="设置"
                data-tip="设置"
                @click="settingsOpen = !settingsOpen">
          <SettingsIcon />
        </button>
        <div v-if="settingsOpen"
             class="settings-popup absolute right-0 top-11 z-30 w-52 rounded-xl border border-white/10
                    bg-neutral-900/95 backdrop-blur-xl shadow-2xl p-1.5">
          <label class="flex items-center justify-between gap-3 px-2 py-2 rounded-lg
                        hover:bg-white/10 cursor-pointer text-sm text-white/90">
            <span>简约背景</span>
            <input type="checkbox"
                   class="toggle toggle-sm"
                   :checked="simpleBackground"
                   @change="toggleSimple" />
          </label>
          <label class="flex items-center justify-between gap-3 px-2 py-2 rounded-lg
                        hover:bg-white/10 cursor-pointer text-sm text-white/90">
            <span>语音自动发送</span>
            <input type="checkbox"
                   class="toggle toggle-sm"
                   :checked="autoSendVoice"
                   @change="toggleAutoSend" />
          </label>
        </div>
      </div>
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
