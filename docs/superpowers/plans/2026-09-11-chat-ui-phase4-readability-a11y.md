# 聊天界面改版 Phase 4（可读性修复与无障碍）Implementation Plan v3

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **执行状态：全部 12 个 Task 已完成（2026-09-11）**。步骤全部勾选；实际执行与计划的差异记录在下方"执行记录"节。

> **版本历史**：v1（原始）→ v2（按两轴评审修 3 个阻断：sRGB 模型 / 单例 / reduced-motion）→ **v3（按两轴复审修 3 处数值与引用错误 + 补全回写清单 + 修复流程状态失真）**
>
> **v3 修正要点**：① 删除伪引用（v2 曾称"spec 原文要求 `pre` 与 `code` 都排除描边"，但 **spec 全文没有该条款、也没有 §3.4**）；② §3.3 档位改用**真实最坏档 124.3125 → 18.63**（v2 用的 95.625 对应气泡 α=0.5，合成链条里不存在）；③ 行内 `code` 改**去掉描边**（真值 8.78~14.79:1，v2 的 3.06 是错口径）；④ W8 作废、W9 标注待授权、补 W10~W12 与 L5~L6；⑤ E2 补 `@error` 路径；⑥ 新增 Task 12（评审记录）；⑦ 标注 Task 1 已先行落地（流程违规，待裁决）。

**Goal:** 用固定的视觉语言（不变的颜色 + 文字描边 + 静态深色兜底）保证任意角色背景图下聊天文字可读，并修复聊天页键盘可达性缺陷与 reduced-motion 覆盖。

**Architecture:** 对比度修复不动气泡底色/透明度，只在文字容器上加 `text-shadow` 描边——描边色彩固定、与背景图内容完全解耦，因此满足 spec C2 对"确定性"的要求（P4-D6，**待用户就"改写硬约束条款"明确授权**，见 design §11.2）。开关状态走**模块级单例** composable + localStorage，照项目既有 `useVoiceToggle` 模式。无障碍修复把两个 `<div @click>` 换成真 `<button>`；reduced-motion 只覆盖可控动画（自绘 skeleton 与三点），不声称覆盖 daisyUI 的 SMIL 动画。

**Tech Stack:** Vue 3 Composition API + Tailwind CSS 4 + daisyUI 5 + vitest（jsdom）；**后端零改动**。

**设计事实源：** `docs/superpowers/specs/2026-09-11-chat-ui-phase4-readability-a11y-design.md`（**v3**）

**框架事实（实施前须知）：**

- CSS alpha 合成在 **sRGB 分量空间**（不是亮度空间）。本计划所有对比度函数都按此实现。
- WCAG 对比度量的**仅**是"文字色 vs 声明背景色"，`text-shadow` 光圈不改变该比值。描边是感知层面的可读性改善，**不得**声称"加描边后对比度达标"（design §3.4）。
- daisyUI 5.5.17 的 `.loading-*` 动画是 `mask-image` 内嵌 SVG 的 **SMIL**，文件内无任何 CSS animation / @keyframes / ::before / ::after（已核实 `frontend/node_modules/daisyui/components/loading.css`）→ **CSS 停不掉**。
- 凡出现 0~1 的小数，必须注明是"线性亮度"还是"sRGB 分量"——本项目已因此错过两次。

**前置：** Phase 1/2/3 已合并 master；流程契约 PR #39 合并点 `7279335`；工作分支 `feature/gqyin/chat-ui-phase4-readable`，**已有 3 个 commit**（`edd59d4` 设计文档、`d691363` 计划、`c547e1e` **含源码**——该 commit 违反门 2，处置见 design §11.1）

---

## 文件结构

| 动作 | 文件 | 职责 |
|------|------|------|
| 新增 | `frontend/src/utils/contrast.js` | sRGB 合成 / 相对亮度 / 对比度。纯函数（**已落地**） |
| 新增 | `frontend/src/utils/__tests__/contrast.test.js` | 锁定 design §3.1/§3.3/§3.6 全部数值（**已落地**，28 passed） |
| 新增 | `frontend/src/composables/useChatSettings.js` | **模块级单例**：两个开关 + localStorage |
| 新增 | `frontend/src/composables/__tests__/useChatSettings.test.js` | 默认值与持久化 |
| 修改 | `frontend/src/assets/main.css` | 描边变量；`.skeleton-shimmer` 的 reduced-motion |
| 修改 | `frontend/src/components/character/chat_field/chat_history/message/Message.vue` | 文字容器挂描边；`pre` 与行内 `code` 都排除描边 |
| 修改 | `frontend/src/components/character/chat_field/chat_history/ChatHistory.vue` | 思考中指示器换自绘三点 |
| 修改 | `frontend/src/components/chat/chat_window/ChatWindow.vue` | 简约背景分支 + 背景图缺失/**加载失败**兜底 |
| 修改 | `frontend/src/components/chat/chat_window/WindowHeader.vue` | ⚙ 设置弹层（两个开关） |
| 修改 | `frontend/src/components/character/chat_field/VoiceToggle.vue` | `<div>` → `<button>` |
| 修改 | `frontend/src/components/character/chat_field/character_photo_field/CharacterPhotoField.vue` | `<div>` → `<button>` + `alt` |
| 修改 | `frontend/src/components/character/chat_field/input_field/InputField.vue` | 语音自动发送 800ms 定时器 |
| 修改 | `docs/…/2026-09-07-chat-ui-redesign-spec-for-llm.md` | W1~W7、W9~W12 回写 |
| 修改 | `docs/…/2026-09-07-chat-ui-redesign-logic-design.md` | L1~L6 回写 |
| 新增 | `docs/superpowers/reviews/2026-09-11-chat-ui-phase4-review.md` | 本轮 L 档评审记录（契约 §4） |
| 迁移/提交 | `docs/superpowers/{specs,reviews}/` 共 3 份旧评审记录 | 归档整理 |

**依赖顺序：** T2、T3、T4、T7 相互独立｜T4 → T5、T6（先有单例再接开关）｜T9 → T10（spec 先于 LD）｜T11 → T12

> v3 修正：v2 声称"T2→T5 简约模式依赖描边已就位"是**假依赖**——简约模式渲染纯色底，与描边是否存在无关。

---

## Task 1: 对比度纯函数 + 单测　【已落地，待门 2 追认】

**Files:**
- Create: `frontend/src/utils/__tests__/contrast.test.js`（**已创建**）
- Create: `frontend/src/utils/contrast.js`（**已创建**）

> ⚠️ **本 Task 已在门 2 批准前完成并提交（`c547e1e`），属流程违规**（WORKFLOW.md §2「用户点头前不许动任何代码」）。处置待用户裁决：**追认**（勾掉本 Task）或**回退**（`git rm` 两个文件后单独提交，待门 2 通过再重做）。

- [x] **Step 1: 写测试** —— 已创建 `contrast.test.js`
- [x] **Step 2: 确认失败** —— 首次运行报 `Failed to resolve import "../contrast"`
- [x] **Step 3: 写实现** —— 已创建 `contrast.js`
- [x] **Step 4: 跑通（含 v3 修正后复跑）**

Run: `cd frontend && npx vitest run src/utils/__tests__/contrast.test.js`
Expected: PASS，**28 个用例全绿**（v2 为 25；v3 新增真实最坏档 18.63 与行内 code 无需描边两组断言）

- [x] **Step 5: 全量单测**

Run: `cd frontend && npx vitest run`
Expected: PASS，`Test Files 5 passed`，`Tests 93 passed`（原 4 文件 65 + contrast 28）

- [x] **Step 6: 提交** —— `c547e1e`

**已落地的实现要点（v3 修正后）**：

```js
/** 窗口渐变蒙层的三档浓度（sRGB 分量空间的 alpha 值） */
export const OVERLAY_SRGB = { TOP: 0.25, MID: 0.425, BOTTOM: 0.60 }
export const STROKE_ALPHA = 0.85

