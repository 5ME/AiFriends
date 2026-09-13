// 对比度计算（纯函数，供单测锁定 design §3.1/§3.3 的数值）。
//
// ⚠️ 颜色空间约定（v1 曾在此处写错，务必遵守）：
//   CSS 的 alpha 合成发生在 **sRGB（gamma）分量空间**，不是亮度空间。
//   正确顺序：先在 sRGB 分量空间混合 → 再线性化求 WCAG 相对亮度。
//   反例（错）：把 0.65×0.75 当作线性亮度直接算比值 —— 会让结论整体偏悲观约一倍。
//
// 本模块有两种输入，命名上严格区分：
//   - sRGB 分量：0~255（overlaySrgb / composite / relLuminance 的入参）
//   - 线性相对亮度：0~1（srgbToLinear 入参、contrastRatio / strokeContrast 入参）

/** 窗口渐变蒙层的三档浓度（design §3.1：渐变端点 0% / 50% / 100%） */
export const OVERLAY_SRGB = {
  TOP: 0.25,
  MID: 0.425,
  BOTTOM: 0.60,
}

/** 文字描边的不透明度（design §3.2 的第一层实心圈 rgba(0,0,0,.85)） */
export const STROKE_ALPHA = 0.85

/**
 * sRGB 分量（0~1）→ 线性相对亮度分量。WCAG 2.x 定义的分段函数，阈值 0.03928。
 */
export function srgbToLinear(c) {
  return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
}

/**
 * sRGB 三元组（0~255）→ WCAG 相对亮度（0~1）。
 */
export function relLuminance(r, g, b) {
  return (
    0.2126 * srgbToLinear(r / 255) +
    0.7152 * srgbToLinear(g / 255) +
    0.0722 * srgbToLinear(b / 255)
  )
}

/**
 * WCAG 对比度比值 (L_light + 0.05) / (L_dark + 0.05)，范围 1~21。与参数顺序无关。
 * 入参为**线性相对亮度**。
 */
export function contrastRatio(l1, l2) {
  const hi = Math.max(l1, l2)
  const lo = Math.min(l1, l2)
  return (hi + 0.05) / (lo + 0.05)
}

/**
 * sRGB 分量空间的 alpha 合成：fg 以 alpha 覆盖在 bg 上。三者均为 sRGB 分量（0~255）。
 */
export function composite(fg, alpha, bg) {
  return fg * alpha + bg * (1 - alpha)
}

/**
 * 黑色蒙层 rgba(0,0,0,alpha) 覆盖在 sRGB 底色 base（0~255）上的结果。
 * 语义化封装 composite(0, alpha, base)。
 */
export function overlaySrgb(alpha, base) {
  return composite(0, alpha, base)
}

/**
 * 白字相对「sRGB 灰阶底色」的对比度。gray 为 sRGB 分量（0~255，三通道相同）。
 *
 * 用于气泡底（黑蒙层叠黑气泡，三通道始终相同）这类灰阶场景。
 * ⚠️ 不要用 relLuminance(gray, 0, 0) 代替它——那等于把灰值当纯红通道，结果会偏亮约 2.5 倍。
 */
export function grayContrast(gray) {
  return contrastRatio(1.0, relLuminance(gray, gray, gray))
}

/**
 * 白字相对「描边像素」的对比度。base 为描边之下的 sRGB 底色（0~255）。
 *
 * ⚠️ 措辞边界：本值描述的是"白字 vs 描边光圈"，**不是** WCAG 意义上的
 * "文字色 vs 声明背景色"。后者（白字 vs 气泡底）在纯白图顶部为 4.16:1，
 * 不因加描边而改变（design §3.4）。本函数用于单测锁定描边的感知承托能力。
 */
export function strokeContrast(base, strokeAlpha = STROKE_ALPHA) {
  const s = overlaySrgb(strokeAlpha, base)
  return contrastRatio(1.0, relLuminance(s, s, s))
}
