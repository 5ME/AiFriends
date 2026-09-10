# 聊天改版 Phase 4（自适应与质感）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Phase 1 遗留的三处硬编码（固定蒙层 K=1、固定舞台压暗、全局写死 `--accent`）替换为「按角色背景图实时计算」的自适应值，并交付「简约背景」降级开关 + WindowHeader ⚙ 设置弹层（含语音自动发送开关）+ 无障碍与 token 收尾。

**Architecture:** 纯函数层（`utils/backgroundAdaptive.js`：亮度/主色/对比度/气泡色解析）→ 组合式层（`useBackgroundAdaptive`：Image + 16×16 canvas 采样 + seq 竞态守卫；`useChatSettings`：localStorage 单例）→ 注入层（ChatIndex 注入 `--accent`，ChatWindow 注入 `--overlay-k`/`--user-bubble-bg`）→ 样式层（`main.css` 主题 token，`.chat-window` 沉浸默认 / `.chat-window.chat-simple` 简约覆盖）。所有采样失败路径静默回退默认值，不阻塞首帧。

**Tech Stack:** Vue 3 `<script setup>`、Vitest 5（jsdom 按需）、Tailwind 4 + daisyUI 5（light 主题）、CSS 自定义属性 + `color-mix`/`calc`（无新依赖）。

---

> **事实源：** `docs/superpowers/specs/2026-09-07-chat-ui-redesign-spec-for-llm.md`（S §6.1/§6.2/§6.3/§6.5/§6.6/§13 Phase 4）+ `docs/superpowers/specs/2026-09-07-chat-ui-redesign-logic-design.md`（LD §3.4/§3.5/§3.10/§3.11/§4.6/§4.7/§8.2/§8.3/§9.2/§10 Phase 4）。
>
> **范围拍板（本计划内的边界决策，评审可核）：**
> 1. **4B（创建页聊天效果预览 + 亮度提示）不在本计划**：LD §10 Phase 4 表中标注为「修改（可选）」，且需在创建/编辑两条流程里验证裁剪（Croppie）与预览的交互，独立 PR 更安全。登记为后续可选批次（沿用 Phase 3 顺延项的处理方式）。
> 2. **`--accent` 所有权上移到 ChatIndex**（偏离 LD §3.4「ChatWindow 持有 useBackgroundAdaptive」）：`main.css:6-9` 已注明「Phase 4 落地后需把 `--accent` 提升/按角色注入，使会话栏选中态与窗口内 accent 一致」。实现为：ChatIndex 单次计算 → 根节点注入 `--accent` + 透传 `overlayK`/`userBubbleBg` 给 ChatWindow（`ready` 保留在组合式契约中，单层蒙层方案下 UI 无需消费）；移动端会话抽屉是 `Teleport to="body"`，脱离 ChatIndex DOM 子树 → SessionList 额外接 `accent` prop 自注入。收益：一次采样、两处一致、无重复 Image 加载。
> 3. **简约模式窗口色改用 `var(--color-base-200)`，AI 气泡改用 `var(--color-base-100)` + 1px 内描边**（偏离 S §6.6「AI=base-200 / chat-bg=#f5f5f4」）：daisyUI 5 light 主题下 `base-200 = oklch(98% 0 0) ≈ #f7f7f7`，与规定的 `#f5f5f4` 相差 2 个色阶 → AI 气泡会**看不见**。改后：窗口 base-200、AI 气泡白色卡片、用户气泡 `--user-bubble-bg`（白字 ≥4.5:1 由 `resolveUserBubble` 保证）。
> 4. **简约模式不跟随系统深色**（偏离 S §6.6「深色 #1c1917，跟随系统」）：全站只有一套 light daisyUI 主题（`frontend/index.html` 无 `data-theme`），若窗口跟系统变深而气泡仍是 base-200 浅色，会出现「深底 + 深字」不可读。改为常亮浅色，与 NavBar/会话栏一致。
> 5. **⚙ 设置弹层是唯一开关落点**（S §6.6 设想 header 内月亮按钮快捷入口）：420px 宽窗口头部已有 `☰(移动端)/语音/⚙/✕`，再加月亮按钮会挤压名字 pill。两个开关并列于 ⚙ 弹层（Q6 已拍板落点），可发现性由 `aria-expanded` + 开启态 `●` 提示点补偿。
> 6. **`--chat-*` token 与工具类写在 `main.css` 且不放进 `@layer`**：Tailwind 4 把 utilities 放进 `@layer utilities`，**未分层的规则恒胜**，因此 `.chat-text` 这类类名可稳定覆盖 `text-white`，无需 `!important` 或 inline style。
> 7. **对比度档位归并**：现网硬编码的 alpha 档为 1.00/0.90/0.85/0.75/0.70/0.60/0.40，token 归并为 1.00/0.85/0.70/0.60/0.40 五档；沉浸模式下单点最大差异 α=0.10（示例问题 0.90→0.85、introduction 0.90→1.00），肉眼不可辨，换取 token 数量可控。
> 8. **daisyUI 内置 loading 指示器（spinner/dots）不做 reduced-motion 静止**：它是「进行中」的唯一反馈，静止会失去语义；本轮只静止自家装饰动画（skeleton shimmer、脉冲点、蒙层过渡）。
> 9. **本地开发验收必须用 `http://localhost:5173`**：`DEBUG=True` 时 `MEDIA_URL=http://127.0.0.1:8000/media/`（settings.py:168）属跨域，而 `CORS_ALLOWED_ORIGINS` 默认只含 `http://localhost:5173`（settings.py:199-203）。用 `127.0.0.1:5173` 打开时 `crossOrigin='anonymous'` 会失败 → 静默回退 K=1（S §6.5 步骤 5 的既定降级路径），会误判为「功能没生效」。生产为 nginx 同源 `/media/`（nginx.conf:23-24），无此问题。

---

## 全局约定（每个 Task 都适用）

- **仓库根**：`D:\MyProjects\AiFriends`（bash/ssh 场景为 `/d/MyProjects/AiFriends`）。
- **基线**：`master = e54af7b`（PR #36 合并点）。分支：`feature/gqyin/chat-ui-redesign-phase4`。
- **工作区有未跟踪/未提交的无关改动**（`.codegraph/.gitignore` M、`.superpowers/brainstorm/**` D、`docs/superpowers/reviews/` ??）——**严禁 `git add -A`/`git add .`**，每个 commit 只 `git add <本 Task 的明确路径>`。
- **测试命令**：`npm --prefix frontend run test:unit`（Vitest）。基线 **65 passed**（voiceState 31 / inputKey 6 / chatFormat 20 / markdown 8）。
- **构建命令**：`npm --prefix frontend run build`（输出到 `backend/static/frontend/`）。
- **测试文件位置**：纯函数/组合式测试放同级 `__tests__/`；需要 DOM 的文件首行加 `// @vitest-environment jsdom`（仓库无 vitest 配置文件，默认 node 环境，见 markdown.test.js 的先例）。
- **commit message 用中文**，格式 `feat(chat): …` / `fix(chat): …` / `docs(chat): …`，不写 Co-Authored-By。

---

## Task 0：分支准备

**Files:**
- 无

- [ ] **Step 1：切分支**

Run:
```bash
cd /d/MyProjects/AiFriends
git checkout master
git pull origin master
git checkout -b feature/gqyin/chat-ui-redesign-phase4
```

Expected: 新分支基于 `e54af7b`。

- [ ] **Step 2：确认基线**

Run:
```bash
git log --oneline -1
npm --prefix frontend run test:unit
```

Expected: `e54af7b Merge pull request #36 …`；`Tests  65 passed (65)`。

---

## Task 1：`backgroundAdaptive.js` 纯函数 + 单测（TDD）

**Files:**
- Create: `frontend/src/utils/backgroundAdaptive.js`
- Test: `frontend/src/utils/__tests__/backgroundAdaptive.test.js`

- [ ] **Step 1：写失败测试**

```js
// frontend/src/utils/__tests__/backgroundAdaptive.test.js
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
```