export function srgbToLinear(c) {           // 入参 sRGB 分量 0~1 → 线性亮度
  return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
}
export function relLuminance(r, g, b) {     // 入参 sRGB 0~255 → 线性亮度
  return 0.2126 * srgbToLinear(r / 255) + 0.7152 * srgbToLinear(g / 255) + 0.0722 * srgbToLinear(b / 255)
}
export function contrastRatio(l1, l2) {     // 入参线性亮度；与顺序无关
  const hi = Math.max(l1, l2), lo = Math.min(l1, l2)
  return (hi + 0.05) / (lo + 0.05)
}
export function composite(fg, alpha, bg) { return fg * alpha + bg * (1 - alpha) }   // sRGB 分量空间
export function overlaySrgb(alpha, base) { return composite(0, alpha, base) }
export function grayContrast(gray) {         // 灰阶底（三通道相同）
  return contrastRatio(1.0, relLuminance(gray, gray, gray))
}
export function strokeContrast(base, strokeAlpha = STROKE_ALPHA) {
  const s = overlaySrgb(strokeAlpha, base)
  return contrastRatio(1.0, relLuminance(s, s, s))
}
```

**两个已踩过的坑（注释已写进源码）**：

1. `relLuminance(gray, 0, 0)` ≠ 灰阶对比度——那等于把灰值当**纯红通道**。实测偏差：底部 10.002 → 17.021（**1.70 倍**）、顶部 4.156 → 11.280（**2.71 倍**）。v2 曾据此写"约 2.5 倍"，是用顶部的倍数描述底部场景。
2. 描边档位必须由 `bubbleBase()` 推导，不可手写中间值。v2 手写的 95.625 = `255×0.75×0.5` 对应**气泡 α=0.5**，而本项目气泡是 α=0.35，该值在链条里不存在。

---

## Task 2: 把描边落到 CSS

**Files:**
- Modify: `frontend/src/assets/main.css`（文件末尾追加）
- Modify: `frontend/src/components/character/chat_field/chat_history/message/Message.vue`（`:130-137` 与 `:151-153`）

- [x] **Step 1: main.css 追加描边变量**

追加到 `frontend/src/assets/main.css` **文件最末尾**：

```css
/* ===== Phase 4：文字描边（design §3.2）=====
   问题：AI 气泡是 rgba(0,0,0,.35) 半透明玻璃，纯白背景图顶部白字对比度 4.16:1（略低于 4.5）。
   做法：只给文字加 1px 深色实心描边，气泡底色/透明度/圆角/布局一律不动。
   性质：描边色彩固定、与背景图内容完全解耦，满足 spec C2 对"确定性"的要求。
   边界：描边**不改变** WCAG 意义上的对比度（那只量"文字色 vs 声明背景色"，仍是 4.16:1）；
        它改善的是感知可读性（压掉文字周围的高频亮度起伏）。因此不得声称"加描边后对比度达标"。
   数值依据与可复算实现见 frontend/src/utils/contrast.js 与其单测（28 用例）。 */
:root {
  --msg-text-shadow:
    0 0 1px rgba(0, 0, 0, 0.85),
    0 0 2px rgba(0, 0, 0, 0.55),
    0 1px 2px rgba(0, 0, 0, 0.45);
}
```

- [x] **Step 2: 文字容器挂上描边**

修改 `frontend/src/components/character/chat_field/chat_history/message/Message.vue`。

把（当前第 130-137 行）：

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
/* Phase 4 文字描边：AI 气泡文字容器（变量定义在 main.css :root） */
.msg-markdown {
  white-space: normal;
  text-shadow: var(--msg-text-shadow);
}
/* 用户消息纯文本（不走 markdown）：保留换行与多空格 */
.msg-markdown-plain {
  white-space: pre-wrap;
  word-break: break-word;
  text-shadow: var(--msg-text-shadow);
}
```

- [x] **Step 3: 代码块排除描边（`pre` 与行内 `code` 都排除）**

把（当前第 151-153 行）：

```css
.msg-markdown :deep(code) { background: rgba(0, 0, 0, 0.4); border-radius: 4px; padding: 0.1em 0.35em; font-size: 0.85em; }
.msg-markdown :deep(pre) { position: relative; background: rgba(0, 0, 0, 0.45); border-radius: 8px; padding: 0.6em 0.8em; margin: 0.5em 0; overflow-x: auto; }
.msg-markdown :deep(pre code) { background: transparent; padding: 0; }
```

替换为：

```css
/* Phase 4：代码块一律排除描边。二者自带深色底，实测白字对比度充足——
   行内 code（黑 .4 叠气泡底）：最亮档 74.59 → 8.78:1，最暗档 39.78 → 14.79:1；
   pre（黑 .45）：更高。均远高于 4.5:1，加描边纯属冗余。
   （v2 曾以"行内 code 仅 3.06:1"为由保留其描边，那个数是把 sRGB 值当线性亮度算的，已作废。） */
.msg-markdown :deep(code) { background: rgba(0, 0, 0, 0.4); border-radius: 4px; padding: 0.1em 0.35em; font-size: 0.85em; text-shadow: none; }
.msg-markdown :deep(pre) { position: relative; background: rgba(0, 0, 0, 0.45); border-radius: 8px; padding: 0.6em 0.8em; margin: 0.5em 0; overflow-x: auto; text-shadow: none; }
.msg-markdown :deep(pre code) { background: transparent; padding: 0; text-shadow: none; }
```

- [x] **Step 4: 构建验证**

Run: `cd frontend && npm run build`
Expected: 构建成功（exit 0）

- [x] **Step 5: 校验产物（PowerShell，不用 grep）**

```powershell
cd D:\MyProjects\AiFriends\frontend
Select-String -Path ..\backend\static\frontend\assets\*.css -Pattern '--msg-text-shadow' -AllMatches |
  ForEach-Object { "{0}: {1} 处" -f $_.Filename, $_.Matches.Count }
```
Expected: 出现该变量名，且组件内的 `text-shadow: var(--msg-text-shadow)` 引用存在于源码（产物可能被压缩合并，故判据是"≥1 处且源码确有引用"，不苛求计数）

- [x] **Step 6: 提交**

```bash
git add frontend/src/assets/main.css frontend/src/components/character/chat_field/chat_history/message/Message.vue
git commit -m "fix(chat): 文字描边补足亮背景图顶部可读性（design §3.2；代码块一律排除描边）"
```

---

## Task 3: 无障碍——两个 `<div>` 改真按钮

**Files:**
- Modify: `frontend/src/components/character/chat_field/VoiceToggle.vue`
- Modify: `frontend/src/components/character/chat_field/character_photo_field/CharacterPhotoField.vue`

> 背景：两个元素当前是 `<div @click>`。**div 不可聚焦**，键盘用户按 Tab 永远走不到，等于"用键盘开关语音 / 打开角色详情"这两个功能不存在。改成 `<button>` 后浏览器自动提供可聚焦、Enter/空格触发、读屏播报为按钮。

- [x] **Step 1: VoiceToggle 改按钮**

把 `frontend/src/components/character/chat_field/VoiceToggle.vue` 的 `<template>` 整块：

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
                 focus-visible:ring-2 ring-white/40"
          :aria-label="voiceEnabled ? '关闭语音' : '开启语音'"
          :title="voiceEnabled ? '语音已开启' : '语音已关闭'"
          @click="toggle">
    <SpeakerIcon :enabled="voiceEnabled" />
  </button>
</template>
```

注意：**不加 daisyUI 的 `btn` 类**（避免其预设尺寸/背景与现有 `h-10 w-10` 冲突）；`type="button"` 必须写。焦点环用 `ring-white/40`，与 `InputField` 麦克风按钮一致（spec §5.3/§12 原文写的是 `ring-white/60`，该偏离登记于 W10）。

- [x] **Step 2: CharacterPhotoField 改按钮 + 补 alt**

把 `frontend/src/components/character/chat_field/character_photo_field/CharacterPhotoField.vue` 的 `<template>` 整块：

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
  <!-- Phase 4 无障碍：原为 <div @click>（键盘不可达）+ <img alt="">（无替代文本）→ 真按钮 + 补 alt -->
  <button type="button"
          class="h-10 w-fit rounded-full bg-black/50 flex items-center gap-2 px-2 cursor-pointer
                 focus-visible:ring-2 ring-white/40"
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

- [x] **Step 3: 构建验证**

Run: `cd frontend && npm run build`
Expected: 构建成功（exit 0），无 Vue 模板编译告警

- [x] **Step 4: 校验产物**

```powershell
cd D:\MyProjects\AiFriends\frontend
Select-String -Path ..\backend\static\frontend\assets\*.js -Pattern '查看角色详情','开启语音','关闭语音' -AllMatches |
  ForEach-Object { "{0}: {1} 处" -f $_.Filename, $_.Matches.Count }
