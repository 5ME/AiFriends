# 聊天界面改版 Phase 4（可读性修复与无障碍）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用固定的视觉语言（不变的颜色 + 文字描边 + 深色降级背景）保证任意角色背景图下聊天文字可读，并修复聊天页的键盘可达性缺陷。

**Architecture:** 对比度修复不动气泡底色/透明度，只在文字容器上加 `text-shadow` 描边——描边自身即深色，成为文字紧邻的背景，因此不依赖其下垫层亮度（这是它优于"加深蒙层"路线的根本原因）。开关状态走模块级单例 composable + localStorage，仿项目既有的 `useVoiceToggle` 模式。无障碍修复把两个 `<div @click>` 换成真 `<button>`。

**Tech Stack:** Vue 3 Composition API + Tailwind CSS 4 + daisyUI 5 + vitest（jsdom）；**后端零改动**。

**设计事实源：** `docs/superpowers/specs/2026-09-11-chat-ui-phase4-readability-a11y-design.md`（本计划所有数值与决策均出自该文档）

**前置：** Phase 1/2/3 已合并 master（`7279335`）；工作分支 `feature/gqyin/chat-ui-phase4-readable` 已创建，设计文档已提交（`edd59d4`）

---

## 文件结构

| 动作 | 文件 | 职责 |
|------|------|------|
| 新增 | `frontend/src/utils/contrast.js` | WCAG 相对亮度 / 对比度比值 / 描边合成。纯函数，无副作用 |
| 新增 | `frontend/src/utils/__tests__/contrast.test.js` | 锁定设计文档 §3.1/§3.3 的全部数值 |
| 新增 | `frontend/src/composables/useChatSettings.js` | `simpleBackground` / `autoSendVoice` 两个开关 + localStorage 持久化 |
| 新增 | `frontend/src/composables/__tests__/useChatSettings.test.js` | 锁定默认值与持久化 |
| 修改 | `frontend/src/assets/main.css` | 文字描边类；`prefers-reduced-motion` 兜底 |
| 修改 | `frontend/src/components/character/chat_field/chat_history/message/Message.vue` | 代码块排除描边 |
| 修改 | `frontend/src/components/chat/chat_window/ChatWindow.vue` | 简约背景模式分支 |
| 修改 | `frontend/src/components/chat/chat_window/WindowHeader.vue` | ⚙ 设置弹层（两个开关）+ 无障碍 |
| 修改 | `frontend/src/components/character/chat_field/VoiceToggle.vue` | `<div>` → `<button>` |
| 修改 | `frontend/src/components/character/chat_field/character_photo_field/CharacterPhotoField.vue` | `<div>` → `<button>` + `alt` |
| 修改 | `frontend/src/components/character/chat_field/input_field/InputField.vue` | 语音自动发送 800ms 定时器 |
| 修改 | `docs/superpowers/specs/2026-09-07-chat-ui-redesign-spec-for-llm.md` | 回写 W1~W5 事实变更 |
| 迁移 | `docs/superpowers/specs/2026-09-07-chat-ui-redesign-review.md` → `reviews/` | 评审记录归位 |
| 提交 | `docs/superpowers/reviews/2026-06-28-pr31-*.md`、`2026-08-19-*.md` | 两份未跟踪的历史评审记录纳入版本控制 |

**任务顺序的依赖关系（不可互换）：**

- Task 1 → Task 2：先有对比度纯函数与测试，才把数值落进 CSS
- Task 2 → Task 5：Task 5 的简约背景模式依赖 Task 2 已加好描边（文字对比度才不依赖背景）
- Task 3 独立于其余任务
- Task 4 → Task 5：先有设置单例，WindowHeader 才能接开关
- Task 6 独立于其余任务（只动一个文件）
- Task 7 → Task 8：先回写 spec，再整理文档目录

---

## Task 1: 对比度纯函数 + 单测（先写测试）

**Files:**
- Create: `frontend/src/utils/__tests__/contrast.test.js`
- Create: `frontend/src/utils/contrast.js`

- [ ] **Step 1: 写失败测试**

创建 `frontend/src/utils/__tests__/contrast.test.js`。测试文件里的 `rel()` 是**独立实现的 WCAG 公式**（不 import 被测模块），避免"用被测代码验证被测代码"。

