# 聊天界面改版 Phase 4B（简约背景重做）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户能**按角色**把聊天窗口切到确定的浅色阅读面——舞台与窗口同色调（舞台 `#e7e5e4`、窗口 `#fafaf9`），所有文字对比度 ≥4.5:1——同时保证沉浸模式**零视觉回归**。

**Architecture:** 在 `.chat-window` 根节点定义一套 `--cbg-*` CSS 变量（默认值 = 当前沉浸模式的逐字原值），`.chat-window.chat-simple` 覆盖为浅色值；舞台同理走 `.chat-stage-root.stage-simple`。**全部颜色收敛为 `main.css` 里的语义类**（`.chat-surface` / `.chat-glass-btn` / `.chat-float` 等），模板只留布局工具类。开关状态按 `character_id` 存 localStorage，由 `ChatWindow`（每会话一个实例）持有。

**Tech Stack:** Vue 3 Composition API + Tailwind CSS 4 + daisyUI 5 + vitest（jsdom 经 docblock 按需开启）；后端零改动。

**Spec:** `docs/superpowers/specs/2026-09-13-chat-ui-phase4b-simple-background-design.md`（含色板与**已实算**的对比度表 §3.3、token 契约 §3.4、逐元素清单 §3.5、异常场景 §3.6）

**前置：** 4A 已合并（本计划复用 4A 引入的 `.thinking-dot`，其 `currentColor` 取色使浅色模式无需改动该类）。

## Global Constraints

- **沉浸模式零视觉回归**（D4B-5）：`--cbg-*` 默认值必须与 `main.css` 现有值**逐字相同**；构建产物中 `rgba(0,0,0,.35)`、`blur(24px)`、`saturate(1.35)`、`0 24px 64px rgba(0,0,0,.45)`、`rgba(0,0,0,.25)` 必须仍存在。
- **浅色值固定，不做运行时解析**：所有对比度已在设计阶段实算（最坏 4.80:1）。**禁止**引入亮度采样、canvas、主色提取、"档位阶梯"（这些是 PR #37/#40 的砍掉项）。
- **不引入过渡动画**（D4B-8）：切换即时生效。
- **会话栏与 NavBar 不改**（D4B-6）。
- 冒号：`--cbg-*` 命名统一，新变量必须先在本计划的 Task 2 定义，后续 Task 只引用。
- 分支：`feature/gqyin/chat-ui-phase4b-simple-bg`；提交信息中文 `type(scope): 摘要`。

---

## 文件结构

| 动作 | 文件 | 职责 |
|------|------|------|
| 新增 | `frontend/src/composables/useChatBg.js` | 按 `character_id` 读写开关（localStorage + 容错） |
| 新增 | `frontend/src/composables/__tests__/useChatBg.test.js` | 读写/容错/每角色隔离 |
| 修改 | `frontend/src/assets/main.css` | `--cbg-*` token 家族 + `.chat-simple` / `.stage-simple` + 语义类 |
| 修改 | `frontend/src/components/chat/chat_window/ChatWindow.vue` | 持有开关、根节点类、引用浮层 token 化 |
| 修改 | `frontend/src/components/chat/chat_window/WindowHeader.vue` | ⚙ 入口 + 设置弹层 + token 化 |
| 新增 | `frontend/src/components/character/icons/SettingsIcon.vue` | ⚙ 内联 SVG |
| 修改 | `frontend/src/components/character/chat_field/character_photo_field/CharacterPhotoField.vue` | token 化 |
| 修改 | `frontend/src/components/character/chat_field/VoiceToggle.vue` | token 化 |
| 修改 | `frontend/src/components/character/icons/SpeakerIcon.vue` | `text-white` → `currentColor` |
| 修改 | `frontend/src/components/character/chat_field/chat_history/ChatHistory.vue` | 骨架/空态/示例问题/思考中 token 化 |
| 修改 | `frontend/src/components/character/chat_field/chat_history/message/Message.vue` | 气泡/名字/时间戳/日期/引用/markdown token 化（含 scoped 样式迁移） |
| 修改 | `frontend/src/components/character/chat_field/input_field/InputField.vue` | 输入区/按钮/错误横幅 token 化 |
| 修改 | `frontend/src/components/character/chat_field/input_field/Microphone.vue` | 语音栏容器 + 小点/文字 token 化 |
| 修改 | `frontend/src/views/chat/ChatIndex.vue` | 移动端抽屉遮罩随模式反转（Task 6） |

---

### Task 1: `useChatBg` 按角色存储

**Files:**
- Create: `frontend/src/composables/useChatBg.js`
- Test: `frontend/src/composables/__tests__/useChatBg.test.js`

**Interfaces:**
- Produces:
  - `STORAGE_KEY = 'chatSimpleBg'`
  - `parseChatBg(raw: string|null): Record<string, boolean>` —— 容错解析，脏数据返回 `{}`
  - `loadChatBgMap(): Record<string, boolean>` —— 读取且**不抛错**（localStorage 不可用返回 `{}`）
  - `saveChatBgMap(map): void` —— 写入且**不抛错**
  - `useChatBg(characterId: number|string)` → `{ simpleOn: ComputedRef<boolean>, setSimple(on: boolean): void, toggleSimple(): void }`

- [ ] **Step 1: 写失败测试**

创建 `frontend/src/composables/__tests__/useChatBg.test.js`：

```js
// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'
import { watch } from 'vue'
import {
  STORAGE_KEY, parseChatBg, loadChatBgMap, saveChatBgMap, useChatBg, __resetChatBgState,
} from '../useChatBg.js'

describe('useChatBg（4B D4B-3：每角色独立）', () => {
  beforeEach(() => {
    localStorage.clear()
    __resetChatBgState()   // 模块单例的初始值取自存储；清了存储必须同步重置内存态
  })

  it('脏数据/异常输入 → 空对象（不抛错）', () => {
    expect(parseChatBg(null)).toEqual({})
    expect(parseChatBg('')).toEqual({})
    expect(parseChatBg('not json')).toEqual({})
    expect(parseChatBg('[1,2]')).toEqual({})
    expect(parseChatBg('null')).toEqual({})
    expect(parseChatBg('{"12":"yes","37":true,"x":false}')).toEqual({ 37: true })  // 仅保留 boolean
  })

  it('读写往返', () => {
    saveChatBgMap({ 12: true })
    expect(loadChatBgMap()).toEqual({ 12: true })
  })

  it('按角色隔离：A 开不影响 B', () => {
    const a = useChatBg(12)
    const b = useChatBg(37)
    a.setSimple(true)
    expect(a.simpleOn.value).toBe(true)
    expect(b.simpleOn.value).toBe(false)
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY))).toEqual({ 12: true })
  })

  it('toggle 在真/假之间往返并持久化', () => {
    const a = useChatBg(12)
    a.toggleSimple()
    expect(a.simpleOn.value).toBe(true)
    a.toggleSimple()
    expect(a.simpleOn.value).toBe(false)
    expect(loadChatBgMap()).toEqual({ 12: false })
  })

  it('数字与字符串 id 等价（路由参数是字符串，store 可能是数字）', () => {
    useChatBg('12').setSimple(true)
    expect(useChatBg(12).simpleOn.value).toBe(true)
  })

  // 防回流：若有人把实现改回 computed 直读 localStorage，本用例立刻失败
  it('状态是响应式的（交互后同一引用可观察到变化）', () => {
    const a = useChatBg(12)
    const seen = []
    const stop = watch(a.simpleOn, (v) => seen.push(v), { flush: 'sync' })
    a.setSimple(true)
    a.setSimple(false)
    stop()
    expect(seen).toEqual([true, false])
  })

  it('localStorage 抛错时退化为内存态，且读写均不抛（E1）', () => {
    const original = window.localStorage.getItem
    window.localStorage.getItem = () => { throw new Error('QuotaExceededError') }
    expect(() => loadChatBgMap()).not.toThrow()
    expect(loadChatBgMap()).toEqual({})
    window.localStorage.getItem = original
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/composables/__tests__/useChatBg.test.js`
Expected: FAIL —— 无法解析 `../useChatBg.js`（模块不存在）

