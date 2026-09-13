// @vitest-environment jsdom
import { describe, expect, it, beforeEach } from 'vitest'
import { createApp, h, nextTick } from 'vue'
import VoiceToggle from '../VoiceToggle.vue'
import { useVoiceToggle } from '@/composables/useVoiceToggle.js'

function mount() {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp({ render: () => h(VoiceToggle) })
  app.mount(host)
  return host
}

describe('VoiceToggle（4A D4A-1：真按钮 + 可访问名称）', () => {
  beforeEach(() => {
    document.body.innerHTML = ''        // 清掉上个用例挂载的节点
    const { voiceEnabled } = useVoiceToggle()
    voiceEnabled.value = true           // 每个用例从已知状态开始
  })

  it('根元素是原生 button 且 type=button（不触发表单提交）', () => {
    const el = mount().querySelector('button')
    expect(el).toBeTruthy()
    expect(el.getAttribute('type')).toBe('button')
  })

  it('可访问名称随状态变化，且 aria-pressed 反映开关态', async () => {
    const { voiceEnabled } = useVoiceToggle()
    const btn = mount().querySelector('button')
    expect(btn.getAttribute('aria-label')).toBe('关闭语音播报')
    expect(btn.getAttribute('aria-pressed')).toBe('true')
    btn.click()
    await nextTick()            // Vue 的 DOM 更新是异步批处理的，同步读会拿到旧值
    expect(voiceEnabled.value).toBe(false)
    expect(btn.getAttribute('aria-label')).toBe('开启语音播报')
    expect(btn.getAttribute('aria-pressed')).toBe('false')
  })

  it('点击能切换（键盘激活由原生 button 提供，见下方约束说明）', () => {
    const { voiceEnabled } = useVoiceToggle()
    const btn = mount().querySelector('button')
    // 起始为 true（beforeEach 已置位），点一次 → false
    btn.click()
    expect(voiceEnabled.value).toBe(false)
  })

  // 约束说明（不写测试）：Enter/空格 触发 click 是浏览器对原生 <button> 的内置行为，
  // jsdom 不会模拟"浏览器合成点击"，因此键盘激活**只能由门 4 的真人键盘走查覆盖**
  // （4A 设计 §6 断言 A1）。若在此处用 dispatchEvent 伪造 click，测到的是我们自己的
  // 代码而非浏览器行为——那是假覆盖，不如不写。
})
