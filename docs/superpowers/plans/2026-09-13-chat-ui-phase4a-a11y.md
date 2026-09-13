# 聊天界面改版 Phase 4A（无障碍修复）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复聊天页三类与观感无关的真实无障碍缺陷——两个核心控件键盘不可达、图标按钮无可访问名称、`prefers-reduced-motion` 在对话区未生效——且**不改变任何像素的观感**。

**Architecture:** 三处 `div`→原生 `<button>`（语义与键盘行为交给浏览器）；一处一行 `aria-label`；对话区"思考中"指示器从 daisyUI `loading-dots`（内嵌 SVG 的 SMIL 动画，CSS 停不掉）换成自绘三点 + 全局 CSS 动画，与 `Microphone.vue` 既有 `animate-pulse-dot` 同构。所有改动集中在模板语义与全局 CSS，**不触碰配色与布局值**。

**Tech Stack:** Vue 3 Composition API + Tailwind CSS 4 + daisyUI 5 + vitest（jsdom 经 docblock 按需开启）；后端零改动。

**Spec:** `docs/superpowers/specs/2026-09-13-chat-ui-phase4a-a11y-design.md`（事实核查、决策 D4A-1~5、逐项设计 §3）

## Global Constraints

- **零视觉变更**（D4A-4）：改 `div`→`button` 后，尺寸/间距/圆角/悬停观感必须与改动前**逐像素一致**。任何差异按回归缺陷处理。
- 目标提交范围：仅 §文件清单 中 5 个源文件 + 新增 3 个测试文件。
- `.thinking-dot` 的颜色必须用 `currentColor` 语义（继承 AI 气泡的文字色），**不得**写死白色——4B 浅色模式会复用该类。
- reduced-motion 下三点**静止但可见**（`opacity: 0.6`），不得隐藏。
- 不引入任何依赖（不装 `@vue/test-utils`、不装 eslint a11y 插件）。
- 分支：`feature/gqyin/chat-ui-phase4a-a11y`；提交信息中文 `type(scope): 摘要`。
- **焦点环规则（D4A-6）**：按**元素实际持有的类名**判定，不按文件/区域。
  - 无 `btn` 类 → 加 `focus-visible:ring-2 ring-white/40`（**4A 沿用项目现状写法**）。含 `VoiceToggle`、`CharacterPhotoField`、`InputField` 的麦克风/发送/停止三个圆钮（实测 `:392/429/438` 无 `.btn`）、`ChatHistory` 示例问题胶囊、`Message` 引用 chip。
  - 有 `btn` 类 → **不加**自定义环（daisyUI 用 `outline-width:2px` + `outline-color:var(--color-base-content)`，与 `ring` 叠加会双环）。含头部件 ⚙/☰/✕、`InputField:454` 的重试按钮。
  - ⚠️ 同一文件里可能两类并存（`InputField` 即是），判断方式是看该元素的 class 串里有没有 `btn`，不要按文件推断。

---

## 文件结构

| 动作 | 文件 | 职责 |
|------|------|------|
| 修改 | `frontend/src/components/character/chat_field/VoiceToggle.vue` | 真按钮 + `aria-pressed` |
| 修改 | `frontend/src/components/character/chat_field/character_photo_field/CharacterPhotoField.vue` | 真按钮 + `aria-label` + `alt` |
| 修改 | `frontend/src/components/navbar/UserMenu.vue` | 触发器补 `aria-label`（一行） |
| 修改 | `frontend/src/components/character/chat_field/chat_history/ChatHistory.vue` | 思考指示器换自绘三点 |
| 修改 | `frontend/src/assets/main.css` | `.thinking-dot` + `@keyframes` + reduce 块 |
| 新增 | `frontend/src/components/character/chat_field/__tests__/VoiceToggle.test.js` | 按钮语义与键盘 |
| 新增 | `frontend/src/components/character/chat_field/character_photo_field/__tests__/CharacterPhotoField.test.js` | 按钮语义与 aria |
| 新增 | `frontend/src/utils/__tests__/thinkingDots.test.js` | 三点数量与 reduce 样式存在性 |

