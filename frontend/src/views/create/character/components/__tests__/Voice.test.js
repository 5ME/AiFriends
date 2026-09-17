// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick } from 'vue'

vi.mock('@/js/http/api', () => ({ default: { get: vi.fn() } }))
import api from '@/js/http/api'
import Voice from '../Voice.vue'

const VOICES = [
  { id: 1, name: '龙安洋', profile: '阳光大男孩', is_mine: false, status: 'ready' },
  { id: 2, name: '龙安欢', profile: '欢脱元气女', is_mine: false, status: 'ready' },
  { id: 3, name: '我的音色', profile: '审核中的', is_mine: true, status: 'deploying' },
]

function mount(props) {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp({ render: () => h(Voice, props) })
  app.mount(host)
  return host
}

describe('Voice.vue（试听与 profile 展示）', () => {
  beforeEach(() => {
    document.body.innerHTML = ''      // 清掉上个用例挂载的节点
    api.get.mockReset()
    global.Audio = class {
      constructor(src) { this.src = src }
      play() { return Promise.resolve() }
      pause() {}
    }
  })

  it('渲染全部音色名，且只渲染当前音色的 profile', () => {
    const host = mount({ voices: VOICES, curVoice: 2 })
    expect(host.textContent).toContain('龙安洋')
    expect(host.textContent).toContain('龙安欢')
    expect(host.textContent).toContain('欢脱元气女')
    expect(host.textContent).not.toContain('阳光大男孩')
  })

  it('点击试听会请求 sample 接口', async () => {
    api.get.mockResolvedValue({ data: { url: 'https://example.test/media/voice_samples/a.mp3' } })
    const host = mount({ voices: VOICES, curVoice: 1 })
    host.querySelector('[data-test="voice-sample-btn"]').click()
    await nextTick()
    await Promise.resolve()
    expect(api.get).toHaveBeenCalledWith('/api/create/character/voice/sample/',
                                         { params: { voice: 1 } })
  })

  it('切换音色会停掉正在播的试听，按钮复位为「试听」', async () => {
    api.get.mockResolvedValue({ data: { url: 'https://example.test/media/voice_samples/a.mp3' } })
    const host = mount({ voices: VOICES, curVoice: 1 })
    const btnText = () => host.querySelector('[data-test="voice-sample-btn"]').textContent

    host.querySelector('[data-test="voice-sample-btn"]').click()
    await Promise.resolve()
    await nextTick()
    expect(btnText()).toContain('停止')

    const select = host.querySelector('select')
    select.value = '2'
    select.dispatchEvent(new Event('change'))
    await nextTick()
    expect(btnText()).toContain('试听')
  })

  it('按归属分成「我的音色」与「平台音色」两组', () => {
    const host = mount({ voices: VOICES, curVoice: 1 })
    const labels = [...host.querySelectorAll('optgroup')].map(g => g.getAttribute('label'))
    expect(labels).toEqual(['我的音色', '平台音色'])

    const mine = host.querySelector('optgroup[label="我的音色"]')
    const platform = host.querySelector('optgroup[label="平台音色"]')
    expect(mine.textContent).toContain('我的音色')
    expect(mine.textContent).toContain('（审核中）')      // 非 ready 的选项带状态标注
    expect(mine.textContent).not.toContain('龙安洋')
    expect(platform.textContent).toContain('龙安洋')
    expect(platform.textContent).toContain('龙安欢')
  })

  it('非 ready 音色的试听按钮禁用，且点击不发请求', async () => {
    const host = mount({ voices: VOICES, curVoice: 3 })
    const btn = host.querySelector('[data-test="voice-sample-btn"]')
    expect(btn.disabled).toBe(true)
    btn.click()
    await nextTick()
    expect(api.get).not.toHaveBeenCalled()
  })
})
