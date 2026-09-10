// frontend/src/composables/__tests__/useChatSettings.test.js
// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

beforeEach(() => {
  localStorage.clear()
  vi.resetModules()
})

const load = () => import('../useChatSettings.js')

describe('useChatSettings（LD §3.11 / D-L7）', () => {
  it('默认两项均关闭', async () => {
    const { useChatSettings } = await load()
    const s = useChatSettings()
    expect(s.simpleBackground.value).toBe(false)
    expect(s.autoSendVoice.value).toBe(false)
  })

  it('读取已持久化的 true', async () => {
    localStorage.setItem('chatSimpleBg', 'true')
    localStorage.setItem('chatAutoSendVoice', 'true')
    const { useChatSettings } = await load()
    const s = useChatSettings()
    expect(s.simpleBackground.value).toBe(true)
    expect(s.autoSendVoice.value).toBe(true)
  })

  it('toggleSimple 写入 localStorage（新模块实例可读回）', async () => {
    const first = await load()
    first.useChatSettings().toggleSimple()
    await nextTick()   // 持久化在 watch 回调（微任务）中执行，断言前先等一次刷新
    expect(localStorage.getItem('chatSimpleBg')).toBe('true')

    vi.resetModules()
    const second = await load()
    expect(second.useChatSettings().simpleBackground.value).toBe(true)
  })

  it('toggleAutoSend 独立 key，互不串扰', async () => {
    const { useChatSettings } = await load()
    const s = useChatSettings()
    s.toggleAutoSend()
    await nextTick()   // 同上：等 watch 回调落盘后再断言 localStorage
    expect(localStorage.getItem('chatAutoSendVoice')).toBe('true')
    expect(localStorage.getItem('chatSimpleBg')).toBe(null)
    expect(s.simpleBackground.value).toBe(false)
  })

  it('localStorage 抛错（隐私模式）→ 降级为默认 false，不崩', async () => {
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError')
    })
    const { useChatSettings } = await load()
    expect(useChatSettings().simpleBackground.value).toBe(false)
    spy.mockRestore()
  })

  it('写入失败（setItem 抛错）→ 不崩，内存状态仍翻转', async () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
    const { useChatSettings } = await load()
    const s = useChatSettings()
    expect(() => s.toggleSimple()).not.toThrow()
    await nextTick()
    expect(s.simpleBackground.value).toBe(true)
    spy.mockRestore()
  })
})