- [ ] **Step 2：运行测试确认失败**

Run: `npm --prefix frontend run test:unit -- backgroundAdaptive`
Expected: FAIL —— `Failed to resolve import "../backgroundAdaptive"`。

- [ ] **Step 3：实现纯函数**

```js
// frontend/src/utils/backgroundAdaptive.js
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
 * 主色提取（spec §6.5 步骤 2 的 dominant）：直方图分桶取像素数最大的桶，
 * 返回该桶内像素的颜色均值（纯色图 → 原色）。无有效像素 → null。
 *
 * 桶宽 64 阶（每通道 4 桶、共 64 桶），非 spec §6.5 字面的「每桶 32 阶」：
 * 采样仅 16×16=256 像素，512 桶时平均 0.5 像素/桶 → 主导色退化为「首个单像素色」噪声；
 * 64 桶时约 4 像素/桶，桶内均值才具备「主导色」语义（2026-09-10 拍板，spec 已回写）。
 */
export function extractDominantColor(pixels) {
  if (!pixels || pixels.length === 0) return null
  const buckets = new Map()
  for (let i = 0; i + 3 < pixels.length; i += 4) {
    if (pixels[i + 3] < 8) continue
    const key = ((pixels[i] >> 6) << 12) | ((pixels[i + 1] >> 6) << 6) | (pixels[i + 2] >> 6)
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
```

- [ ] **Step 4：运行测试确认通过**

Run: `npm --prefix frontend run test:unit -- backgroundAdaptive`
Expected: PASS（本文件 29 passed；评审追加「桶宽 64 阶」用例后为 30 passed）。

- [ ] **Step 5：全量回归 + 提交**

Run:
```bash
npm --prefix frontend run test:unit
git add frontend/src/utils/backgroundAdaptive.js frontend/src/utils/__tests__/backgroundAdaptive.test.js
git commit -m "feat(chat): backgroundAdaptive 纯函数（亮度/主色/对比度/气泡色解析）+ 29 例单测（spec §6.5 / LD §9.2）"
```
Expected: `Tests  94 passed`（65 + 29）。评审后追加 fix commit `fix(chat): extractDominantColor 桶宽改 64 阶…`（含 1 例新用例）→ **95 passed**。

---

## Task 2：`useBackgroundAdaptive` 组合式 + 竞态单测

> **本任务附带 Task 1 评审的 3 项 Minor 清理**（评审建议并入本 commit，见下方 Step 0）：
> ① `extractDominantColor` 位打包步长与桶宽一致化（`>> 6` 配 `<< 4 / << 2`，当前 `<< 12 / << 6` 语义正确但易被后人误改）；
> ② `computeOverlayK` 加 `Number.isFinite` 防御（NaN 会污染 `--overlay-k` 使渐变失效）；
> ③ 补 `resolveUserBubble` 三档全不达标的兜底分支用例（`'#ffffff'` → `'#0b825a'`）。

- [ ] **Step 0：Task 1 评审 Minor 清理**

`frontend/src/utils/backgroundAdaptive.js`：

```js
    const key = ((pixels[i] >> 6) << 4) | ((pixels[i + 1] >> 6) << 2) | (pixels[i + 2] >> 6)
```

```js
/** 蒙层系数（spec §6.5 步骤 3）：K 随 avg 单调递增，clamp [0.6, 1.5]；非有限值防御性回落下限 */
export function computeOverlayK(avg) {
  if (!Number.isFinite(avg)) return MIN_K
  const k = MIN_K + (avg - 0.5) * 1.8
  return Math.min(MAX_K, Math.max(MIN_K, k))
}
```

`frontend/src/utils/__tests__/backgroundAdaptive.test.js` 追加两例：

```js
  it('三档全不达标 → 兜底 #10b981@70%（#ffffff 白图场景）', () => {
    expect(resolveUserBubble('#ffffff')).toBe('#0b825a')
  })
```

```js
  it('非有限 avg → 回落下限 0.6（NaN 防御）', () => {
    expect(computeOverlayK(NaN)).toBe(0.6)
    expect(computeOverlayK(undefined)).toBe(0.6)
  })
```

（`resolveUserBubble('#ffffff')`：70%/60%/50% 三档白字对比度 2.08/2.85/3.95 均 <4.5 → 走兜底分支。）

Run: `npm --prefix frontend run test:unit` → Expected: `Tests  97 passed`（95 + 2）。

**Files:**
- Create: `frontend/src/composables/useBackgroundAdaptive.js`
- Test: `frontend/src/composables/__tests__/useBackgroundAdaptive.test.js`

- [ ] **Step 1：写失败测试**

```js
// frontend/src/composables/__tests__/useBackgroundAdaptive.test.js
// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
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
```

- [ ] **Step 2：运行测试确认失败**

Run: `npm --prefix frontend run test:unit -- useBackgroundAdaptive`
Expected: FAIL —— 无法解析 `../useBackgroundAdaptive.js`。

- [ ] **Step 3：实现组合式**

```js
// frontend/src/composables/useBackgroundAdaptive.js
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
 * 返回 { overlayK, accent, userBubbleBg, ready }：默认值先渲染，采样完成后热更新。
 * 竞态防护：每次采样自增 loadSeq，迟到的 onload 一律丢弃（切换会话场景）。
 */
export function useBackgroundAdaptive(imageUrl) {
  const overlayK = ref(DEFAULT_OVERLAY_K)
  const accent = ref(ACCENT_FALLBACK)
  const userBubbleBg = ref(resolveUserBubble(ACCENT_FALLBACK))
  const ready = ref(false)
  let loadSeq = 0

  function applyDefaults() {
    overlayK.value = DEFAULT_OVERLAY_K
    accent.value = ACCENT_FALLBACK
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
        userBubbleBg.value = resolveUserBubble(accent.value)
      } catch (e) {
        // 跨域被拦 / canvas 不可用：保持默认值，不阻塞渲染
        overlayK.value = DEFAULT_OVERLAY_K
        accent.value = ACCENT_FALLBACK
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

  return { overlayK, accent, userBubbleBg, ready }
}
```

- [ ] **Step 4：运行测试确认通过**

Run: `npm --prefix frontend run test:unit -- useBackgroundAdaptive`
Expected: PASS（8 passed）。

- [ ] **Step 5：全量回归 + 提交**

Run:
```bash
npm --prefix frontend run test:unit
git add frontend/src/composables/useBackgroundAdaptive.js frontend/src/composables/__tests__/useBackgroundAdaptive.test.js
git commit -m "feat(chat): useBackgroundAdaptive 采样组合式（16×16 canvas + seq 竞态守卫 + 三层降级）+ 8 例单测"
```
Expected: `Tests  106 passed`（97 + 本任务 9 例；纯白用例改判 1.5 + 新增浅灰非 clamp 用例）。

---

## Task 3：`useChatSettings` 单例 + 持久化单测

> **本任务附带 Task 2 评审的 2 项 Minor 清理**（评审建议并入后续 commit）：
> ① `useBackgroundAdaptive` 采样失败分支补 `console.warn`（仓库前端约定，且 Task 4 的现场诊断依赖它）；
> ② 组合式测试补 `afterEach` 还原 mock（`vi.restoreAllMocks()` + `vi.unstubAllGlobals()`），消除 `origCreate` 二次绑定上一次 spy 的隐患。
> 其余 4 项 Minor（SAMPLE_SIZE/willReadFrequently 断言、resetModules 冗余、非字符串 URL 守卫、onScopeDispose 取消在途加载）**判定不修**，理由：前两项属可选强化、后两项为良性且当前用法下无实际影响。

- [ ] **Step 0：Task 2 评审 Minor 清理**

`frontend/src/composables/useBackgroundAdaptive.js` 的 catch 分支改为：

```js
      } catch (e) {
        // 跨域被拦 / canvas 不可用：保持默认值，不阻塞渲染（Task 4 现场诊断依赖此告警）
        console.warn('背景采样失败，回退默认蒙层与主色', e)
        overlayK.value = DEFAULT_OVERLAY_K
        accent.value = ACCENT_FALLBACK
        userBubbleBg.value = resolveUserBubble(ACCENT_FALLBACK)
      }
```

