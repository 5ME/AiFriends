// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { createApp, h, nextTick } from 'vue'
import { __resetChatBgState } from '@/composables/useChatBg.js'
import { __resetSessionPreview, useSessionPreview } from '@/composables/useSessionPreview.js'

vi.mock('@/components/character/chat_field/chat_history/ChatHistory.vue', () => ({
  // scrollToBottom 与真实组件 defineExpose 的方法同名：否则 scheduleScroll 的 rAF
  // 回调会抛 TypeError（噪音，会掩盖真实错误）
  default: { name: 'ChatHistory', render: () => h('div'), methods: { scrollToBottom() {} } },
}))
// InputField stub：渲染真按钮，按真实时序发事件（发送 → 流开始 → 增量 → 流结束），
// 这样"会话栏预览"这类跨组件接线由真实交互路径驱动，而不是伸手进组件实例
vi.mock('@/components/character/chat_field/input_field/InputField.vue', () => ({
  default: {
    name: 'InputField',
    emits: ['pushBackMessage', 'appendToLastMessage', 'streamState'],
    setup(_, { emit }) {
      return () => h('div', [
        h('button', {
          class: 'stub-send',
          type: 'button',
          onClick: () => {
            emit('pushBackMessage', { role: 'user', content: '我说的话', id: 'u1' })
            emit('pushBackMessage', { role: 'ai', content: '', id: 'a1' })
          },
        }),
        h('button', {
          class: 'stub-stream-start',
          type: 'button',
          onClick: () => emit('streamState', { streaming: true, thinking: false }),
        }),
        h('button', {
          class: 'stub-ai-delta',
          type: 'button',
          onClick: () => emit('appendToLastMessage', 'AI 回复'),
        }),
        h('button', {
          class: 'stub-stream-end',
          type: 'button',
          onClick: () => emit('streamState', { streaming: false, thinking: false }),
        }),
      ])
    },
  },
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

  it('背景图加载失败时走深色兜底（E3）：Image 预探测 onerror', async () => {
    // 用 stub 的 Image 强制触发 onerror —— 真实浏览器里"坏图地址"走的就是这条路径。
    // 这样 E3 无需去造一个坏 URL 就能自动化验证。
    const OriginalImage = globalThis.Image
    globalThis.Image = class {
      set src(_v) { queueMicrotask(() => this.onerror && this.onerror()) }
    }
    try {
      const host = mount()
      await nextTick()
      await nextTick()   // 等 onerror 的微任务落地
      expect(host.querySelector('.chat-window')?.className).toContain('no-bg')
      expect(host.querySelector('.window-scrim')).toBeNull()
      expect(host.querySelector('.chat-stage-root')?.className).toContain('no-bg')
    } finally {
      globalThis.Image = OriginalImage
    }
  })

  it('无背景图的角色：不渲染背景图与蒙层（E2）', async () => {
    const host = mount({ id: 4, character: { id: 21, name: '无图', background_image: '' } })
    await nextTick()
    expect(host.querySelector('.window-scrim')).toBeNull()
    expect(host.querySelector('.chat-window')?.className).toContain('no-bg')
  })
})

describe('ChatWindow 会话栏预览接线（M 档）', () => {
  beforeEach(() => {
    localStorage.clear()
    __resetChatBgState()
    __resetSessionPreview()
  })

  /** 走一遍真实时序：发送 → 流开始 → （可选）AI 增量 → 流结束 */
  function runTurn(host, { withAiDelta = true } = {}) {
    host.querySelector('.stub-send').click()
    host.querySelector('.stub-stream-start').click()
    if (withAiDelta) host.querySelector('.stub-ai-delta').click()
    host.querySelector('.stub-stream-end').click()
  }

  it('发送即写入用户文本预览（不等 AI 回复），流结束后改写为 AI 回复', async () => {
    const host = mount()
    const { previews } = useSessionPreview()

    host.querySelector('.stub-send').click()
    await nextTick()
    expect(previews[FRIEND.id].text).toBe('我说的话')

    host.querySelector('.stub-stream-start').click()
    host.querySelector('.stub-ai-delta').click()
    await nextTick()
    host.querySelector('.stub-stream-end').click()
    await nextTick()
    expect(previews[FRIEND.id].text).toBe('AI 回复')
  })

  it('AI 内容为空（出错/中断）→ 保留用户文本，不把预览刷成空白', async () => {
    const host = mount()
    const { previews } = useSessionPreview()

    runTurn(host, { withAiDelta: false })
    await nextTick()
    expect(previews[FRIEND.id].text).toBe('我说的话')
  })

  it('从未进入 streaming 的状态变化不写预览（thinking 切换不误触发）', async () => {
    const host = mount()
    const { previews } = useSessionPreview()

    host.querySelector('.stub-stream-end').click()
    await nextTick()
    expect(previews[FRIEND.id]).toBeUndefined()
  })

  it('预览时间跟随写入时刻（会话栏据此显示 HH:mm）', async () => {
    const host = mount()
    const { previews } = useSessionPreview()

    runTurn(host)
    await nextTick()
    expect(Number.isNaN(new Date(previews[FRIEND.id].at).getTime())).toBe(false)
  })
})
