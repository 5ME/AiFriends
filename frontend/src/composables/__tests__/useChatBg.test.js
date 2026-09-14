// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'
import { watch } from 'vue'
import {
  STORAGE_KEY, parseChatBg, loadChatBgMap, saveChatBgMap, useChatBg, __resetChatBgState,
} from '../useChatBg.js'

describe('useChatBg（4B D4B-3：每角色独立）', () => {
  beforeEach(() => {
    localStorage.clear()
    __resetChatBgState()   // 模块单例的初始值取自存储；清了存储必须同步重置内存态
  })

  it('脏数据/异常输入 → 空对象（不抛错）', () => {
    expect(parseChatBg(null)).toEqual({})
    expect(parseChatBg('')).toEqual({})
    expect(parseChatBg('not json')).toEqual({})
    expect(parseChatBg('[1,2]')).toEqual({})
    expect(parseChatBg('null')).toEqual({})
    expect(parseChatBg('{"12":"yes","37":true,"x":false}')).toEqual({ 37: true })  // 仅保留 boolean
  })

  it('读写往返', () => {
    saveChatBgMap({ 12: true })
    expect(loadChatBgMap()).toEqual({ 12: true })
  })

  it('按角色隔离：A 开不影响 B', () => {
    const a = useChatBg(12)
    const b = useChatBg(37)
    a.setSimple(true)
    expect(a.simpleOn.value).toBe(true)
    expect(b.simpleOn.value).toBe(false)
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY))).toEqual({ 12: true })
  })

  it('toggle 在真/假之间往返并持久化', () => {
    const a = useChatBg(12)
    a.toggleSimple()
    expect(a.simpleOn.value).toBe(true)
    a.toggleSimple()
    expect(a.simpleOn.value).toBe(false)
    expect(loadChatBgMap()).toEqual({ 12: false })
  })

  it('数字与字符串 id 等价（路由参数是字符串，store 可能是数字）', () => {
    useChatBg('12').setSimple(true)
    expect(useChatBg(12).simpleOn.value).toBe(true)
  })

  // 防回流：若有人把实现改回 computed 直读 localStorage，本用例立刻失败
  it('状态是响应式的（交互后同一引用可观察到变化）', () => {
    const a = useChatBg(12)
    const seen = []
    const stop = watch(a.simpleOn, (v) => seen.push(v), { flush: 'sync' })
    a.setSimple(true)
    a.setSimple(false)
    stop()
    expect(seen).toEqual([true, false])
  })

  it('localStorage 抛错时退化为内存态，且读写均不抛（E1）', () => {
    const original = window.localStorage.getItem
    window.localStorage.getItem = () => { throw new Error('QuotaExceededError') }
    expect(() => loadChatBgMap()).not.toThrow()
    expect(loadChatBgMap()).toEqual({})
    window.localStorage.getItem = original
  })
})
