import { ref, toValue, watch } from 'vue'
import {
  ACCENT_FALLBACK,
  accentFallback,
  averageLuminance,
  computeOverlayK,
  extractDominantColor,
  resolveUserBubble,
} from '@/utils/backgroundAdaptive.js'

const SAMPLE_SIZE = 16
export const DEFAULT_OVERLAY_K = 1

/**
 * 背景亮度/主色自适应（spec §6.5 / LD §3.10）。
 * 返回 { overlayK, accent, accentStrong, userBubbleBg, ready }：默认值先渲染，采样完成后热更新。
 * 竞态防护：每次采样自增 loadSeq，迟到的 onload 一律丢弃（切换会话场景）。
 */
export function useBackgroundAdaptive(imageUrl) {
  const overlayK = ref(DEFAULT_OVERLAY_K)
  const accent = ref(ACCENT_FALLBACK)
  // accentStrong：把主色按对比度阶梯压深，保证充当地色时白字/白图标 ≥4.5:1
  // （原始主色可能很浅——如浅蓝 #abcae9 上白图标只有 1.6:1，实机验收暴露的缺陷）
  const accentStrong = ref(resolveUserBubble(ACCENT_FALLBACK))
  const userBubbleBg = ref(resolveUserBubble(ACCENT_FALLBACK))
  const ready = ref(false)
  let loadSeq = 0

  function applyDefaults() {
    overlayK.value = DEFAULT_OVERLAY_K
    accent.value = ACCENT_FALLBACK
    accentStrong.value = resolveUserBubble(ACCENT_FALLBACK)
    userBubbleBg.value = resolveUserBubble(ACCENT_FALLBACK)
    ready.value = true
  }

  function sample(url) {
    const seq = ++loadSeq
    ready.value = false
    if (!url) {
      applyDefaults()
      return
    }
    const img = new Image()
    img.crossOrigin = 'anonymous'   // 同源无碍；跨域无 CORS 头时走 onerror 降级（spec §6.5 步骤 5）
    img.onload = () => {
      if (seq !== loadSeq) return
      try {
        const canvas = document.createElement('canvas')
        canvas.width = SAMPLE_SIZE
        canvas.height = SAMPLE_SIZE
        const ctx = canvas.getContext('2d', { willReadFrequently: true })
        ctx.drawImage(img, 0, 0, SAMPLE_SIZE, SAMPLE_SIZE)
        const { data } = ctx.getImageData(0, 0, SAMPLE_SIZE, SAMPLE_SIZE)
        overlayK.value = computeOverlayK(averageLuminance(data))
        accent.value = accentFallback(extractDominantColor(data))
        accentStrong.value = resolveUserBubble(accent.value)
        userBubbleBg.value = resolveUserBubble(accent.value)
      } catch (e) {
        // 跨域被拦 / canvas 不可用：保持默认值，不阻塞渲染（Task 4 现场诊断依赖此告警）
        console.warn('背景采样失败，回退默认蒙层与主色', e)
        overlayK.value = DEFAULT_OVERLAY_K
        accent.value = ACCENT_FALLBACK
        accentStrong.value = resolveUserBubble(ACCENT_FALLBACK)
        userBubbleBg.value = resolveUserBubble(ACCENT_FALLBACK)
      }
      ready.value = true
    }
    img.onerror = () => {
      if (seq !== loadSeq) return
      applyDefaults()
    }
    img.src = url
  }

  watch(() => toValue(imageUrl), sample, { immediate: true })

  return { overlayK, accent, accentStrong, userBubbleBg, ready }
}