- [ ] **Step 3: 实现**

创建 `frontend/src/composables/useChatBg.js`：

```js
// 简约背景开关（4B D4B-3：**每角色独立**）。
// 存 localStorage：{"<character_id>": true}。键名与值都做校验——脏数据一律忽略，
// 任何存储异常都不得影响聊天页渲染（E1）。
//
// ⚠️ 响应式关键：状态必须落在**模块级 ref**（与既有 useVoiceToggle / useToast 同惯例）。
// 若写成 computed(() => loadChatBgMap()[key]) —— 读取 localStorage 不是响应式依赖，
// computed 缓存后**永不失效**，表现为"点了开关没反应"。评审探针已复现该缺陷。
import { computed, ref, watch } from 'vue'

export const STORAGE_KEY = 'chatSimpleBg'

/** 解析存储值：只接受 {"<数字id>": boolean} 形状，其余丢弃 */
export function parseChatBg(raw) {
  try {
    const parsed = JSON.parse(raw ?? '')
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    const out = {}
    for (const [k, v] of Object.entries(parsed)) {
      if (typeof v === 'boolean' && /^\d+$/.test(k)) out[k] = v
    }
    return out
  } catch {
    return {}
  }
}

export function loadChatBgMap() {
  try {
    return parseChatBg(window.localStorage.getItem(STORAGE_KEY))
  } catch {
    return {}
  }
}

export function saveChatBgMap(map) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(map))
  } catch {
    // 隐私模式/配额耗尽：静默降级为内存态
  }
}

// 模块级单例：启动读一次，之后每次变更持久化（deep 覆盖 future 的嵌套写）
const state = ref(loadChatBgMap())
watch(state, (v) => saveChatBgMap(v), { deep: true })

/** 仅供测试：把模块状态重新对回存储（单测里清空 localStorage 后必须调用，
 *  否则上一用例的内存态会污染下一用例——模块状态只在首次 import 时读一次） */
export function __resetChatBgState() {
  state.value = loadChatBgMap()
}

/** @param {number|string} characterId */
export function useChatBg(characterId) {
  const key = String(characterId)
  const simpleOn = computed(() => state.value[key] === true)

  function setSimple(on) {
    state.value = { ...state.value, [key]: !!on }
  }

  return { simpleOn, setSimple, toggleSimple: () => setSimple(!simpleOn.value) }
}
```

> **为什么不用 computed 直读 localStorage**：`computed` 只跟踪响应式依赖，读 `localStorage` 不会建立依赖关系，缓存值永不失效——开关写入了存储但界面不更新。这是评审用探针实测出的 P0 缺陷（`expected false to be true`），已在上面修正。
>
> **代价**：模块级状态使"跨标签页同步"仍不支持（不做），但同一页内多组件共享同一状态（正是所需）。读取时机为模块首次 import 时，若存储不可用则退化为 `{}`（E1）。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/composables/__tests__/useChatBg.test.js`
Expected: PASS（7 个用例）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/composables/useChatBg.js frontend/src/composables/__tests__/useChatBg.test.js
git commit -m "feat(chat): useChatBg 按角色记忆简约背景 + 存储容错（4B T1，D4B-3）"
```

---

### Task 2: `main.css` —— token 家族与语义类

**Files:**
- Modify: `frontend/src/assets/main.css`

**Interfaces:**
- Produces（后续所有 Task 只引用这些名字，不得新增颜色）：

  | 变量 | 沉浸默认（现状原值） | `.chat-simple` |
  |---|---|---|
  | `--cbg-window` | `transparent` | `#fafaf9` |
  | `--cbg-bubble-ai` | `rgba(0, 0, 0, 0.35)` | `#ffffff` |
  | `--cbg-bubble-ai-border` | `transparent` | `#e7e5e4` |
  | `--cbg-text` | `#ffffff` | `#1c1917` |
  | `--cbg-text-2` | `rgba(255, 255, 255, 0.70)` | `#57534e` |
  | `--cbg-text-3` | `rgba(255, 255, 255, 0.40)` | `#78716c` |
  | `--cbg-surface` | `rgba(0, 0, 0, 0.40)` | `#ffffff` |
  | `--cbg-surface-2` | `rgba(0, 0, 0, 0.35)` | `#ffffff` |
  | `--cbg-surface-border` | `transparent` | `#e7e5e4` |
  | `--cbg-float` | `rgba(0, 0, 0, 0.25)` | `#f5f5f4` |
  | `--cbg-float-strong` | `rgba(0, 0, 0, 0.30)` | `#e7e5e4` |
  | `--cbg-hover` | `rgba(0, 0, 0, 0.20)` | `rgba(28, 25, 23, 0.06)` |
  | `--cbg-ring` | `rgba(255, 255, 255, 0.40)` | `rgba(28, 25, 23, 0.30)` |
  | `--cbg-shadow` | `0 24px 64px rgba(0, 0, 0, 0.45)` | `0 24px 64px rgba(28, 25, 23, 0.18)` |
  | `--cbg-code` | `rgba(0, 0, 0, 0.40)` | `rgba(28, 25, 23, 0.06)` |
  | `--cbg-code-block` | `rgba(0, 0, 0, 0.45)` | `rgba(28, 25, 23, 0.08)` |
  | `--cbg-code-block-hover` | `rgba(0, 0, 0, 0.75)` | `rgba(28, 25, 23, 0.14)` |
  | `--cbg-skeleton-a/b` | `rgba(255,255,255,0.08)` / `0.18` | `rgba(28,25,23,0.06)` / `0.14` |
  | `--cbg-danger` | `#fca5a5` | `#b91c1c` |
  | `--cbg-link` | `#7dd3fc` | `#0f766e` |

- [ ] **Step 1: 写失败测试**

创建 `frontend/src/utils/__tests__/chatBgTokens.test.js`：

```js
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
// 注：本文件同时从 main.css 与 ChatIndex.vue 读源码做断言

const css = readFileSync(fileURLToPath(new URL('../../assets/main.css', import.meta.url)), 'utf8')
// 取 .chat-window 基础块：命中第一个 "{" 到第一个 "}" —— 该块内无颜色函数嵌套，安全
const plain = css.match(/\.chat-window\s*\{[^}]*\}/)?.[0] ?? ''
// 取浅色覆盖块：用非贪婪 + s 标志，避免被下一段 "{" 提前截断
const simple = css.match(/\.chat-window\.chat-simple\s*\{[\s\S]*?\n\}/)?.[0] ?? ''

describe('4B token 家族（设计 §3.4）', () => {
  it('沉浸默认值必须与改造前逐字一致（D4B-5 零回归的前提）', () => {
    expect(plain).toContain('rgba(0, 0, 0, 0.35)')      // --cbg-bubble-ai
    expect(plain).toContain('rgba(255, 255, 255, 0.70)') // --cbg-text-2
    expect(plain).toContain('0 24px 64px rgba(0, 0, 0, 0.45)')  // --cbg-shadow
  })

  it('浅色覆盖块含设计 §3.3 的全部关键值', () => {
    expect(simple).toContain('#fafaf9')
    expect(simple).toContain('#ffffff')
    expect(simple).toContain('#e7e5e4')
    expect(simple).toContain('#1c1917')
    expect(simple).toContain('#57534e')
    expect(simple).toContain('#78716c')
    expect(simple).toContain('#f5f5f4')   // chip 底；其上的 --cbg-text-2 对比 6.99:1
  })

  it('舞台浅色块存在且使用 #e7e5e4（舞台略深于窗口）', () => {
    const stage = css.match(/\.chat-stage-root\.stage-simple[\s\S]*?\n\}/)?.[0] ?? ''
    expect(stage).toContain('#e7e5e4')
  })

  it('用户气泡引用 var(--accent) 而非硬编码 #10b981（D4B-7）', () => {
    const bubble = css.match(/\.msg-bubble-user\s*\{[^}]*\}/)?.[0] ?? ''
    expect(bubble).toContain('var(--accent)')
    expect(bubble).not.toContain('#10b981')
  })

  it('未引入被砍掉的机制（防蔓延）', () => {
    // 只查**声明位**：main.css 的注释里本就提到过 --overlay-k / --user-bubble-bg
    // （Phase 1 留下的前瞻注释），用 not.toContain 会误报——评审实测发现
    expect(css).not.toMatch(/--overlay-k\s*:/)
    expect(css).not.toMatch(/--user-bubble-bg\s*:/)
    expect(css).not.toMatch(/--msg-text-shadow\s*:/)
  })

  it('新增的 token 与语义类不得落进 @layer（否则被 utilities 压过，浅色静默失效）', () => {
    const layers = css.match(/@layer[^{;]*/g) ?? []
    // 本批此前 main.css 零 @layer；若新增，必须显式评审（见设计 §3.4 硬性约束一）
    expect(layers).toEqual([])
  })

})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/utils/__tests__/chatBgTokens.test.js`
Expected: FAIL —— 无 `.chat-window.chat-simple`