---

### Task 1: `VoiceToggle` 改为真按钮

**Files:**
- Modify: `frontend/src/components/character/chat_field/VoiceToggle.vue`
- Test: `frontend/src/components/character/chat_field/__tests__/VoiceToggle.test.js`

**Interfaces:**
- Consumes: `useVoiceToggle()`（既有）→ `{ voiceEnabled, toggle }`
- Produces: 根元素由 `div` 变为 `button[type=button]`，带 `aria-label` 与 `aria-pressed`；**类名列表不变**（4A 约定）

- [ ] **Step 1: 写失败测试**

创建 `frontend/src/components/character/chat_field/__tests__/VoiceToggle.test.js`：

```js
// @vitest-environment jsdom
import { describe, expect, it, beforeEach } from 'vitest'
import { createApp, h, nextTick } from 'vue'
import VoiceToggle from '../VoiceToggle.vue'
import { useVoiceToggle } from '@/composables/useVoiceToggle.js'

function mount() {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp({ render: () => h(VoiceToggle) })
  app.mount(host)
  return host
}

describe('VoiceToggle（4A D4A-1：真按钮 + 可访问名称）', () => {
  beforeEach(() => {
    document.body.innerHTML = ''        // 清掉上个用例挂载的节点
    const { voiceEnabled } = useVoiceToggle()
    voiceEnabled.value = true           // 每个用例从已知状态开始
  })

  it('根元素是原生 button 且 type=button（不触发表单提交）', () => {
    const el = mount().querySelector('button')
    expect(el).toBeTruthy()
    expect(el.getAttribute('type')).toBe('button')
  })

  it('可访问名称随状态变化，且 aria-pressed 反映开关态', async () => {
    const { voiceEnabled } = useVoiceToggle()
    const btn = mount().querySelector('button')
    expect(btn.getAttribute('aria-label')).toBe('关闭语音播报')
    expect(btn.getAttribute('aria-pressed')).toBe('true')
    btn.click()
    await nextTick()            // Vue 的 DOM 更新是异步批处理的，同步读会拿到旧值
    expect(voiceEnabled.value).toBe(false)
    expect(btn.getAttribute('aria-label')).toBe('开启语音播报')
    expect(btn.getAttribute('aria-pressed')).toBe('false')
  })

  it('点击能切换（键盘激活由原生 button 提供，见下方约束说明）', () => {
    const { voiceEnabled } = useVoiceToggle()
    const btn = mount().querySelector('button')
    // 起始为 true（beforeEach 已置位），点一次 → false
    btn.click()
    expect(voiceEnabled.value).toBe(false)
  })

  // 约束说明（不写测试）：Enter/空格 触发 click 是浏览器对原生 <button> 的内置行为，
  // jsdom 不会模拟"浏览器合成点击"，因此键盘激活**只能由门 4 的真人键盘走查覆盖**
  // （4A 设计 §6 断言 A1）。若在此处用 dispatchEvent 伪造 click，测到的是我们自己的
  // 代码而非浏览器行为——那是假覆盖，不如不写。
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/components/character/chat_field/__tests__/VoiceToggle.test.js`
Expected: FAIL —— `querySelector('button')` 返回 `null`（当前根元素是 `div`）

- [ ] **Step 3: 实现**

替换 `VoiceToggle.vue` 的 template：

```html
<template>
  <button type="button"
          class="h-10 w-10 rounded-full bg-black/50
                 flex items-center justify-center cursor-pointer
                 hover:bg-black/60 transition-colors shrink-0
                 focus-visible:ring-2 ring-white/40 outline-none"
          :title="voiceEnabled ? '语音已开启' : '语音已关闭'"
          :aria-label="voiceEnabled ? '关闭语音播报' : '开启语音播报'"
          :aria-pressed="voiceEnabled"
          @click="toggle">
    <SpeakerIcon :enabled="voiceEnabled" />
  </button>
</template>
```

