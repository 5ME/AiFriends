
// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest'
import { createApp, h } from 'vue'

vi.mock('@/components/character/CharacterDetail.vue', () => ({
  default: { name: 'CharacterDetail', render: () => h('div') },
}))
import WindowHeader from '../WindowHeader.vue'

const CHARACTER = { id: 12, name: '龙安洋', photo: '/media/p.png' }

function mount(simpleBg = false) {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp({
    render: () => h(WindowHeader, { character: CHARACTER, simpleBg }),
  })
  app.mount(host)
  return host
}

describe('WindowHeader 设置弹层（4B T4）', () => {
  it('默认不显示弹层；⚙ 有可访问名称', () => {
    const host = mount()
    expect(host.querySelector('[role="dialog"], .chat-popover')).toBeNull()
    expect(host.querySelector('button[aria-label="聊天设置"]')).toBeTruthy()
  })

  it('点击 ⚙ 打开弹层，开关状态与 simpleBg 同步', async () => {
    const host = mount(true)
    host.querySelector('button[aria-label="聊天设置"]').click()
    await new Promise((r) => setTimeout(r))
    const sw = host.querySelector('[role="switch"]')
    expect(sw).toBeTruthy()
    expect(sw.getAttribute('aria-checked')).toBe('true')
  })

  it('弹层明示生效范围（含角色名）——B5 硬性断言', async () => {
    const host = mount()
    host.querySelector('button[aria-label="聊天设置"]').click()
    await new Promise((r) => setTimeout(r))
    expect(host.textContent).toContain('仅对《龙安洋》生效')
  })

  it('开关触发 toggleSimpleBg 事件', async () => {
    const host = document.createElement('div')
    document.body.appendChild(host)
    const onToggle = vi.fn()
    createApp({
      render: () => h(WindowHeader, { character: CHARACTER, simpleBg: false, onToggleSimpleBg: onToggle }),
    }).mount(host)
    host.querySelector('button[aria-label="聊天设置"]').click()
    await new Promise((r) => setTimeout(r))
    host.querySelector('[role="switch"]').click()
    expect(onToggle).toHaveBeenCalled()
  })
})