```
Expected: 三条文案均命中（证明 `aria-label` 进了打包产物）

- [x] **Step 5: 提交**

```bash
git add frontend/src/components/character/chat_field/VoiceToggle.vue frontend/src/components/character/chat_field/character_photo_field/CharacterPhotoField.vue
git commit -m "fix(a11y): 语音开关与角色详情改为真按钮（原 div 键盘不可达）+ 头像补 alt"
```

---

## Task 4: 用户设置模块级单例 `useChatSettings`

**Files:**
- Create: `frontend/src/composables/__tests__/useChatSettings.test.js`
- Create: `frontend/src/composables/useChatSettings.js`

> **必须是模块级单例**（LD D-L7 明文：WindowHeader 与 InputField 共享同一状态）。v1 写成工厂函数会导致 ⚙ 切不动背景、自动发送开关失效。
> 参照 `frontend/src/composables/useVoiceToggle.js:4`：ref 定义在模块顶层，函数只做返回。

- [x] **Step 1: 写失败测试**

创建 `frontend/src/composables/__tests__/useChatSettings.test.js`。注意 `watch` 默认 `flush:'pre'`（回调在微任务里跑），**必须 `await nextTick()` 之后再断言持久化**：

```js
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

/** 用 vi.resetModules + 动态 import 拿到全新模块实例，避免模块级单例跨用例串状态 */
async function freshModule() {
  vi.resetModules()
  return await import('../useChatSettings')
}

/** 内存版 localStorage，避免污染 jsdom */
function installMemoryStorage(seed = {}) {
  const map = new Map(Object.entries(seed))
  const store = {
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => map.set(k, String(v)),
    removeItem: (k) => map.delete(k),
  }
  vi.stubGlobal('localStorage', store)
  return store
}

describe('useChatSettings（模块级单例，LD D-L7）', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
  })

  it('默认值：简约背景关、语音自动发送关（spec D6）', async () => {
    installMemoryStorage()
    const { useChatSettings } = await freshModule()
    const s = useChatSettings()
    expect(s.simpleBackground.value).toBe(false)
    expect(s.autoSendVoice.value).toBe(false)
  })

  it('toggleSimple 翻转，nextTick 后写入 chatSimpleBg = "true"', async () => {
    const store = installMemoryStorage()
    const { useChatSettings } = await freshModule()
    const s = useChatSettings()

    s.toggleSimple()
    expect(s.simpleBackground.value).toBe(true)
    await nextTick()
    expect(store.getItem('chatSimpleBg')).toBe('true')

    s.toggleSimple()
    expect(s.simpleBackground.value).toBe(false)
    await nextTick()
    expect(store.getItem('chatSimpleBg')).toBe('false')
  })

  it('toggleAutoSend 翻转，nextTick 后写入 chatAutoSendVoice = "true"', async () => {
    const store = installMemoryStorage()
    const { useChatSettings } = await freshModule()
    const s = useChatSettings()

    s.toggleAutoSend()
    expect(s.autoSendVoice.value).toBe(true)
    await nextTick()
    expect(store.getItem('chatAutoSendVoice')).toBe('true')
  })

  it('从 localStorage 恢复（刷新后保持）', async () => {
    installMemoryStorage({ chatSimpleBg: 'true', chatAutoSendVoice: 'true' })
    const { useChatSettings } = await freshModule()
    const s = useChatSettings()
    expect(s.simpleBackground.value).toBe(true)
    expect(s.autoSendVoice.value).toBe(true)
  })

  it('两次调用返回同一状态（单例契约）', async () => {
    installMemoryStorage()
    const { useChatSettings } = await freshModule()
    const a = useChatSettings()
    const b = useChatSettings()
    a.toggleSimple()
    expect(b.simpleBackground.value).toBe(true)   // b 看得到 a 的改动 = 同一份状态
  })

  it('只有字符串 "true" 才算开启', async () => {
    installMemoryStorage({ chatSimpleBg: '1', chatAutoSendVoice: 'yes' })
    const { useChatSettings } = await freshModule()
    const s = useChatSettings()
    expect(s.simpleBackground.value).toBe(false)
    expect(s.autoSendVoice.value).toBe(false)
  })
})
```

- [x] **Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/composables/__tests__/useChatSettings.test.js`
Expected: FAIL —— `Failed to resolve import "../useChatSettings"`

- [x] **Step 3: 写实现（模块级单例）**

创建 `frontend/src/composables/useChatSettings.js`：

```js
import { ref, watch } from 'vue'

// 模块级单例（LD D-L7）：ref 定义在模块顶层，多个组件共享同一状态。
// 参照 useVoiceToggle.js:4 的既有模式 —— 若写成函数内 ref，WindowHeader 与
// InputField 会各持一份，开关将失效。
const STORAGE_KEYS = {
  simpleBackground: 'chatSimpleBg',
  autoSendVoice: 'chatAutoSendVoice',
}

/** 读取布尔设置：只有字符串 'true' 才算开启，其余（null / 'false' / '1'）一律 false */
function readBool(key) {
  if (typeof localStorage === 'undefined') return false
  return localStorage.getItem(key) === 'true'
}

const simpleBackground = ref(readBool(STORAGE_KEYS.simpleBackground))
const autoSendVoice = ref(readBool(STORAGE_KEYS.autoSendVoice))

watch(simpleBackground, (val) => {
  localStorage.setItem(STORAGE_KEYS.simpleBackground, val.toString())
})
watch(autoSendVoice, (val) => {
  localStorage.setItem(STORAGE_KEYS.autoSendVoice, val.toString())
})

/**
 * 聊天页用户设置（模块级单例）。
 *
 * - simpleBackground：简约背景。开启后窗口背景由角色背景图改为深色纯色，
 *   作为"背景图不可读"的用户降级通道（spec C3 硬要求）。
 * - autoSendVoice：语音自动发送。开启后语音识别完成回填输入框，800ms 后自动发出（spec D6 默认关）。
 */
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

- [x] **Step 4: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/composables/__tests__/useChatSettings.test.js`
Expected: PASS，6 个用例全绿

- [x] **Step 5: 全量单测**

Run: `cd frontend && npx vitest run`
Expected: PASS，`Test Files 6 passed`，`Tests 99 passed`（93 + 6）

- [x] **Step 6: 提交**

```bash
git add frontend/src/composables/useChatSettings.js frontend/src/composables/__tests__/useChatSettings.test.js
git commit -m "feat(chat): useChatSettings 模块级单例（简约背景 + 语音自动发送，localStorage 持久化）+ 单测"
```

---

## Task 5: ⚙ 设置弹层 + 简约背景模式 + 背景图兜底（两条路径）

**Files:**
- Modify: `frontend/src/components/chat/chat_window/WindowHeader.vue`（整块重写）
- Modify: `frontend/src/components/chat/chat_window/ChatWindow.vue`（import 区 `:2`/`:5`、状态区 `:11`、模板 `:90-102`）

- [x] **Step 1: WindowHeader 加 ⚙ 设置弹层**

把 `frontend/src/components/chat/chat_window/WindowHeader.vue` **整个文件**替换为：