> 说明：类名与改动前**完全一致**，仅追加 `focus-visible:ring-2 ring-white/40 outline-none`（D4A-6：本组件**无** `btn` 类，且此前是 `div` 完全不可聚焦，故必须有焦点环）。`SpeakerIcon` 不动（其 `text-white` 归 4B 的浅色模式处理）。
>
> **为什么 4A 不写 `chat-focus`**（评审 N2 的路线选择，**采纳选项 ②**）：若 4A 就写 `chat-focus`，则该类尚不存在、且模板同时带 `outline-none` → **完全没有焦点指示**（连浏览器默认 outline 都被关掉），而 4A 的全部目的就是焦点可见。改为"**4A 保持项目现状写法，4B 的 Task 5 统一换成 `chat-focus`**"：零跨批次耦合、4A 的环与现有 `InputField`/`ChatHistory` 同色同形，4B 那边 `main.css` 本就定义 `.chat-focus`，门禁在 Task 5 之后照样绿。代价是 4A 的焦点环不 token 化一个批次——可接受（4A 先交付，交付时它是唯一形态）。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/components/character/chat_field/__tests__/VoiceToggle.test.js`
Expected: PASS（3 个用例）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/character/chat_field/VoiceToggle.vue frontend/src/components/character/chat_field/__tests__/VoiceToggle.test.js
git commit -m "fix(a11y): VoiceToggle 改原生 button（键盘用户此前完全不可达）+ aria-pressed（4A T1）"
```

---

### Task 2: `CharacterPhotoField` 改为真按钮

**Files:**
- Modify: `frontend/src/components/character/chat_field/character_photo_field/CharacterPhotoField.vue`
- Test: `frontend/src/components/character/chat_field/character_photo_field/__tests__/CharacterPhotoField.test.js`

**Interfaces:**
- Consumes: `character` prop（含 `name`、`photo`）；`CharacterDetail` 组件（测试中以 stub 替换，避免拉起整棵弹窗依赖树）
- Produces: 头像 pill 根元素变为 `button[type=button]`，`aria-label` 含角色名，内部 `<img>` 的 `alt` 非空

- [ ] **Step 1: 写失败测试**

创建 `frontend/src/components/character/chat_field/character_photo_field/__tests__/CharacterPhotoField.test.js`：

```js
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/components/character/chat_field/character_photo_field/__tests__/CharacterPhotoField.test.js`
Expected: FAIL —— 无 `button`（当前是 `div`）

- [ ] **Step 3: 实现**

替换 `CharacterPhotoField.vue` 的 `<div class="h-10 w-fit ...">` 块：

```html
<template>
  <!-- 提示：<button> 内不得再嵌套交互元素；若日后需要在 pill 内加次级按钮，必须拆分结构 -->
  <button type="button"
          class="h-10 w-fit rounded-full bg-black/50 flex items-center gap-2 px-2 cursor-pointer
                 focus-visible:ring-2 ring-white/40 outline-none"
          :aria-label="`查看 ${character.name} 的角色详情`"
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

> `w-fit` 保留（宽度仍由内容决定）；`break-all` 保留（其调整属观感，划归 4B）。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/components/character/chat_field/character_photo_field/__tests__/CharacterPhotoField.test.js`
Expected: PASS（3 个用例）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/character/chat_field/character_photo_field/
git commit -m "fix(a11y): 角色头像 pill 改原生 button + 可访问名称与头像 alt（4A T2）"
```

---

### Task 3: `UserMenu` 触发器补可访问名称

**Files:**
- Modify: `frontend/src/components/navbar/UserMenu.vue:41`

**Interfaces:**
- 无接口变化；仅新增一个属性。**不改** `tabindex="0"` / `role="button"`（依赖 daisyUI `dropdown` 的 `:focus-within` 展开机制，换 `<button>` 会改变焦点模型）

- [ ] **Step 1: 实施（一行）**

```html
<!-- before -->
<div tabindex="0" role="button" class="avatar btn btn-circle w-10 h-10 mr-6">
<!-- after -->
<div tabindex="0" role="button" class="avatar btn btn-circle w-10 h-10 mr-6"
     aria-label="用户菜单">