```js
import { describe, expect, it } from 'vitest'
import {
  OVERLAY_K,
  srgbToLinear,
  relLuminance,
  contrastRatio,
  composite,
  overlayColor,
  strokePixelLuminance,
} from '../contrast'

/** 测试侧独立实现 WCAG 相对亮度，避免与被测实现互相印证 */
function rel(v) {
  return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)
}

const WHITE = 1.0
const STROKE = 0.85
const EPS = 1e-9

describe('contrastRatio（WCAG）', () => {
  it('白 vs 黑 = 21', () => {
    expect(contrastRatio(1.0, 0.0)).toBeCloseTo(21, 10)
  })

  it('同色 = 1', () => {
    expect(contrastRatio(0.42, 0.42)).toBeCloseTo(1, 10)
  })

  it('与参数顺序无关（自动取亮者为分子）', () => {
    expect(contrastRatio(0.1, 0.7)).toBeCloseTo(contrastRatio(0.7, 0.1), 10)
  })

  it('已知对：#10b981 纯色 vs 白 ≈ 2.54', () => {
    // #10b981 sRGB(16,185,129) → 线性亮度 0.3925（灰阶近似），白字对比度 ≈ 2.54
    expect(contrastRatio(1.0, relLuminance(16, 185, 129))).toBeCloseTo(2.54, 1)
  })
})

describe('srgbToLinear', () => {
  it('两段式曲线：0.04 走线性段，0.5 走幂函数段', () => {
    expect(srgbToLinear(0.04)).toBeCloseTo(0.04 / 12.92, 10)
    expect(srgbToLinear(0.5)).toBeCloseTo(rel(0.5), 10)
  })

  it('端点：0 → 0，1 → 1', () => {
    expect(srgbToLinear(0)).toBeCloseTo(0, 10)
    expect(srgbToLinear(1)).toBeCloseTo(1, 10)
  })
})

describe('relLuminance', () => {
  it('白 = 1，黑 = 0', () => {
    expect(relLuminance(255, 255, 255)).toBeCloseTo(1, 10)
    expect(relLuminance(0, 0, 0)).toBeCloseTo(0, 10)
  })

  it('灰阶通道：v=128 → rel(128/255)', () => {
    const v = 128 / 255
    expect(relLuminance(128, 128, 128)).toBeCloseTo(rel(v), 10)
  })
})

describe('composite / overlayColor / strokePixelLuminance', () => {
  it('alpha=1 → 取前景', () => {
    expect(composite(1.0, 1.0, 0.0)).toBe(1.0)
  })

  it('alpha=0 → 取背景', () => {
    expect(composite(0.0, 1.0, 0.37)).toBe(0.37)
  })

  it('overlayColor(a) = composite(0, a, v)', () => {
    expect(overlayColor(0.25, 0.8)).toBeCloseTo(composite(0, 0.25, 0.8), 12)
  })

  it('描边像素 = 描边黑叠在底色之上', () => {
    expect(strokePixelLuminance(0.26, STROKE)).toBeCloseTo(0.15 * 0.26, 12)
  })
})

describe('设计文档 §3.3 压力测试表（描边后白字对比度）', () => {
  it('底色 0.26（气泡本色）→ 19.80，达标', () => {
    const r = contrastRatio(WHITE, strokePixelLuminance(0.26, STROKE))
    expect(r).toBeCloseTo(19.8, 1)
    expect(r).toBeGreaterThanOrEqual(4.5)
  })

  it('底色 0.375（纯白图最坏实际）→ 18.63，达标', () => {
    const r = contrastRatio(WHITE, strokePixelLuminance(0.375, STROKE))
    expect(r).toBeCloseTo(18.63, 1)
    expect(r).toBeGreaterThanOrEqual(4.5)
  })

  it('底色 0.75（气泡全透明 + 蒙层 0.25）→ 16.92，达标', () => {
    const r = contrastRatio(WHITE, strokePixelLuminance(0.75, STROKE))
    expect(r).toBeCloseTo(16.92, 1)
    expect(r).toBeGreaterThanOrEqual(4.5)
  })

  it('底色 1.0（纯白 + 零蒙层，理论极限）→ 15.08，达标', () => {
    const r = contrastRatio(WHITE, strokePixelLuminance(1.0, STROKE))
    expect(r).toBeCloseTo(15.08, 1)
    expect(r).toBeGreaterThanOrEqual(4.5)
  })

  it('单调性：底色越暗，对比度越高', () => {
    const a = contrastRatio(WHITE, strokePixelLuminance(1.0, STROKE))
    const b = contrastRatio(WHITE, strokePixelLuminance(0.375, STROKE))
    const c = contrastRatio(WHITE, strokePixelLuminance(0.26, STROKE))
    expect(a).toBeLessThan(b)
    expect(b).toBeLessThan(c)
  })
})

describe('设计文档 §3.1 现状复核（描边之前，光靠蒙层 + 气泡不够）', () => {
  const bubbleBase = (img, scrim) => composite(0, 0.35, overlayColor(scrim, img))

  it('OVERLAY_K 顶/中/底三档 = 0.25 / 0.425 / 0.60', () => {
    expect(OVERLAY_K.TOP).toBe(0.25)
    expect(OVERLAY_K.MID).toBe(0.425)
    expect(OVERLAY_K.BOTTOM).toBe(0.60)
  })

  it('纯白图三档底色 = 0.488 / 0.374 / 0.260', () => {
    expect(bubbleBase(1.0, OVERLAY_K.TOP)).toBeCloseTo(0.488, 3)
    expect(bubbleBase(1.0, OVERLAY_K.MID)).toBeCloseTo(0.374, 3)
    expect(bubbleBase(1.0, OVERLAY_K.BOTTOM)).toBeCloseTo(0.260, 3)
  })

  it('纯白图顶部不达标（这就是要修的问题）', () => {
    expect(contrastRatio(WHITE, bubbleBase(1.0, OVERLAY_K.TOP))).toBeLessThan(4.5)
  })

  it('中灰图（0.7）顶部不达标', () => {
    expect(contrastRatio(WHITE, bubbleBase(0.7, OVERLAY_K.TOP))).toBeLessThan(4.5)
  })

  it('深图（0.4）底部达标——所以问题只在亮图', () => {
    expect(contrastRatio(WHITE, bubbleBase(0.4, OVERLAY_K.BOTTOM))).toBeGreaterThanOrEqual(4.5)
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/utils/__tests__/contrast.test.js`
Expected: FAIL —— 报 `Failed to resolve import "../contrast"`（模块不存在）

- [ ] **Step 3: 写最小实现**

创建 `frontend/src/utils/contrast.js`。全部为纯函数，输入输出均为 **0~1 的相对亮度**（不是 sRGB 分量）。

```js
// WCAG 相对亮度与对比度计算（纯函数，供单测锁定设计文档 §3.3 的数值）。
//
// 术语约定：本模块中所有"亮度"均为 WCAG 相对亮度（线性，0~1）。
// - 黑白图（灰阶）：相对亮度 == 该灰度值（灰阶下 sRGB→线性 的复合恰为恒等）
// - 白字：相对亮度恒为 1.0
//
// 为什么需要它：design 文档 §3.3 的对比度表必须可复算、可回归，
// 否则"文字看得清"这个结论只能靠肉眼，无法在改动后自动验证。

/** 窗口渐变蒙层的三档浓度（design §3.1 表：顶 25% / 中 50% / 底 75%） */
export const OVERLAY_K = {
  TOP: 0.25,
  MID: 0.425,
  BOTTOM: 0.60,
}

/**
 * 单通道 sRGB 分量（0~1）→ WCAG 相对亮度（线性）。
 */
export function srgbToLinear(c) {
  return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
}

/**
 * sRGB 三元组（0~255）→ WCAG 相对亮度（0~1）。用于测试中的具体颜色断言。
 */
export function relLuminance(r, g, b) {
  return (
    0.2126 * srgbToLinear(r / 255) +
    0.7152 * srgbToLinear(g / 255) +
    0.0722 * srgbToLinear(b / 255)
  )
}

/**
 * WCAG 对比度比值 (L_light + 0.05) / (L_dark + 0.05)，范围 1~21。
 * 与参数顺序无关。
 */
export function contrastRatio(l1, l2) {
  const hi = Math.max(l1, l2)
  const lo = Math.min(l1, l2)
  return (hi + 0.05) / (lo + 0.05)
}

/**
 * alpha 混合：fg 以 alpha 覆盖在 bg 上。三者均为相对亮度。
 */
export function composite(fg, alpha, bg) {
  return fg * alpha + bg * (1 - alpha)
}

/**
 * 黑色蒙层 rgba(0,0,0,alpha) 覆盖在底色 base 上的结果亮度（等价 composite(0, alpha, base)，语义更清晰）。
 */
export function overlayColor(alpha, base) {
  return composite(0, alpha, base)
}

/**
 * 文字描边像素的亮度：描边色 rgba(0,0,0,strokeAlpha) 覆盖在底色 base 之上。
 * 白字的紧邻背景就是这一层，因此白字对比度 = contrastRatio(1, 本函数结果)。
 */
export function strokePixelLuminance(base, strokeAlpha) {
  return overlayColor(strokeAlpha, base)
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/utils/__tests__/contrast.test.js`
Expected: PASS，约 21 个用例全绿

