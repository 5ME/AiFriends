// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { createApp, h, nextTick } from 'vue'
import { __resetChatBgState } from '@/composables/useChatBg.js'

vi.mock('@/components/character/chat_field/chat_history/ChatHistory.vue', () => ({
  default: { name: 'ChatHistory', render: () => h('div') },
}))
vi.mock('@/components/character/chat_field/input_field/InputField.vue', () => ({
  default: { name: 'InputField', render: () => h('div') },
}))
// stub 渲染一个真按钮：点击即 emit，测试用真实点击驱动（比 __vueParentComponent 稳，
// 后者只在 Vue 的 dev 构建下存在）
vi.mock('@/components/chat/chat_window/WindowHeader.vue', () => ({
  default: {
    name: 'WindowHeader',
    props: ['character', 'simpleBg'],
    emits: ['close', 'openDrawer', 'toggleSimpleBg'],
    setup(props, { emit }) {
      return () => h('button', {
        class: 'stub-header',
        type: 'button',
        onClick: () => emit('toggleSimpleBg'),
      })
    },
  },
}))

import ChatWindow from '../ChatWindow.vue'

const FRIEND = {
  id: 3,
  character: { id: 12, name: '龙安洋', background_image: '/media/bg.png' },
}

function mount(friend = FRIEND) {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp({ render: () => h(ChatWindow, { friend }) })
  app.mount(host)
  return host
}

describe('ChatWindow 简约模式接线（4B T3）', () => {
  beforeEach(() => {
    localStorage.clear()
    __resetChatBgState()   // ⚠️ 必须：模块单例的初值只在首次读存储时取一次。
                           // 只清 localStorage 而不重置内存态 → 种子写不进 state（评审 R-1 实测：
                           // 用例 2 必红、用例 3 假通过）
  })

  it('默认沉浸：窗口根无 chat-simple，舞台无 stage-simple', () => {
    const host = mount()
    expect(host.querySelector('.chat-window')?.className).not.toContain('chat-simple')
    expect(host.querySelector('.chat-stage-root')?.className).not.toContain('stage-simple')
  })

  it('开关为真时，窗口与舞台同时加类（同色调，D4B-2）', async () => {
    localStorage.setItem('chatSimpleBg', JSON.stringify({ 12: true }))
    __resetChatBgState()      // 种子写入存储后必须同步进内存态
    const host = mount()
    await nextTick()
    expect(host.querySelector('.chat-window')?.className).toContain('chat-simple')
    expect(host.querySelector('.chat-stage-root')?.className).toContain('stage-simple')
  })

  it('切换仅影响当前角色（每角色独立，D4B-3）', async () => {
    localStorage.setItem('chatSimpleBg', JSON.stringify({ 99: true }))
    __resetChatBgState()
    const host = mount()
    await nextTick()
    expect(host.querySelector('.chat-window')?.className).not.toContain('chat-simple')
  })

  // ⚠️ 必需：真实交互路径。仅在 mount 前写 localStorage 的用例**无法**发现
  // "computed 读非响应式数据"这类缺陷（评审探针已证），必须由点击驱动一次。
  it('点击开关后窗口与舞台类名同时更新（交互路径）', async () => {
    const host = mount()
    await nextTick()
    expect(host.querySelector('.chat-window')?.className).not.toContain('chat-simple')

    // WindowHeader 在本测试中被 stub 成一个真按钮：直接点击（真实交互路径）
    host.querySelector('.stub-header').click()
    await nextTick()
    expect(host.querySelector('.chat-window')?.className).toContain('chat-simple')
    expect(host.querySelector('.chat-stage-root')?.className).toContain('stage-simple')
    expect(JSON.parse(localStorage.getItem('chatSimpleBg'))).toEqual({ 12: true })
  })

  it('无背景图的角色：不渲染背景图与蒙层（E2）', async () => {
    const host = mount({ id: 4, character: { id: 21, name: '无图', background_image: '' } })
    await nextTick()
    expect(host.querySelector('.window-scrim')).toBeNull()
    expect(host.querySelector('.chat-window')?.className).toContain('no-bg')
  })
})
