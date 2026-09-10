/**
 * 背景自适应纯函数（spec §6.5 / LD §3.10，用例清单 LD §9.2）。
 * 本文件不做任何 DOM/副作用操作：Image + canvas 采样与竞态守门在
 * composables/useBackgroundAdaptive.js 中完成。
 */

export const ACCENT_FALLBACK = '#10b981'
export const MIX_STEPS = [70, 60, 50]
export const MIN_CONTRAST = 4.5
const MIN_K = 0.6
const MAX_K = 1.5

/** '#rrggbb' / 'rrggbb' → [r,g,b]；非法 → null */
export function hexToRgb(hex) {
  if (typeof hex !== 'string') return null
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) return null
  const n = parseInt(m[1], 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

/** [r,g,b] → '#rrggbb'（四舍五入并夹取 0~255） */
export function rgbToHex(rgb) {
  return '#' + rgb
    .map(v => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0'))
    .join('')
}

/** WCAG 相对亮度（sRGB 线性化）→ 0~1；非法 → null */
export function relativeLuminance(color) {
  const rgb = hexToRgb(color)
  if (!rgb) return null
  const [r, g, b] = rgb.map(v => {
    const s = v / 255
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/** WCAG 对比度（1~21）；任一参数非法 → 1 */
export function contrastRatio(a, b) {
  const la = relativeLuminance(a)
  const lb = relativeLuminance(b)
  if (la === null || lb === null) return 1
  const [hi, lo] = la >= lb ? [la, lb] : [lb, la]
  return (hi + 0.05) / (lo + 0.05)
}

/** 与黑色按 pct% 混合（spec §6.1 阶梯档）；基色非法时用 ACCENT_FALLBACK */
export function mixWithBlack(color, pct) {
  const rgb = hexToRgb(color) || hexToRgb(ACCENT_FALLBACK)
  const k = Math.max(0, Math.min(100, pct)) / 100
  return rgbToHex(rgb.map(v => v * k))
}

/**
 * 己方气泡背景（spec §6.1 / LD §8.2）：70→60→50 取首个「白字对比度 ≥4.5」档；
 * 三档全不达标 → #10b981@70%（理论兜底，accentFallback 已保证 L∈[0.15,0.85]）。
 */
export function resolveUserBubble(accent) {
  const base = hexToRgb(accent) ? accent : ACCENT_FALLBACK
  for (const pct of MIX_STEPS) {
    const mixed = mixWithBlack(base, pct)
    if (contrastRatio(mixed, '#ffffff') >= MIN_CONTRAST) return mixed
  }
  return mixWithBlack(ACCENT_FALLBACK, 70)
}

/** 蒙层系数（spec §6.5 步骤 3）：K 随 avg 单调递增，clamp [0.6, 1.5] */
export function computeOverlayK(avg) {
  const k = MIN_K + (avg - 0.5) * 1.8
  return Math.min(MAX_K, Math.max(MIN_K, k))
}

/**
 * 感知亮度均值（spec §6.5 步骤 2 的 avg）：RGBA 像素按 sRGB 加权平均，
 * **不做 gamma 线性化**——保证语义与 spec 一致（纯白≈1、纯黑≈0、中灰≈0.5）。
 * alpha < 8 的像素视为透明跳过；无有效像素 → 0。
 */
export function averageLuminance(pixels) {
  if (!pixels || pixels.length === 0) return 0
  let sum = 0
  let count = 0
  for (let i = 0; i + 3 < pixels.length; i += 4) {
    if (pixels[i + 3] < 8) continue
    sum += (0.2126 * pixels[i] + 0.7152 * pixels[i + 1] + 0.0722 * pixels[i + 2]) / 255
    count++
  }
  return count === 0 ? 0 : sum / count
}

/**
 * 主色提取（spec §6.5 步骤 2 的 dominant）：每通道 32 阶直方图取像素数最大的桶，
 * 返回该桶内像素的颜色均值（纯色图 → 原色）。无有效像素 → null。
 */
export function extractDominantColor(pixels) {
  if (!pixels || pixels.length === 0) return null
  const buckets = new Map()
  for (let i = 0; i + 3 < pixels.length; i += 4) {
    if (pixels[i + 3] < 8) continue
    const key = ((pixels[i] >> 5) << 10) | ((pixels[i + 1] >> 5) << 5) | (pixels[i + 2] >> 5)
    const acc = buckets.get(key) || [0, 0, 0, 0]
    acc[0] += pixels[i]
    acc[1] += pixels[i + 1]
    acc[2] += pixels[i + 2]
    acc[3] += 1
    buckets.set(key, acc)
  }
  if (buckets.size === 0) return null
  let best = null
  for (const acc of buckets.values()) {
    if (!best || acc[3] > best[3]) best = acc
  }
  return rgbToHex([best[0] / best[3], best[1] / best[3], best[2] / best[3]])
}

/** accent 可读性兜底（LD §3.10 步骤 4）：非法颜色或 L∉[0.15,0.85] → #10b981 */
export function accentFallback(color) {
  const l = relativeLuminance(color)
  if (l === null || l > 0.85 || l < 0.15) return ACCENT_FALLBACK
  return color
}