- [ ] **Step 3: 实现**

在 `frontend/src/assets/main.css` 中，**把 `.chat-window` 现有块替换为**：

```css
/* 角色之窗：3:5 竖版容器，纯 CSS 尺寸公式（LD §8.1，无需 JS resize）
   4B：本块同时是 --cbg-* token 的**默认值来源**（沉浸模式）。
   默认值必须与 4B 之前逐字相同，否则沉浸模式回归（D4B-5）。 */
.chat-window {
  width: min(420px, calc((100vh - 64px - 48px) * 0.6));
  aspect-ratio: 3 / 5;
  max-height: calc(100vh - 64px - 48px);
  border-radius: 24px;
  box-shadow: var(--cbg-shadow);
  overflow: hidden;

  /* 沉浸模式（默认）：值 = 改造前原值 */
  --cbg-window: transparent;
  --cbg-bubble-ai: rgba(0, 0, 0, 0.35);
  --cbg-bubble-ai-border: transparent;
  --cbg-text: #ffffff;
  --cbg-text-2: rgba(255, 255, 255, 0.70);
  --cbg-text-3: rgba(255, 255, 255, 0.40);
  --cbg-surface: rgba(0, 0, 0, 0.40);
  --cbg-surface-2: rgba(0, 0, 0, 0.35);
  --cbg-surface-border: transparent;
  --cbg-float: rgba(0, 0, 0, 0.25);
  --cbg-float-strong: rgba(0, 0, 0, 0.30);
  --cbg-hover: rgba(0, 0, 0, 0.20);
  --cbg-ring: rgba(255, 255, 255, 0.40);
  --cbg-shadow: 0 24px 64px rgba(0, 0, 0, 0.45);
  --cbg-code: rgba(0, 0, 0, 0.40);
  --cbg-code-block: rgba(0, 0, 0, 0.45);
  --cbg-code-block-hover: rgba(0, 0, 0, 0.75);   /* 现状 Message.vue:171 原值 */
  --cbg-skeleton-a: rgba(255, 255, 255, 0.08);
  --cbg-skeleton-b: rgba(255, 255, 255, 0.18);
  --cbg-danger: #fca5a5;
  --cbg-link: #7dd3fc;
}

/* 4B 简约模式（浅色）。所有值见设计 §3.3，对比度已实算（最坏 4.80:1）。
   注意：本块只覆盖颜色；几何、间距、字体一律不变。 */
.chat-window.chat-simple {
  --cbg-window: #fafaf9;
  --cbg-bubble-ai: #ffffff;
  --cbg-bubble-ai-border: #e7e5e4;
  --cbg-text: #1c1917;
  --cbg-text-2: #57534e;
  --cbg-text-3: #78716c;
  --cbg-surface: #ffffff;
  --cbg-surface-2: #ffffff;
  --cbg-surface-border: #e7e5e4;
  --cbg-float: #f5f5f4;
  --cbg-float-strong: #e7e5e4;
  --cbg-hover: rgba(28, 25, 23, 0.06);
  --cbg-ring: rgba(28, 25, 23, 0.30);
  --cbg-shadow: 0 24px 64px rgba(28, 25, 23, 0.18);
  --cbg-code: rgba(28, 25, 23, 0.06);
  --cbg-code-block: rgba(28, 25, 23, 0.08);
  --cbg-code-block-hover: rgba(28, 25, 23, 0.14);
  --cbg-skeleton-a: rgba(28, 25, 23, 0.06);
  --cbg-skeleton-b: rgba(28, 25, 23, 0.14);
  --cbg-danger: #b91c1c;
  --cbg-link: #0f766e;
}
```

`@media (max-width: 1023px)` 内的 `.chat-window` 块只保留几何覆盖（`box-shadow: none`），**不重复声明 token**（变量继承自上方）。

随后在文件末尾追加**语义类**（模板只引用这些类，不直接写颜色）：

```css
/* ===== 4B 语义类：模板只引用类名，颜色全部收敛到 --cbg-* token ===== */

/* 窗口背景（沉浸：透明，由背景图铺满；简约：纯色） */
.chat-window-bg { background-color: var(--cbg-window); }

/* 玻璃/纯色表面：头部条、输入栏、弹层、语音栏 */
.chat-surface {
  background-color: var(--cbg-surface);
  border: 1px solid var(--cbg-surface-border);
}
.chat-surface-2 {
  background-color: var(--cbg-surface-2);
  border: 1px solid var(--cbg-surface-border);
}
.chat-surface-pop {
  background-color: var(--cbg-surface);
  border-color: var(--cbg-surface-border);
}

/* 图标按钮（头部件 ☰/✕/⚙、语音开关、麦克风、发送）：未激活态 */
.chat-icon-btn {
  color: var(--cbg-text);
  background: transparent;
}
.chat-icon-btn:hover { background: var(--cbg-hover); }

/* 状态也必须走语义层，不能在元素上再挂 bg-[var(--accent)] / bg-neutral-700 / text-white 这类
   工具类 —— 未分层类压过 @layer utilities，工具类会被上面两条规则**静默压掉**：
   麦克风聆听/识别中与发送键激活时的绿底会在沉浸模式也消失（评审 R-4 实测）。
   故状态一律用类切换，值在类里定义。 */
.chat-icon-btn-active {
  --cbg-own-accent: var(--accent);
  color: #ffffff;
  background-color: var(--cbg-own-accent);
}
.chat-btn-idle {
  color: var(--cbg-text);
  background-color: var(--cbg-hover);
}
.chat-btn-idle:disabled { opacity: 0.5; }

/* VoiceToggle 专用：底色用浮层族，但图标必须是**主文字**色（设计 §3.5：
   "语音开关 → `--cbg-float`，图标 `--cbg-text`"；直接用 .chat-float 会得到
   --cbg-text-2，与设计不符 —— 评审 R-4） */
.chat-icon-btn-solid {
  color: var(--cbg-text);
  background-color: var(--cbg-float);
}
.chat-icon-btn-solid:hover { background-color: var(--cbg-float-strong); }

/* 文字层级 */
.chat-text   { color: var(--cbg-text); }
.chat-text-2 { color: var(--cbg-text-2); }
.chat-text-3 { color: var(--cbg-text-3); }

/* 浮层胶囊：引用 chip、示例问题、日期胶囊、名字 pill */
.chat-float {
  background-color: var(--cbg-float);
  color: var(--cbg-text-2);
}
.chat-float-strong {
  background-color: var(--cbg-float-strong);
  color: var(--cbg-text);
}
.chat-float-hover:hover { background-color: var(--cbg-float-strong); }

/* 焦点环（浅色下白环不可见） */
.chat-focus:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px var(--cbg-ring);
}

/* 危险文字（语音错误横幅） */
.chat-danger { color: var(--cbg-danger); }

/* 引用浮层（窗口内 modal） */
.chat-modal {
  background-color: var(--cbg-surface);
  border-color: var(--cbg-surface-border);
}

/* 骨架（颜色随模式反转） */
.chat-window .skeleton-shimmer {
  background: linear-gradient(90deg,
    var(--cbg-skeleton-a) 25%, var(--cbg-skeleton-b) 50%, var(--cbg-skeleton-a) 75%);
  background-size: 200% 100%;
}
```