`frontend/src/composables/__tests__/useBackgroundAdaptive.test.js` 的 import 行补 `afterEach`，并在 `beforeEach` 之后追加：

```js
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
```

Run: `npm --prefix frontend run test:unit` → Expected: `Tests  106 passed`（数量不变，验证未回归）。

**Files:**
- Create: `frontend/src/composables/useChatSettings.js`
- Test: `frontend/src/composables/__tests__/useChatSettings.test.js`

- [ ] **Step 1：写失败测试**

```js
// frontend/src/composables/__tests__/useChatSettings.test.js
// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

beforeEach(() => {
  localStorage.clear()
  vi.resetModules()
})

const load = () => import('../useChatSettings.js')

describe('useChatSettings（LD §3.11 / D-L7）', () => {
  it('默认两项均关闭', async () => {
    const { useChatSettings } = await load()
    const s = useChatSettings()
    expect(s.simpleBackground.value).toBe(false)
    expect(s.autoSendVoice.value).toBe(false)
  })

  it('读取已持久化的 true', async () => {
    localStorage.setItem('chatSimpleBg', 'true')
    localStorage.setItem('chatAutoSendVoice', 'true')
    const { useChatSettings } = await load()
    const s = useChatSettings()
    expect(s.simpleBackground.value).toBe(true)
    expect(s.autoSendVoice.value).toBe(true)
  })

  it('toggleSimple 写入 localStorage（新模块实例可读回）', async () => {
    const first = await load()
    first.useChatSettings().toggleSimple()
    await nextTick()          // Vue watch 默认 flush:'pre'，持久化回调在微任务执行
    expect(localStorage.getItem('chatSimpleBg')).toBe('true')

    vi.resetModules()
    const second = await load()
    expect(second.useChatSettings().simpleBackground.value).toBe(true)
  })

  it('toggleAutoSend 独立 key，互不串扰', async () => {
    const { useChatSettings } = await load()
    const s = useChatSettings()
    s.toggleAutoSend()
    await nextTick()          // 同上：等待持久化 watcher 落盘
    expect(localStorage.getItem('chatAutoSendVoice')).toBe('true')
    expect(localStorage.getItem('chatSimpleBg')).toBe(null)
    expect(s.simpleBackground.value).toBe(false)
  })

  it('localStorage 抛错（隐私模式）→ 降级为默认 false，不崩', async () => {
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError')
    })
    const { useChatSettings } = await load()
    expect(useChatSettings().simpleBackground.value).toBe(false)
    spy.mockRestore()
  })
})
```

- [ ] **Step 2：运行测试确认失败**

Run: `npm --prefix frontend run test:unit -- useChatSettings`
Expected: FAIL —— 模块不存在。

- [ ] **Step 3：实现单例**

```js
// frontend/src/composables/useChatSettings.js
import { ref, watch } from 'vue'

const KEY_SIMPLE_BG = 'chatSimpleBg'
const KEY_AUTO_SEND = 'chatAutoSendVoice'

function readFlag(key) {
  try {
    return localStorage.getItem(key) === 'true'
  } catch (e) {
    return false   // 隐私模式/禁用存储：降级为「关闭」，不阻塞
  }
}

function writeFlag(key, value) {
  try {
    localStorage.setItem(key, String(value))
  } catch (e) {
    // 配额/隐私模式：静默丢弃持久化，本次会话内仍生效
  }
}

// 模块级单例（仿 useVoiceToggle）：WindowHeader 设置弹层与 InputField 自动发送共享同一状态
const simpleBackground = ref(readFlag(KEY_SIMPLE_BG))
const autoSendVoice = ref(readFlag(KEY_AUTO_SEND))

watch(simpleBackground, (v) => writeFlag(KEY_SIMPLE_BG, v))
watch(autoSendVoice, (v) => writeFlag(KEY_AUTO_SEND, v))

export function useChatSettings() {
  function toggleSimple() {
    simpleBackground.value = !simpleBackground.value
  }

  function toggleAutoSend() {
    autoSendVoice.value = !autoSendVoice.value
  }

  return { simpleBackground, autoSendVoice, toggleSimple, toggleAutoSend }
}
```

- [ ] **Step 4：运行测试确认通过**

Run: `npm --prefix frontend run test:unit -- useChatSettings`
Expected: PASS（5 passed）。

- [ ] **Step 5：全量回归 + 提交**

Run:
```bash
npm --prefix frontend run test:unit
git add frontend/src/composables/useChatSettings.js frontend/src/composables/__tests__/useChatSettings.test.js
git commit -m "feat(chat): useChatSettings 模块级单例（简约背景/语音自动发送 + localStorage 持久化）+ 5 例单测"
```
Expected: `Tests  111 passed`（5 例新测；持久化断言需 `await nextTick()` 等待 watcher 落盘）。

---

## Task 4：自适应接入（ChatIndex → ChatWindow/SessionList + main.css 蒙层/舞台/气泡变量）

**Files:**
- Modify: `frontend/src/views/chat/ChatIndex.vue`
- Modify: `frontend/src/components/chat/chat_window/ChatWindow.vue`
- Modify: `frontend/src/components/chat/SessionList.vue`
- Modify: `frontend/src/assets/main.css`

- [ ] **Step 1：ChatIndex 单次采样 + 注入 `--accent`**

`frontend/src/views/chat/ChatIndex.vue` 脚本区（import 段与 `const isMobile` 之后）加入：

```js
import { useBackgroundAdaptive } from '@/composables/useBackgroundAdaptive.js'

// 背景自适应（Phase 4）：ChatIndex 单次采样 → 根节点注入 --accent（会话栏选中态与窗口内一致，
// 见 main.css 顶部 Phase 1 注释），K/气泡色透传给 ChatWindow
const backgroundUrl = computed(() => friend.value?.character?.background_image || '')
const { overlayK, accent, userBubbleBg } = useBackgroundAdaptive(backgroundUrl)
```

模板根节点与两个消费点改成：

```html
  <div class="flex h-[calc(100dvh-64px)]" :style="{ '--accent': accent }">
```

```html
      <SessionList :active-id="activeCharacterId" :accent="accent" @select="handleSelect" />
```

```html
            <SessionList :active-id="activeCharacterId"
                         :accent="accent"
                         @select="handleSelect"
                         @closeDrawer="drawerOpen = false" />
```

```html
      <ChatWindow v-else :key="friend.character.id"
                  :friend="friend"
                  :overlay-k="overlayK"
                  :user-bubble-bg="userBubbleBg"
                  @closed="handleClose"
                  @openDrawer="drawerOpen = true" />
```

- [ ] **Step 2：SessionList 接 accent 并自注入（Teleport 到 body 时不再继承 ChatIndex 变量）**

`frontend/src/components/chat/SessionList.vue`：

```js
const props = defineProps(['activeId', 'accent'])
```

```html
  <div class="flex flex-col h-full" :style="{ '--accent': props.accent }">
```

- [ ] **Step 3：ChatWindow 注入 `--overlay-k`/`--user-bubble-bg` + 单层蒙层（K 过渡）**

`frontend/src/components/chat/chat_window/ChatWindow.vue` 脚本区：

```js
import { useChatSettings } from '@/composables/useChatSettings.js'

const props = defineProps(['friend', 'overlayK', 'userBubbleBg'])
const { simpleBackground } = useChatSettings()
```

模板中舞台 + 窗口段落整体替换为：