- [ ] **Step 5: 跑全量单测确认无回归**

Run: `cd frontend && npx vitest run`
Expected: PASS，`Test Files 5 passed`，`Tests 86 passed`（原 4 文件 65 用例 + 新增 1 文件约 21 用例）

- [ ] **Step 6: 提交**

```bash
git add frontend/src/utils/contrast.js frontend/src/utils/__tests__/contrast.test.js
git commit -m "test(chat): 对比度纯函数 + 单测（锁定 design §3.1/§3.3 数值：现状 1.95:1 不达标 → 描边后 15.08:1）"
```

---

## Task 2: 把描边落到 CSS（本轮核心修复）

**Files:**
- Modify: `frontend/src/assets/main.css`（在文件末尾追加）
- Modify: `frontend/src/components/character/chat_field/chat_history/message/Message.vue:133-137`

- [ ] **Step 1: 在 main.css 末尾追加描边类**

追加到 `frontend/src/assets/main.css` 文件**最末尾**（现有内容见 main.css:1-117；追加在末尾可保证与既有规则无顺序冲突）。

```css
/* ===== Phase 4：文字描边（design §3.2）=====
   问题：AI 气泡是 rgba(0,0,0,.35) 半透明玻璃，背景图偏亮时白字对比度仅 1.95~3.39:1（不可读）。
   做法：只给文字加 1px 深色实心描边，气泡底色/透明度/圆角/布局一律不动。
   原理：描边自身即深色，成为文字紧邻的背景，不依赖其下垫层有多亮——即使底色纯白（1.0）
        仍有 15.08:1。这是它优于"加深蒙层"路线的根本原因（蒙层永远受制于图有多亮，
        且加深到够用会压死创作者的构图，违背 spec C1）。
   数值依据与可复算实现见 frontend/src/utils/contrast.js 与其单测。 */
.msg-text-outline {
  text-shadow:
    0 0 1px rgba(0, 0, 0, 0.85),
    0 0 2px rgba(0, 0, 0, 0.55),
    0 1px 2px rgba(0, 0, 0, 0.45);
}
```

- [ ] **Step 2: 让文字容器挂上该类**

修改 `frontend/src/components/character/chat_field/chat_history/message/Message.vue`。

把（原第 130-137 行的两个规则块）：

```css
.msg-markdown {
  white-space: normal;
}
/* 用户消息纯文本（不走 markdown）：保留换行与多空格 */
.msg-markdown-plain {
  white-space: pre-wrap;
  word-break: break-word;
}
```

替换为：

```css
.msg-markdown {
  white-space: normal;
  /* Phase 4 文字描边（design §3.2）：全局类，见 main.css */
  text-shadow: var(--msg-text-shadow);
}
/* 用户消息纯文本（不走 markdown）：保留换行与多空格 */
.msg-markdown-plain {
  white-space: pre-wrap;
  word-break: break-word;
  text-shadow: var(--msg-text-shadow);
}
```

> 实现说明：`main.css` 的 `.msg-text-outline` 在本组件 scoped 样式之外，直接写在这两个类里会重复三次数值。因此**改为在 main.css 定义 CSS 变量**，见下一步。若你选择直接重复 `text-shadow` 字面量也可以，但必须与 `.msg-text-outline` 完全一致。

- [ ] **Step 3: 在 main.css 把描边值同时暴露为变量**

修改 `frontend/src/assets/main.css`：把 Step 1 追加的 `.msg-text-outline` 规则改为下面这版（补一个 `:root` 变量，供 scoped 样式引用，同时保留全局类以便将来直接在模板上用）。

```css
/* ===== Phase 4：文字描边（design §3.2）=====
   问题：AI 气泡是 rgba(0,0,0,.35) 半透明玻璃，背景图偏亮时白字对比度仅 1.95~3.39:1（不可读）。
   做法：只给文字加 1px 深色实心描边，气泡底色/透明度/圆角/布局一律不动。
   原理：描边自身即深色，成为文字紧邻的背景，不依赖其下垫层有多亮——即使底色纯白（1.0）
        仍有 15.08:1。这是它优于"加深蒙层"路线的根本原因（蒙层永远受制于图有多亮，
        且加深到够用会压死创作者的构图，违背 spec C1）。
   数值依据与可复算实现见 frontend/src/utils/contrast.js 与其单测。 */
:root {
  --msg-text-shadow:
    0 0 1px rgba(0, 0, 0, 0.85),
    0 0 2px rgba(0, 0, 0, 0.55),
    0 1px 2px rgba(0, 0, 0, 0.45);
}
.msg-text-outline {
  text-shadow: var(--msg-text-shadow);
}
```

- [ ] **Step 4: 代码块排除描边**

修改 `frontend/src/components/character/chat_field/chat_history/message/Message.vue`。把下面这两行（原第 151-153 行）：

```css
.msg-markdown :deep(code) { background: rgba(0, 0, 0, 0.4); border-radius: 4px; padding: 0.1em 0.35em; font-size: 0.85em; }
.msg-markdown :deep(pre) { position: relative; background: rgba(0, 0, 0, 0.45); border-radius: 8px; padding: 0.6em 0.8em; margin: 0.5em 0; overflow-x: auto; }
.msg-markdown :deep(pre code) { background: transparent; padding: 0; }
```

替换为：

```css
/* Phase 4：代码块自带深色底，叠描边会显脏 → 排除描边（design §3.4）。
   注意 text-shadow 会继承：pre 用 none 绝对重置；行内 code 因背景仅 0.4 仍偏亮，保留描边。 */
.msg-markdown :deep(code) { background: rgba(0, 0, 0, 0.4); border-radius: 4px; padding: 0.1em 0.35em; font-size: 0.85em; }
.msg-markdown :deep(pre) { position: relative; background: rgba(0, 0, 0, 0.45); border-radius: 8px; padding: 0.6em 0.8em; margin: 0.5em 0; overflow-x: auto; text-shadow: none; }
.msg-markdown :deep(pre code) { background: transparent; padding: 0; text-shadow: none; }
```