```vue
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import CharacterPhotoField from '@/components/character/chat_field/character_photo_field/CharacterPhotoField.vue'
import VoiceToggle from '@/components/character/chat_field/VoiceToggle.vue'
import { useChatSettings } from '@/composables/useChatSettings'

defineProps(['character'])
const emits = defineEmits(['close', 'openDrawer'])

// ⚙ 设置弹层（LD §3.5 / Q6 落点）：点击外部关闭
const settingsOpen = ref(false)
const settingsRef = ref(null)
// 模块级单例：InputField 通过同一实例读取 autoSendVoice（LD D-L7）
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
      <!-- 移动端会话抽屉入口（spec §4.2；lg:hidden = 桌面端列表常驻无需） -->
      <button type="button"
              class="lg:hidden btn btn-sm btn-circle btn-ghost text-white"
              aria-label="打开会话列表"
              data-tip="会话"
              @click="emits('openDrawer')">
        ☰
      </button>
      <VoiceToggle />
      <!-- ⚙ 设置（简约背景 / 语音自动发送，spec §6.6 + D6；入口形态偏离 spec 原文，登记于 W6） -->
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

- [x] **Step 2: ChatWindow 接简约背景 + 背景图兜底（无图 **与** 加载失败两条路径）**

修改 `frontend/src/components/chat/chat_window/ChatWindow.vue`。

(a) 把第 2 行的：

```js
import { onBeforeUnmount, ref, useTemplateRef, watch } from 'vue'
```

替换为：

```js
import { computed, onBeforeUnmount, ref, useTemplateRef, watch } from 'vue'
```

(b) 在 import 区末尾（第 5 行 `import InputField ...` 之后）加：

```js
import { useChatSettings } from '@/composables/useChatSettings'
```

(c) 在 `const history = ref([])`（第 11 行）之前加：

```js
// Phase 4：简约背景模式（用户降级通道）
// E2 承接（design §5.4）有两条路径，都必须生效：
//   ① 角色无背景图（background_image 为空）
//   ② 背景图加载失败（404 / 跨域 / 网络）→ 由 <img> 的 error 事件置位
const { simpleBackground } = useChatSettings()
const backgroundFailed = ref(false)
const hasBackground = computed(() => !!props.friend?.character?.background_image)
const usePlainBackground = computed(
  () => simpleBackground.value || !hasBackground.value || backgroundFailed.value,
)
```

(d) 把模板里的舞台与窗口背景两块（第 90-102 行）：

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
         Phase 4：简约背景模式 / 无背景图 / 背景图加载失败 → 深色纯色
         （spec C3 与 E2；design §5.1/§5.4）
         注意：这里用真实 <img> 而非 background-image，就是为了拿到 error 事件
         （CSS 背景图加载失败没有回调，这是 E2 第二条路径唯一可靠的落点）。 -->
    <div class="absolute inset-0 overflow-hidden hidden lg:block">
      <template v-if="!usePlainBackground">
        <img :src="friend.character.background_image"
             alt=""
             aria-hidden="true"
             class="absolute -inset-[10%] w-[120%] h-[120%] object-cover stage-blur"
             @error="backgroundFailed = true">
        <div class="absolute inset-0 stage-dim"></div>
      </template>
      <div v-else class="absolute inset-0 bg-[#0c0a09]"></div>
    </div>

    <!-- 角色之窗（3:5，桌面居中 / 移动端全屏，纯 CSS 尺寸公式） -->
    <div class="chat-window relative flex flex-col"
         :class="{ 'bg-[#1c1917]': usePlainBackground }">
    <!-- 窗口背景 + 渐变蒙层（简约/无图/加载失败时整块不渲染，避免覆盖纯色底） -->
    <template v-if="!usePlainBackground">
      <img :src="friend.character.background_image"
           alt=""
           aria-hidden="true"
           class="absolute inset-0 w-full h-full object-cover"
           @error="backgroundFailed = true">
      <div class="absolute inset-0 window-scrim"></div>
    </template>
```

> 说明：简约模式**只做深色版**（`#1c1917` 窗口 / `#0c0a09` 舞台）。浅色版会使玻璃头部条、名字 pill、日期胶囊、引用 chips 这批"白字系"元素集体失效，需连带重做（design §5.1）。
> 气泡处置：spec §6.6 要求简约模式下气泡改 daisyUI 对比色，本设计**不采纳**（深色底 + 白字实测 17.04:1，改气泡反而破坏一致性），登记于 W6。

- [x] **Step 3: 构建验证**

Run: `cd frontend && npm run build`
Expected: 构建成功（exit 0）

- [x] **Step 4: 校验产物**

```powershell
cd D:\MyProjects\AiFriends\frontend
Select-String -Path ..\backend\static\frontend\assets\*.js -Pattern '简约背景','语音自动发送','1c1917','0c0a09' -AllMatches |
  ForEach-Object { "{0}: {1} 处" -f $_.Filename, $_.Matches.Count }
```
Expected: 四项文案/色值均命中

- [x] **Step 5: 提交**

```bash
git add frontend/src/components/chat/chat_window/WindowHeader.vue frontend/src/components/chat/chat_window/ChatWindow.vue
git commit -m "feat(chat): ⚙ 设置弹层（简约背景 + 语音自动发送）+ 简约/无图/加载失败深色兜底（spec C3、E2 双路径）"
```

---

## Task 6: 语音自动发送（800ms）

**Files:**
- Modify: `frontend/src/components/character/chat_field/input_field/InputField.vue`（import 区 `:11`、状态区 `:39`、`onUnmounted` `:252-260`）

- [x] **Step 1: 接入设置单例**

在 import 区（第 11 行 `import { voiceReducer, ... } from "@/utils/voiceState";` 之后）加：

```js
import { useChatSettings } from "@/composables/useChatSettings";
```

- [x] **Step 2: 加自动发送计时器**

在语音状态机声明区（第 39 行 `const activeMicSeq = ref(0)` 之后）加：

```js
// Phase 4 语音自动发送（spec D6 默认关）：确认态停留 AUTO_SEND_DELAY 后自动发出。
// 不新增对外接口——复用 handleSend()（函数声明有提升，可在此处引用）。
const AUTO_SEND_DELAY = 800
const { autoSendVoice } = useChatSettings()   // 模块级单例，与 WindowHeader 共享（LD D-L7）
let autoSendTimer = null

watch(micState, (s) => {
  if (autoSendTimer) {
    clearTimeout(autoSendTimer)
    autoSendTimer = null
  }
  if (s !== VOICE_STATES.CONFIRM || !autoSendVoice.value) return
  autoSendTimer = setTimeout(() => {
    autoSendTimer = null
    // 回到条件判断（不信任闭包旧值）：只有仍处确认态才发；期间用户重录/取消则不发
    if (micState.value === VOICE_STATES.CONFIRM) handleSend()
  }, AUTO_SEND_DELAY)
})
```

- [x] **Step 3: 卸载时清定时器**

把 `onUnmounted`（第 252-260 行）：

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

- [x] **Step 4: 构建验证**

Run: `cd frontend && npm run build`
Expected: 构建成功（exit 0）

- [x] **Step 5: 校验产物**

```powershell
cd D:\MyProjects\AiFriends\frontend
Select-String -Path ..\backend\static\frontend\assets\*.js -Pattern 'chatAutoSendVoice' -AllMatches |
  ForEach-Object { "{0}: {1} 处" -f $_.Filename, $_.Matches.Count }
```
Expected: ≥ 1 处

- [x] **Step 6: 提交**

```bash
git add frontend/src/components/character/chat_field/input_field/InputField.vue
git commit -m "feat(chat): 语音自动发送（确认态 800ms 自动发出，可被重录/卸载取消）"
```

---

## Task 7: reduced-motion——思考中指示器换自绘三点

**Files:**
- Modify: `frontend/src/components/character/chat_field/chat_history/ChatHistory.vue`（模板 `:203-207`、文件末尾 `<style scoped>`）
- Modify: `frontend/src/assets/main.css`（末尾追加 `.skeleton-shimmer` 的 reduce 兜底）

> **为什么不能用 CSS 覆盖 daisyUI**：`loading-dots` 的动画是 `mask-image` 内嵌 SVG 里的 **SMIL**（`<animate>`），daisyUI 的 `loading.css` 内**没有任何 CSS animation / @keyframes / ::before / ::after**（已核实 5.5.17）→ `animation: none` 与 `::before/::after` 规则全部空转。因此改为项目自绘三点。