同时把这些**既有块改为引用 token**（值等价，浅色自动生效）：

```css
.stage-dim { background: rgba(0, 0, 0, 0.35); }          /* 沉浸基线不动 */
.chat-stage-root.stage-simple .stage-blur { display: none; }
.chat-stage-root.stage-simple .stage-dim  { background: #e7e5e4; }

/* 无背景图 / 图片加载失败时的深色兜底（E2/E3）。顺序有意放在 .chat-simple 之后：
   若该子树正好是简单模式，浅色 token 会因后者在源顺序靠后而取胜，符合 §3.6-E3 的约定。 */
.chat-stage-root.no-bg .stage-dim { background: #1c1917; }
.chat-window.no-bg { --cbg-window: #1c1917; }

.msg-bubble-ai {
  background: var(--cbg-bubble-ai);
  border: 1px solid var(--cbg-bubble-ai-border);
  backdrop-filter: blur(8px);
  color: var(--cbg-text);
  border-top-left-radius: 4px;
}
.msg-bubble-user {
  background: color-mix(in srgb, var(--accent) 70%, black);   /* D4B-7：不再硬编码 #10b981 */
  color: #ffffff;
  border-top-right-radius: 4px;
}
.msg-name-pill {
  background: var(--cbg-float-strong);
  color: var(--cbg-text);
  border-radius: 9999px;
  padding: 1px 8px;
  font-size: 14px;
}
.date-capsule {
  background: var(--cbg-float);
  color: var(--cbg-text-2);
  font-size: 12px;
  border-radius: 9999px;
  padding: 2px 12px;
}
```

> **注意（层级）**：以上所有 token 与语义类**必须写在 `@layer` 之外**（`main.css` 目前零 `@layer`，这是它们能压过 Tailwind utilities 的原因）。不要为求整洁套 `@layer components`——会让浅色模式静默失效，且单测只有新增的那条断言能发现。
>
> **注意（盒模型）**：`.msg-bubble-ai` 新增 `border: 1px solid transparent` 在沉浸模式下不可见（`transparent`），但**会改变盒模型**——`.msg-bubble` 是 `padding` 型气泡，1px 边框会让气泡整体宽/高各 +2px。为守住 D4B-5，同时给 `.msg-bubble` 加 `border: 1px solid transparent;` 并把 `padding` 从 `8px 12px` 改为 `7px 11px`（净尺寸不变）。**实施时必须用截图对照验证**（Task 6 Step 4）。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/utils/__tests__/chatBgTokens.test.js`
Expected: PASS（6 个用例）——token 家族与 @layer 守卫共 6 条；颜色门禁与遮罩断言已移到 Task 5 / Task 6（见评审 R3-1）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/assets/main.css frontend/src/utils/__tests__/chatBgTokens.test.js
git commit -m "feat(chat): 4B token 家族 + 语义类（沉浸默认值逐字保留；浅色按设计 §3.3）"
```

---

### Task 3: `ChatWindow` 持有开关 + 舞台/窗口根类 + 引用浮层

**Files:**
- Modify: `frontend/src/components/chat/chat_window/ChatWindow.vue`

**Interfaces:**
- Consumes: `useChatBg(friend.character.id)`（Task 1）、`.chat-simple`/`.stage-simple`/`.chat-modal`（Task 2）
- Produces: `<WindowHeader>` 新增 `:simple-bg` prop 与 `@toggleSimpleBg` 事件（Task 4 消费）；无背景图/加载失败时不再渲染背景图层（E2/E3）

- [ ] **Step 1: 写失败测试**

创建 `frontend/src/components/chat/chat_window/__tests__/ChatWindow.test.js`：

```js
// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { createApp, h, nextTick } from 'vue'
import { __resetChatBgState } from '@/composables/useChatBg.js'

vi.mock('@/components/character/chat_field/chat_history/ChatHistory.vue', () => ({
  default: { name: 'ChatHistory', render: () => h('div') },
}))
vi.mock('@/components/character/chat_field/input_field/InputField.vue', () => ({
  default: { name: 'InputField', render: () => h('div') },
}))
// stub 渲染一个真按钮：点击即 emit，测试用真实点击驱动（比 __vueParentComponent 稳，
// 后者只在 Vue 的 dev 构建下存在）
vi.mock('@/components/chat/chat_window/WindowHeader.vue', () => ({
  default: {
    name: 'WindowHeader',
    props: ['character', 'simpleBg'],
    emits: ['close', 'openDrawer', 'toggleSimpleBg'],
    setup(props, { emit }) {
      return () => h('button', {
        class: 'stub-header',
        type: 'button',
        onClick: () => emit('toggleSimpleBg'),
      })
    },
  },
}))

import ChatWindow from '../ChatWindow.vue'

const FRIEND = {
  id: 3,
  character: { id: 12, name: '龙安洋', background_image: '/media/bg.png' },
}

function mount(friend = FRIEND) {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp({ render: () => h(ChatWindow, { friend }) })
  app.mount(host)
  return host
}

describe('ChatWindow 简约模式接线（4B T3）', () => {
  beforeEach(() => {
    localStorage.clear()
    __resetChatBgState()   // ⚠️ 必须：模块单例的初值只在首次读存储时取一次。
                           // 只清 localStorage 而不重置内存态 → 种子写不进 state（评审 R-1 实测：
                           // 用例 2 必红、用例 3 假通过）
  })

  it('默认沉浸：窗口根无 chat-simple，舞台无 stage-simple', () => {
    const host = mount()
    expect(host.querySelector('.chat-window')?.className).not.toContain('chat-simple')
    expect(host.querySelector('.chat-stage-root')?.className).not.toContain('stage-simple')
  })

  it('开关为真时，窗口与舞台同时加类（同色调，D4B-2）', async () => {
    localStorage.setItem('chatSimpleBg', JSON.stringify({ 12: true }))
    __resetChatBgState()      // 种子写入存储后必须同步进内存态
    const host = mount()
    await nextTick()
    expect(host.querySelector('.chat-window')?.className).toContain('chat-simple')
    expect(host.querySelector('.chat-stage-root')?.className).toContain('stage-simple')
  })

  it('切换仅影响当前角色（每角色独立，D4B-3）', async () => {
    localStorage.setItem('chatSimpleBg', JSON.stringify({ 99: true }))
    __resetChatBgState()
    const host = mount()
    await nextTick()
    expect(host.querySelector('.chat-window')?.className).not.toContain('chat-simple')
  })

  // ⚠️ 必需：真实交互路径。仅在 mount 前写 localStorage 的用例**无法**发现
  // "computed 读非响应式数据"这类缺陷（评审探针已证），必须由点击驱动一次。
  it('点击开关后窗口与舞台类名同时更新（交互路径）', async () => {
    const host = mount()
    await nextTick()
    expect(host.querySelector('.chat-window')?.className).not.toContain('chat-simple')

    // WindowHeader 在本测试中被 stub 成一个真按钮：直接点击（真实交互路径）
    host.querySelector('.stub-header').click()
    await nextTick()
    expect(host.querySelector('.chat-window')?.className).toContain('chat-simple')
    expect(host.querySelector('.chat-stage-root')?.className).toContain('stage-simple')
    expect(JSON.parse(localStorage.getItem('chatSimpleBg'))).toEqual({ 12: true })
  })

  it('无背景图的角色：不渲染背景图与蒙层（E2）', async () => {
    const host = mount({ id: 4, character: { id: 21, name: '无图', background_image: '' } })
    await nextTick()
    expect(host.querySelector('.window-scrim')).toBeNull()
    expect(host.querySelector('.chat-window')?.className).toContain('no-bg')
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/components/chat/chat_window/__tests__/ChatWindow.test.js`
Expected: FAIL —— 找不到 `.chat-stage-root`（当前舞台容器无此类名）