```

- [ ] **Step 2: 验证（无单测，走产物核对）**

Run: `cd frontend && npm run build && grep -c '用户菜单' ../backend/static/frontend/assets/*.js`
Expected: ≥1（字符串进入产物；源码核对：`git diff` 仅 1 行新增）

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/navbar/UserMenu.vue
git commit -m "fix(a11y): NavBar 用户菜单补 aria-label（此前无任何可访问名称，4A T3）"
```

---

### Task 4: 对话区思考指示器换自绘三点

**Files:**
- Modify: `frontend/src/components/character/chat_field/chat_history/ChatHistory.vue:203-206`
- Modify: `frontend/src/assets/main.css`
- Test: `frontend/src/utils/__tests__/thinkingDots.test.js`

**Interfaces:**
- Produces: 全局类 `.thinking-dot`（3 个 span，`currentColor` 取色）+ `@keyframes thinking-bounce` + `@media (prefers-reduced-motion: reduce)` 块
- **4B 依赖**：浅色模式下 `.thinking-dot` 的颜色由 `currentColor` 自动跟随 AI 气泡文字色，无需改动本类

- [ ] **Step 1: 写失败测试**

创建 `frontend/src/utils/__tests__/thinkingDots.test.js`：

```js
// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const css = readFileSync(
  fileURLToPath(new URL('../../assets/main.css', import.meta.url)),
  'utf8',
)

describe('思考中三点（4A T4：替换 CSS 停不掉的 daisyUI SMIL）', () => {
  it('.thinking-dot 用 currentColor 取色（4B 浅色模式复用前提）', () => {
    const block = css.match(/\.thinking-dot\s*\{[^}]*\}/s)?.[0] ?? ''
    expect(block).toContain('currentColor')
  })

  it('定义了 thinking-bounce 关键帧', () => {
    expect(css).toContain('@keyframes thinking-bounce')
  })

  it('reduced-motion 下三点静止但保留可见（opacity 不得为 0）', () => {
    const reduce = css.match(/@media \(prefers-reduced-motion: reduce\)\s*\{[\s\S]*?\n\}/)?.[0] ?? ''
    expect(reduce).toContain('.thinking-dot')
    expect(reduce).toMatch(/animation:\s*none/)
    expect(reduce).not.toMatch(/\.thinking-dot[^}]*opacity:\s*0[;\s]/)
  })

  it('同一 reduce 块内覆盖骨架 shimmer（4A F7 遗漏项）', () => {
    const reduce = css.match(/@media \(prefers-reduced-motion: reduce\)\s*\{[\s\S]*?\n\}/)?.[0] ?? ''
    expect(reduce).toContain('.skeleton-shimmer')
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/utils/__tests__/thinkingDots.test.js`
Expected: FAIL —— `main.css` 中无 `.thinking-dot`

- [ ] **Step 3: 实现 CSS**

在 `frontend/src/assets/main.css` 末尾追加：

```css
/* 思考中三点（4A：替换 daisyUI loading-dots。后者的动画在内嵌 SVG 的 SMIL 里，
   CSS 既覆盖不了也不响应 prefers-reduced-motion；自绘三点与 Microphone 既有
   animate-pulse-dot 同构，走同一套 reduce 处理） */
.thinking-dot {
  width: 4px;
  height: 4px;
  border-radius: 9999px;
  background: currentColor;
  opacity: 0.35;
  animation: thinking-bounce 1.2s ease-in-out infinite;
}
.thinking-dot:nth-child(2) { animation-delay: 0.2s; }
.thinking-dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes thinking-bounce {
  0%, 60%, 100% { opacity: 0.35; transform: translateY(0); }
  30%           { opacity: 1;    transform: translateY(-3px); }
}

