import { ref, watch } from 'vue'

const KEY_SIMPLE_BG = 'chatSimpleBg'
const KEY_AUTO_SEND = 'chatAutoSendVoice'

function readFlag(key) {
  try {
    return localStorage.getItem(key) === 'true'
  } catch (e) {
    return false   // 隐私模式/禁用存储：降级为「关闭」，不阻塞
  }
}

function writeFlag(key, value) {
  try {
    localStorage.setItem(key, String(value))
  } catch (e) {
    // 配额/隐私模式：静默丢弃持久化，本次会话内仍生效
  }
}

// 模块级单例（仿 useVoiceToggle）：WindowHeader 设置弹层与 InputField 自动发送共享同一状态
const simpleBackground = ref(readFlag(KEY_SIMPLE_BG))
const autoSendVoice = ref(readFlag(KEY_AUTO_SEND))

watch(simpleBackground, (v) => writeFlag(KEY_SIMPLE_BG, v))
watch(autoSendVoice, (v) => writeFlag(KEY_AUTO_SEND, v))

/**
 * 用户级聊天设置（LD §3.11 / D-L7）：模块级单例，无参调用，返回共享 ref 与两个切换函数。
 * 消费方：WindowHeader 设置弹层（简约背景）、InputField 语音自动发送。
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