```html
  <div class="chat-stage-root absolute inset-0 flex items-center justify-center"
       :style="{ '--overlay-k': overlayK, '--user-bubble-bg': userBubbleBg }">
    <!-- 舞台（桌面端：同图模糊压暗延展；移动端无舞台；简约模式 → base-200 纯色） -->
    <div class="absolute inset-0 overflow-hidden hidden lg:block">
      <template v-if="!simpleBackground">
        <div class="absolute -inset-[10%] bg-cover bg-center stage-blur"
             :style="{ backgroundImage: `url(${friend.character.background_image})` }"></div>
        <div class="absolute inset-0 stage-dim"></div>
      </template>
      <div v-else class="absolute inset-0 bg-base-200"></div>
    </div>

    <!-- 角色之窗（3:5，桌面居中 / 移动端全屏，纯 CSS 尺寸公式） -->
    <div class="chat-window relative flex flex-col" :class="{ 'chat-simple': simpleBackground }">
    <!-- 窗口背景 + 渐变蒙层（单层，停点随 --overlay-k 过渡；spec §6.3/§6.5） -->
         基础层（K=1）保证首帧即可读；自适应层（K 由背景图亮度算出）ready 后交叉接棒（spec §6.5） -->
    <template v-if="!simpleBackground">
      <div class="absolute inset-0 bg-cover bg-center"
           :style="{ backgroundImage: `url(${friend.character.background_image})` }"></div>
      <div class="absolute inset-0 window-scrim"></div>
    </template>
```

（其余内容列、引用浮层不动；`</div>` 收尾层级不变。）

- [ ] **Step 4：main.css 蒙层/舞台/气泡变量**

`frontend/src/assets/main.css` 三处替换：

```css
/* 窗口内渐变蒙层（Phase 1 固定 K=1；Phase 4 单层蒙层 + --overlay-k 过渡，spec §6.3）。
   停点 = 0.25K / 0.60K，K 由 ChatWindow 根节点（.chat-stage-root）注入。 */
.window-scrim {
  background: linear-gradient(180deg,
    rgba(0, 0, 0, calc(0.25 * var(--overlay-k, 1))) 0%,
    rgba(0, 0, 0, calc(0.60 * var(--overlay-k, 1))) 100%);
}

/* --overlay-k 注册为可动画数值属性：注册后浏览器才能对自定义属性做过渡（单层蒙层的停点是 K 的
   线性函数 → 过渡期间 alpha 单调变化；不支持 @property 的浏览器直接跳变，属可接受降级）。 */
@property --overlay-k {
  syntax: '<number>';
  inherits: true;
  initial-value: 1;
}
.chat-stage-root {
  transition-property: --overlay-k;
  transition-duration: 300ms;
  transition-timing-function: ease;
}

@media (prefers-reduced-motion: reduce) {
  .chat-stage-root {
    transition: none;
  }
}
```

```css
.stage-dim {
  background: rgba(0, 0, 0, calc(0.35 * var(--overlay-k, 1)));
}
```

```css
/* 消息气泡（spec §6.1；用户气泡背景 = resolveUserBubble(accent) 运行时解析值） */
.msg-bubble-user {
  background: var(--user-bubble-bg, color-mix(in srgb, #10b981 70%, black));
  color: #ffffff;
  border-top-right-radius: 4px;
}
```


```css
/* 角色之窗：3:5 竖版容器，纯 CSS 尺寸公式（LD §8.1，无需 JS resize） */
/* 注意：这里**不得**声明 --overlay-k/--user-bubble-bg——自定义属性在元素上声明会遮蔽
   祖先注入值，窗口内的自适应蒙层将永远读到默认 1。默认值一律由使用处的 var(x, 1) 兜底。 */
.chat-window {
  width: min(420px, calc((100vh - 64px - 48px) * 0.6));
  /* …其余不变… */
}
```

- [ ] **Step 5：构建 + 单测 + 本地目检**

Run:
```bash
npm --prefix frontend run test:unit
npm --prefix frontend run build
```
Expected: `Tests  112 passed`；build exit 0（仅既有 daisyUI `@property` 与 chunk 体积告警）。

本地目检（**必须用 `http://localhost:5173`**，见范围拍板 #9）：
1. 用一个**白底**背景图的角色进聊天页 → 窗口蒙层明显加深；DevTools 选中 `.chat-window` 的父节点执行
   `getComputedStyle($0).getPropertyValue('--overlay-k')` → ` 1.32` 左右。
2. 换一个**深色**背景图的角色 → `--overlay-k` → ` 0.6`，窗口透亮。
3. 会话栏选中态颜色随角色主色变化（不再是固定绿）。
4. 若 `--overlay-k` 恒为 1：控制台执行下面的采样诊断，确认是「加载失败/跨域」还是代码问题：
   ```js
   const img = new Image(); img.crossOrigin = 'anonymous';
   img.onerror = () => console.warn('采样不可用（CORS/加载失败）→ 已按 spec 回退 K=1');
   img.onload = () => console.log('采样可用', img.width, img.height);
   img.src = '<当前角色背景图 URL>';
   ```

- [ ] **Step 6：提交**

```bash
git add frontend/src/views/chat/ChatIndex.vue frontend/src/components/chat/chat_window/ChatWindow.vue frontend/src/components/chat/SessionList.vue frontend/src/assets/main.css
git commit -m "feat(chat): 背景亮度自适应接入（ChatIndex 采样 + --accent/--overlay-k/--user-bubble-bg 注入 + 蒙层交叉淡入 + 舞台系数）"
```

---

## Task 5：简约背景模式（主题 token 化 + `.chat-simple` 分支）

**Files:**
- Modify: `frontend/src/assets/main.css`（token 定义 + 现有类改用 token）
- Modify: `frontend/src/components/character/chat_field/chat_history/message/Message.vue`
- Modify: `frontend/src/components/character/chat_field/chat_history/ChatHistory.vue`
- Modify: `frontend/src/components/character/chat_field/input_field/InputField.vue`
- Modify: `frontend/src/components/character/chat_field/input_field/Microphone.vue`
- Modify: `frontend/src/components/chat/chat_window/WindowHeader.vue`

**设计：** `.chat-window` 定义沉浸默认 token；`.chat-window.chat-simple` 覆盖为 daisyUI 浅色对比值。template 里的硬编码色换成未分层的工具类（范围拍板 #6），因此**沉浸模式视觉零回归**（每个 token 的默认值都等于被替换掉的现网值）。

- [ ] **Step 1：main.css 追加 token 与工具类**

在 `main.css` 的 `.chat-window` 规则之前插入：

```css
/* ===== 聊天主题 token（Phase 4）=====
   沉浸模式（默认）：深色玻璃 + 白色系文字，压在角色背景图之上。
   简约模式（.chat-simple，spec §6.6 C3 降级）：纯色窗口 + daisyUI 对比色。
   工具类保持「未分层」（不写进 @layer），从而稳定覆盖 Tailwind 同名 utility。 */

/* 文字层级 */
.chat-text    { color: var(--chat-text); }
.chat-text-2  { color: var(--chat-text-2); }
.chat-text-3  { color: var(--chat-text-3); }
.chat-text-4  { color: var(--chat-text-4); }
.chat-text-5  { color: var(--chat-text-5); }
.chat-error   { color: var(--chat-error); }

/* 图标按钮：自身在 accent 底上时用 .is-active 提权（两 class 胜一 class） */
.chat-icon-btn        { color: var(--chat-text); }
.chat-icon-btn.is-active { color: #ffffff; }

/* 玻璃面板（头部条 / 输入栏 / 波形区） */
.glass-panel {
  background: var(--chat-glass);
  backdrop-filter: blur(12px);
  box-shadow: inset 0 0 0 1px var(--chat-glass-border, transparent);
}
.glass-bar {
  background: var(--chat-glass);
  backdrop-filter: blur(12px);
}

/* 胶囊按钮（引用 chip / 示例问题） */
.chat-chip-btn {
  background: var(--chat-chip);
  backdrop-filter: blur(8px);
}
.chat-chip-btn:hover {
  background: var(--chat-chip-hover);
}

/* 焦点环（Phase 4 a11y：统一 outline，避免 Tailwind ring 与 daisyUI 冲突） */
.chat-ring:focus-visible {
  outline: 2px solid var(--chat-ring);
  outline-offset: 2px;
}
```

在 `.chat-window` 规则块内追加 token 默认值（**注意：不要在此声明 `--overlay-k`**，理由见 Task 4 Step 4a 的遮蔽说明）：