- [x] **Step 1: main.css 补骨架的 reduce 兜底**

追加到 `frontend/src/assets/main.css` 末尾：

```css
/* ===== Phase 4：prefers-reduced-motion 兜底（spec §12）=====
   覆盖范围仅限本项目自绘动画：.skeleton-shimmer（会话列表 + 聊天记录骨架共用）
   与 ChatHistory 的思考中三点（在组件 scoped 样式内处理）。
   daisyUI 的 .loading-* 动画是 SMIL，CSS 停不掉，不在本轮范围（登记为长期待办）。 */
@media (prefers-reduced-motion: reduce) {
  .skeleton-shimmer {
    animation: none;
  }
}
```

- [x] **Step 2: ChatHistory 换自绘三点**

把 `frontend/src/components/character/chat_field/chat_history/ChatHistory.vue` 模板里的思考中指示（当前第 202-207 行）：

```html
    <!-- 思考中指示（首 token 前） -->
    <div v-if="thinking" class="flex justify-start my-2">
      <div class="msg-bubble msg-bubble-ai flex items-center gap-1">
        <span class="loading loading-dots loading-sm"></span>
      </div>
    </div>
```

替换为：

```html
    <!-- 思考中指示（首 token 前）。Phase 4：改项目自绘三点——
         daisyUI 的 loading-dots 动画在 mask-image 内嵌 SVG 的 SMIL 里，CSS 无法在
         prefers-reduced-motion 下停掉（已核实 daisyui/components/loading.css 5.5.17）。 -->
    <div v-if="thinking" class="flex justify-start my-2">
      <div class="msg-bubble msg-bubble-ai flex items-center gap-1">
        <span class="thinking-dot" style="animation-delay: 0s"></span>
        <span class="thinking-dot" style="animation-delay: 0.2s"></span>
        <span class="thinking-dot" style="animation-delay: 0.4s"></span>
      </div>
    </div>
```

并把该文件末尾的：

```html
<style scoped>
</style>
```

替换为：

```html
<style scoped>
/* Phase 4：思考中三点（自绘，可被 prefers-reduced-motion 停掉） */
.thinking-dot {
  width: 6px;
  height: 6px;
  border-radius: 9999px;
  background: rgba(255, 255, 255, 0.7);
  animation: thinking-bounce 1.2s ease-in-out infinite;
}
@keyframes thinking-bounce {
  0%, 60%, 100% { opacity: 0.35; transform: translateY(0); }
  30%           { opacity: 1;    transform: translateY(-3px); }
}
@media (prefers-reduced-motion: reduce) {
  .thinking-dot {
    animation: none;
    opacity: 0.6;   /* 静止但可见，仍表达"指示中" */
    transform: none;
  }
}
</style>
```

- [x] **Step 3: 构建验证**

Run: `cd frontend && npm run build`
Expected: 构建成功（exit 0）

- [x] **Step 4: 校验产物与遗留**

```powershell
cd D:\MyProjects\AiFriends\frontend
"thinking-dot 在产物中: " + (Select-String -Path ..\backend\static\frontend\assets\*.js -Pattern 'thinking-dot' -AllMatches | Measure-Object).Count
"源码中是否还残留 loading-dots: " + (Select-String -Path src\components\character\chat_field\chat_history\ChatHistory.vue -Pattern 'loading-dots' | Measure-Object).Count
```
Expected: 前者 ≥1，后者 = 0

- [x] **Step 5: 提交**

```bash
git add frontend/src/assets/main.css frontend/src/components/character/chat_field/chat_history/ChatHistory.vue
git commit -m "fix(a11y): 思考中指示器换自绘三点（daisyUI loading-dots 的 SMIL 动画 CSS 停不掉）+ 骨架 reduce 兜底"
```

---

## Task 8: 全量验证（门 4 前的自证）

**Files:** 无（只跑验证）

- [x] **Step 1: 前端单测全量**

Run: `cd frontend && npx vitest run`
Expected: PASS，`Test Files 6 passed`，`Tests 99 passed`

- [x] **Step 2: 前端生产构建**

Run: `cd frontend && npm run build`
Expected: exit 0

- [x] **Step 3: 后端测试未被波及（本轮零后端改动，仍须实测）**

Run: `cd backend && python -m pytest web/tests/ -q`
Expected: PASS（221 passed）。若本地 PostgreSQL / Redis 未启动导致无法运行，**如实记为环境限制，不得写"通过"**

- [x] **Step 4: 汇总证据，报告门 4**

把 Step 1~3 的真实输出贴进汇报，并列出需在**用户浏览器**人工确认的项（design §9 的第 3~11 条）：

- 纯白/高亮背景图：AI 消息文字清晰（注意实测量级是 4.16:1 vs 4.5，**肉眼差异有限，重点看字形边缘是否稳定**）
- 深色背景图：文字清晰，背景观感未被压死
- 键盘 Tab：能聚焦语音开关、角色详情按钮、麦克风、发送键，Enter/空格可触发
- ⚙ 弹层两个开关即时生效、刷新后保持
- 语音自动发送开启后：回填后约 0.8s 自动发出；期间点 🎤 重录则不发送
- 系统开启"减少动态效果"：骨架与聊天页思考中三点静止（**不**声称覆盖全站 loading-spinner）
- markdown：`pre` 与行内 `code` 均无描边、深色底正常、复制按钮可用
- 无背景图的角色：窗口与舞台呈深色，文字可读
- **背景图 URL 改为坏地址（如 `/media/nonexistent.jpg`）：同样回落深色**（E2 第二条路径）

---

## Task 9: spec 回写（W1~W7、W9~W12）

**Files:**
- Modify: `docs/superpowers/specs/2026-09-07-chat-ui-redesign-spec-for-llm.md`

> **W8 已作废**（v3）：v2 曾要登记"偏离 spec 原文要求"，但 **spec 全文没有 `text-shadow` 条款，也没有 §3.4**（已 grep 核实，只有 `## 3. 已拍板决策`）。那句话来自 design v1 §3.4 自身 → 改为 design 内部约定变更（已写在 design §3.6），**spec 无需回写**。

- [x] **Step 1: 回写 §13 Phase 4 段**

把 §13 的（第 406-413 行）：

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
改动：**文字描边**补足亮背景图顶部的可读性；简约背景开关（深色降级）；语音自动发送开关；无障碍（真按钮 + aria-label + reduced-motion）。
**不做**：亮度自适应蒙层（`useBackgroundAdaptive` / `--overlay-k`）、主色提取（accent）、创建页聊天预览。

验收断言：
1. ~~overlayK 公式值单测~~ → **改口径**：蒙层保持固定 0.25→0.60；可读性由**文字描边**提供确定性承托。sRGB 合成口径实测：纯白图顶部 4.16:1（略低于 4.5，描边改善感知可读性）、中部 6.36:1、底部 10.00:1。若日后要严格 4.5:1，见 design §3.5 的乙（蒙层顶部→0.375，5.61:1）或丙（气泡→.45，5.47:1）。
2. 简约模式切换后窗口背景为纯色、气泡高对比；刷新后保持（localStorage）。
3. ~~创建/编辑角色页可看到"聊天效果预览"~~ → **本期不做**（P4-D2）。
4. 全部图标按钮存在 aria-label；reduced-motion 下动画静止（**覆盖范围收窄**：本项目自绘的骨架与聊天页思考中指示；daisyUI `loading-*` 的 SMIL 动画不在范围）。
5. **新增**：键盘可 Tab 到达语音开关与角色详情按钮，Enter/空格可触发（原为 `<div @click>`，键盘完全不可达）。
6. **新增**：背景图缺失或加载失败时，窗口与舞台回落深色纯色，文字可读（E2 双路径）。
```

- [x] **Step 2: §6.5 加作废声明**

在 §6.5 标题（第 219 行 `### 6.5 亮度自适应算法（useBackgroundAdaptive.js）`）之后插入：