- [ ] **Step 5: 构建验证（不靠肉眼确认 CSS 编译通过）**

Run: `cd frontend && npm run build`
Expected: 构建成功（exit 0）；产物写入 `backend/static/frontend/`

- [ ] **Step 6: 确认产物里真的带上了描边**

Run:
```bash
cd frontend && grep -c -- "--msg-text-shadow" ../backend/static/frontend/assets/*.css
```
Expected: 每个 CSS 产物文件计数 ≥ 2（`:root` 定义处 + `.msg-text-outline` 引用处各 1；证明变量未被打包器丢弃）

- [ ] **Step 7: 提交**

```bash
git add frontend/src/assets/main.css frontend/src/components/character/chat_field/chat_history/message/Message.vue
git commit -m "fix(chat): 文字描边修复亮背景图下正文不可读（1.95:1 → 15.08:1，design §3.2；代码块排除描边）"
```

---

## Task 3: 无障碍——两个 `<div>` 改真按钮

**Files:**
- Modify: `frontend/src/components/character/chat_field/VoiceToggle.vue`
- Modify: `frontend/src/components/character/chat_field/character_photo_field/CharacterPhotoField.vue`

> 背景：这两个元素当前是 `<div @click>`。**div 不可聚焦**，键盘用户按 Tab 永远走不到，等于"用键盘开关语音 / 打开角色详情"这两个功能不存在。改成 `<button>` 后浏览器自动提供可聚焦、Enter/空格触发、读屏播报为按钮。这是功能修复，不是美化。

- [ ] **Step 1: VoiceToggle 改按钮**

修改 `frontend/src/components/character/chat_field/VoiceToggle.vue`，把 `<template>` 整块：

```vue
<template>
  <div class="h-10 w-10 rounded-full bg-black/50
              flex items-center justify-center cursor-pointer
              hover:bg-black/60 transition-colors shrink-0"
       :title="voiceEnabled ? '语音已开启' : '语音已关闭'"
       @click="toggle">
    <SpeakerIcon :enabled="voiceEnabled" />
  </div>
</template>
```

替换为：

```vue
<template>
  <!-- Phase 4 无障碍：原为 <div @click>，键盘不可达（Tab 聚焦不到）→ 改真按钮 -->
  <button type="button"
          class="h-10 w-10 rounded-full bg-black/50
                 flex items-center justify-center cursor-pointer
                 hover:bg-black/60 transition-colors shrink-0
                 focus-visible:ring-2 ring-white/60"
          :aria-label="voiceEnabled ? '关闭语音' : '开启语音'"
          :title="voiceEnabled ? '语音已开启' : '语音已关闭'"
          @click="toggle">
    <SpeakerIcon :enabled="voiceEnabled" />
  </button>
</template>
```

注意：**不加 daisyUI 的 `btn` 类**（避免其预设尺寸/背景与现有 `h-10 w-10` 冲突）；`type="button"` 必须写（否则在表单内会变成提交按钮）。

- [ ] **Step 2: CharacterPhotoField 改按钮 + 补 alt**

修改 `frontend/src/components/character/chat_field/character_photo_field/CharacterPhotoField.vue`，把 `<template>` 整块：

```vue
<template>
  <div class="h-10 w-fit rounded-full bg-black/50 flex items-center gap-2 px-2 cursor-pointer"
       @click="handleAvatarClick">
    <div class="avatar">
      <div class="w-8 rounded-full">
        <img :src="character.photo" alt="">
      </div>
    </div>
    <div class="text-white text-sm line-clamp-1 break-all">
      {{ character.name }}
    </div>
  </div>

  <CharacterDetail ref="character-detail-ref" :character="character" mode="chat"/>
</template>
```

替换为：

```vue
<template>
  <!-- Phase 4 无障碍：原为 <div @click>（键盘不可达）+ <img alt="">（无替代文本）→ 改真按钮 + 补 alt -->
  <button type="button"
          class="h-10 w-fit rounded-full bg-black/50 flex items-center gap-2 px-2 cursor-pointer
                 focus-visible:ring-2 ring-white/60"
          aria-label="查看角色详情"
          @click="handleAvatarClick">
    <div class="avatar">
      <div class="w-8 rounded-full">
        <img :src="character.photo" :alt="`${character.name}的头像`">
      </div>
    </div>
    <div class="text-white text-sm line-clamp-1 break-all">
      {{ character.name }}
    </div>
  </button>

  <CharacterDetail ref="character-detail-ref" :character="character" mode="chat"/>
</template>
```

- [ ] **Step 3: 构建验证**

Run: `cd frontend && npm run build`
Expected: 构建成功（exit 0），无 Vue 模板编译告警

- [ ] **Step 4: 确认按钮真的进了产物**

Run:
```bash
cd frontend && grep -c "查看角色详情\|开启语音\|关闭语音" ../backend/static/frontend/assets/*.js
```
Expected: 计数 ≥ 3（说明 `aria-label` 的三条文案都进了打包产物）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/character/chat_field/VoiceToggle.vue frontend/src/components/character/chat_field/character_photo_field/CharacterPhotoField.vue
git commit -m "fix(a11y): 语音开关与角色详情改为真按钮（原 div 键盘不可达）+ 头像补 alt"
```

---

## Task 4: 用户设置单例 `useChatSettings`

**Files:**
- Create: `frontend/src/composables/__tests__/useChatSettings.test.js`
- Create: `frontend/src/composables/useChatSettings.js`

> 参照既有 `frontend/src/composables/useVoiceToggle.js` 的模块级单例写法（多组件共享同一状态，避免重复读 localStorage）。
> **可测试性设计**：composable 接受可选的 storage 参数，便于单测注入内存实现，不污染 jsdom 的 localStorage、也不依赖模块重载顺序。

- [ ] **Step 1: 写失败测试**

创建 `frontend/src/composables/__tests__/useChatSettings.test.js`：

```js
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useChatSettings } from '../useChatSettings'

/** 内存版 storage，避免污染 jsdom 的 localStorage 与模块重载顺序 */
function memoryStorage(seed = {}) {
  const map = new Map(Object.entries(seed))
  return {
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => map.set(k, String(v)),
    removeItem: (k) => map.delete(k),
  }
}