/* 4A：全局装饰动画的 reduce 兜底（骨架 shimmer 此前遗漏） */
@media (prefers-reduced-motion: reduce) {
  .thinking-dot { animation: none; opacity: 0.6; }
  .skeleton-shimmer { animation: none; }
}
```

- [ ] **Step 4: 实现模板**

替换 `ChatHistory.vue` 第 203-206 行：

```html
<!-- 思考中指示（首 token 前）：自绘三点——daisyUI loading-dots 是 SMIL，停不掉（4A 设计 §1-F4）。
     内层 h-5（20px）定尺盒是**几何约束**：daisyUI 的 loading-sm 是 20×20（aspect-ratio:1 +
     width:calc(--size-selector*5)=20px），去掉后气泡高度会从约 44px 塌到约 20px，
     破坏"零视觉变更"（评审 R-3 实测）。三点排在 20px 盒内 → 外尺寸逐像素守住。 -->
<div v-if="thinking" class="flex justify-start my-2">
  <div class="msg-bubble msg-bubble-ai">
    <div class="h-5 flex items-center gap-1">
      <span class="thinking-dot"></span>
      <span class="thinking-dot"></span>
      <span class="thinking-dot"></span>
    </div>
  </div>
</div>
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/utils/__tests__/thinkingDots.test.js`
Expected: PASS（4 个用例）

- [ ] **Step 6: 提交**

```bash
git add frontend/src/assets/main.css frontend/src/components/character/chat_field/chat_history/ChatHistory.vue frontend/src/utils/__tests__/thinkingDots.test.js
git commit -m "fix(a11y): 思考中指示器换自绘三点（daisyUI loading-dots 是 SMIL，reduced-motion 下永动）+ 骨架 reduce 兜底（4A T4）"
```

---

### Task 5: 全量验证与产物核对

**Files:** 无源码改动（仅验证）

- [ ] **Step 1: 全量前端单测**

Run: `cd frontend && npx vitest run`
Expected: 既有 65 passed + 本批新增 10（T1 3 + T2 3 + T4 4）= **75 passed**，0 failed

- [ ] **Step 2: 构建**

Run: `cd frontend && npm run build`
Expected: exit 0（既有 daisyUI `@property` 与 chunk 体积告警可忽略）

- [ ] **Step 3: 产物核对（正反两向）**

```bash
cd frontend/../backend/static/frontend/assets
grep -c "thinking-dot" *.css           # 期望 ≥1
grep -c "thinking-bounce" *.css        # 期望 ≥1
grep -c "用户菜单" *.js                 # 期望 ≥1
grep -c "loading-dots" *.js            # 期望 0（模板已不再使用）
```

- [ ] **Step 4: 截图对照（零视觉回归，D4A-4）**

在云端部署后（门 4）对同一角色截取「头部件 + 思考中态」，与改动前截图逐项比对：胶囊尺寸、间距、圆角、悬停底色、图标大小。**必须一致**。

- [ ] **Step 5: 手工键盘走查（云端）**

Tab 顺序：`用户菜单 → 头像 pill → 语音开关 → ☰/✕ → 消息区 → 输入框 → 麦克风 → 发送`；语音开关与头像 pill 上按 Enter/空格均生效；开启系统"减少动态效果"后三点静止但可见。

---

## 自查清单（提交 PR 前）

- [ ] 仅 §文件清单 中的文件被改动（`git diff --stat` 核对）
- [ ] 无任何颜色/尺寸/间距值被修改（`git diff` 中 template 只出现属性增删）
- [ ] 75 个前端单测全绿
- [ ] 产物核对 4 项全部命中
- [ ] 无 `TODO`/占位符残留
- [ ] PR 描述含：门 1/门 2 链接、验收断言 A1~A6 的逐条证据
