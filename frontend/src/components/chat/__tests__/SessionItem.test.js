// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick } from 'vue'
import SessionItem from '../SessionItem.vue'

// 固定"现在"为本地时间 2026-03-15 12:00：时间列断言与机器时区无关
// （时区用 Date 本地构造 + fake timer，避免 ISO 串在 UTC 机器上跨日）
const NOW = new Date(2026, 2, 15, 12, 0, 0)

function makeSession(over = {}) {
  return {
    id: 3,
    last_message: '第二句回复',
    last_message_at: new Date(2026, 2, 15, 9, 5).toISOString(),
    character: { id: 12, name: '龙安洋', photo: '/media/p.png' },
    ...over,
  }
}

function mount(props) {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp({ render: () => h(SessionItem, props) })
  app.mount(host)
  return host
}

describe('SessionItem 会话栏条目（M 档：最后消息预览 + 时间）', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.useFakeTimers()
    vi.setSystemTime(NOW)
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('渲染名字、服务端预览与时间（今天 → HH:mm）', () => {
    const text = mount({ session: makeSession(), active: false })
      .querySelector('button').textContent

    expect(text).toContain('龙安洋')
    expect(text).toContain('第二句回复')
    expect(text).toContain('09:05')
  })

  it('无消息的好友 → 占位文案「还没有消息」，不渲染时间', () => {
    const text = mount({
      session: makeSession({ last_message: '', last_message_at: null }),
      active: false,
    }).querySelector('button').textContent

    expect(text).toContain('还没有消息')
    expect(text).not.toMatch(/\d{2}:\d{2}/)
  })

  it('本地预览（preview prop）覆盖服务端值 —— 发送后的乐观更新', () => {
    const text = mount({
      session: makeSession(),
      active: false,
      preview: { text: 'AI 刚说的话', at: new Date(2026, 2, 15, 12, 0).toISOString() },
    }).querySelector('button').textContent

    expect(text).toContain('AI 刚说的话')
    expect(text).not.toContain('第二句回复')
    expect(text).toContain('12:00')   // 时间列同样跟随本地预览
  })

  it('preview 文本为空（脏数据）→ 回退服务端值，不刷成空白', () => {
    const text = mount({
      session: makeSession(),
      active: false,
      preview: { text: '', at: new Date(2026, 2, 15, 12, 0).toISOString() },
    }).querySelector('button').textContent

    expect(text).toContain('第二句回复')
  })

  it('点击 → emit select(character.id)', async () => {
    let selected = null
    const host = document.createElement('div')
    document.body.appendChild(host)
    createApp({
      render: () => h(SessionItem, {
        session: makeSession(),
        active: false,
        onSelect: (id) => { selected = id },
      }),
    }).mount(host)

    host.querySelector('button').click()
    await nextTick()
    expect(selected).toBe(12)
  })

  it('选中态 → session-active + aria-current="true"；未选中 → session-inactive 且无 aria-current', () => {
    const activeBtn = mount({ session: makeSession(), active: true }).querySelector('button')
    expect(activeBtn.className).toContain('session-active')
    expect(activeBtn.getAttribute('aria-current')).toBe('true')

    const idleBtn = mount({ session: makeSession(), active: false }).querySelector('button')
    expect(idleBtn.className).toContain('session-inactive')
    expect(idleBtn.getAttribute('aria-current')).toBeNull()
  })

  it('时间列对读屏隐藏（避免可访问名称里夹一个裸时间），预览保留在可访问名称中', () => {
    const btn = mount({ session: makeSession(), active: false }).querySelector('button')
    const hidden = [...btn.querySelectorAll('[aria-hidden="true"]')]

    expect(hidden.map((el) => el.textContent.trim())).toEqual(['09:05'])
    expect(btn.textContent).toContain('第二句回复')
  })
})

describe('SessionItem 弱化文字的颜色契约（评审 F1 修复）', () => {
  // 底色最差的是"选中行"（accent 40% 叠在 base-200 上）：深色主题下旧写法
  // text-neutral-500 只有 1.67:1。改用主题自适应的 base-content/80 后，
  // 6 个场景（浅/深 × 普通/hover/选中）实测最差 5.37:1，全部过 AA 4.5:1。
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.useFakeTimers()
    vi.setSystemTime(NOW)
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('预览行与时间列用 text-base-content/80，不用 text-neutral-500', () => {
    const btn = mount({ session: makeSession(), active: false }).querySelector('button')
    const time = btn.querySelector('[aria-hidden="true"]')
    const preview = btn.querySelector('p')

    for (const el of [time, preview]) {
      expect(el).toBeTruthy()
      expect(el.className).toContain('text-base-content/80')
      expect(el.className).not.toContain('text-neutral-500')
    }
  })

  it('无消息占位文案与预览共用同一颜色（占位也是需要读的文字）', () => {
    const btn = mount({
      session: makeSession({ last_message: '', last_message_at: null }),
      active: false,
    }).querySelector('button')

    expect(btn.querySelector('p').className).toContain('text-base-content/80')
  })
})
