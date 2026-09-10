// frontend/src/composables/__tests__/useBackgroundAdaptive.test.js
// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, nextTick, ref } from 'vue'

/** 采样像素可由用例改写（模块级可变） */
const pixels = { value: new Uint8ClampedArray([255, 255, 255, 255]) }
let imageInstances = []
let getImageDataThrows = false

class FakeImage {
  constructor() {
    this.crossOrigin = null
    this.onload = null
    this.onerror = null
    this.src = ''
    imageInstances.push(this)
  }
}

const solid = (r, g, b) => new Uint8ClampedArray([r, g, b, 255])

beforeEach(() => {
  imageInstances = []
  getImageDataThrows = false
  pixels.value = solid(255, 255, 255)
  vi.resetModules()
  vi.stubGlobal('Image', FakeImage)
  const origCreate = document.createElement.bind(document)
  vi.spyOn(document, 'createElement').mockImplementation((tag, ...rest) => {
    if (tag !== 'canvas') return origCreate(tag, ...rest)
    return {
      width: 0,
      height: 0,
      getContext: () => ({
        drawImage: () => {},
        getImageData: () => {
          if (getImageDataThrows) throw new Error('SecurityError: tainted canvas')
          return { data: pixels.value }
        },
      }),
    }
  })
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

async function composable(url) {
  const mod = await import('../useBackgroundAdaptive.js')
  return mod.useBackgroundAdaptive(url)
}

describe('useBackgroundAdaptive（LD §3.10）', () => {
  it('纯白图 avg=1.0 → overlayK 达上界 1.5、主色回退、userBubbleBg 达标、ready=true', async () => {
    const a = await composable('/media/white.png')
    expect(imageInstances[0].crossOrigin).toBe('anonymous')
    imageInstances[0].onload()
    expect(a.overlayK.value).toBeCloseTo(1.5, 2)    // avg=1.0 → clamp 上界（非 1.32；1.32 对应 avg≈0.9）
    expect(a.accent.value).toBe('#10b981')          // 纯白主色 → accentFallback
    expect(a.userBubbleBg.value).toBe('#0b825a')
    expect(a.ready.value).toBe(true)
  })

  it('黑图 → overlayK=0.6', async () => {
    pixels.value = solid(0, 0, 0)
    const a = await composable('/media/black.png')
    imageInstances[0].onload()
    expect(a.overlayK.value).toBe(0.6)
  })

  it('浅灰图 avg≈0.90 → overlayK≈1.32（非 clamp 区间，验证 avg→K 通路）', async () => {
    pixels.value = solid(230, 230, 230)              // 230/255 = 0.902 → K = 1.3235
    const a = await composable('/media/light.png')
    imageInstances[0].onload()
    expect(a.overlayK.value).toBeCloseTo(1.32, 2)
  })

  it('可读主色 → accent 采用该色，userBubbleBg 随之重算', async () => {
    pixels.value = solid(59, 130, 246)              // #3b82f6
    const a = await composable('/media/blue.png')
    imageInstances[0].onload()
    expect(a.accent.value).toBe('#3b82f6')
    expect(a.userBubbleBg.value).not.toBe('#0b825a')
  })

  it('空 URL → 默认值且不创建 Image（无背景图不等于加载失败）', async () => {
    const a = await composable('')
    expect(imageInstances).toHaveLength(0)
    expect(a.overlayK.value).toBe(1)
    expect(a.accent.value).toBe('#10b981')
    expect(a.ready.value).toBe(true)
  })

  it('加载失败（onerror）→ 默认值 + ready=true（E2 不阻塞）', async () => {
    const a = await composable('/media/broken.png')
    imageInstances[0].onerror()
    expect(a.overlayK.value).toBe(1)
    expect(a.accent.value).toBe('#10b981')
    expect(a.ready.value).toBe(true)
  })

  it('跨域污染画布（getImageData 抛错）→ 保持默认值且 ready=true', async () => {
    getImageDataThrows = true
    const a = await composable('https://other-host/media/x.png')
    imageInstances[0].onload()
    expect(a.overlayK.value).toBe(1)
    expect(a.accent.value).toBe('#10b981')
    expect(a.ready.value).toBe(true)
  })

  it('切换会话竞态：旧图迟到 onload 不得覆盖新图结果', async () => {
    const url = ref('/media/a.png')
    const a = await composable(computed(() => url.value))
    const stale = imageInstances[0]

    pixels.value = solid(0, 0, 0)
    url.value = '/media/b.png'
    await nextTick()
    const fresh = imageInstances[1]

    stale.onload()                                   // 迟到：seq 已过期 → 丢弃
    expect(a.overlayK.value).toBe(1)
    fresh.onload()
    expect(a.overlayK.value).toBe(0.6)
  })

  it('就绪前 ready=false（供蒙层交叉淡入使用）', async () => {
    const a = await composable('/media/white.png')
    expect(a.ready.value).toBe(false)
    imageInstances[0].onload()
    expect(a.ready.value).toBe(true)
  })
})
