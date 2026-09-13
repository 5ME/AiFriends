import { describe, expect, it } from 'vitest'
import {
  OVERLAY_SRGB,
  srgbToLinear,
  relLuminance,
  contrastRatio,
  composite,
  overlaySrgb,
  grayContrast,
  strokeContrast,
} from '../contrast'

/** 测试侧独立实现 WCAG 相对亮度（输入 sRGB 0~255），避免与被测实现互相印证 */
function rel(v255) {
  const v = v255 / 255
  return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)
}

const WHITE = 1.0
const STROKE = 0.85

describe('srgbToLinear（阈值 0.03928 的分段函数）', () => {
  it('低于阈值走线性段', () => {
    // 0.02 < 0.03928 → 0.02/12.92
    expect(srgbToLinear(0.02)).toBeCloseTo(0.02 / 12.92, 10)
  })

  it('高于阈值走幂函数段', () => {
    expect(srgbToLinear(0.5)).toBeCloseTo(rel(0.5 * 255), 10)
    expect(srgbToLinear(0.1)).toBeCloseTo(rel(25.5), 10)
  })

  it('端点：0 → 0，1 → 1', () => {
    expect(srgbToLinear(0)).toBeCloseTo(0, 10)
    expect(srgbToLinear(1)).toBeCloseTo(1, 10)
  })
})

describe('relLuminance（sRGB 0~255 → 相对亮度）', () => {
  it('白 = 1，黑 = 0', () => {
    expect(relLuminance(255, 255, 255)).toBeCloseTo(1, 10)
    expect(relLuminance(0, 0, 0)).toBeCloseTo(0, 10)
  })

  it('灰阶：v=128 → rel(128)', () => {
    expect(relLuminance(128, 128, 128)).toBeCloseTo(rel(128), 10)
  })

  it('#10b981 纯色 → 2.54:1 vs 白（spec §6.1 既有数值）', () => {
    expect(contrastRatio(WHITE, relLuminance(0x10, 0xb9, 0x81))).toBeCloseTo(2.54, 1)
  })
})

describe('contrastRatio（WCAG）', () => {
  it('白 vs 黑 = 21', () => {
    expect(contrastRatio(1.0, 0.0)).toBeCloseTo(21, 10)
  })

  it('同色 = 1', () => {
    expect(contrastRatio(0.42, 0.42)).toBeCloseTo(1, 10)
  })

  it('与参数顺序无关', () => {
    expect(contrastRatio(0.1, 0.7)).toBeCloseTo(contrastRatio(0.7, 0.1), 10)
  })
})

describe('composite / overlaySrgb（sRGB 分量空间混合）', () => {
  it('alpha=1 → 取前景', () => {
    expect(composite(255, 1.0, 0)).toBeCloseTo(255, 10)
  })

  it('alpha=0 → 取背景', () => {
    expect(composite(0, 0.0, 94.35)).toBeCloseTo(94.35, 10)
  })

  it('黑蒙层 α 覆盖 sRGB 底：overlaySrgb(α, v) = v(1-α)', () => {
    expect(overlaySrgb(0.25, 255)).toBeCloseTo(191.25, 10)
    expect(overlaySrgb(0.35, 191.25)).toBeCloseTo(124.3125, 10)
  })
})

describe('design §3.1 现状（sRGB 口径，纯白背景图）', () => {
  // 气泡底 = 白图经蒙层 α 后，再经 AI 气泡 rgba(0,0,0,.35)
  // 三通道始终相同（黑叠黑）→ 用 grayContrast（灰阶），不要用 relLuminance(g, 0, 0)
  const bubbleBase = (scrim) => overlaySrgb(0.35, overlaySrgb(scrim, 255))

  it('渐变端点浓度 = 0.25 / 0.425 / 0.60', () => {
    expect(OVERLAY_SRGB.TOP).toBe(0.25)
    expect(OVERLAY_SRGB.MID).toBe(0.425)
    expect(OVERLAY_SRGB.BOTTOM).toBe(0.60)
  })

  it('三档气泡底 sRGB = 124.31 / 95.31 / 66.30', () => {
    expect(bubbleBase(OVERLAY_SRGB.TOP)).toBeCloseTo(124.31, 2)
    expect(bubbleBase(OVERLAY_SRGB.MID)).toBeCloseTo(95.31, 2)
    expect(bubbleBase(OVERLAY_SRGB.BOTTOM)).toBeCloseTo(66.30, 2)
  })

  it('顶部 4.16:1 —— 略低于 4.5（这就是要补承托的位置）', () => {
    const r = grayContrast(bubbleBase(OVERLAY_SRGB.TOP))
    expect(r).toBeCloseTo(4.16, 2)
    expect(r).toBeLessThan(4.5)
  })

  it('中部 6.36:1 已达标', () => {
    const r = grayContrast(bubbleBase(OVERLAY_SRGB.MID))
    expect(r).toBeCloseTo(6.36, 1)
    expect(r).toBeGreaterThanOrEqual(4.5)
  })

  it('底部 10.00:1 已达标', () => {
    expect(grayContrast(bubbleBase(OVERLAY_SRGB.BOTTOM))).toBeCloseTo(10.0, 1)
  })

  it('蒙层上限 K=1.5（顶部 0.375）→ 5.61:1 达标（v1 曾误称"救不回来"）', () => {
    const r = grayContrast(bubbleBase(0.375))
    expect(r).toBeCloseTo(5.61, 1)
    expect(r).toBeGreaterThanOrEqual(4.5)
  })

  it('己方气泡 color-mix(srgb,#10b981 70%,black) → 4.85:1 达标（v1 曾误算 3.45）', () => {
    const r = contrastRatio(WHITE, relLuminance(0x10 * 0.7, 0xb9 * 0.7, 0x81 * 0.7))
    expect(r).toBeCloseTo(4.85, 1)
    expect(r).toBeGreaterThanOrEqual(4.5)
  })
})

describe('design §3.3 描边后（描边像素 = 底色 × 0.15）', () => {
  it('底色 66.30（气泡本色）→ 19.80:1', () => {
    expect(strokeContrast(66.30, STROKE)).toBeCloseTo(19.8, 1)
  })

  it('底色 95.625（纯白图最坏实际）→ 19.26:1', () => {
    expect(strokeContrast(95.625, STROKE)).toBeCloseTo(19.26, 2)
  })

  it('底色 191.25（气泡全透明 + 蒙层 0.25）→ 16.92:1', () => {
    expect(strokeContrast(191.25, STROKE)).toBeCloseTo(16.92, 2)
  })

  it('底色 255（纯白 + 零蒙层，理论极限）→ 15.08:1', () => {
    expect(strokeContrast(255, STROKE)).toBeCloseTo(15.08, 2)
  })

  it('四档全部 ≥4.5', () => {
    for (const base of [66.30, 95.625, 191.25, 255]) {
      expect(strokeContrast(base, STROKE)).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('单调性：底色越暗，对比度越高', () => {
    const a = strokeContrast(255, STROKE)
    const b = strokeContrast(95.625, STROKE)
    const c = strokeContrast(66.30, STROKE)
    expect(a).toBeLessThan(b)
    expect(b).toBeLessThan(c)
  })
})
