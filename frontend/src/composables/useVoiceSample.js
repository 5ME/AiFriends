// 模块级单例：同一时刻只允许一段试听在播
let current = null

export function stopCurrentSample() {
  if (current) {
    current.pause()
    current = null
  }
}

export function playSample(url) {
  stopCurrentSample()
  const el = new Audio(url)
  current = el
  el.play().catch(() => {})
  return el
}

export function isCurrentSample(el) {
  return current === el
}
