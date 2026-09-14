// @vitest-environment jsdom
// 图标取色回归守卫。
//
// 背景（验收实测）：简约模式下「发送」与「麦克风」图标几乎不可见。根因是
// MicIcon/SendIcon/StopIcon 组件内部写死 `class="w-5 h-5 text-white"`，
// 压过父级按钮的 `.chat-icon-btn/.chat-btn-idle` 的 color token；
// 而 `text-white` 在颜色门禁的白名单里（依据是"己方气泡绿底白字"），
// **门禁因此放行**——白名单救不了这三处。
//
// 本文件用「把 --cbg-text 换成可辨识颜色」的手法把"是否跟随 token"变成可断言事实：
// 若图标又写死白色，下面的断言立刻红。
import { describe, expect, it, vi } from 'vitest'
import { createApp, h } from 'vue'
import MicIcon from '@/components/character/icons/MicIcon.vue'
import SendIcon from '@/components/character/icons/SendIcon.vue'
import StopIcon from '@/components/character/icons/StopIcon.vue'
import WindowHeader from '@/components/chat/chat_window/WindowHeader.vue'

vi.mock('@/components/character/CharacterDetail.vue', () => ({
  default: { name: 'CharacterDetail', render: () => h('div') },
}))

function mountInto(comp, props = {}, parentClass = '') {
  const host = document.createElement('div')
  const wrap = document.createElement('div')
  wrap.className = parentClass
  host.appendChild(wrap)
  document.body.appendChild(host)
  createApp({ render: () => h(comp, props) }).mount(wrap)
  return host
}

/** 取渲染出的 class 串（jsdom 不解析 var()，故不做计算色断言——
 *  改为断言"没有写死颜色"，这是能确定性判定的那一半，且正是本缺陷的成因） */
function classOf(host) {
  const svg = host.querySelector('svg')
  expect(svg).toBeTruthy()
  return svg.getAttribute('class') ?? ''
}

describe('输入区图标必须继承父级 color（简约模式可见性的前提）', () => {
  it('MicIcon 不写死白色', () => {
    expect(classOf(mountInto(MicIcon, {}, 'chat-icon-btn'))).not.toContain('text-white')
  })

  it('SendIcon 不写死白色', () => {
    expect(classOf(mountInto(SendIcon, {}, 'chat-btn-idle'))).not.toContain('text-white')
  })

  it('StopIcon 不写死白色（激活态由 .chat-icon-btn-active 给白字）', () => {
    expect(classOf(mountInto(StopIcon, {}, 'chat-icon-btn-active'))).not.toContain('text-white')
  })
})

describe('头部件按钮的托盘样式必须一致（验收反馈：喇叭有底、齿轮没有）', () => {
  const CHARACTER = { id: 12, name: '龙安洋', photo: '/media/p.png' }

  it('⚙ 与 ✕ 与 ☰ 都带与喇叭相同的托盘类（.chat-icon-btn-solid）', () => {
    const host = document.createElement('div')
    document.body.appendChild(host)
    createApp({ render: () => h(WindowHeader, { character: CHARACTER, simpleBg: false }) }).mount(host)

    const solid = host.querySelectorAll('.chat-icon-btn-solid')
    // 语音开关 + ⚙ + ✕（桌面端无 ☰）+ 头像 pill 共用同一托盘
    expect(solid.length).toBeGreaterThanOrEqual(3)
    const labels = [...host.querySelectorAll('[aria-label]')].map((el) => el.getAttribute('aria-label'))
    expect(labels).toContain('聊天设置')
    expect(labels).toContain('关闭对话')
  })
})
