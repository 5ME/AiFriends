// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick } from 'vue'

vi.mock('@/js/http/api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
import api from '@/js/http/api'
import MyVoiceManager from '../MyVoiceManager.vue'

const VOICES = [
  { id: 1, name: '龙安洋', profile: '阳光大男孩', is_mine: false, status: 'ready' },
  { id: 2, name: '我的音色', profile: '温柔', is_mine: true, status: 'deploying' },
  { id: 3, name: '被拒的', profile: '', is_mine: true, status: 'rejected' },
]

function mount(props) {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp({ render: () => h(MyVoiceManager, props) })
  app.mount(host)
  return host
}

async function openForm(host) {
  host.querySelector('[data-test="toggle-upload"]').click()
  await nextTick()
}

function setFile(host, file) {
  const input = host.querySelector('[data-test="sample-input"]')
  Object.defineProperty(input, 'files', { value: [file], configurable: true })
  input.dispatchEvent(new Event('change'))
}

async function fillForm(host, { name = '我的新音色', consent = true } = {}) {
  const nameInput = host.querySelector('[data-test="voice-name-input"]')
  nameInput.value = name
  nameInput.dispatchEvent(new Event('input'))
  host.querySelector('[data-test="consent-checkbox"]').checked = consent
  host.querySelector('[data-test="consent-checkbox"]').dispatchEvent(new Event('change'))
  await nextTick()
}

describe('MyVoiceManager（我的音色：上传 / 状态 / 删除）', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    api.get.mockReset()
    api.post.mockReset()
    api.post.mockResolvedValue({ data: { message: 'success' } })
    global.confirm = vi.fn(() => true)
  })

  it('只列出我的音色，并带状态标注', () => {
    const host = mount({ voices: VOICES })
    expect(host.textContent).toContain('我的音色')
    expect(host.textContent).toContain('审核中')
    expect(host.textContent).toContain('审核未通过')
    expect(host.textContent).not.toContain('龙安洋')     // 平台音色不进这个列表
  })

  it('未勾选授权声明时拦住提交，不发请求', async () => {
    const host = mount({ voices: VOICES })
    await openForm(host)
    setFile(host, new File(['ID3x'], 's.mp3', { type: 'audio/mpeg' }))
    await fillForm(host, { consent: false })
    host.querySelector('[data-test="clone-submit"]').click()
    await nextTick()
    expect(api.post).not.toHaveBeenCalled()
    expect(host.textContent).toContain('授权')
  })

  it('超过 8MB 的文件在前端就被拦住，不发请求', async () => {
    const host = mount({ voices: VOICES })
    await openForm(host)
    setFile(host, new File([new ArrayBuffer(8 * 1024 * 1024 + 1)], 'big.mp3'))
    await fillForm(host)
    host.querySelector('[data-test="clone-submit"]').click()
    await nextTick()
    expect(api.post).not.toHaveBeenCalled()
    expect(host.textContent).toContain('8MB')
  })

  it('提交调用 clone 接口，FormData 含 file/name/profile/consent', async () => {
    const host = mount({ voices: VOICES })
    await openForm(host)
    setFile(host, new File(['ID3x'], 's.mp3', { type: 'audio/mpeg' }))
    await fillForm(host)
    host.querySelector('[data-test="clone-submit"]').click()
    await nextTick()
    await Promise.resolve()
    expect(api.post).toHaveBeenCalled()
    const [url, fd] = api.post.mock.calls[0]
    expect(url).toBe('/api/create/character/voice/clone/')
    expect(fd.get('name')).toBe('我的新音色')
    expect(fd.get('consent')).toBe('true')
    expect(fd.get('file').name).toBe('s.mp3')
  })

  it('删除按钮调用 remove 接口', async () => {
    const host = mount({ voices: VOICES })
    host.querySelector('[data-test="voice-remove-2"]').click()
    await nextTick()
    await Promise.resolve()
    expect(api.post).toHaveBeenCalledWith('/api/create/character/voice/remove/',
                                          { voice: 2 })
  })

  it('隐私说明不过度承诺：不含"全链路"与"已删除"', async () => {
    // ⚠️ 别写成 not.toContain('删除')：被批准的文案本身就含"我们会立即删除"，
    //    那样写必然失败，而"让它通过"的最短路径是把文案改弱 —— 正好毁掉 spec §8 的要求
    const host = mount({ voices: VOICES })
    await openForm(host)
    expect(host.textContent).toContain('立即删除')
    expect(host.textContent).not.toContain('全链路')
    expect(host.textContent).not.toContain('已删除')
  })
})