```css
  /* 沉浸模式 token（值 = Phase 1~3 的现网硬编码值，保证零视觉回归） */
  --chat-text: #ffffff;
  --chat-text-2: rgba(255, 255, 255, 0.85);
  --chat-text-3: rgba(255, 255, 255, 0.70);
  --chat-text-4: rgba(255, 255, 255, 0.60);
  --chat-text-5: rgba(255, 255, 255, 0.40);
  --chat-error: #fca5a5;
  --chat-glass: rgba(0, 0, 0, 0.35);
  --chat-glass-border: transparent;
  --chat-chip: rgba(0, 0, 0, 0.25);
  --chat-chip-hover: rgba(0, 0, 0, 0.40);
  --chat-code-bg: rgba(0, 0, 0, 0.45);
  --chat-code-inline-bg: rgba(0, 0, 0, 0.40);
  --chat-hairline: rgba(255, 255, 255, 0.30);
  --chat-link: #7dd3fc;
  --chat-ring: rgba(255, 255, 255, 0.40);
  --chat-shimmer: rgba(255, 255, 255, 0.08);
  --chat-shimmer-hi: rgba(255, 255, 255, 0.18);
  --bubble-ai-bg: rgba(0, 0, 0, 0.35);
  --bubble-ai-text: #ffffff;
  --bubble-ai-border: transparent;
  --chat-bg: transparent;
```

在 `.chat-window` 的移动端 media query 之后追加简约模式覆盖：

```css
/* 简约背景模式（spec §6.6；范围拍板 #3/#4：窗口 base-200、AI 气泡白色卡片、常亮浅色） */
.chat-window.chat-simple {
  --chat-text: var(--color-base-content);
  --chat-text-2: color-mix(in srgb, var(--color-base-content) 85%, transparent);
  --chat-text-3: color-mix(in srgb, var(--color-base-content) 70%, transparent);
  --chat-text-4: color-mix(in srgb, var(--color-base-content) 60%, transparent);
  --chat-text-5: color-mix(in srgb, var(--color-base-content) 45%, transparent);
  --chat-error: #b91c1c;
  --chat-glass: var(--color-base-200);
  --chat-glass-border: var(--color-base-300);
  --chat-chip: color-mix(in srgb, var(--color-base-content) 8%, transparent);
  --chat-chip-hover: color-mix(in srgb, var(--color-base-content) 16%, transparent);
  --chat-code-bg: color-mix(in srgb, var(--color-base-content) 8%, transparent);
  --chat-code-inline-bg: color-mix(in srgb, var(--color-base-content) 8%, transparent);
  --chat-hairline: color-mix(in srgb, var(--color-base-content) 25%, transparent);
  --chat-link: #0369a1;
  --chat-ring: color-mix(in srgb, var(--color-base-content) 35%, transparent);
  --chat-shimmer: color-mix(in srgb, var(--color-base-content) 6%, transparent);
  --chat-shimmer-hi: color-mix(in srgb, var(--color-base-content) 14%, transparent);
  --bubble-ai-bg: var(--color-base-100);
  --bubble-ai-text: var(--color-base-content);
  --bubble-ai-border: var(--color-base-300);
  --chat-bg: var(--color-base-200);
  background: var(--chat-bg);
}
```

- [ ] **Step 2：main.css 既有类改用 token**

| 类 | 原值 | 新值 |
|----|------|------|
| `.msg-bubble-ai` | `background: rgba(0, 0, 0, 0.35); backdrop-filter: blur(8px); color: #ffffff;` | `background: var(--bubble-ai-bg); backdrop-filter: blur(8px); color: var(--bubble-ai-text); box-shadow: inset 0 0 0 1px var(--bubble-ai-border);` |
| `.msg-name-pill` | `background: rgba(0, 0, 0, 0.3); … color: rgba(255, 255, 255, 0.7);` | `background: var(--chat-chip); … color: var(--chat-text-3);` |
| `.date-capsule` | `background: rgba(0, 0, 0, 0.25); color: rgba(255, 255, 255, 0.6);` | `background: var(--chat-chip); color: var(--chat-text-4);` |
| `.skeleton-shimmer` | `background: linear-gradient(90deg, rgba(255,255,255,0.08) 25%, rgba(255,255,255,0.18) 50%, rgba(255,255,255,0.08) 75%);` | `background: linear-gradient(90deg, var(--chat-shimmer, color-mix(in srgb, var(--color-base-content) 6%, transparent)) 25%, var(--chat-shimmer-hi, color-mix(in srgb, var(--color-base-content) 14%, transparent)) 50%, var(--chat-shimmer, color-mix(in srgb, var(--color-base-content) 6%, transparent)) 75%);` |

并在文件末尾追加（Phase 4 断言 4：reduced-motion 静止自家装饰动画；daisyUI loading 指示器按范围拍板 #8 保留）：

```css
@media (prefers-reduced-motion: reduce) {
  .skeleton-shimmer {
    animation: none;
  }
}
```

> 附带修正：`.skeleton-shimmer` 的 fallback 由白色系改为深色系——SessionList 骨架在浅色 `bg-base-200` 上原本几乎不可见（白 shimmer 盖浅灰底），fallback 改深后会话栏骨架可见；`.chat-window` 子树内仍走沉浸 token，视觉不变。

- [ ] **Step 3：Message.vue 替换硬编码色**

| 位置 | 原 | 新 |
|------|----|----|
| 用户侧 hover 时间戳（`text-white/60`） | `text-white/60` | `chat-text-4` |
| AI 侧 hover 时间戳（`text-white/60`） | `text-white/60` | `chat-text-4` |
| 引用 chip 按钮 | `bg-black/25 backdrop-blur text-white/90 rounded-full … hover:bg-black/40 transition-colors max-w-48` | `chat-chip-btn chat-text rounded-full … transition-colors max-w-48` |
| 引用 chip 段号（`text-white/75`） | `text-white/75` | `chat-text-3` |
| `:deep(code)` | `background: rgba(0, 0, 0, 0.4);` | `background: var(--chat-code-inline-bg);` |
| `:deep(pre)` | `background: rgba(0, 0, 0, 0.45);` | `background: var(--chat-code-bg);` |
| `:deep(blockquote)` | `border-left: 3px solid rgba(255, 255, 255, 0.3); … color: rgba(255, 255, 255, 0.85);` | `border-left: 3px solid var(--chat-hairline); … color: var(--chat-text-2);` |
| `:deep(a)` | `color: #7dd3fc;` | `color: var(--chat-link);` |
| 代码复制按钮 | `background: rgba(0, 0, 0, 0.5); color: rgba(255, 255, 255, 0.85);` | `background: var(--chat-code-bg); color: var(--chat-text);` |

- [ ] **Step 4：ChatHistory.vue / InputField.vue / Microphone.vue / WindowHeader.vue 替换**

`ChatHistory.vue`：

| 原 | 新 |
|----|----|
| `<p class="text-center text-sm text-red-300">{{ loadError }}</p>` | `<p class="text-center text-sm chat-error">{{ loadError }}</p>` |
| `<p v-if="character?.introduction" class="text-white/90 text-lg leading-relaxed">` | `<p v-if="character?.introduction" class="chat-text text-lg leading-relaxed">` |
| 示例问题按钮 `class="bg-black/25 backdrop-blur text-white/90 rounded-full px-4 py-2 text-sm cursor-pointer hover:bg-black/40 transition-colors focus-visible:ring-2 ring-white/40"` | `class="chat-chip-btn chat-text rounded-full px-4 py-2 text-sm cursor-pointer transition-colors chat-ring"` |

`InputField.vue`：