- [ ] **Step 3: 实现脚本部分**

在 `ChatWindow.vue` 的 `<script setup>` 中追加：

```js
import { useChatBg } from '@/composables/useChatBg.js'

// 4B：简约背景按角色记忆（D4B-3）；:key 重建保证切换角色即换状态
const { simpleOn, toggleSimple } = useChatBg(props.friend.character.id)

// E2/E3：无背景图（空串）或图片加载失败时不渲染背景图层，避免 url(undefined) 与破图。
// ⚠️ 必须用 Image 预探测：监听器挂在用 :style 设 CSS background-image 的 <div> 上时，
// `error` 事件**不会触发**（评审 R-5 实测）——那样写 bgFailed 永远是 false，是死代码。
const bgFailed = ref(false)
const hasBg = computed(() => !!props.friend.character.background_image && !bgFailed.value)

watch(
  () => props.friend.character.background_image,
  (url) => {
    bgFailed.value = false
    if (!url) return
    const probe = new Image()
    probe.onerror = () => { bgFailed.value = true }
    probe.src = url
  },
  { immediate: true },
)
```

（在既有 `import { onBeforeUnmount, ref, useTemplateRef, watch } from 'vue'` 中补 `computed`）

- [ ] **Step 4: 实现模板**

把舞台与窗口两块替换为（保留既有类名与结构，仅**加**类与条件）：

```html
<div class="absolute inset-0 flex items-center justify-center">
  <!-- 舞台（桌面端：沉浸=同图模糊压暗；简约=纯色 #e7e5e4；无图=深色兜底） -->
  <div class="chat-stage-root absolute inset-0 overflow-hidden hidden lg:block"
       :class="{ 'stage-simple': simpleOn, 'no-bg': !hasBg }">
    <div v-if="hasBg"
         class="absolute -inset-[10%] bg-cover bg-center stage-blur"
         :style="{ backgroundImage: `url(${friend.character.background_image})` }"></div>
    <div class="absolute inset-0 stage-dim"></div>
  </div>

  <div class="chat-window relative flex flex-col"
       :class="{ 'chat-simple': simpleOn, 'no-bg': !hasBg }">
    <div v-if="hasBg"
         class="absolute inset-0 bg-cover bg-center"
         :style="{ backgroundImage: `url(${friend.character.background_image})` }"></div>
    <div v-if="hasBg" class="absolute inset-0 window-scrim"></div>
    <div class="chat-window-bg absolute inset-0"></div>

    <div class="relative z-10 flex flex-col h-full">
      <WindowHeader :character="friend.character"
                    :simple-bg="simpleOn"
                    @close="emits('closed')"
                    @openDrawer="emits('openDrawer')"
                    @toggleSimpleBg="toggleSimple" />
      <!-- ChatHistory / InputField 不变 -->
    </div>
  </div>

  <!-- 引用浮层：改引用 token（浅色下变浅底深字） -->
  <div v-if="activeCitation" ...>
    <div class="... chat-modal ..." @click.stop>
      <p class="chat-text ...">
      <button class="... chat-text-2 chat-focus" ...>
      <div class="... chat-text-2 ...">
```

并按设计 §3.6-4 处理层序：头部容器加 `relative z-30`（**自身建层叠上下文**——PR #40 踩过的坑：头部若无 z-index，弹层 `z-30` 出不去被气泡遮挡），弹层 `z-30`、引用浮层 `z-20`。两者可同时存在而互不干扰（弹层盖住浮层），**不需要**在打开其一时关闭另一个。

- [ ] **Step 5: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/components/chat/chat_window/__tests__/ChatWindow.test.js`
Expected: PASS（4 个用例）

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/chat/chat_window/ChatWindow.vue frontend/src/components/chat/chat_window/__tests__/ChatWindow.test.js
git commit -m "feat(chat): 简约背景接线——窗口与舞台同色切换 + 无背景图兜底（4B T3）"
```

---

### Task 4: `WindowHeader` 设置弹层 + ⚙ 图标

**Files:**
- Create: `frontend/src/components/character/icons/SettingsIcon.vue`
- Modify: `frontend/src/components/chat/chat_window/WindowHeader.vue`

**Interfaces:**
- Consumes: `simple-bg` prop、`toggleSimpleBg` 事件（Task 3）
- Produces: `<button aria-label="聊天设置" aria-expanded>` + `role="switch" aria-checked` 的开关；弹层含"仅对《角色名》生效"范围说明（D4B-3 的界面交代，硬性）

- [ ] **Step 1: 创建 ⚙ 图标（内联 SVG，不用 emoji 字形）**

```vue
<script setup lang="ts">
</script>

<template>
  <!-- 齿轮（内联 SVG，不用 emoji 字形——各平台形状不一，PR #40 验收反馈） -->
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
       stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
       class="w-5 h-5">
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </svg>
</template>
```

- [ ] **Step 2: 写失败测试**

创建 `frontend/src/components/chat/chat_window/__tests__/WindowHeader.test.js`：

```js
// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest'
import { createApp, h } from 'vue'

vi.mock('@/components/character/CharacterDetail.vue', () => ({
  default: { name: 'CharacterDetail', render: () => h('div') },
}))
import WindowHeader from '../WindowHeader.vue'

const CHARACTER = { id: 12, name: '龙安洋', photo: '/media/p.png' }

function mount(simpleBg = false) {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp({
    render: () => h(WindowHeader, { character: CHARACTER, simpleBg }),
  })
  app.mount(host)
  return host
}

describe('WindowHeader 设置弹层（4B T4）', () => {
  it('默认不显示弹层；⚙ 有可访问名称', () => {
    const host = mount()
    expect(host.querySelector('[role="dialog"], .chat-popover')).toBeNull()
    expect(host.querySelector('button[aria-label="聊天设置"]')).toBeTruthy()
  })

  it('点击 ⚙ 打开弹层，开关状态与 simpleBg 同步', async () => {
    const host = mount(true)
    host.querySelector('button[aria-label="聊天设置"]').click()
    await new Promise((r) => setTimeout(r))
    const sw = host.querySelector('[role="switch"]')
    expect(sw).toBeTruthy()
    expect(sw.getAttribute('aria-checked')).toBe('true')
  })

  it('弹层明示生效范围（含角色名）——B5 硬性断言', async () => {
    const host = mount()
    host.querySelector('button[aria-label="聊天设置"]').click()
    await new Promise((r) => setTimeout(r))
    expect(host.textContent).toContain('仅对《龙安洋》生效')
  })

  it('开关触发 toggleSimpleBg 事件', async () => {
    const host = document.createElement('div')
    document.body.appendChild(host)
    const onToggle = vi.fn()
    createApp({
      render: () => h(WindowHeader, { character: CHARACTER, simpleBg: false, onToggleSimpleBg: onToggle }),
    }).mount(host)
    host.querySelector('button[aria-label="聊天设置"]').click()
    await new Promise((r) => setTimeout(r))
    host.querySelector('[role="switch"]').click()
    expect(onToggle).toHaveBeenCalled()
  })
})
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/components/chat/chat_window/__tests__/WindowHeader.test.js`
Expected: FAIL —— 无 `aria-label="聊天设置"` 按钮

