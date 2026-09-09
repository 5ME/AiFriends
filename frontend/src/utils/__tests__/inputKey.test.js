import { describe, it, expect } from 'vitest'
import { shouldSendOnEnter } from '../inputKey'

describe('shouldSendOnEnter（spec §5.3 / E8 硬性）', () => {
  it('普通 Enter → true', () => {
    expect(shouldSendOnEnter({ key: 'Enter', isComposing: false, keyCode: 13, shiftKey: false })).toBe(true)
  })
  it('非 Enter 键 → false', () => {
    expect(shouldSendOnEnter({ key: 'a', isComposing: false, keyCode: 65, shiftKey: false })).toBe(false)
  })
  it('IME 组合中（isComposing）→ false', () => {
    expect(shouldSendOnEnter({ key: 'Enter', isComposing: true, keyCode: 13, shiftKey: false })).toBe(false)
  })
  it('IME 组合中（keyCode 229）→ false', () => {
    expect(shouldSendOnEnter({ key: 'Enter', isComposing: false, keyCode: 229, shiftKey: false })).toBe(false)
  })
  it('Shift+Enter（换行）→ false', () => {
    expect(shouldSendOnEnter({ key: 'Enter', isComposing: false, keyCode: 13, shiftKey: true })).toBe(false)
  })
  it('缺事件对象 → false（防御）', () => {
    expect(shouldSendOnEnter(null)).toBe(false)
  })
})