| 元素 | 原 | 新 |
|------|----|----|
| 🎤 按钮 | `… justify-center text-white cursor-pointer hover:bg-black/20 transition-colors focus-visible:ring-2 ring-white/40 tooltip tooltip-top` + `:class="[LISTENING, TRANSCRIBING].includes(micState) ? 'bg-[var(--accent)]' : '']"` | `… justify-center chat-icon-btn cursor-pointer hover:bg-black/20 transition-colors chat-ring tooltip tooltip-top` + `:class="[VOICE_STATES.LISTENING, VOICE_STATES.TRANSCRIBING].includes(micState) ? 'bg-[var(--accent)] is-active' : ''"` |
| textarea | `… resize-none bg-black/35 backdrop-blur text-base text-white rounded-xl px-3 py-2.5 leading-6 outline-none` | `… resize-none glass-panel text-base chat-text rounded-xl px-3 py-2.5 leading-6 outline-none` |
| 停止按钮 | `… justify-center text-white cursor-pointer bg-[var(--accent)] focus-visible:ring-2 ring-white/40 tooltip tooltip-top` | `… justify-center chat-icon-btn is-active cursor-pointer bg-[var(--accent)] chat-ring tooltip tooltip-top` |
| 发送按钮 | `… justify-center text-white cursor-pointer transition-opacity focus-visible:ring-2 ring-white/40 tooltip tooltip-top` | `… justify-center chat-icon-btn is-active cursor-pointer transition-opacity chat-ring tooltip tooltip-top` |
| 错误条文字 | `<p class="text-red-300 text-xs flex-1"` | `<p class="chat-error text-xs flex-1"` |

`Microphone.vue`：

| 原 | 新 |
|----|----|
| 容器 `class="relative w-full h-12 flex items-center bg-black/35 backdrop-blur rounded-xl"` | `class="relative w-full h-12 flex items-center glass-panel rounded-xl"` |
| 三处 `<span class="text-white/40 …">`（初始化中/正在聆听…/识别中...） | `class="chat-text-5 …"`（保留原有 size/margin 类） |
| 取消按钮 `div role="button" tabindex="0"` + `@keydown.enter/space` | 见 Task 7 Step 3（原生 `<button type="button">`，与 a11y 一起改） |

`WindowHeader.vue`：

| 原 | 新 |
|----|----|
| 头部容器 `class="h-14 shrink-0 px-3 flex items-center justify-between gap-2 bg-black/40 backdrop-blur"` | `class="h-14 shrink-0 px-3 flex items-center justify-between gap-2 glass-bar"` |
| ☰ 按钮 `class="lg:hidden btn btn-sm btn-circle btn-ghost text-white"` | `class="lg:hidden btn btn-sm btn-circle btn-ghost chat-icon-btn"` |
| ✕ 按钮 `class="btn btn-sm btn-circle btn-ghost text-white"` | `class="btn btn-sm btn-circle btn-ghost chat-icon-btn"` |

- [ ] **Step 5：构建 + 目检两种模式**

Run:
```bash
npm --prefix frontend run test:unit
npm --prefix frontend run build
Select-String -Path backend/static/frontend/assets/*.css -Pattern "chat-simple"   # 产物含简约模式规则（注意：构建经 Lightning CSS 压缩，勿用带空格的 CSS 字面量做断言）
```
Expected: 112 passed；build exit 0；grep ≥1。

目检（本地，`http://localhost:5173`；⚙ 开关在 Task 6 落地后可临时用控制台切换）：
```js
localStorage.setItem('chatSimpleBg', 'true'); location.reload()
```
1. 窗口变 `#f7f7f7` 纯色、无蒙层、舞台浅灰；AI 气泡为白色卡片（带 1px 描边）、文字深色；用户气泡仍为深色底白字。
2. 头部条/输入栏为浅灰面板 + 1px 描边，图标为深色且可见。
3. 代码块、引用块、日期胶囊、引用 chip、示例问题在浅底下均可读。
4. 清回 `localStorage.removeItem('chatSimpleBg')` 并刷新 → 沉浸模式与 Phase 3 视觉一致（无回归）。

- [ ] **Step 6：提交**

```bash
git add frontend/src/assets/main.css frontend/src/components/character/chat_field/chat_history/message/Message.vue frontend/src/components/character/chat_field/chat_history/ChatHistory.vue frontend/src/components/character/chat_field/input_field/InputField.vue frontend/src/components/character/chat_field/input_field/Microphone.vue frontend/src/components/chat/chat_window/WindowHeader.vue
git commit -m "feat(chat): 简约背景模式（.chat-window 主题 token + daisyUI 浅色对比覆盖，沉浸模式零视觉回归）"
```

---

## Task 6：WindowHeader ⚙ 设置弹层 + 头部组件无障碍

**Files:**
- Modify: `frontend/src/components/chat/chat_window/WindowHeader.vue`
- Modify: `frontend/src/components/character/chat_field/VoiceToggle.vue`
- Modify: `frontend/src/components/character/chat_field/character_photo_field/CharacterPhotoField.vue`

- [ ] **Step 1：WindowHeader 加 ⚙ 弹层（两个开关）**

```vue
<script setup lang="ts">
import { onBeforeUnmount, ref, useTemplateRef, watch } from 'vue'
import CharacterPhotoField from '@/components/character/chat_field/character_photo_field/CharacterPhotoField.vue'
import VoiceToggle from '@/components/character/chat_field/VoiceToggle.vue'
import { useChatSettings } from '@/composables/useChatSettings.js'

defineProps(['character'])
const emits = defineEmits(['close', 'openDrawer'])

const { simpleBackground, autoSendVoice, toggleSimple, toggleAutoSend } = useChatSettings()

// ⚙ 设置弹层（Q6）：简约背景 + 语音自动发送；点外部/Esc 关闭
const settingsOpen = ref(false)
const settingsRef = useTemplateRef('settings-ref')

function onDocPointerDown(e) {
  if (!settingsRef.value?.contains(e.target)) settingsOpen.value = false
}

function onKeydown(e) {
  if (e.key === 'Escape') settingsOpen.value = false
}

watch(settingsOpen, (open) => {
  if (open) {
    document.addEventListener('pointerdown', onDocPointerDown)
    window.addEventListener('keydown', onKeydown)
  } else {
    document.removeEventListener('pointerdown', onDocPointerDown)
    window.removeEventListener('keydown', onKeydown)
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocPointerDown)
  window.removeEventListener('keydown', onKeydown)
})
</script>
```

模板右列（`☰` 与 `VoiceToggle` 之后、`✕` 之前）插入：

```html
      <div ref="settings-ref" class="relative">
        <button type="button"
                class="btn btn-sm btn-circle btn-ghost chat-icon-btn"
                aria-label="聊天设置"
                :aria-expanded="settingsOpen ? 'true' : 'false'"
                aria-haspopup="dialog"
                data-tip="设置"
                @click="settingsOpen = !settingsOpen">
          ⚙
        </button>

        <div v-if="settingsOpen"
             role="dialog"
             aria-label="聊天设置"
             class="absolute right-0 top-full mt-2 z-30 w-60 rounded-xl bg-base-100 text-base-content p-3 shadow-xl">
          <label class="flex items-center justify-between gap-3 py-1.5 cursor-pointer">
            <span class="text-sm">简约背景</span>
            <input type="checkbox"
                   class="toggle toggle-sm"
                   :checked="simpleBackground"
                   aria-label="简约背景"
                   @change="toggleSimple" />
          </label>
          <label class="flex items-center justify-between gap-3 py-1.5 cursor-pointer">
            <span class="text-sm">语音自动发送</span>
            <input type="checkbox"
                   class="toggle toggle-sm"
                   :checked="autoSendVoice"
                   aria-label="语音自动发送"
                   @change="toggleAutoSend" />
          </label>
          <p class="text-[11px] text-base-content/60 pt-1 leading-snug">
            看到背景图时已自动适配蒙层；如仍觉得花，可开简约背景。
          </p>
        </div>
      </div>
```

- [ ] **Step 2：VoiceToggle 语义化 + aria**

`VoiceToggle.vue` 模板整体替换为：

```html
<template>
  <button type="button"
          class="h-10 w-10 rounded-full glass-panel
                 flex items-center justify-center cursor-pointer
                 hover:bg-black/60 transition-colors shrink-0 chat-ring"
          :aria-label="voiceEnabled ? '语音已开启，点击关闭' : '语音已关闭，点击开启'"
          :aria-pressed="voiceEnabled ? 'true' : 'false'"
          :title="voiceEnabled ? '语音已开启' : '语音已关闭'"
          @click="toggle">
    <SpeakerIcon :enabled="voiceEnabled" />
  </button>
</template>
```