- [ ] **Step 4: 实现 `WindowHeader.vue`**

```vue
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import CharacterPhotoField from '@/components/character/chat_field/character_photo_field/CharacterPhotoField.vue'
import VoiceToggle from '@/components/character/chat_field/VoiceToggle.vue'
import SettingsIcon from '@/components/character/icons/SettingsIcon.vue'

const props = defineProps(['character', 'simpleBg'])
const emits = defineEmits(['close', 'openDrawer', 'toggleSimpleBg'])

const settingsOpen = ref(false)
const popoverRef = ref(null)
const gearWrapRef = ref(null)   // 包裹层：仅用于「点外关闭」的 contains 判断
const gearBtnRef = ref(null)    // 触发器本体：焦点回归必须落在可聚焦的 <button> 上（评审 R-5）

const scopeLabel = computed(() => `仅对《${props.character?.name ?? '该角色'}》生效`)

function closeSettings() {
  settingsOpen.value = false
  gearBtnRef.value?.focus()       // 焦点回归触发器本体（B7）
}

function onDocClick(e) {
  if (!settingsOpen.value) return
  if (popoverRef.value?.contains(e.target) || gearWrapRef.value?.contains(e.target)) return
  closeSettings()
}

function onKeydown(e) {
  if (e.key === 'Escape' && settingsOpen.value) closeSettings()
}

watch(settingsOpen, (open) => {
  if (open) {
    document.addEventListener('click', onDocClick)
    document.addEventListener('keydown', onKeydown)
  } else {
    document.removeEventListener('click', onDocClick)
    document.removeEventListener('keydown', onKeydown)
  }
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onKeydown)
})
</script>
```

模板（`relative` 建层叠上下文，弹层 `z-30` 出得去——这是 PR #40 踩过的坑）：

```html
<template>
  <div class="relative h-14 shrink-0 px-3 flex items-center justify-between gap-2
              chat-surface z-30">
    <CharacterPhotoField :character="character" />

    <div class="flex items-center gap-2">
      <button type="button"
              class="lg:hidden chat-icon-btn btn btn-sm btn-circle btn-ghost"
              aria-label="打开会话列表" data-tip="会话"
              @click="emits('openDrawer')">
        ☰
      </button>

      <!-- ⚙ 设置（4B：简约背景开关落点，D4B-4） -->
      <div ref="gearWrapRef" class="relative">
        <button type="button"
                class="chat-icon-btn btn btn-sm btn-circle btn-ghost"
                aria-label="聊天设置"
                :aria-expanded="settingsOpen ? 'true' : 'false'"
                data-tip="设置"
                @click="settingsOpen = !settingsOpen">
          <SettingsIcon />
        </button>

        <div v-if="settingsOpen" ref="popoverRef"
             class="chat-modal absolute right-0 top-12 z-30 w-64 rounded-xl border
                    p-3 shadow-xl"
             role="dialog" aria-label="聊天设置">
          <div class="flex items-center justify-between gap-3">
            <span class="chat-text text-sm">简约背景</span>
            <button type="button" role="switch"
                    :aria-checked="simpleBg ? 'true' : 'false'"
                    aria-label="简约背景"
                    class="relative h-5 w-9 shrink-0 rounded-full transition-colors chat-focus"
                    :style="{ backgroundColor: simpleBg ? 'var(--accent)' : 'var(--cbg-float)' }"
                    @click="emits('toggleSimpleBg')">
              <span class="absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all"
                    :style="{ left: simpleBg ? '18px' : '2px' }"></span>
            </button>
          </div>
          <!-- 生效范围说明：上一次被否的原因之一是"全局偏好但界面没说明"（D4B-3） -->
          <p class="chat-text-2 text-xs mt-1.5">{{ scopeLabel }}</p>
        </div>
      </div>

      <VoiceToggle />
      <button type="button"
              class="chat-icon-btn btn btn-sm btn-circle btn-ghost"
              aria-label="关闭对话" data-tip="关闭"
              @click="emits('close')">
        ✕
      </button>
    </div>
  </div>
</template>
```

> **注意**：`☰` / `✕` 本次仍为字符字形（其换 SVG 属图标统一，见 4B 设计 §7 边界外的独立项）。弹层内开关若与 daisyUI `btn` 类冲突，改纯 Tailwind 类（如上）。

- [ ] **Step 5: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/components/chat/chat_window/__tests__/WindowHeader.test.js`
Expected: PASS（4 个用例）

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/character/icons/SettingsIcon.vue frontend/src/components/chat/chat_window/
git commit -m "feat(chat): ⚙ 设置弹层（简约背景开关 + 生效范围明示 + 焦点管理）（4B T4）"
```

---

### Task 5: 消息区与输入区 token 化

**Files:**
- Modify: `frontend/src/components/character/chat_field/chat_history/message/Message.vue`
- Modify: `frontend/src/components/character/chat_field/chat_history/ChatHistory.vue`
- Modify: `frontend/src/components/character/chat_field/input_field/InputField.vue`
- Modify: `frontend/src/components/character/chat_field/input_field/Microphone.vue`
- Modify: `frontend/src/components/character/chat_field/VoiceToggle.vue`
- Modify: `frontend/src/components/character/chat_field/character_photo_field/CharacterPhotoField.vue`
- Modify: `frontend/src/components/character/icons/SpeakerIcon.vue`

**Interfaces:**
- 仅替换类名与颜色声明，**不改结构、不改布局值**

- [ ] **Step 1: 逐文件替换（按设计 §3.5 清单）**

