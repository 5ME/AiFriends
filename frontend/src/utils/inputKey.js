// Enter 发送判定（E8 硬性：中文输入法候选状态下 Enter 一律不发送）
export function shouldSendOnEnter(e) {
  if (!e || e.key !== 'Enter') return false
  if (e.isComposing || e.keyCode === 229) return false
  if (e.shiftKey) return false
  return true
}
