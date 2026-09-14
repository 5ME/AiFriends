// @vitest-environment jsdom
// 说明：本用例覆盖 SessionList 的「预览 store → 置顶」接线。promote() 本身在
// useSessionPreview.test.js 里做过纯函数测试，这里只验线路（列表真的重排、预览真的透传）。
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick } from 'vue'
import { __resetSessionPreview, setPreview } from '@/composables/useSessionPreview.js'

vi.mock('@/js/http/api', () => ({ default: { get: vi.fn() } }))

import api from '@/js/http/api'
import SessionList from '../SessionList.vue'

function makeFriend(id, name, lastMessage) {
  return {
    id,
    last_message: lastMessage,
    last_message_at: new Date(2026, 2, 15, 9, 5).toISOString(),
    character: { id: 100 + id, name, photo: '/media/p.png' },
  }
}

/** 等 api promise 落地 + 渲染（nextTick 每轮都会先清空微任务队列，多轮是为了稳） */
async function settle() {
  for (let i = 0; i < 3; i++) await nextTick()
}

async function mountWith(friends) {
  api.get.mockResolvedValue({ data: { friends } })
  const host = document.createElement('div')
  document.body.appendChild(host)
  createApp({ render: () => h(SessionList, { activeId: null }) }).mount(host)
  await settle()
  return host
}

const names = (host) => [...host.querySelectorAll('button')].map((b) => b.textContent.trim())

describe('SessionList 会话栏（M 档：预览透传 + 置顶接线）', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
    __resetSessionPreview()
  })

  it('按接口顺序渲染，并把服务端 last_message 透传给条目', async () => {
    const host = await mountWith([
      makeFriend(3, '龙安洋', '第一条会话的预览'),
      makeFriend(7, '安小然', '第二条会话的预览'),
    ])

    const rows = names(host)
    expect(rows).toHaveLength(2)
    expect(rows[0]).toContain('龙安洋')
    expect(rows[0]).toContain('第一条会话的预览')
    expect(rows[1]).toContain('第二条会话的预览')
  })

  it('本地预览写入 → 该会话置顶且预览文本即时更新（不等重新拉取）', async () => {
    const host = await mountWith([
      makeFriend(3, '龙安洋', '第一条会话的预览'),
      makeFriend(7, '安小然', '第二条会话的预览'),
    ])

    setPreview(7, { text: '刚发出的消息', at: new Date(2026, 2, 15, 12, 0).toISOString() })
    await settle()

    const rows = names(host)
    expect(rows[0]).toContain('安小然')
    expect(rows[0]).toContain('刚发出的消息')
    expect(rows[1]).toContain('龙安洋')
  })

  it('已在首位的会话再次写入预览 → 顺序不变（不抖动）', async () => {
    const host = await mountWith([
      makeFriend(3, '龙安洋', '旧预览'),
      makeFriend(7, '安小然', '第二条会话的预览'),
    ])

    setPreview(3, { text: '新预览', at: new Date(2026, 2, 15, 12, 0).toISOString() })
    await settle()

    const rows = names(host)
    expect(rows[0]).toContain('龙安洋')
    expect(rows[0]).toContain('新预览')
    expect(rows[1]).toContain('安小然')
  })
})