| 文件 | 替换 |
|------|------|
| `Message.vue`（**逐处，勿漏**） | ① 时间戳 ×2 处 `text-white/60` → `chat-text-2`（`:92` `:107`）<br>② 引用 chip 按钮（`:117-118`）`bg-black/25 backdrop-blur text-white/90 hover:bg-black/40` → `chat-float chat-float-hover chat-focus`<br>③ **chip 内的「第N段」span（`:122`）`text-white/75` → `chat-text-2`**<br>④ 名字 pill：用既有 `.msg-name-pill`（已在 main.css token 化，无需改模板）<br>⑤ scoped 样式 `:deep(code)`（`:151`）`rgba(0,0,0,0.4)` → `var(--cbg-code)`<br>⑥ scoped 样式 `:deep(pre)`（`:152`）`rgba(0,0,0,0.45)` → `var(--cbg-code-block)`<br>⑦ **scoped 样式 `:deep(blockquote)`（`:154`）`border-left: 3px solid rgba(255,255,255,0.3)` → `var(--cbg-text-2)`；`color: rgba(255,255,255,0.85)` → `var(--cbg-text-2)`**<br>⑧ **scoped 样式 `:deep(a)`（`:155`）`color: #7dd3fc` → `var(--cbg-link)`**<br>⑨ **`.code-copy-btn`（`:162-163`）`background: rgba(0,0,0,0.5)` → `var(--cbg-code-block)`；`color: rgba(255,255,255,0.85)` → `var(--cbg-text-2)`；`:hover`（`:171`）`background: rgba(0,0,0,0.75)` → `var(--cbg-code-block-hover)`**<br>⚠️ ③⑦⑧⑨ 四处**原计划漏列**（评审 R-4 实测发现）：根因是计划用「Tailwind 工具类正则」统计硬编码，而 `Message.vue` 的 scoped 样式里是 `rgba()`/十六进制字面量，正则匹配不到。**本表按文件逐处重数列出** |
| `ChatHistory.vue` | 骨架块 `skeleton-shimmer` 保留
| `InputField.vue` | 麦克风/发送/停止按钮 `text-white` + `hover:bg-black/20` → `chat-icon-btn chat-focus`（**加**环：实测这三个圆钮**没有** `.btn` 类，`:392/429/438` 只有 Tailwind 工具类）；**激活态** `class` 绑定里**删掉** `bg-[var(--accent)]` 与 `text-white` 字面量，改挂 `chat-icon-btn-active`（状态值在 CSS 类里，理由见 Task 2 的 R-4 注释）；未激活发送键 `bg-neutral-700 opacity-50` → `chat-btn-idle`；textarea `bg-black/35 text-white` → `chat-surface-2 chat-text`，加 `placeholder:text-[var(--cbg-text-3)]`；错误横幅 `text-red-300` → `chat-danger` + 保留字号 |
| `Microphone.vue` | 语音栏容器 `bg-black/35 backdrop-blur` → `chat-surface-2`；"语音初始化中…"/"识别中…"/"**正在聆听…**" 的 `text-white/40` → `chat-text-3`（`:272` `:281` `:291`，三处都要改）；小点与音浪 `bg-blue-400` **保留**（品牌色，两模式均可见，已进白名单） |
| `VoiceToggle.vue` | `bg-black/50` + `hover:bg-black/60` → **`--cbg-glass-btn` / `--cbg-glass-btn-hover`**（**不得**用 `--cbg-float`：0.25 会让胶囊暗度减半，评审 N5）；图标色 `--cbg-text`（用 `.chat-icon-btn-solid`，其 color 已设 `--cbg-text`）；焦点环 → `chat-focus`（4A T1 已引入，此处由 token 接管） |
| `CharacterPhotoField.vue` | `bg-black/50` → **`--cbg-glass-btn`**（同上，不得用 `--cbg-float`；现状无 hover，不加 hover 态）；名字 `text-white` → `chat-text`；加 `chat-focus`（4A T2 已引入） |
| `SpeakerIcon.vue` | 两处 `text-white` / `text-white/40` → `text-current` / `opacity-40` |
| （说明） | 焦点环按**元素实际持有的类名**判定，不按文件/区域：**有 `btn` 类**（⚙/☰/✕、`InputField:454` 重试）→ 只加 `chat-icon-btn`，**不加** `chat-focus`（daisyUI 用 `outline-width:2px` + `outline-color:var(--color-base-content)`，与 `ring` 叠加会双环）；**无 `btn` 类**（麦克风/发送/停止三个圆钮、`VoiceToggle`、`CharacterPhotoField`、示例问题、引用 chip）→ `chat-focus` **必须加**，否则抹掉 4A 挣来的焦点可见性（评审 R-2 实测） |

- [ ] **Step 1b: 新建 token 残留门禁（随本任务落地）**

创建 `frontend/src/utils/__tests__/chatBgLiterals.test.js`：

```js
// 门禁：聊天窗口相关文件里不得残留未 token 化的颜色字面量（评审 R-4 的机制性修复）。
// 随本任务的 token 化落地——**只有 Task 5 全部改完才可能绿**（评审 R3-1 的放置要求）。
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

// 前 6 个在 components/character/chat_field/ 下，后 2 个在 components/chat/chat_window/ 下
const TARGETS = [
  'chat_history/message/Message.vue',
  'chat_history/ChatHistory.vue',
  'input_field/InputField.vue',
  'input_field/Microphone.vue',
  'character_photo_field/CharacterPhotoField.vue',
  'VoiceToggle.vue',
]

// 引用浮层（评审 N1 末条：那 6 处字面量原本无任何机检）
const WINDOW_TARGETS = [
  'ChatWindow.vue',
  'WindowHeader.vue',
]

/** 扫描前剥掉全部注释：HTML <!-- -->、CSS 块注释、整行 //（评审 R3-3：
 *  Microphone.vue:261-262 的 HTML 注释续行含 bg-black/35，不剥会让门禁永远红） */
function stripComments(src) {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .filter((l) => !l.trim().startsWith('//'))
    .join('\n')
}

/** 覆盖面：任意可能承载颜色的工具类 + CSS 颜色字面量（评审 R3-4：
 *  初稿只认白/黑两族，漏掉 bg-neutral-700 等）。只放行白名单，其余一律计入。 */
/** ① 工具类：**只认调色板名**。这样天然排除 `text-sm`(字号) / `text-center`(对齐) /
 *  `border-radius`(CSS 属性名) / `outline-none` —— 初版写成 `[a-z][a-z0-9-]*` 通配，
 *  实测把这三类全判红，门禁永远绿不了（评审 N1）。 */
const COLOR_UTIL =
  /\b(?:text|bg|border|ring|divide|outline|fill|stroke|from|to|via)-(?:white|black|neutral|stone|gray|slate|zinc|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)(?:-\d{2,3})?(?:\/\d+)?\b/g

/** ② 任意值：只认**看起来是颜色**的，并放行 var(--cbg-*)。
 *  初版的负向前瞻只挡住第一支，导致计划**要求新加**的
 *  `placeholder:text-[var(--cbg-text-3)]` 反被判红（评审 N1 实测）。 */
const ARBITRARY_COLOR =
  /\b(?:text|bg|border|ring)-\[(?!var\(--cbg-)(?:#|rgba?\(|hsla?\(|oklch\(|color-mix\()[^\]]*\]/g

const CSS_COLOR = /rgba?\(|#[0-9a-fA-F]{3,8}\b/g

/** 白名单（每条都要有依据）：
 *  - `text-white`：己方气泡绿底白字，沉浸/简约两模式都成立（设计 §3.5）
 *  - `bg-blue-400`：Microphone 六小点与音浪，品牌色保留（设计 §3.5「小点保留」） */
const ALLOWED = new Set(['text-white', 'bg-blue-400'])

/** 只扫模板部分：scoped `<style>` 里的 CSS 属性名（border-radius / text-decoration）
 *  会污染工具类扫描；样式里的颜色由 CSS_COLOR 负责（评审 N1 建议）。 */
function stripStyleBlocks(src) {
  return src.replace(/<style[\s\S]*?<\/style>/g, '')
}

describe('颜色字面量残留门禁（Token 化完成度）', () => {
  it('6 个聊天窗口相关文件无未 token 化残留', () => {
    const offenders = []
    for (const rel of TARGETS) {
      const raw = readFileSync(
        fileURLToPath(new URL('../../components/character/chat_field/' + rel, import.meta.url)),
        'utf8',
      )
      const tmpl = stripStyleBlocks(stripComments(raw))
      const style = stripComments(raw.match(/<style[\s\S]*?<\/style>/)?.[0] ?? '')
      const hits = [
        ...(tmpl.match(COLOR_UTIL) ?? []),
        ...(tmpl.match(ARBITRARY_COLOR) ?? []),
        ...(style.match(CSS_COLOR) ?? []),
      ].filter((h) => !ALLOWED.has(h))
      if (hits.length) offenders.push(rel + ': ' + [...new Set(hits)].join(', '))
    }
    for (const rel of WINDOW_TARGETS) {
      const raw = readFileSync(
        fileURLToPath(new URL('../../chat/chat_window/' + rel, import.meta.url)),
        'utf8',
      )
      const tmpl = stripStyleBlocks(stripComments(raw))
      const style = stripComments(raw.match(/<style[\s\S]*?<\/style>/)?.[0] ?? '')
      const hits = [
        ...(tmpl.match(COLOR_UTIL) ?? []),
        ...(tmpl.match(ARBITRARY_COLOR) ?? []),
        ...(style.match(CSS_COLOR) ?? []),
      ].filter((h) => !ALLOWED.has(h))
      if (hits.length) offenders.push(rel + ': ' + [...new Set(hits)].join(', '))
    }
    expect(offenders).toEqual([])
  })
})
```

Run: `cd frontend && npx vitest run src/utils/__tests__/chatBgLiterals.test.js`
Expected: **FAIL（这是预期的：门禁写在替换之前，逐文件改到绿为止）**

