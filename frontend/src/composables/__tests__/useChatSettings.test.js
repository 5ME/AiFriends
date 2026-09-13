import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

/** 用 vi.resetModules + 动态 import 拿到全新模块实例，避免模块级单例跨用例串状态 */
async function freshModule() {
  vi.resetModules()
  return await import('../useChatSettings')
}

/** 内存版 localStorage，避免污染 jsdom */
function installMemoryStorage(seed = {}) {
  const map = new Map(Object.entries(seed))
  const store = {
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => map.set(k, String(v)),
    removeItem: (k) => map.delete(k),
  }
  vi.stubGlobal('localStorage', store)
  return store
}

describe('useChatSettings（模块级单例，LD D-L7）', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
  })

  it('默认值：简约背景关、语音自动发送关（spec D6）', async () => {
    installMemoryStorage()
    const { useChatSettings } = await freshModule()
    const s = useChatSettings()
    expect(s.simpleBackground.value).toBe(false)
    expect(s.autoSendVoice.value).toBe(false)
  })

  it('toggleSimple 翻转，nextTick 后写入 chatSimpleBg = "true"', async () => {
    const store = installMemoryStorage()
    const { useChatSettings } = await freshModule()
    const s = useChatSettings()

    s.toggleSimple()
    expect(s.simpleBackground.value).toBe(true)
    await nextTick()
    expect(store.getItem('chatSimpleBg')).toBe('true')

    s.toggleSimple()
    expect(s.simpleBackground.value).toBe(false)
    await nextTick()
    expect(store.getItem('chatSimpleBg')).toBe('false')
  })

  it('toggleAutoSend 翻转，nextTick 后写入 chatAutoSendVoice = "true"', async () => {
    const store = installMemoryStorage()
    const { useChatSettings } = await freshModule()
    const s = useChatSettings()

    s.toggleAutoSend()
    expect(s.autoSendVoice.value).toBe(true)
    await nextTick()
    expect(store.getItem('chatAutoSendVoice')).toBe('true')
  })

  it('从 localStorage 恢复（刷新后保持）', async () => {
    installMemoryStorage({ chatSimpleBg: 'true', chatAutoSendVoice: 'true' })
    const { useChatSettings } = await freshModule()
    const s = useChatSettings()
    expect(s.simpleBackground.value).toBe(true)
    expect(s.autoSendVoice.value).toBe(true)
  })

  it('两次调用返回同一状态（单例契约）', async () => {
    installMemoryStorage()
    const { useChatSettings } = await freshModule()
    const a = useChatSettings()
    const b = useChatSettings()
    a.toggleSimple()
    expect(b.simpleBackground.value).toBe(true)   // b 看得到 a 的改动 = 同一份状态
  })

  it('只有字符串 "true" 才算开启', async () => {
    installMemoryStorage({ chatSimpleBg: '1', chatAutoSendVoice: 'yes' })
    const { useChatSettings } = await freshModule()
    const s = useChatSettings()
    expect(s.simpleBackground.value).toBe(false)
    expect(s.autoSendVoice.value).toBe(false)
  })
})