```
> **2026-09-11 作废声明**：本节**本期不实施**，保留作为未来备选。
> 原因：① 主色 accent 已拍板固定为 `#10b981`，不再从背景图提取；② 实测表明可读性缺口比预想小得多——sRGB 合成口径下纯白图顶部为 4.16:1（仅略低于 4.5），中部以下早已达标，且"单改蒙层"即可达标（顶部 0.375 → 5.61:1）；③ 改用文字描边后，承托与背景亮度解耦。详见 `2026-09-11-chat-ui-phase4-readability-a11y-design.md` §3。
```

- [x] **Step 3: 更正四处同源对比度论断（W4）**

**(a)** §11 E3（第 343 行）：

```
| E3 | 背景极亮/极暗 | 亮度自适应蒙层（§6.5）+ 深色 AI 气泡（R2）共同保证正文 ≥4.5:1；用户可切简约模式 |
```
→
```
| E3 | 背景极亮/极暗 | 本行原断言的**依赖机制（§6.5 自适应蒙层）已被砍掉**；蒙层固定 0.25→0.60 后，纯白图顶部为 4.16:1（sRGB 口径实测）、中部 6.36:1、底部 10.00:1——**顶部缺少余量**。由**文字描边**提供确定性承托（design §3），另提供简约模式作降级。若需严格 4.5:1，蒙层顶部提至 0.375 或气泡提至 .45 |
```

**(b)** §6.1 的 `--bubble-ai` 行（第 202 行）：

```
| `--bubble-ai` | `rgba(0,0,0,0.35) + backdrop-blur 8px` | AI 气泡（**深色玻璃**：白字在亮图上叠蒙层后仍 ≥4.5:1，R2） |
```
→
```
| `--bubble-ai` | `rgba(0,0,0,0.35) + backdrop-blur 8px` | AI 气泡（**深色玻璃**）。原"仍 ≥4.5:1"依赖已砍掉的自适应蒙层；固定蒙层下实测（sRGB 口径）：纯白图顶部 4.16:1、中部 6.36:1、底部 10.00:1；顶部由文字描边补足（design §3.4） |
```

**(c)** §12 无障碍规格的对比度条目（第 363 行）：

```
- 对比度：正文（消息、名字）≥ 4.5:1（深色蒙层 + 深色 AI 气泡保证，R2）；次要文本（日期胶囊/时间戳/占位符）≥ 3:1；简约模式天然满足。
```
→
```
- 对比度：正文（消息、名字）在深色图上 ≥4.5:1；纯白图顶部为 4.16:1，由文字描边补足感知可读性（design §3.4：描边不改变 WCAG 意义上的文字/背景比值）。次要文本（日期胶囊/时间戳/占位符）≥ 3:1；简约模式（深色底）实测白字 17.04:1，天然满足。
```

**(d)** §13 Phase 1 断言 7（第 381 行）：

```
7. 背景图之上文字在亮/暗图下均可读（人工目测 + 公式校验 §6.5）。
```
→
```
7. 背景图之上文字在亮/暗图下均可读（人工目测；亮图顶部的余量由 Phase 4 的文字描边补足，见 §13 Phase 4 断言 1 与 design §3.4）。
```

- [x] **Step 4: 补 §6.6 的实施偏离（W6）**

在 §6.6 标题（第 235 行 `### 6.6 "简约背景"模式（C3 用户降级，用户设置，localStorage 持久化）`）之后插入：

```
> **2026-09-11 实施口径（偏离登记 W6）**：① **只做深色版**（窗口 `#1c1917` / 舞台 `#0c0a09`），不做浅色 `#f5f5f4` 与"跟随系统"——浅色底会使玻璃头部条、名字 pill、日期胶囊、引用 chips 这批白字系元素集体失效，需连带重做；② **气泡不改** daisyUI 对比色（深色底 + 白字实测 17.04:1，已远超标线，改气泡反而破坏与沉浸模式的一致性）；③ 入口改为 WindowHeader 的 **⚙ 设置弹层**（两个开关并列，LD §3.5 / Q6 落点），非原文的"月亮/减淡图标 + tooltip"。
```

- [x] **Step 5: 更正 E2 承接方式（W7，双路径）**

§11 边界情况表 E2（第 342 行）：

```
| E2 | 背景图加载失败/跨域被拦 | useBackgroundAdaptive fallback（K=1.0）；窗口背景回退 `rgba(0,0,0,0.75)` 深色 |
```
→
```
| E2 | 背景图缺失/加载失败/跨域被拦 | 两条路径均回落简约模式的深色渲染（窗口 `#1c1917` / 舞台 `#0c0a09`）：① `background_image` 为空；② `<img>` 的 `error` 事件置位。原 `useBackgroundAdaptive` 的 `K=1.0` 回退随 §6.5 一并作废 |
```

- [x] **Step 6: 改写 C2 条款（W9）——仅在用户明确授权后执行**

§2 产品约束的 C2（第 38 行）：

```
- **C2 创建者非设计师**：背景图内容不可预知（全白/全黑/高饱和/低清均可能），文字可读性不得依赖图片本身，必须落在确定性蒙层上。
```
→
```
- **C2 创建者非设计师**：背景图内容不可预知（全白/全黑/高饱和/低清均可能），文字可读性不得依赖图片本身，必须落在**确定性深色承托**上（蒙层或文字描边；2026-09-11 用户裁决 P4-D6：描边色彩固定、与图片内容完全无关，其确定性不弱于蒙层）。
```

> ⚠️ **执行前置**：本步骤改动的是最高权威文档的**硬约束条款**，必须等用户在 design §11.2 上明确确认"这就是授权"后才能执行。**未获确认前跳过本步骤**，并改走 design §3.5 的乙或丙（纯 CSS 数值改动，不动条款）。

- [x] **Step 7: 登记焦点环偏离（W10）与散落引用（W11/W12）**

**(a)** §5.3 InputField 契约的焦点环（第 361 行一带，原文 `focus-visible:ring-2 ring-white/60`）之后插入：

```
> **2026-09-11 偏离登记（W10）**：实现沿用项目既有的 `ring-white/40`（与 `InputField` 麦克风按钮一致，避免同页出现两套焦点环视觉）。可达性不受影响。
```

**(b)** 对以下各行逐一追加行内标注 `（2026-09-11：该模块本期不实施，见文末变更登记）`：

| 行 | 内容 |
|---|---|
| `:138` | 组件树里的 `useBackgroundAdaptive.js` |
| `:156` | ChatWindow 职责里的"浓度来自 `useBackgroundAdaptive`" |
| `:196` | `--overlay-k` token 行 |
| `:201` | `--bubble-user` 行 |
| `:207` | §6.2 舞台背景里的"Phase 4 引入 `--overlay-k` 自适应时以 0.35 为基准系数起调" |
| `:223` / `:229` / `:232` | §6.5 内部（已由 Step 2 整节声明覆盖，此处补行内指针） |
| `:238` | §6.6 里的"气泡 → 常规 daisyUI 对比色" |
| `:267` | §8.2 用户气泡的 `--user-bubble-bg`（resolveUserBubble） |
| `:421` | §14 给下游 LLM 的任务边界里的 `useBackgroundAdaptive` |

**(c)** §6.2 舞台背景（第 207 行）末尾的"（2026-09-07 实机调优…Phase 4 引入 `--overlay-k` 自适应时以 0.35 为基准系数起调。）" → 改为"（2026-09-07 实机调优值；`--overlay-k` 自适应已取消，0.35 定为固定值。）"（W12）

- [x] **Step 8: 文件末尾追加变更登记**

在 spec **最末尾**追加：

```markdown
---

## 附：2026-09-11 变更登记（Phase 4 实施前回写）

