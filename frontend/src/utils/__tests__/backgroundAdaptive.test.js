import { describe, expect, it } from 'vitest'
import {
  ACCENT_FALLBACK,
  accentFallback,
  averageLuminance,
  computeOverlayK,
  contrastRatio,
  extractDominantColor,
  hexToRgb,
  mixWithBlack,
  relativeLuminance,
  resolveUserBubble,
} from '../backgroundAdaptive'

/** 生成 n 个同色 RGBA 像素（默认不透明） */
function solidPixels(r, g, b, n = 4, a = 255) {
  const out = new Uint8ClampedArray(n * 4)
  for (let i = 0; i < n; i++) {
    out[i * 4] = r
    out[i * 4 + 1] = g
    out[i * 4 + 2] = b
    out[i * 4 + 3] = a
  }
  return out
}

describe('hexToRgb / 基础解析', () => {
  it("带 # 与不带 # 均可解析", () => {
    expect(hexToRgb('#10b981')).toEqual([16, 185, 129])
    expect(hexToRgb('10b981')).toEqual([16, 185, 129])
  })

  it('大写十六进制可解析', () => {
    expect(hexToRgb('#10B981')).toEqual([16, 185, 129])
  })

  it('非法输入 → null', () => {
    expect(hexToRgb('#abc')).toBeNull()
    expect(hexToRgb('not-a-color')).toBeNull()
    expect(hexToRgb(null)).toBeNull()
    expect(hexToRgb(123)).toBeNull()
  })
})

describe('relativeLuminance / contrastRatio（WCAG）', () => {
  it('白 → 1，黑 → 0', () => {
    expect(relativeLuminance('#ffffff')).toBeCloseTo(1, 5)
    expect(relativeLuminance('#000000')).toBeCloseTo(0, 5)
  })

  it('#10b981 相对亮度 ≈ 0.364', () => {
    expect(relativeLuminance('#10b981')).toBeCloseTo(0.364, 3)
  })

  it('#10b981 vs 白 ≈ 2.54（LD §9.2）', () => {
    expect(contrastRatio('#10b981', '#ffffff')).toBeCloseTo(2.54, 2)
  })

  it('对比度与参数顺序无关', () => {
    expect(contrastRatio('#ffffff', '#10b981')).toBeCloseTo(
      contrastRatio('#10b981', '#ffffff'), 6)
  })

  it('非法颜色 → 1（防御性下限）', () => {
    expect(contrastRatio('bad', '#ffffff')).toBe(1)
  })
})

describe('mixWithBlack（spec §6.1 阶梯混黑档）', () => {
  it('70% 档 → #0b825a，白字对比度 ≥4.5', () => {
    const mixed = mixWithBlack('#10b981', 70)
    expect(mixed).toBe('#0b825a')
    expect(contrastRatio(mixed, '#ffffff')).toBeGreaterThanOrEqual(4.5)
  })

  it('非法基色 → 用 ACCENT_FALLBACK 兜底', () => {
    expect(mixWithBlack('bad', 70)).toBe(mixWithBlack(ACCENT_FALLBACK, 70))
  })
})

describe('resolveUserBubble（LD §9.2 阶梯寻档）', () => {
  it('#10b981 → 70% 档达标（≈4.8）', () => {
    const bg = resolveUserBubble('#10b981')
    expect(bg).toBe('#0b825a')
    expect(contrastRatio(bg, '#ffffff')).toBeGreaterThanOrEqual(4.5)
  })

  it('高亮黄 #fac832：70%/60% 不达标，落到 50% 档（不回退）', () => {
    expect(contrastRatio(mixWithBlack('#fac832', 70), '#ffffff')).toBeLessThan(4.5)
    expect(contrastRatio(mixWithBlack('#fac832', 60), '#ffffff')).toBeLessThan(4.5)
    const bg = resolveUserBubble('#fac832')
    expect(bg).toBe('#7d6419')
    expect(contrastRatio(bg, '#ffffff')).toBeGreaterThanOrEqual(4.5)
  })

  it('非法 accent → 回退 #10b981@70%', () => {
    expect(resolveUserBubble('bad')).toBe(mixWithBlack(ACCENT_FALLBACK, 70))
    expect(resolveUserBubble(null)).toBe(mixWithBlack(ACCENT_FALLBACK, 70))
  })

  it('任一返回值的白字对比度恒 ≥4.5（抽样断言）', () => {
    const samples = ['#10b981', '#fac832', '#3b82f6', '#ef4444', '#a855f7', '#14b8a6']
    for (const c of samples) {
      expect(contrastRatio(resolveUserBubble(c), '#ffffff')).toBeGreaterThanOrEqual(4.5)
    }
  })
})

