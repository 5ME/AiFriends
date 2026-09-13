import { ref, watch } from 'vue'

// 模块级单例（LD D-L7）：ref 定义在模块顶层，多个组件共享同一状态。
// 参照 useVoiceToggle.js:4 的既有模式 —— 若写成函数内 ref，WindowHeader 与
// InputField 会各持一份，开关将失效。
const STORAGE_KEYS = {
  simpleBackground: 'chatSimpleBg',
  autoSendVoice: 'chatAutoSendVoice',
}

/** 读取布尔设置：只有字符串 'true' 才算开启，其余（null / 'false' / '1'）一律 false */
function readBool(key) {
  if (typeof localStorage === 'undefined') return false
  return localStorage.getItem(key) === 'true'
}

const simpleBackground = ref(readBool(STORAGE_KEYS.simpleBackground))
const autoSendVoice = ref(readBool(STORAGE_KEYS.autoSendVoice))

watch(simpleBackground, (val) => {
  localStorage.setItem(STORAGE_KEYS.simpleBackground, val.toString())
})
watch(autoSendVoice, (val) => {
  localStorage.setItem(STORAGE_KEYS.autoSendVoice, val.toString())
})

/**
 * 聊天页用户设置（模块级单例）。
 *
 * - simpleBackground：简约背景。开启后窗口背景由角色背景图改为深色纯色，
 *   作为"背景图不可读"的用户降级通道（spec C3 硬要求）。
 * - autoSendVoice：语音自动发送。开启后语音识别完成回填输入框，800ms 后自动发出（spec D6 默认关）。
 */
export function useChatSettings() {
  function toggleSimple() {
    simpleBackground.value = !simpleBackground.value
  }

  function toggleAutoSend() {
    autoSendVoice.value = !autoSendVoice.value
  }

  return { simpleBackground, autoSendVoice, toggleSimple, toggleAutoSend }
}