describe('useChatSettings', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it('默认值：简约背景关、语音自动发送关（spec D6 默认关闭）', () => {
    const s = useChatSettings(memoryStorage())
    expect(s.simpleBackground.value).toBe(false)
    expect(s.autoSendVoice.value).toBe(false)
  })

  it('toggleSimple 翻转并写 localStorage（key: chatSimpleBg）', () => {
    const store = memoryStorage()
    const s = useChatSettings(store)
    s.toggleSimple()
    expect(s.simpleBackground.value).toBe(true)
    expect(store.getItem('chatSimpleBg')).toBe('true')
    s.toggleSimple()
    expect(s.simpleBackground.value).toBe(false)
    expect(store.getItem('chatSimpleBg')).toBe('false')
  })

  it('toggleAutoSend 翻转并写 localStorage（key: chatAutoSendVoice）', () => {
    const store = memoryStorage()
    const s = useChatSettings(store)
    s.toggleAutoSend()
    expect(s.autoSendVoice.value).toBe(true)
    expect(store.getItem('chatAutoSendVoice')).toBe('true')
  })

  it('从 localStorage 恢复（刷新后保持）', () => {
    const s = useChatSettings(memoryStorage({ chatSimpleBg: 'true', chatAutoSendVoice: 'true' }))
    expect(s.simpleBackground.value).toBe(true)
    expect(s.autoSendVoice.value).toBe(true)
  })

  it('只有字符串 "true" 才算开启，其他值一律 false', () => {
    const s = useChatSettings(memoryStorage({ chatSimpleBg: '1', chatAutoSendVoice: 'yes' }))
    expect(s.simpleBackground.value).toBe(false)
    expect(s.autoSendVoice.value).toBe(false)
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/composables/__tests__/useChatSettings.test.js`
Expected: FAIL —— 报 `Failed to resolve import "../useChatSettings"`

- [ ] **Step 3: 写实现**

创建 `frontend/src/composables/useChatSettings.js`：

```js
import { ref, watch } from 'vue'

// 默认 storage：浏览器 localStorage。测试可注入内存实现（避免污染 jsdom 与依赖模块重载顺序）。
const defaultStorage = typeof localStorage !== 'undefined' ? localStorage : null

const STORAGE_KEYS = {
  simpleBackground: 'chatSimpleBg',
  autoSendVoice: 'chatAutoSendVoice',
}

/**
 * 读取布尔设置：只有字符串 'true' 才算开启，其余（含 null / 'false' / '1'）一律 false。
 */
function readBool(storage, key) {
  if (!storage) return false
  return storage.getItem(key) === 'true'
}

/**
 * 聊天页用户设置（模块级单例，仿 useVoiceToggle）。
 *
 * 两项设置（spec §6.6 / LD §3.11，默认均关）：
 * - simpleBackground：简约背景。开启后窗口背景由角色背景图改为深色纯色，
 *   作为"背景图不可读"的用户降级通道（spec C3 硬要求）。
 * - autoSendVoice：语音自动发送。开启后语音识别完成回填输入框，800ms 后自动发出（spec D6 默认关）。
 *
 * 持久化：localStorage，刷新不丢失。
 */
export function useChatSettings(storage = defaultStorage) {
  const simpleBackground = ref(readBool(storage, STORAGE_KEYS.simpleBackground))
  const autoSendVoice = ref(readBool(storage, STORAGE_KEYS.autoSendVoice))

  watch(simpleBackground, (val) => {
    storage?.setItem(STORAGE_KEYS.simpleBackground, val.toString())
  })
  watch(autoSendVoice, (val) => {
    storage?.setItem(STORAGE_KEYS.autoSendVoice, val.toString())
  })

  function toggleSimple() {
    simpleBackground.value = !simpleBackground.value
  }

  function toggleAutoSend() {
    autoSendVoice.value = !autoSendVoice.value
  }

  return { simpleBackground, autoSendVoice, toggleSimple, toggleAutoSend }
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/composables/__tests__/useChatSettings.test.js`
Expected: PASS，5 个用例全绿

- [ ] **Step 5: 全量单测**

Run: `cd frontend && npx vitest run`
Expected: PASS，`Test Files 6 passed`，`Tests 91 passed`（contrast 约 21 + useChatSettings 5 + 原有 65）

- [ ] **Step 6: 提交**

```bash
git add frontend/src/composables/useChatSettings.js frontend/src/composables/__tests__/useChatSettings.test.js
git commit -m "feat(chat): useChatSettings 用户设置单例（简约背景 + 语音自动发送，localStorage 持久化）+ 单测"
```

---

## Task 5: 简约背景模式 + ⚙ 设置弹层

**Files:**
- Modify: `frontend/src/components/chat/chat_window/ChatWindow.vue`（模板 90-95 行一带）
- Modify: `frontend/src/components/chat/chat_window/WindowHeader.vue`（整块重写）

- [ ] **Step 1: WindowHeader 加 ⚙ 设置弹层**

把 `frontend/src/components/chat/chat_window/WindowHeader.vue` **整个文件**替换为：

```vue
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import CharacterPhotoField from '@/components/character/chat_field/character_photo_field/CharacterPhotoField.vue'
import VoiceToggle from '@/components/character/chat_field/VoiceToggle.vue'
import { useChatSettings } from '@/composables/useChatSettings'

defineProps(['character'])
const emits = defineEmits(['close', 'openDrawer'])

// ⚙ 设置弹层（LD §3.5 / Q6 拍板落点）：点击外部关闭
const settingsOpen = ref(false)
const settingsRef = ref(null)
const { simpleBackground, autoSendVoice, toggleSimple, toggleAutoSend } = useChatSettings()

function onDocClick(e) {
  if (settingsOpen.value && settingsRef.value && !settingsRef.value.contains(e.target)) {
    settingsOpen.value = false
  }
}
onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))
</script>

<template>
  <div class="h-14 shrink-0 px-3 flex items-center justify-between gap-2
              bg-black/40 backdrop-blur">
    <!-- 头像 + 名字 pill（点击开详情，复用现有能力） -->
    <CharacterPhotoField :character="character" />

    <div class="flex items-center gap-2">
      <!-- 移动端会话抽屉入口（spec §4.2「头部菜单按钮」；lg:hidden = 桌面端列表常驻无需） -->
      <button type="button"
              class="lg:hidden btn btn-sm btn-circle btn-ghost text-white"
              aria-label="打开会话列表"
              data-tip="会话"
              @click="emits('openDrawer')">
        ☰
      </button>
      <VoiceToggle />
      <!-- ⚙ 设置（简约背景 / 语音自动发送，spec §6.6 + D6） -->
      <div ref="settingsRef" class="relative">
        <button type="button"
                class="btn btn-sm btn-circle btn-ghost text-white"
                aria-label="设置"
                data-tip="设置"
                @click="settingsOpen = !settingsOpen">
          ⚙
        </button>
        <div v-if="settingsOpen"
             class="absolute right-0 top-11 z-30 w-52 rounded-xl border border-white/10
                    bg-neutral-900/95 backdrop-blur-xl shadow-2xl p-1.5">
          <label class="flex items-center justify-between gap-3 px-2 py-2 rounded-lg
                        hover:bg-white/10 cursor-pointer text-sm text-white/90">
            <span>简约背景</span>
            <input type="checkbox"
                   class="toggle toggle-sm"
                   :checked="simpleBackground"
                   @change="toggleSimple" />
          </label>
          <label class="flex items-center justify-between gap-3 px-2 py-2 rounded-lg
                        hover:bg-white/10 cursor-pointer text-sm text-white/90">
            <span>语音自动发送</span>
            <input type="checkbox"
                   class="toggle toggle-sm"
                   :checked="autoSendVoice"
                   @change="toggleAutoSend" />
          </label>
        </div>
      </div>
      <button type="button"
              class="btn btn-sm btn-circle btn-ghost text-white"
              aria-label="关闭对话"
              data-tip="关闭"
              @click="emits('close')">
        ✕
      </button>
    </div>
  </div>
</template>

<style scoped>
</style>
```

- [ ] **Step 2: ChatWindow 接简约背景分支**

修改 `frontend/src/components/chat/chat_window/ChatWindow.vue`。

先在 `<script setup lang="ts">` 的 import 区（第 5 行 `import InputField ...` 之后）加一行：

```js
import { useChatSettings } from '@/composables/useChatSettings'
```

再在 `const history = ref([])`（第 11 行）之前加一行：

```js
const { simpleBackground } = useChatSettings()
```

然后把模板里的舞台与窗口背景两块（第 90-102 行）：

```html
    <!-- 舞台（桌面端：同图模糊压暗延展；移动端无舞台） -->
    <div class="absolute inset-0 overflow-hidden hidden lg:block">
      <div class="absolute -inset-[10%] bg-cover bg-center stage-blur"
           :style="{ backgroundImage: `url(${friend.character.background_image})` }"></div>
      <div class="absolute inset-0 stage-dim"></div>
    </div>

    <!-- 角色之窗（3:5，桌面居中 / 移动端全屏，纯 CSS 尺寸公式） -->
    <div class="chat-window relative flex flex-col">
    <!-- 窗口背景 + 渐变蒙层 -->
    <div class="absolute inset-0 bg-cover bg-center"
         :style="{ backgroundImage: `url(${friend.character.background_image})` }"></div>
    <div class="absolute inset-0 window-scrim"></div>
```

替换为：

```html
    <!-- 舞台（桌面端：同图模糊压暗延展；移动端无舞台）
         Phase 4：简约背景模式下改为深色纯色（spec §6.6 用户降级通道 C3） -->
    <div class="absolute inset-0 overflow-hidden hidden lg:block">
      <template v-if="!simpleBackground">
        <div class="absolute -inset-[10%] bg-cover bg-center stage-blur"
             :style="{ backgroundImage: `url(${friend.character.background_image})` }"></div>
        <div class="absolute inset-0 stage-dim"></div>
      </template>
      <div v-else class="absolute inset-0 bg-[#0c0a09]"></div>
    </div>

    <!-- 角色之窗（3:5，桌面居中 / 移动端全屏，纯 CSS 尺寸公式） -->
    <div class="chat-window relative flex flex-col"
         :class="{ 'bg-[#1c1917]': simpleBackground }">
    <!-- 窗口背景 + 渐变蒙层（简约模式下整块不渲染，避免覆盖纯色底） -->
    <template v-if="!simpleBackground">
      <div class="absolute inset-0 bg-cover bg-center"
           :style="{ backgroundImage: `url(${friend.character.background_image})` }"></div>
      <div class="absolute inset-0 window-scrim"></div>
    </template>
```

> 说明：简约模式**只做深色版**（`#1c1917` 窗口 / `#0c0a09` 舞台）。浅色版会使玻璃头部条、名字 pill、日期胶囊、引用 chips 这批"白字系"元素集体失效，需连带重做，收益不成比例（design §5.1）。

- [ ] **Step 3: 构建验证**

Run: `cd frontend && npm run build`
Expected: 构建成功（exit 0）

- [ ] **Step 4: 确认开关文案与深色值进了产物**

Run:
```bash
cd frontend && grep -c "简约背景\|语音自动发送\|1c1917" ../backend/static/frontend/assets/*.js
```
Expected: 计数 ≥ 3

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/chat/chat_window/WindowHeader.vue frontend/src/components/chat/chat_window/ChatWindow.vue
git commit -m "feat(chat): ⚙ 设置弹层（简约背景 + 语音自动发送）+ 简约背景深色降级分支（spec §6.6/C3）"
```

---

## Task 6: 语音自动发送（800ms）+ reduced-motion 兜底

**Files:**
- Modify: `frontend/src/components/character/chat_field/input_field/InputField.vue`（import 区 7-11 行、状态区 34-39 行、onUnmounted 252-260 行）
- Modify: `frontend/src/assets/main.css`（末尾追加）

- [ ] **Step 1: InputField 接入设置**

修改 `frontend/src/components/character/chat_field/input_field/InputField.vue`。

在 import 区（第 11 行 `import { voiceReducer, ... } from "@/utils/voiceState";` 之后）加：

```js
import { useChatSettings } from "@/composables/useChatSettings";
```

在语音状态机声明区（第 39 行 `const activeMicSeq = ref(0)` 之后）加：

```js
// Phase 4 语音自动发送（spec D6 默认关）：确认态停留 AUTO_SEND_DELAY 后自动发出。
// 不新增对外接口——复用 handleSend()，参数取当时的 message 值。
const AUTO_SEND_DELAY = 800
const { autoSendVoice } = useChatSettings()
let autoSendTimer = null

watch(micState, (s) => {
  if (autoSendTimer) {
    clearTimeout(autoSendTimer)
    autoSendTimer = null
  }
  if (s !== VOICE_STATES.CONFIRM || !autoSendVoice.value) return
  autoSendTimer = setTimeout(() => {
    autoSendTimer = null
    // 回到条件判断（不信任闭包里的旧值）：只有仍处确认态才发
    if (micState.value === VOICE_STATES.CONFIRM) handleSend()
  }, AUTO_SEND_DELAY)
})
```

- [ ] **Step 2: 卸载时清定时器**

把 onUnmounted 钩子（第 252-260 行）：

```js
onUnmounted(() => {
  if (abortController) {
    abortController.abort()  // 通知后端客户端已断开，停止 TTS
    abortController = null
  }
  audioPlayer.pause();
  audioPlayer.src = '';
  window.removeEventListener('keydown', onGlobalKeydown)
});
```

替换为：

```js
onUnmounted(() => {
  if (abortController) {
    abortController.abort()  // 通知后端客户端已断开，停止 TTS
    abortController = null
  }
  if (autoSendTimer) {        // Phase 4：切换会话时取消待触发的自动发送
    clearTimeout(autoSendTimer)
    autoSendTimer = null
  }
  audioPlayer.pause();
  audioPlayer.src = '';
  window.removeEventListener('keydown', onGlobalKeydown)
});
```

- [ ] **Step 3: main.css 补 reduced-motion 兜底**

追加到 `frontend/src/assets/main.css` 末尾：

```css
/* ===== Phase 4：prefers-reduced-motion 兜底（spec §12 硬要求）=====
   Microphone.vue 内的波形/三点已在 Phase 3 处理；此处补两处遗漏：
   1. .skeleton-shimmer —— 会话列表骨架与聊天记录骨架共用（main.css 内的循环动画）
   2. .loading-dots —— "思考中"指示器（ChatHistory.vue 用的 daisyUI 组件），
      其旋转由 daisyUI 的 ::before/::after 承载，必须一并停掉 */
@media (prefers-reduced-motion: reduce) {
  .skeleton-shimmer {
    animation: none;
  }
  .loading-dots::before,
  .loading-dots::after {
    animation: none;
    opacity: 0.6;    /* 用不透明度区分三点，静止下仍能看出是"指示中" */
  }
}
```

- [ ] **Step 4: 构建验证**

Run: `cd frontend && npm run build`
Expected: 构建成功（exit 0）

- [ ] **Step 5: 确认 reduced-motion 与自动发送都进了产物**

Run:
```bash
cd frontend && grep -c "prefers-reduced-motion" ../backend/static/frontend/assets/*.css && grep -c "chatAutoSendVoice" ../backend/static/frontend/assets/*.js
```
Expected: CSS 中 ≥ 1，JS 中 ≥ 1

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/character/chat_field/input_field/InputField.vue frontend/src/assets/main.css
git commit -m "feat(chat): 语音自动发送开关接入（确认态 800ms 自动发出，可被重录/卸载取消）+ reduced-motion 补骨架与思考中指示"
```

---

## Task 7: 回写 spec 的事实变更（W1~W5）

**Files:**
- Modify: `docs/superpowers/specs/2026-09-07-chat-ui-redesign-spec-for-llm.md`

- [ ] **Step 1: 回写 §13 Phase 4 断言 1 与断言 3**

在 `docs/superpowers/specs/2026-09-07-chat-ui-redesign-spec-for-llm.md` 的 §13「Phase 4 —— 自适应与质感」段（第 406-413 行一带），把：

```
### Phase 4 —— 自适应与质感
改动：useBackgroundAdaptive 全量接入（蒙层系数 + accent）；简约背景开关；创建页聊天预览 + 亮度提示；无障碍细节。

验收断言：
1. 白图（avg≈0.9）→ overlayK≈1.32（深蒙层）；黑图（avg≈0.1）→ overlayK≈0.6（浅蒙层）；K 随亮度单调递增（公式值，自动化单测）。
2. 简约模式切换后窗口背景为纯色、气泡高对比；刷新后保持（localStorage）。
3. 创建/编辑角色页可看到"聊天效果预览"。
4. 全部图标按钮存在 aria-label；reduced-motion 下动画静止。
```

替换为：

```
### Phase 4 —— 可读性修复与无障碍（2026-09-11 目标改写，见文末变更登记）
改动：**文字描边**修复亮背景图下正文不可读；简约背景开关（深色降级）；语音自动发送开关；无障碍（真按钮 + aria-label + reduced-motion）。
**不做**：亮度自适应蒙层（`useBackgroundAdaptive` / `--overlay-k`）、主色提取（accent）、创建页聊天预览。

验收断言：
1. ~~overlayK 公式值单测~~ → **已作废**：蒙层保持固定 0.25→0.60，不引入亮度自适应。对比度改由**文字描边**保证：描边后白字对比度在底色 0.26 / 0.375 / 0.75 / 1.0 四档下分别为 19.80 / 18.63 / 16.92 / 15.08，全部 ≥4.5:1（自动化单测锁定，见 `frontend/src/utils/__tests__/contrast.test.js`）。
2. 简约模式切换后窗口背景为纯色、气泡高对比；刷新后保持（localStorage）。
3. ~~创建/编辑角色页可看到"聊天效果预览"~~ → **本期不做**（可读性已由描边兜底，预览的救火价值消失）。
4. 全部图标按钮存在 aria-label；reduced-motion 下动画静止。
5. **新增**：键盘可 Tab 到达语音开关与角色详情按钮，Enter/空格可触发（原为 `<div @click>`，键盘完全不可达）。
```

- [ ] **Step 2: 更正 §6.5 与 §11 E3 的错误论断**

在 §6.5「亮度自适应算法」标题下方（第 219 行 `### 6.5 亮度自适应算法（useBackgroundAdaptive.js）` 之后）插入：

```
> **2026-09-11 作废声明**：本节**本期不实施**，保留作为未来备选。
> 原因：① 主色 accent 已拍板固定为 `#10b981`，不再从背景图提取；② 可读性问题经实测确认**不能靠蒙层解决**——单改蒙层需顶部浓度达 0.57，背景图上半部分将基本不可见，违背 C1；③ 改用文字描边后，白字对比度与背景亮度解耦（纯白底色下仍有 15.08:1）。详见 `2026-09-11-chat-ui-phase4-readability-a11y-design.md` §3。
```

把 §11 边界情况表里 E3 那一行（第 343 行）：

```
| E3 | 背景极亮/极暗 | 亮度自适应蒙层（§6.5）+ 深色 AI 气泡（R2）共同保证正文 ≥4.5:1；用户可切简约模式 |
```

替换为：

```
| E3 | 背景极亮/极暗 | **原文"蒙层 + 深色气泡共同保证 ≥4.5:1"经实测不成立**（纯白图顶部仅 1.95:1；单改任一项都救不回：气泡需 0.77 不透明度、或顶部蒙层需 0.57）。改由**文字描边**保证（design §3.3），另提供简约模式作降级 |
```

- [ ] **Step 3: 在文件末尾登记变更理由**

在 `2026-09-07-chat-ui-redesign-spec-for-llm.md` **文件最末尾**追加：

```markdown
---

## 附：2026-09-11 变更登记（Phase 4 实施前回写）

| # | 位置 | 变更 | 理由 |
|---|------|------|------|
| W1 | §13 Phase 4 断言 3 | 标为"本期不做" | 用户拍板 P4-D2。可读性已由文字描边兜底，创建页预览的"救火"价值消失 |
| W2 | §13 Phase 4 断言 1 | 标为"已作废"，改为描边方案的对比度断言 | overlayK 自适应不实施（P4-D1 颜色固定 + 描边方案已解决可读性） |
| W3 | §6.5 整节 | 加作废声明，保留为未来备选 | 同上 |
| W4 | §11 E3 | 更正错误论断并附实测数字 | 原文"蒙层 + 深色气泡共同保证 ≥4.5:1"在数学上不成立，实测纯白图顶部仅 1.95:1 |
| W5 | §13 Phase 4 断言 2 / 4 | 保留为必做，并新增断言 5 | 本轮确实实施：简约背景开关、aria-label、reduced-motion；断言 5 为键盘可达性（原 `<div @click>` 缺陷） |

决策记录（三项用户拍板）：P4-D1 界面主色固定 `#10b981`（不做背景图主色提取）；P4-D2 创建页聊天预览不做；P4-D3 己方气泡加同款描边、颜色不动。
详细设计与实测依据：`2026-09-11-chat-ui-phase4-readability-a11y-design.md`。
```

- [ ] **Step 4: 验证回写结果（独立进程读盘断言）**

Run:
```bash
cd D:/MyProjects/AiFriends && grep -c "已作废\|本期不做\|2026-09-11 作废声明\|2026-09-11 变更登记" docs/superpowers/specs/2026-09-07-chat-ui-redesign-spec-for-llm.md
```
Expected: 计数 ≥ 4

- [ ] **Step 5: 提交**

```bash
git add docs/superpowers/specs/2026-09-07-chat-ui-redesign-spec-for-llm.md
git commit -m "docs(chat): spec 回写 Phase 4 事实变更（W1~W5）—— 作废 overlayK 自适应、更正 E3 对比度论断、登记三项用户决策"
```

---

## Task 8: 评审文档归位

**Files:**
- Move: `docs/superpowers/specs/2026-09-07-chat-ui-redesign-review.md` → `docs/superpowers/reviews/`
- Add: `docs/superpowers/reviews/2026-06-28-pr31-docker-compose-review.md`
- Add: `docs/superpowers/reviews/2026-08-19-deployment-registry-refactor-spec-review.md`

- [ ] **Step 1: 移动误归档的评审报告**

Run:
```bash
cd D:/MyProjects/AiFriends && git mv docs/superpowers/specs/2026-09-07-chat-ui-redesign-review.md docs/superpowers/reviews/2026-09-07-chat-ui-redesign-review.md && git status --short -- docs/superpowers/
```
Expected: 显示 `R  docs/superpowers/specs/2026-09-07-chat-ui-redesign-review.md -> docs/superpowers/reviews/2026-09-07-chat-ui-redesign-review.md`

- [ ] **Step 2: 纳入两份未跟踪的历史评审记录**

Run:
```bash
cd D:/MyProjects/AiFriends && git add docs/superpowers/reviews/2026-06-28-pr31-docker-compose-review.md docs/superpowers/reviews/2026-08-19-deployment-registry-refactor-spec-review.md && git status --short -- docs/superpowers/reviews/
```
Expected: 两条 `A ` 记录

- [ ] **Step 3: 确认没有误伤工作区其他杂物**

Run:
```bash
cd D:/MyProjects/AiFriends && git status --short
```
Expected: 仍能看到未跟踪/未提交的 `.codegraph/.gitignore` 与 `.superpowers/brainstorm/**` 条目（**它们不应出现在本次暂存区**），且除 docs 与 frontend 外无其他待提交文件

- [ ] **Step 4: 提交**

```bash
git add docs/superpowers/reviews/
git commit -m "docs: 评审记录归位（chat-ui-redesign-review 移入 reviews/）+ 补提交两份历史评审记录"
```

---

## Task 9: 全量验证（门 4 前的自证）

**Files:** 无（只跑验证）

- [ ] **Step 1: 前端单测全量**

Run: `cd frontend && npx vitest run`
Expected: PASS，`Test Files 6 passed`，`Tests 91 passed`（contrast 约 21 + useChatSettings 5 + 原有 65）

- [ ] **Step 2: 前端生产构建**

Run: `cd frontend && npm run build`
Expected: exit 0

- [ ] **Step 3: 后端测试未被波及（本轮零后端改动，仍需实测确认）**

Run: `cd backend && python -m pytest web/tests/ -q`
Expected: PASS（221 passed；若本地 PG/Redis 未起则记录为环境限制，不得写"通过"）

- [ ] **Step 4: 汇总证据并报告门 4**

把 Step 1~3 的真实输出贴进汇报，并列出需要在**用户浏览器**里人工确认的项（design §9 的人工清单 3~9）：

- 亮背景图（纯白/高亮）下 AI 消息与己方消息文字清晰可读（对照当前 master 的"几乎看不见"）
- 深色背景图下文字清晰，且背景观感未被压死（证明没有加深蒙层）
- 键盘 Tab 能聚焦语音开关、角色详情按钮、麦克风、发送键，Enter/空格可触发
- ⚙ 弹层两个开关切换即时生效、刷新后保持
- 语音自动发送开启后说一句话 → 回填后约 0.8s 自动发出；期间点 🎤 重录则不发送
- 系统开启"减少动态效果"后骨架微光与"思考中"三点静止且仍可见
- markdown 代码块：无描边、深色底正常、复制按钮可用

---

## 范围外（明确不做，防止蔓延）

1. 亮度自适应蒙层 / `--overlay-k` / `useBackgroundAdaptive` / `utils/backgroundAdaptive.js`（design §4）
2. 主色提取 / `resolveUserBubble` / `accentFallback`（P4-D1）
3. 创建页聊天效果预览 + 亮度提示（P4-D2）
4. 简约模式的**浅色版**（design §5.1：白字系元素需连带重做，收益不成比例）
5. 工作区其他杂物：`.codegraph/.gitignore` 改动、`.superpowers/brainstorm/**` 删除记录
6. 后端任何改动（本轮零后端）