describe('computeOverlayK（spec §6.5 步骤 3 / LD §9.2）', () => {
  it('白图 avg=0.9 → 1.32（深蒙层）', () => {
    expect(computeOverlayK(0.9)).toBeCloseTo(1.32, 5)
  })

  it('黑图 avg=0.1 → 0.6（浅蒙层下限）', () => {
    expect(computeOverlayK(0.1)).toBe(0.6)
  })

  it('avg=0.5 → 0.6（公式基准点）', () => {
    expect(computeOverlayK(0.5)).toBeCloseTo(0.6, 6)
  })

  it('clamp 上界 1.5（avg=1.0）', () => {
    expect(computeOverlayK(1)).toBe(1.5)
    expect(computeOverlayK(1.4)).toBe(1.5)
  })

  it('K 随 avg 单调不降', () => {
    let prev = -Infinity
    for (let avg = 0; avg <= 1.0001; avg += 0.05) {
      const k = computeOverlayK(avg)
      expect(k).toBeGreaterThanOrEqual(prev)
      prev = k
    }
  })
})

describe('averageLuminance（sRGB 加权感知均值）', () => {
  it('纯白 → 1，纯黑 → 0', () => {
    expect(averageLuminance(solidPixels(255, 255, 255))).toBeCloseTo(1, 5)
    expect(averageLuminance(solidPixels(0, 0, 0))).toBeCloseTo(0, 5)
  })

  it('中灰 #808080 → ≈0.502（不做 gamma 线性化）', () => {
    expect(averageLuminance(solidPixels(128, 128, 128))).toBeCloseTo(0.502, 3)
  })

  it('全透明像素被跳过 → 0；空输入 → 0', () => {
    expect(averageLuminance(solidPixels(255, 255, 255, 4, 0))).toBe(0)
    expect(averageLuminance(new Uint8ClampedArray(0))).toBe(0)
    expect(averageLuminance(null)).toBe(0)
  })
})

describe('extractDominantColor（LD §9.2 直方图分桶）', () => {
  it('纯色图 → 该色本身（桶内取均值）', () => {
    expect(extractDominantColor(solidPixels(16, 185, 129))).toBe('#10b981')
  })

  it('桶宽 64 阶：90 与 100 同桶 → 取均值 95', () => {
    const pixels = new Uint8ClampedArray([
      ...solidPixels(90, 90, 90, 2),
      ...solidPixels(100, 100, 100, 2),
    ])
    expect(extractDominantColor(pixels)).toBe('#5f5f5f')
  })

  it('多数色胜出', () => {
    const pixels = new Uint8ClampedArray([
      ...solidPixels(200, 30, 30, 3),
      ...solidPixels(20, 20, 200, 1),
    ])
    expect(extractDominantColor(pixels)).toBe('#c81e1e')
  })

  it('空输入 / 全透明 → null', () => {
    expect(extractDominantColor(new Uint8ClampedArray(0))).toBeNull()
    expect(extractDominantColor(null)).toBeNull()
    expect(extractDominantColor(solidPixels(16, 185, 129, 4, 0))).toBeNull()
  })
})

describe('accentFallback（LD §3.10 步骤 4）', () => {
  it('亮度过高（白）→ 回退 #10b981', () => {
    expect(accentFallback('#ffffff')).toBe(ACCENT_FALLBACK)
  })

  it('亮度过低（黑）→ 回退 #10b981', () => {
    expect(accentFallback('#000000')).toBe(ACCENT_FALLBACK)
  })

  it('非法颜色 → 回退 #10b981', () => {
    expect(accentFallback(null)).toBe(ACCENT_FALLBACK)
    expect(accentFallback('bad')).toBe(ACCENT_FALLBACK)
  })

  it('可读范围内的颜色原样保留（#10b981 / 亮黄 #facc15 / 蓝 #3b82f6）', () => {
    for (const c of ['#10b981', '#facc15', '#3b82f6']) {
      expect(accentFallback(c)).toBe(c)
    }
  })
})
