// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick, reactive } from 'vue'

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

/** 带 emit 探针的挂载：用于观察轮询触发的 refresh 次数 */
function mountWithSpy(voices) {
  const changed = vi.fn()
  const host = document.createElement('div')
  document.body.appendChild(host)
  createApp({
    render: () => h(MyVoiceManager, { voices, onChanged: changed }),
  }).mount(host)
  return { host, changed }
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

  it('有审核中的音色时每 30 秒请求刷新，落地后停止', async () => {
    // 审核实测只要约 15 秒（Beat 是 5 分钟节奏），但界面不轮询的话用户得手动刷新页面
    // 才能看到「可用」—— spec §6.2.9 / 计划 Task 7 都要求这条
    vi.useFakeTimers()
    try {
      const voices = reactive([
        { id: 1, name: '审核中', profile: '', is_mine: true, status: 'deploying' },
      ])
      const { changed } = mountWithSpy(voices)
      await nextTick()
      expect(changed).not.toHaveBeenCalled()     // 挂载时不该立刻刷（父组件刚给过数据）

      await vi.advanceTimersByTimeAsync(30000)
      expect(changed).toHaveBeenCalledTimes(1)
      await vi.advanceTimersByTimeAsync(30000)
      expect(changed).toHaveBeenCalledTimes(2)

      // 全部落地 → 停止轮询
      voices.splice(0, voices.length,
                    { id: 1, name: '审核中', profile: '', is_mine: true, status: 'ready' })
      await nextTick()
      await vi.advanceTimersByTimeAsync(90000)
      expect(changed).toHaveBeenCalledTimes(2)   // 没有新增触发
    } finally {
      vi.useRealTimers()
    }
  })

  it('没有审核中的音色时不轮询', async () => {
    vi.useFakeTimers()
    try {
      const { changed } = mountWithSpy([
        { id: 1, name: '可用的', profile: '', is_mine: true, status: 'ready' },
        { id: 2, name: '被拒的', profile: '', is_mine: true, status: 'rejected' },
      ])
      await nextTick()
      await vi.advanceTimersByTimeAsync(120000)
      expect(changed).not.toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })

  it('轮询有上限：长期停在同一状态时停手，并提示用户自己刷新', async () => {
    // 先例 useDocumentPolling 有 MAX_POLLS + 超时提示；spec 风险 9 也描述过
    // "音色长期停在 deploying"（Beat 只扫 24 小时内的行）—— 没有上限就会无限轮询且不给提示
    vi.useFakeTimers()
    try {
      const voices = reactive([
        { id: 1, name: '卡住的', profile: '', is_mine: true, status: 'deploying' },
      ])
      const { host, changed } = mountWithSpy(voices)
      await nextTick()

      await vi.advanceTimersByTimeAsync(30000 * 25)
      expect(changed).toHaveBeenCalledTimes(20)      // 到上限即停
      expect(host.textContent).toContain('刷新')      // 并告诉用户该怎么办

      // 新的复刻进来（计数变化）→ 重新开始轮询、提示消失
      voices.push({ id: 2, name: '新提交的', profile: '', is_mine: true, status: 'deploying' })
      await nextTick()
      await vi.advanceTimersByTimeAsync(30000)
      expect(changed).toHaveBeenCalledTimes(21)
      expect(host.textContent).not.toContain('刷新')
    } finally {
      vi.useRealTimers()
    }
  })
})