> **顺序说明**（评审小事 2）：Step 1b 是本任务的 TDD 红点——先在 Step 1b 建门禁（允许红），Step 1 的"逐文件替换"完成后它自然变绿；若把门禁放在替换之后，就成了"事后补测"，红点会失去意义。Step 2 的构建核对在两者之后。

- [ ] **Step 2: 构建并核对产物（正反两向）**

```bash
cd frontend && npm run build
cd ../backend/static/frontend/assets
grep -c "cbg-window" *.css        # ≥1
grep -c "chat-simple" *.css       # ≥1
grep -c "stage-simple" *.css      # ≥1
grep -c "#fafaf9" *.css           # ≥1
grep -c "#e7e5e4" *.css           # ≥1
grep -c "overlay-k" *.css         # 0（砍掉项未引入）
```

- [ ] **Step 3: 全量单测**

Run: `cd frontend && npx vitest run`
Expected: 4A 后基线 **75** + 本批新增 24（T1 7 + T2 6 + T3 5 + T4 4 + 门禁 `chatBgLiterals` 1 + 遮罩 `chatBgScrim` 1）= **99 passed**，0 failed

- [ ] **Step 4: 提交**

```bash
git add frontend/src/
git commit -m "feat(chat): 消息区与输入区 token 化——浅色模式全量生效（4B T5）"
```

---

### Task 6: 移动端抽屉遮罩随模式反转

**Files:**
- Modify: `frontend/src/views/chat/ChatIndex.vue:119`
- Test: `frontend/src/utils/__tests__/chatBgTokens.test.js`（追加一条源码断言）

**Interfaces:**
- Consumes: `useChatBg(activeCharacterId)`（Task 1，模块级单例——与 `ChatWindow` 读同一状态，不会不一致）、`.chat-simple` 语义（Task 2）
- Produces: 抽屉遮罩类名随模式切换（`bg-black/50` ⟷ `bg-[#1c1917]/40`）

> **背景**：用户裁决（2026-09-13）纳入本批。遮罩是 `lg` 以下的移动端独有覆盖层，属简约模式的组成部分；纯黑遮罩在浅色整页中会显得突兀。实算见设计 §3.7。

> **断言归属**：本任务的遮罩断言**单独放在本任务的 Step 里**，不塞进 `chatBgTokens.test.js`——门禁要跟它验证的改动走（评审 R3-1：把跨任务断言塞进 Task 2，会让 Task 2 Step 4 的"预期 PASS"永远红）。

- [ ] **Step 1: 新建遮罩断言并确认失败**

创建 `frontend/src/utils/__tests__/chatBgScrim.test.js`：

```js
// 移动端抽屉遮罩随模式反转（设计 §3.7，用户裁决纳入）
// 用源码断言而非组件测试：遮罩位于 lg:hidden 的 Teleport 抽屉内，
// 触发它需 mock useMediaQuery 与 Teleport 目标，成本远高于价值；
// 本条核心风险是"人删了简约分支"，源码断言足以拦住。
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

describe('抽屉遮罩（4B T6）', () => {
  it('遮罩类名随模式切换', () => {
    const src = readFileSync(
      fileURLToPath(new URL('../../views/chat/ChatIndex.vue', import.meta.url)),
      'utf8',
    )
    expect(src).toContain('bg-[#1c1917]/40')   // 简约：暖深色 40%
    expect(src).toContain('bg-black/50')       // 沉浸：现状不变
  })
})
```

Run: `cd frontend && npx vitest run src/utils/__tests__/chatBgScrim.test.js`
Expected: FAIL —— `ChatIndex.vue` 中还没有 `bg-[#1c1917]/40`

> **为什么用源码断言而不是组件测试**：遮罩位于 `lg:hidden` 的 Teleport 抽屉内，要触发它需 mock `useMediaQuery` 与 Teleport 目标，成本远高于价值；本条的核心风险是"人删了简约分支"，源码断言足以拦住。

- [ ] **Step 2: 实现**

`ChatIndex.vue` 的 `<script setup>` 中：

```js
import { useChatBg } from '@/composables/useChatBg.js'
// 抽屉与 ChatWindow 是兄弟节点，但 useChatBg 是模块级单例 → 两处读到同一状态
const { simpleOn: simpleBg } = useChatBg(activeCharacterId)
```

模板第 119 行（`Teleport` 内的遮罩）：

```html
<!-- 移动端抽屉遮罩：沉浸=黑 50%（现状不变）；简约=暖深色 40%（设计 §3.7） -->
<div class="absolute inset-0"
     :class="simpleBg ? 'bg-[#1c1917]/40' : 'bg-black/50'"
     @click="drawerOpen = false"></div>
```

> `activeCharacterId` 在会话中心（`null`）时 `String(null)` 得 `'null'`，读取结果恒为 `false` → 遮罩保持黑 50%，无副作用。

- [ ] **Step 2: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/utils/__tests__/chatBgScrim.test.js`
Expected: PASS（1 个用例）

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/chat/ChatIndex.vue frontend/src/utils/__tests__/chatBgScrim.test.js
git commit -m "fix(chat): 移动端抽屉遮罩随模式反转（浅色整页不再出现纯黑块）（4B T6）"
```

---

### Task 7: 验证与验收证据

**Files:** 无源码改动

- [ ] **Step 1: 零回归截图对照（D4B-5，最重的一条）**

云端部署后，对**同一角色**、**同一视口**，逐项对照改动前后的截图：头部条高度与描边、气泡内外边距（Step 2 的 1px 边框补偿必须做到净尺寸不变）、名字 pill、日期胶囊、引用 chip、输入栏、思考中三点、舞台模糊与压暗。**任何差异都算回归缺陷**，修完再验。

- [ ] **Step 2: 浅色模式逐元素走查（设计 §3.5 全表）**

开启简约后确认：窗口底 `#fafaf9`、舞台 `#e7e5e4`、AI 气泡白底+描边、用户气泡仍绿底白字、时间戳/日期/引用可读、占位符可读、代码块与行内 code 底色变浅、链接可读、空态与示例问题可读、语音错误横幅可读。

- [ ] **Step 3: 每角色独立 + 持久化（B3/B4）**

A 角色开启 → 刷新仍开启 → 切到 B 角色（应为沉浸）→ 切回 A（仍简约）。

- [ ] **Step 4: 键盘与弹层（B7）**

Tab 到 ⚙ → Enter 打开 → Tab 到开关 → 空格切换 → Esc 关闭 → 焦点回到 ⚙。

- [ ] **Step 5: 异常路径（B9）**

① 无背景图角色（`background_image=""`）② 故意把图片 URL 改坏 → 两种情况下都不出现破图/亮底白字；开启简约同样正常。

- [ ] **Step 6: 收集 PR 证据**

```bash
cd frontend && npx vitest run          # 输出贴进 PR
npm run build && ls -la ../backend/static/frontend/assets/   # 产物 hash
```

---

## 自查清单（提交 PR 前）

- [ ] 仅 §文件结构 中列出的文件被改动（含已裁决纳入的 `ChatIndex.vue`——见设计 §9 Q-4B-1）
- [ ] `grep -rn "#10b981" frontend/src/assets/main.css` → 仅剩 `--accent` 定义与 fallback
- [ ] 未引入 `--overlay-k` / `--user-bubble-bg` / `--msg-text-shadow` / canvas 采样 / 主色提取
- [ ] 沉浸模式截图与 master 逐项一致（Task 6 Step 1）
- [ ] 浅色模式对比度抽查 ≥ 设计 §3.3 表中值
- [ ] 全部单测全绿；产物核对 6 项命中
- [ ] PR 描述含：门 1/门 2 链接、断言 B1~B10 的逐条证据、**验收清单**（§5.2 九步）