- [ ] **Step 3：CharacterPhotoField 语义化 + aria**

`CharacterPhotoField.vue` 第一个根节点替换为：

```html
  <button type="button"
          class="h-10 w-fit rounded-full glass-panel flex items-center gap-2 px-2 cursor-pointer chat-ring"
          :aria-label="`查看${character.name}的详情`"
          @click="handleAvatarClick">
    <div class="avatar">
      <div class="w-8 rounded-full">
        <img :src="character.photo" alt="">
      </div>
    </div>
    <div class="chat-text text-sm line-clamp-1 break-all">
      {{ character.name }}
    </div>
  </button>
```

- [ ] **Step 4：构建 + 目检**

Run: `npm --prefix frontend run build` 与 `npm --prefix frontend run test:unit`
Expected: build exit 0；112 passed。

目检（`http://localhost:5173`）：
1. 点 ⚙ → 弹层出现；勾「简约背景」→ 窗口立即变纯色；点弹层外 → 关闭；Esc → 关闭。
2. 刷新后两项开关状态保持。
3. `document.querySelectorAll('button:not([aria-label])').length` → 在聊天页应为 0（关闭按钮/会话项除外，若有则逐个补 aria）。
4. 头像 pill / 语音按钮点击行为与改造前一致（详情弹窗、语音开关）。

- [ ] **Step 5：提交**

```bash
git add frontend/src/components/chat/chat_window/WindowHeader.vue frontend/src/components/character/chat_field/VoiceToggle.vue frontend/src/components/character/chat_field/character_photo_field/CharacterPhotoField.vue
git commit -m "feat(chat): WindowHeader ⚙ 设置弹层（简约背景 + 语音自动发送）+ 头部组件语义化与 aria（Phase 4 断言 4）"
```

---

## Task 7：InputField 语音自动发送接线 + Microphone 取消按钮原生化

**Files:**
- Modify: `frontend/src/components/character/chat_field/input_field/InputField.vue`
- Modify: `frontend/src/components/character/chat_field/input_field/Microphone.vue`

- [ ] **Step 1：InputField 接 `autoSendVoice` + 800ms 定时器**

脚本区 import 段加入：

```js
import { useChatSettings } from "@/composables/useChatSettings.js";
```

在 `const { voiceEnabled } = useVoiceToggle()` 之后加入：

```js
const { autoSendVoice } = useChatSettings()

// 语音自动发送（LD §4.6 / §6）：confirm 回填后 800ms 自动发送；用户编辑/重录/取消/发送均取消计时
const AUTO_SEND_DELAY = 800
let autoSendTimer = null

function clearAutoSendTimer() {
  if (autoSendTimer) {
    clearTimeout(autoSendTimer)
    autoSendTimer = null
  }
}
```

`onMicTranscript` 改为：

```js
function onMicTranscript(text, seq) {
  // 迟到结果（CANCEL 后 in-flight ASR）或旧会话结果丢弃：状态 + seq 令牌双守卫（LD §6「忽略结果」）
  if (!acceptTranscript(micState.value, seq, activeMicSeq.value)) return
  message.value = text       // 回填 textarea（D6：不再识别即发送；watch(message) 自动 autoGrow）
  transition(VOICE_EVENTS.TRANSCRIPT_TEXT)
  if (autoSendVoice.value) {
    clearAutoSendTimer()
    autoSendTimer = setTimeout(() => {
      autoSendTimer = null
      handleSend()
    }, AUTO_SEND_DELAY)
  }
}
```

取消计时的四处接线：
1. `handleSend()` 函数体最前面（`let content = ""` 之前）加 `clearAutoSendTimer()`
2. textarea 的 `@input` 改为 `@input="clearAutoSendTimer(); transition(VOICE_EVENTS.EDIT_TEXT)"`
3. `handleMicClick()` 函数体最前面加 `clearAutoSendTimer()`
4. `onUnmounted(() => { … })` 内加 `clearAutoSendTimer()`（放在 `audioPlayer.pause()` 之前）

- [ ] **Step 2：构建 + 目检**

Run: `npm --prefix frontend run build` 与 `npm --prefix frontend run test:unit`
Expected: build exit 0；112 passed。

目检（本地，需真实麦克风）：
1. ⚙ 打开「语音自动发送」→ 点 🎤 说一句 → 识别文本回填后约 0.8s 自动发出（消息出现在历史中）。
2. 关闭开关 → 再录 → 只回填不发送。
3. 开启状态下识别回填后**立刻手动编辑** → 计时取消，不自动发送。
4. 开启状态下识别回填后立刻点 🎤 重录 → 计时取消。
5. 关闭开关时仍有在途计时（先开启录制，弹层里关掉开关）→ 最长 0.8s 内发出一次；可接受，登记为已知边界。

- [ ] **Step 3：Microphone 取消按钮原生化**

`Microphone.vue` 模板中的取消节点替换为：

```html
    <!--取消（✕ 语义，沿用 KeyboardIcon；原生 button 自带 Enter/Space 可达）-->
    <button type="button"
            class="absolute right-2 w-8 h-8 flex justify-center items-center cursor-pointer chat-text chat-ring"
            aria-label="取消语音输入"
            @click="emits('cancel')">
      <KeyboardIcon/>
    </button>
```

> 注意：`Microphone` 渲染在 `InputField` 的 `<form>` 内，必须保留 `type="button"`，否则点击会提交表单。

- [ ] **Step 4：构建 + 目检 + 提交**

Run:
```bash
npm --prefix frontend run test:unit && npm --prefix frontend run build
git add frontend/src/components/character/chat_field/input_field/InputField.vue frontend/src/components/character/chat_field/input_field/Microphone.vue
git commit -m "feat(chat): 语音自动发送接线（confirm 后 800ms，编辑/重录/发送取消计时）+ Microphone 取消按钮原生化"
```
Expected: 111 passed；build exit 0。目检：聆听中点取消 → 回 idle，且**不触发**表单提交（页面不刷新、不发送空消息）。

---

## Task 8：文档回写（spec / logic-design）

**Files:**
- Modify: `docs/superpowers/specs/2026-09-07-chat-ui-redesign-spec-for-llm.md`
- Modify: `docs/superpowers/specs/2026-09-07-chat-ui-redesign-logic-design.md`

- [ ] **Step 1：spec 回写**

1. §6.1 `--bubble-user` 行尾补：`（2026-09-10 实现确认：混合基色为黑，70% 档 = #0b825a，白字对比 ≈4.82）`。
2. §6.6 改为本轮拍板版本：
   - 窗口背景 → `var(--color-base-200)`（原 `#f5f5f4`；daisyUI 5 light 的 base-200≈#f7f7f7，与之一致且避免与 AI 气泡同色）
   - AI 气泡 → `var(--color-base-100)` + 1px `base-300` 内描边（原 base-200 在浅色窗口上不可见）
   - 「跟随系统深色」**取消**：全站单一 light 主题，深色窗口会造成深底深字（2026-09-10 拍板）
   - 入口 → WindowHeader ⚙ 设置弹层（与「语音自动发送」并列），不设独立月亮按钮（420px 头部宽度预算）
3. §13 Phase 4 断言 3（创建页预览）标注 **延后**：`（2026-09-10 拍板：创建页聊天预览属可选增强，延后到独立批次；本轮交付断言 1/2/4）`。
4. §13 Phase 4 改动行补「⚙ 设置弹层（简约背景 + 语音自动发送）」。

- [ ] **Step 2：logic-design 回写**

