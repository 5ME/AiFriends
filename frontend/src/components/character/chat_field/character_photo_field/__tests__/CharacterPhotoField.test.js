// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest'
import { createApp, h } from 'vue'

// CharacterDetail 会拉起弹窗/路由等依赖链；本测试只关心 pill 的语义
vi.mock('@/components/character/CharacterDetail.vue', () => ({
  default: { name: 'CharacterDetail', render: () => h('div') },
}))

import CharacterPhotoField from '../CharacterPhotoField.vue'

const CHARACTER = { id: 7, name: '龙安洋', photo: '/media/x.png' }

function mount() {
  const host = document.createElement('div')
  document.body.appendChild(host)
  createApp({ render: () => h(CharacterPhotoField, { character: CHARACTER }) }).mount(host)
  return host
}

describe('CharacterPhotoField（4A D4A-1/D4A-2）', () => {
  it('头像 pill 根元素是原生 button', () => {
    const btn = mount().querySelector('button')
    expect(btn).toBeTruthy()
    expect(btn.getAttribute('type')).toBe('button')
  })

  it('可访问名称包含角色名（不是空名称）', () => {
    const btn = mount().querySelector('button')
    expect(btn.getAttribute('aria-label')).toBe('查看 龙安洋 的角色详情')
  })

  it('头像 alt 非空且含角色名（头像不是装饰图）', () => {
    const img = mount().querySelector('button img')
    expect(img.getAttribute('alt')).toBe('龙安洋的头像')
  })
})