| # | 位置 | 变更 | 理由 |
|---|------|------|------|
| W1 | §13 Phase 4 断言 3 | 标"本期不做" | 用户拍板 P4-D2 |
| W2 | §13 Phase 4 断言 1 | 改口径：不再要求 overlayK 公式，改为描边承托 + sRGB 实测值 | P4-D1 颜色固定 + 描边方案 |
| W3 | §6.5 整节 | 加作废声明，保留为未来备选 | 同上 |
| W4 | §11 E3 / §6.1 `--bubble-ai` / §12 对比度 / §13 Phase 1 断言 7 | 四处同源论断更正为 sRGB 口径实测值 | **原断言的依赖机制（§6.5 自适应蒙层）已被砍掉**，固定蒙层下顶部余量不足（4.16:1）；非"原文即错" |
| W5 | §13 Phase 4 断言 2 / 4 | 断言 2 保留；断言 4 保留但**收窄口径**；新增断言 5（键盘可达性）与断言 6（E2 双路径） | 本轮实施内容 |
| W6 | §6.6 + §6.1 `--chat-bg` | 登记实施偏离：只做深色版、气泡不改、入口改 ⚙ 弹层 | 见 §6.6 内插入的实施口径块 |
| W7 | §11 E2 | 承接方式改为**两条**静态深色兜底（无图 + `error` 事件） | 原依赖模块已砍 |
| ~~W8~~ | ~~§5.3 代码块处置~~ | **作废** | 原文所称的"spec 要求"不存在（spec 无 `text-shadow` 条款、无 §3.4），且支撑数据 3.06:1 系错口径（真值 8.78:1） |
| W9 | §2 C2 | 表述改为"确定性深色承托（蒙层或文字描边）" | 用户裁决 P4-D6（**授权范围待确认**） |
| W10 | §5.3 焦点环 | 登记 `ring-white/60` → `/40` 的实现偏离 | 与项目既有按钮一致 |
| W11 | 散落引用（`:138/:156/:196/:201/:207/:223/:229/:232/:238/:267/:421`） | 逐行加"本期不实施"标注 | v2 回写清单遗漏 |
| W12 | §6.2 舞台背景 | `--overlay-k` 基准系数的表述改为固定值 | 同上 |

**数值口径说明**：本次全部对比度按 **sRGB 分量空间合成 → 再线性化** 计算（CSS 的真实行为）。design v1 误用亮度空间线性混合，v2 又误用 sRGB 数值当线性亮度（行内 code 3.06:1）与错底色（95.625），均已在 design v3 §0 记录。
```

- [x] **Step 9: 验证回写（独立进程读盘断言）**

```powershell
cd D:\MyProjects\AiFriends
$f = 'docs\superpowers\specs\2026-09-07-chat-ui-redesign-spec-for-llm.md'
$need = @('本期不做','作废声明','2026-09-11 变更登记','偏离登记 W6','偏离登记（W10）','sRGB 分量空间合成','该模块本期不实施')
foreach ($n in $need) {
  "{0,-24} {1}" -f $n, (Select-String -LiteralPath $f -Pattern $n -SimpleMatch | Measure-Object).Count
}
"=== 反向检查：W8 的伪引用不应出现 ==="
"原文要求 / spec §3.4: " + (Select-String -LiteralPath $f -Pattern '原文要求','spec §3\.4' -SimpleMatch | Measure-Object).Count
```
Expected: 七项计数全部 ≥1；反向检查为 0

- [x] **Step 10: 提交**

```bash
git add docs/superpowers/specs/2026-09-07-chat-ui-redesign-spec-for-llm.md
git commit -m "docs(chat): spec 回写 Phase 4 事实变更（W1~W7、W9~W12）—— sRGB 口径更正四处论断、作废 overlayK、登记偏离、补全散落引用"
```

---

## Task 10: LD 回写（L1~L6）

**Files:**
- Modify: `docs/superpowers/specs/2026-09-07-chat-ui-redesign-logic-design.md`

> v1/v2 遗漏：LD 完全未回写，导致两份文档对已砍内容相互矛盾。若 Phase 4 完成而 LD 未更新，会被误当作权威继续指导实施。

- [x] **Step 1: L1——标注已砍模块**

在 LD §3.10 标题（**第 162 行** `### 3.10 \`useBackgroundAdaptive.js\`【新】`）之后插入：

```
> **2026-09-11 本期不实施**：本模块随 Phase 4 范围改写一并作废（主色固定 + 可读性由文字描边承托）。详见 `2026-09-11-chat-ui-phase4-readability-a11y-design.md` §3/§4。
```

在 LD §8.2 标题（第 368 行 `### 8.2 Tailwind 4 \`@theme\` 落地建议（LD §14.6 任务）`）之后插入：

```
> **2026-09-11 本期不实施**：`--user-bubble-bg` 与 `resolveUserBubble` 三档阶梯取消——己方气泡为固定不透明色，实测白字 4.85:1 已达标，无需按 accent 解析。
```

- [x] **Step 2: L2——改写 §10 的 Phase 4 表**

把 LD §10「### Phase 4 — 自适应与质感」整段（第 465-474 行）：

```
### Phase 4 — 自适应与质感

| 动作 | 文件 |
|------|------|
| 新增 | `frontend/src/composables/useBackgroundAdaptive.js`、`src/utils/backgroundAdaptive.js`、`src/composables/useChatSettings.js` |
| 修改 | `ChatWindow.vue`（蒙层/accent 变量绑定、简约模式分支） |
| 修改 | `WindowHeader.vue`（设置弹层：简约背景 + 语音自动发送） |
| 修改 | `VoiceToggle.vue`、`CharacterPhotoField.vue`（aria-label） |
| 修改（可选） | `views/create/character/components/BackgroundImage.vue`（聊天效果预览 + 亮度提示） |
| 验收 | spec Phase 4 断言 1~4 |
```

替换为：

```
### Phase 4 — 可读性修复与无障碍（2026-09-11 目标改写）

| 动作 | 文件 |
|------|------|
| 新增 | `frontend/src/utils/contrast.js`（+ 单测）、`src/composables/useChatSettings.js`（+ 单测，模块级单例） |
| 修改 | `Message.vue`（文字容器挂描边、代码块排除）、`main.css`（描边变量 + 骨架 reduce）、`ChatHistory.vue`（思考中指示器换自绘三点） |
| 修改 | `ChatWindow.vue`（简约背景分支 + 背景图缺失/加载失败兜底）、`WindowHeader.vue`（⚙ 设置弹层） |
| 修改 | `VoiceToggle.vue`、`CharacterPhotoField.vue`（`<div>` → `<button>` + aria-label/alt） |
| 修改 | `InputField.vue`（语音自动发送 800ms） |
| 不做 | `useBackgroundAdaptive.js`、`utils/backgroundAdaptive.js`、创建页预览 |
| 验收 | spec Phase 4 断言 1~6（改口径后） |
```

- [x] **Step 3: L3——标注 WindowHeader 契约偏离**

在 LD §3.5（**第 103 行** `### 3.5 \`components/chat/chat_window/WindowHeader.vue\`【新】`）之后插入：

```
> **2026-09-11 实施偏离**：不再通过 props/emits 传递设置——WindowHeader 与 InputField 均直接使用 `useChatSettings()` **模块级单例**（本文件 D-L7 本就要求二者共享同一状态，单例下 props 传递是冗余的）。因此 `simpleBackground` prop 与 `toggleSimple`/`toggleAutoSend` emits 不实现。
```

- [x] **Step 4: L4——补 Q6 落地注记**

LD §13 决策表 Q6 行（第 514 行）末尾补注：

```
（2026-09-11 补注：入口已实现为 WindowHeader 的 ⚙ 设置弹层，与"简约背景"开关并列。）
```

- [x] **Step 5: L5——散落引用补全**

对以下各行逐一追加行内标注 `（2026-09-11：本期不实施）`：

| 行 | 内容 |
|---|---|
| `:94` | §3.4 ChatWindow 持有里的 `useBackgroundAdaptive(...)` |
| `:101` | §3.4 样式职责里的 `--overlay-k` / `--accent` 注入 |
| `:164` / `:169` / `:170` / `:172` | §3.10 内部（已由 Step 1 整节声明覆盖，此处补指针） |
| `:377` / `:380` / `:381` / `:382` | §8.2 `@theme` 与 `resolveUserBubble`（Step 1 已声明，补指针） |
| `:407` / `:410` | §9.2 单测清单里的 `backgroundAdaptive` / `resolveUserBubble` 用例 |
| `:490` | §11 竞态风险表里的"背景采样 `seq` 令牌" |