1. §3.4 ChatWindow：`useBackgroundAdaptive` 调用点上移到 ChatIndex（单次采样 + 根节点注入 `--accent`；`overlayK`/`userBubbleBg`/`ready` 经 props 下发），并注明 Teleport 抽屉需 SessionList 自注入 `--accent`。
2. §3.5 WindowHeader 结构行改为：`[CharacterPhotoField] [VoiceToggle] [⚙设置] [✕关闭]`（移动端另有 ☰），删除独立「简约背景切换」按钮。
3. §3.10 补实现细节：`averageLuminance` 为 sRGB 加权均值（不做 gamma 线性化）；`extractDominantColor` 取最大桶内均值；失败三层降级（空 URL / onerror / canvas 抛错）。
4. §8.2 token 清单补 `--chat-*` 家族与 `.chat-simple` 覆盖表（简约模式判定值），并记「工具类不进 @layer」的覆盖策略。
5. §10 Phase 4 行更新为「已完成（4A）」+ 4B 延后登记。
6. §11 风险表补一行：`CSS 变量注入层级（Teleport 抽屉脱离子树）→ SessionList accent prop 自注入`。

- [ ] **Step 3：提交**

```bash
git add docs/superpowers/specs/2026-09-07-chat-ui-redesign-spec-for-llm.md docs/superpowers/specs/2026-09-07-chat-ui-redesign-logic-design.md
git commit -m "docs(chat): Phase 4 拍板回写（简约模式配色/⚙ 唯一入口/accent 归属上移/4B 延后）"
```

---

## Task 9：验证与云交付

**Files:**
- 无（仅验证与交付操作）

- [ ] **Step 1：全量自动化验证**

Run:
```bash
npm --prefix frontend run test:unit
npm --prefix frontend run build
cd backend && python -m pytest web/tests/ -q
```
Expected: `Tests  112 passed`（65 + 47 新增）；build exit 0（仅既有告警）；后端 `232 passed, 3 deselected`（本轮后端零改动，作为回归基线）。

- [ ] **Step 2：本地手工验收（对照 spec §13 Phase 4 断言）**

| # | 断言 | 操作 | 通过标准 |
|---|------|------|----------|
| 1 | K 随亮度单调自适应 | 白底图角色 ↔ 深色图角色，读 `getComputedStyle(el).getPropertyValue('--overlay-k')` | ≈1.32 / 0.6；白图窗口明显压暗 |
| 2 | 简约模式切换 + 持久化 | ⚙ → 简约背景；刷新 | 窗口纯色、气泡高对比；刷新后仍为简约 |
| 3 | 图标按钮 aria-label | 聊天页执行 `document.querySelectorAll('button:not([aria-label])').length` | 0（会话项按钮已带文本，可豁免） |
| 4 | reduced-motion | DevTools Rendering → Emulate `prefers-reduced-motion: reduce`；加载历史 + 切会话 | skeleton 不闪烁、脉冲点不动、蒙层无过渡 |
| 5 | 语音自动发送 | ⚙ 开 → 录一句 | ~0.8s 自动发送；关闭后仅回填 |
| 6 | 回归（Phase 1~3） | 切会话、✕→会话中心、停止生成、引用浮层、语音错误态重试、IME Enter 不发送、长文本 4 行内滚 | 全部与 Phase 3 验收一致 |

- [ ] **Step 3：云部署（沿用 registry 流程）**

Run（本地构建推送 → 服务器拉取）：
```bash
cd /d/MyProjects/AiFriends
ACR_IMAGE=<公网 ACR 地址>:phase4 ./deploy/build.sh
ssh -i C:\Users\YGQ\.ssh\ecs-keypair.pem gqyin@8.153.201.12 'cd /home/gqyin/source-code/ai-friends && git pull && ./deploy/server-deploy.sh'
```
Expected: build/push 成功；服务器 `migrate` 无迁移（本轮零迁移）→ `up -d` → 容器 `ai-friends-web/celery/nginx/redis/db` 全 Up；`curl -s http://127.0.0.1/api/health/` → `{"status":"ok",...}`。

- [ ] **Step 4：云上手工验收**

在 `https://8.153.201.12`（同源 `/media/`）重复 Step 2 的 6 项，并额外确认：
- 「同源预检」：控制台
  ```js
  const img = new Image(); img.crossOrigin = 'anonymous';
  img.onerror = () => console.warn('采样不可用 → 已回退');
  img.onload = () => console.log('采样可用');
  img.src = '<当前角色背景图绝对 URL>';
  ```
  → 输出「采样可用」（若输出不可用，说明线上 media 与页面非同源，需按 `DJANGO_MEDIA_URL` 修正后重验）。
- 至少 3 个不同亮度的角色背景图（亮/中/暗）逐一确认蒙层观感与文字可读性。

- [ ] **Step 5：提 PR**

```bash
git push -u origin feature/gqyin/chat-ui-redesign-phase4
```
PR 正文包含：改动摘要、spec §13 Phase 4 断言 1~4 的验收结论、范围拍板 1~9、已知边界（关闭开关时在途 0.8s 计时、4B 延后、daisyUI loading 不做 reduced-motion）、以及 `docs/superpowers/reviews/` 交叉引用。

- [ ] **Step 6：合并（等用户点头）**

按用户既有偏好：**先云上验收通过 → 用户确认后再合并**；合并后用 `--no-ff` 或 GitHub PR merge，**保留分支不删除**。

---

## Self-Review

**1. Spec 覆盖检查**

| spec/LD 要求 | 落点 |
|---|---|
| S §6.5 亮度自适应（公式/主色/失败降级/竞态） | Task 1（公式与纯函数）+ Task 2（采样与竞态）+ Task 4（注入与蒙层） |
| S §6.1 `--accent` / `--overlay-k` / `--bubble-user` | Task 1（resolveUserBubble）+ Task 4（注入） |
| S §6.2/§6.3 舞台与窗口蒙层系数 | Task 4 |
| S §6.6 简约背景模式 | Task 5（token 与模式分支）+ Task 6（开关入口） |
| S §13 Phase 4 断言 1 | Task 1 单测 + Task 9 目检 1 |
| S §13 Phase 4 断言 2 | Task 5 + Task 9 目检 2 |
| S §13 Phase 4 断言 3（创建页预览） | **延后**（范围拍板 #1，已回写 spec） |
| S §13 Phase 4 断言 4（aria + reduced-motion） | Task 5 Step 2（shimmer/蒙层）+ Task 6（aria 语义化）+ Task 7 Step 3（取消按钮）+ Task 9 目检 3/4 |
| LD §3.10 `useBackgroundAdaptive` 签名与流程 | Task 2 |
| LD §3.11 `useChatSettings` | Task 3 |
| LD §3.5 WindowHeader ⚙ 弹层（两个开关） | Task 6 |
| LD §4.6/§4.7 语音自动发送 800ms | Task 7 |
| LD §8.2 token 与 `resolveUserBubble` | Task 1 + Task 5 |
| LD §9.2 `backgroundAdaptive` 用例清单 | Task 1 全部覆盖（含 clamp/单调/空输入/回退分支） |

**2. 占位符扫描**：无 TBD/TODO；每个改动步骤都给了可直接套用的代码或「原 → 新」精确替换对；命令均带 Expected。

**3. 类型/命名一致性**：`overlayK`/`accent`/`userBubbleBg`/`ready` 在 Task 2 定义、Task 4 透传（props 名 `overlay-k`/`user-bubble-bg`/`ready`）；`computeOverlayK`/`averageLuminance`/`extractDominantColor`/`accentFallback`/`resolveUserBubble`/`mixWithBlack` 在 Task 1 定义、Task 2 消费；`simpleBackground`/`autoSendVoice`/`toggleSimple`/`toggleAutoSend` 在 Task 3 定义、Task 5/6/7 消费；token 名 `--chat-text{,-2..-5}`/`--chat-glass{,-border}`/`--chat-chip{,-hover}`/`--chat-code{,-inline}-bg`/`--chat-hairline`/`--chat-link`/`--chat-ring`/`--chat-error`/`--chat-shimmer{,-hi}`/`--bubble-ai-{bg,text,border}`/`--chat-bg`/`--overlay-k`/`--user-bubble-bg` 在 Task 5 Step 1 统一声明，Task 4/5 引用一致。
