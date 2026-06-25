import { ref, watch } from 'vue'

// 模块级单例：多个组件共享同一状态，避免重复读 localStorage
const voiceEnabled = ref(localStorage.getItem('voiceEnabled') !== 'false')

// 持久化到 localStorage，刷新不丢失
watch(voiceEnabled, (val) => {
  localStorage.setItem('voiceEnabled', val.toString())
})

export function useVoiceToggle() {
  function toggle() {
    voiceEnabled.value = !voiceEnabled.value
  }

  return { voiceEnabled, toggle }
}