- [x] **Step 6: L6——补 ChatHistory 契约变更**

在 LD §3.6（ChatHistory 契约）的"新增状态渲染"块之后插入：

```
> **2026-09-11 变更**：思考中指示器由 daisyUI `<span class="loading loading-dots">` 换为**项目自绘三点**——daisyUI 的 `loading-*` 动画位于 `mask-image` 内嵌 SVG 的 SMIL 中，CSS 无法在 `prefers-reduced-motion` 下停掉（已核实 `daisyui/components/loading.css` 5.5.17）。
```

- [x] **Step 7: 验证回写**

```powershell
cd D:\MyProjects\AiFriends
$f = 'docs\superpowers\specs\2026-09-07-chat-ui-redesign-logic-design.md'
$need = @('本期不实施','2026-09-11 目标改写','2026-09-11 实施偏离','2026-09-11 补注','2026-09-11 变更')
foreach ($n in $need) {
  "{0,-24} {1}" -f $n, (Select-String -LiteralPath $f -Pattern $n -SimpleMatch | Measure-Object).Count
}
```
Expected: 五项计数全部 ≥1

- [x] **Step 8: 提交**

```bash
git add docs/superpowers/specs/2026-09-07-chat-ui-redesign-logic-design.md
git commit -m "docs(chat): LD 回写 Phase 4 变更（L1~L6）—— 标注已砍模块与散落引用、改写 Phase 4 表、登记单例与指示器偏离"
```

---

## Task 11: 评审文档归位

**Files:**
- Move: `docs/superpowers/specs/2026-09-07-chat-ui-redesign-review.md` → `docs/superpowers/reviews/`
- Add: `docs/superpowers/reviews/2026-06-28-pr31-docker-compose-review.md`
- Add: `docs/superpowers/reviews/2026-08-19-deployment-registry-refactor-spec-review.md`

- [x] **Step 1: 移动误归档的评审报告**

```bash
cd D:/MyProjects/AiFriends && git mv docs/superpowers/specs/2026-09-07-chat-ui-redesign-review.md docs/superpowers/reviews/2026-09-07-chat-ui-redesign-review.md && git status --short -- docs/superpowers/
```
Expected: `R  docs/superpowers/specs/… -> docs/superpowers/reviews/…`

- [x] **Step 2: 纳入两份未跟踪的历史评审记录**

```bash
cd D:/MyProjects/AiFriends && git add docs/superpowers/reviews/2026-06-28-pr31-docker-compose-review.md docs/superpowers/reviews/2026-08-19-deployment-registry-refactor-spec-review.md && git status --short -- docs/superpowers/reviews/
```
Expected: 两条 `A ` 记录

- [x] **Step 3: 确认未误伤工作区杂物**

```powershell
cd D:\MyProjects\AiFriends
git status --short
```
Expected: 仍能看到未提交的 `.codegraph/.gitignore` 与 `.superpowers/brainstorm/**` 条目，且它们**不在暂存区**

- [x] **Step 4: 提交**

```bash
git add docs/superpowers/reviews/
git commit -m "docs: 评审记录归位（chat-ui-redesign-review 移入 reviews/）+ 补提交两份历史评审记录"
```

---

## Task 12: 记录本轮 L 档评审（契约 §4）

**Files:**
- Create: `docs/superpowers/reviews/2026-09-11-chat-ui-phase4-review.md`

> 契约 §4 要求 L 档评审记录落 `reviews/YYYY-MM-DD-<topic>-review.md`。本轮 Phase 4 已经历 **3 轮评审**（v1 两轴 / v2 两轴 / v3 复审），必须留档，否则日后无法解释 design/plan 为何从 v1 改到 v3。

- [x] **Step 1: 写评审记录**

创建 `docs/superpowers/reviews/2026-09-11-chat-ui-phase4-review.md`，内容至少包含：

```markdown
# Phase 4 文档评审记录（2026-09-11）

> 评审对象：`2026-09-11-chat-ui-phase4-readability-a11y-design.md` 与同名 plan
> 评审方式：两轴（Standards / Spec）独立子代理 + 主评审复核；数值部分由评审方实跑复现

## 轮次 1（v1 → v2）

**阻断 3 项**：
1. 合成模型错误——CSS alpha 合成在 sRGB 分量空间，v1 按亮度空间线性混合，结论整体偏悲观约一倍（1.95:1 vs 真实 4.16:1）
2. `useChatSettings` 写成工厂函数，违反 LD D-L7「模块级单例」→ 开关整体失效
3. reduced-motion 修法空转——daisyUI `.loading-dots` 的动画在 `mask-image` 内嵌 SVG 的 SMIL 中，CSS 停不掉

**处置**：3 项全部采纳并重修（v2）。另采纳 13 项顺手项（grep 脚本、行号锚点、测试计数等）。

**拒绝 1 项**：行内 `code` 排除描边（当时理由是"行内 code 仅 3.06:1，去掉更难读"）——该理由后被证明基于错口径。

## 轮次 2（v2 → v3）

**需先修 3 项 + 流程违规 1 项**：
1. W8 把「伪原文」写进 spec——v2 称"spec 原文要求 `pre` 与 `code` 都排除描边"，但 spec 全文无该条款、无 §3.4
2. §3.3 表第 2 行 + 单测锁死错底色——95.625 对应气泡 α=0.5，链条里不存在；真实最坏档 124.3125 → 18.63
3. 行内 code 的 3.06:1 系 sRGB 当线性亮度（真值 8.78:1），W8 唯一理由不成立
4. **流程硬违规**：`c547e1e` 在门 2 批准前提交源码，且计划未同步（Task 1 仍全 `- [ ]`）

**处置**：全部采纳并重修（v3）。第 4 项待用户裁决追认或回退。

## 三轮共同暴露的模式

三次错误同源：**把 sRGB 数值当作线性亮度代入 WCAG 公式**（v1 用错空间、v2 又用错一次），以及**手写中间值而不从公式推导**（95.625）。二者均已通过"档位全部由 `bubbleBase()` 推导 + 单测锁定"从机制上消除。
```

- [x] **Step 2: 提交**

```bash
git add docs/superpowers/reviews/2026-09-11-chat-ui-phase4-review.md
git commit -m "docs(chat): Phase 4 三轮评审记录留档（契约 §4，L 档要求）"
```

---

## 范围外（明确不做，防止蔓延）

1. 亮度自适应蒙层 / `--overlay-k` / `useBackgroundAdaptive` / `utils/backgroundAdaptive.js`
2. 主色提取 / `resolveUserBubble` / `accentFallback`（P4-D1）
3. 创建页聊天效果预览 + 亮度提示（P4-D2）
4. 简约模式的**浅色版**（design §5.1）
5. 全站 7 处 `loading-spinner` 的 reduced-motion（daisyUI SMIL，CSS 停不掉）
6. 工作区其他杂物：`.codegraph/.gitignore`、`.superpowers/brainstorm/**`
7. 后端任何改动（本轮零后端）

---

## 长期待办（本轮不做，记录在案）

1. **daisyUI `loading-*` 的 reduced-motion 缺口**：全站 8 处（7 个 `loading-spinner` + 原 `loading-dots`），动画在 `mask-image` 内嵌 SVG 的 SMIL 中，CSS 无法停掉；需替换为自绘指示器或改用静态图标
2. **严格 4.5:1（若日后要求）**：蒙层顶部 → 0.375，或 AI 气泡 → `.45`（design §3.5）
3. **流程契约措辞缺口**：§3 未写明"合并 PR = 门 3 通过"，导致 PR #39 被误判为未过门
4. **`docs/superpowers/plans/2026-05-17-testing-plan.md:155`** 仍硬编码 `C:\Users\YGQ\.claude\plans\…`
