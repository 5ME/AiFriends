# 聊天界面改版 Phase 4B —— 简约背景重做 · 设计文档

> 状态：**待门 1/门 2 批准**（2026-09-13 起草）
> 分级：**L**（跨 12 个前端文件 + 全局 token 家族；纯前端，后端零改动）
> 上游事实源：`2026-09-07-chat-ui-redesign-spec-for-llm.md` §2-C3 / §6.1 / §6.6 / §13-Phase 4；`2026-09-07-chat-ui-redesign-logic-design.md` §3.4 / §3.5 / §8.2 / §10
> 关联批次：`2026-09-13-chat-ui-phase4a-a11y-design.md`（4A 先交付；4B 依赖 4A 已合并，但**不依赖其代码**，仅依赖同一批文件不被并发修改）
> ⚠️ 本主题已被否决两次：**PR #37**（自适应蒙层 + 浅色简约）、**PR #40**（深色简约 + 文字描边）。本文件为第三次起草，**不延续任何被判否的方案**。

---

## 0. 为什么重做，以及这一版改了什么

### 0.1 两次被否的共同点（owner 2026-09-13 于 PR #40 的结论）

> "「简约背景」该是什么样，两次都是 Agent 自己拍的，两次都没拍对。"

具体到观感：

| 轮次 | 方案 | 被否的直接原因 |
|------|------|----------------|
| PR #37 | 窗口浅色 `#f5f5f4` + 自适应蒙层 + 舞台压暗 | 整体「做得不好」；实测暴露亮图下浮层文字仅 1.59~2.43:1 |
| PR #40 | 窗口深色 `#1c1917` + 舞台压到近黑 | 「深色简约背景造成'把舞台变黑'的观感，**与'简约背景'这个名字不符**」 |

### 0.2 本版与前两版的根本区别

**设计决策由用户拍板，不再由 Agent 拍。** 2026-09-13 澄清阶段已确认四项：

| # | 决策 | 用户原话/选择 |
|---|------|--------------|
| ① | 舞台与窗口**必须同色调** | 「我理解窗口和舞台色调应该一致吧」（否掉了 Agent 提出的"舞台不动、只换窗口"方案——那会让窗口像贴在暗色板上的一块板） |
| ② | 底色方向 **浅色（暖石白）** | 「浅色（暖石白，推荐）」 |
| ③ | 范围 **每角色独立** | 「每角色独立（推荐）」——不再出现"开一个角色、所有角色都变，界面又没说明" |
| ④ | 层次：**舞台略深、窗口纯白** | 「同色阶：舞台略深、窗口纯白（推荐）」 |

**本版不做的事**（防蔓延，均为前两版被判否或额外引入的复杂度）：

| 砍掉项 | 理由 |
|--------|------|
| 亮度自适应蒙层 / canvas 采样 / `--overlay-k` | 简约模式下没有图，**不需要**自适应；沉浸模式的固定蒙层已在 Phase 1~3 实测可用 |
| 主色提取 `accent` | 悬浮在"提取出来的颜色好不好看"上，不可控；**沿用全局 `--accent`** |
| 文字描边 `--msg-text-shadow` | 随 PR #40 一并作废；浅色模式下无图，不需要承托 |
| 创建页聊天效果预览 | 独立价值，属另一主题（创建流程），不在本批 |
| 跟随系统深色 | 与全站单一 light 主题矛盾；用户已选"浅色" |
| 舞台提亮 `brightness(1.3)`、压暗 0.35→0.22 | 那是对深色方案的补偿；本版不改沉浸模式一个像素 |

### 0.3 为什么"浅色简约"能同时满足可读性与 C3

沉浸模式的可读性上限由**背景图内容**决定。最坏情况（纯白背景图）下，实测（WCAG 口径，sRGB 分量空间合成）：

| 位置 | 现状（master，固定蒙层 K=1） | 是否达标 |
|------|------------------------------|----------|
| 顶部浮层文字（名字 pill，白 70%） | **2.63:1** | ✗（正文需 ≥4.5:1） |
| 顶部 AI 气泡白字（`bg-black/35` 叠 α=0.25 蒙层） | **4.17:1** | △ 接近 |
| 中部白字 | 3.07:1 | ✗ |
| 底部白字 | 5.74:1 | ✓（仅底部） |

而浅色简约模式**全部 ≥ 4.59:1**（§3.3 逐项列出）。这正是 spec §2-C3「背景非用户所设，用户须能降级」存在的意义：**沉浸模式有视觉风险但氛围好，简约模式牺牲氛围换取确定性**。两者都由用户在**每个角色**上自行取舍。

---

## 1. 事实核查（实施前基线，本机 master `7279335` 已核实）

| # | 事实 | 证据 | 影响 |
|---|------|------|------|
| F1 | 窗口与舞台的背景图都来自 `friend.character.background_image`，直接写在 `:style` 内联 | `ChatWindow.vue:93`（舞台）与 `:100-101`（窗口） | 简约模式必须同时接管两处 |
| F2 | `.window-scrim`（渐变蒙层）、`.stage-blur`/`.stage-dim`、`.msg-bubble-*`、`.date-capsule`、`.msg-name-pill`、`.session-active`、`.skeleton-shimmer` 全部定义在 `assets/main.css`，**值写死** | `main.css:26-114` | 需要 token 化；但**默认值必须逐字保留**，否则沉浸模式回归 |
| F3 | 硬编码白/黑玻璃类共 **38 处**，分布在 **9** 个文件 | 实测逐文件：`InputField(9) / Message(6) / ChatWindow(5) / ChatHistory(5) / Microphone(5) / WindowHeader(3) / VoiceToggle(2) / CharacterPhotoField(2) / ChatIndex(1)`；按 token 分：`text-white(7) / text-white-90(4) / ring-white-40(4) / text-white-40(3) / bg-black-50(3) / bg-black-40(3) / bg-black-35(3) / text-white-60(2) / border-white-10(2) / bg-black-25(2) / 其余 5 种各 1` | 这是"浅色化"的真实工作量；**逐处替换为 token，不重写模板结构**。<br>⚠️ 初稿写"34 处 / 8 文件"是**错的**（漏了 `ChatIndex.vue`，且部分文件漏数）——评审实测发现 |
| F4 | `--accent` 定义在全局 `:root`（`#10b981`），无任何地方按角色覆盖 | `main.css:10-12` | 简约与沉浸两模式**共用同一个 accent**，本批不引入提取 |
| F4b | daisyUI **实际版本 5.5.18**（本机 `node -e` 读取 `node_modules/daisyui/package.json`）；spec §1 写的 5.5.17 为旧值 | 本机实测 | 仅影响引用准确性；`loading.css` 的内容（`mask-image` + SMIL、无 CSS 动画）在 5.5.18 上成立 |
| F5 | 用户气泡底色 `color-mix(in srgb, #10b981 70%, black)` = `#0b825a`，白字对比 **4.82:1** | `main.css:76`；对比度实算 | 两模式下均已达标。**但**它硬编码了 `#10b981`，若日后 accent 可变就会失效 → 本批改为引用 `var(--accent)` |
| F6 | 会话栏（`SessionList`/`SessionItem`）与 NavBar **已是浅色**（daisyUI 默认主题：`bg-base-200`/`bg-base-100` + 深字），`session-active` 用 accent 40% 打底 | `SessionList.vue:60`、`SessionItem.vue`、`main.css:44-49` | 简约模式窗口变浅后，**全页色调反而统一**；会话栏不改 |
| F7 | 移动端（<1024px）窗口铺满，**无舞台** | `main.css:23-31`（媒体查询）、`ChatWindow.vue:91`（`hidden lg:block`） | 简约模式在移动端只影响窗口自身；逻辑天然兼容 |
| F8 | `--user-bubble-bg` / `--overlay-k` 在 master **没有任何声明位** | `git grep -n -E "--(overlay-k|user-bubble-bg)\\s*:"` → 无输出。⚠️ 初稿写「`grep ... frontend/src` → 空」是**错的**：`main.css` 第 33/38/58 行的注释里就提到过这两个名字，grep 会命中——评审实测发现。**故 4B 计划的防蔓延断言必须只查声明位**（`/--overlay-k\s*:/`），不能只查子串 | 本版不引入（砍掉项） |
| F9 | 头部条（`.h-14 bg-black/40 backdrop-blur`）、输入栏（`bg-black/35 backdrop-blur`）、思考中气泡、引用 chip、示例问题、日期胶囊、名字 pill 都是"深玻璃 + 白字"族 | `WindowHeader.vue:8`、`InputField.vue:406`、`ChatHistory.vue:192,204`、`Message.vue:117`、`main.css` | **浅色模式 = 这一族的整体反转**（不是个别调色） |
| F10 | `SpeakerIcon` 内部写死 `text-white` / `text-white/40`；`MicIcon`/`SendIcon`/`StopIcon` 继承 `currentColor` | `SpeakerIcon.vue:12,26`；`InputField.vue:392-445`（按钮类名给 `text-white`） | 浅色下需把这两个来源都改为 token |
| F11 | `localStorage` 在本项目已有先例：`useVoiceToggle`（全局布尔） | `composables/useVoiceToggle.js` | 本批新增 key，**不改** `useVoiceToggle` |
| F12 | `Character.background_image` 为空时，`ChatWindow` 仍会渲染 `url(undefined)` | `ChatWindow.vue:100-101`（无 `v-if`） | 空背景图场景本批必须显式处理（§3.6 E2） |

---

## 2. 决策记录

| # | 决策 | 来源 |
|---|------|------|
| D4B-1 | 简约模式底色为**浅色**：舞台 `#e7e5e4`、窗口 `#fafaf9`、AI 气泡 `#ffffff`、文字 `#1c1917` | 用户 2026-09-13 选择「浅色（暖石白）」 |
| D4B-2 | **舞台与窗口同色调**，舞台略深一档，形成"舞台 → 窗口"两级层次 | 用户 2026-09-13：「窗口和舞台色调应该一致」+「舞台略深、窗口纯白」 |
| D4B-3 | 开关**每角色独立**（按 `character_id` 记忆） | 用户 2026-09-13：「每角色独立」 |
| D4B-4 | 开关落在 WindowHeader 的 **⚙ 设置弹层**内（不设独立月亮按钮） | LD §3.5 + Q6（已拍板） |
| D4B-5 | 沉浸模式**零视觉回归**：所有类名/数值改动必须产出与当前**逐字相同**的 CSS 结果 | 契约门 4 + 前两轮教训 |
| D4B-6 | 会话栏与 NavBar **不改**（它们本就是浅色） | 本设计 §1-F6；见 §9 待决 Q-4B-1 |
| D4B-7 | 用户气泡底色改为引用 `var(--accent)`（原先硬编码 `#10b981`），行为等价、为将来留口 | §1-F5 |
| D4B-8 | 切换**不做过渡动画**（避免再引入 `@property` 注册那类复杂度） | 砍掉项，见 §0.2 |

### 2.1 已否决的替代方案

| 方案 | 否决理由 |
|------|----------|
| 舞台不动、只换窗口（Agent 初版提案） | 用户当场否掉：窗口会像贴在暗色板上的一块板，**色调不一致** |
| 深色简约（PR #40） | 用户：「把舞台变黑，与'简约背景'这个名字不符」 |
| 自适应蒙层 + 主色提取（PR #37） | 简约模式无图可采样；主色提取不可控。已在 §0.2 列为砍掉项 |
| 全局用户偏好（PR #37/#40 的实现） | 语义与直觉不符；用户已选「每角色独立」 |
| 舞台=窗口同色（无明度差） | 窗口边界只能靠描边/阴影，偏弱；用户已选"舞台略深" |
| 复用 `useChatSettings`（PR #40 的单例） | 该实现是"一个布尔给全站"，与"每角色独立"直接冲突；本批新写，不继承 |

---

## 3. 详细设计

### 3.1 状态模型

**存储**（localStorage，key 与结构）：

```jsonc
// key: "chatSimpleBg"   value: { "<character_id>": true, ... }
{
  "12": true,     // 角色 12 开了简约背景
  "37": false     // 显式关闭（与"从未设置过"等价，但保留写入便于将来做"重置"）
}
```

**为什么不用 PR #40 的 `useChatSettings` 单例**：那个实现把两个开关（简约背景、语音自动发送）合并进一个模块级单例，语义是"全局用户偏好"。本批只需**一个**按角色区分的布尔，写一个职责单一的 composable 更清楚（`useChatBg(characterId)`），也避免把"语音自动发送"这个与本主题无关的开关一起拖进来。

> **登记**：`useChatSettings` 单例与"语音自动发送"（Phase 3 spec §9 的 D6 已拍板默认关、作为设置项）**不在本批**。若日后要做，另行立项。

**读**：`ChatWindow` 挂载时按 `character_id` 读一次；**写**：切换时写回。跨标签页同步不做（YAGNI）。

### 3.2 组件与数据流

```
ChatWindow.vue                      ← 拥有 simpleBg 状态（每个会话一个实例，:key 重建）
├── 计算 stageClass / windowClass   → "chat-simple" 开关
├── 舞台（桌面）  .stage-blur / .stage-dim   → token 化后受 .chat-stage-root.chat-simple 作用
├── .chat-window  → 加 .chat-simple 类 + 注入 --cbg-* token
│   ├── WindowHeader.vue            ← 新增 ⚙ 弹层（开关落点）
│   │   ├── CharacterPhotoField.vue ← token 化（浅色下变深字）
│   │   ├── VoiceToggle.vue         ← token 化（+ SpeakerIcon 改 currentColor）
│   │   └── 收纳 ☰ / ✕ 的 token 化
│   ├── ChatHistory.vue             ← 示例问题、骨架、思考中气泡 token 化
│   │   └── Message.vue             ← 气泡、名字 pill、时间戳、日期胶囊、引用 chip、markdown token 化
│   └── InputField.vue              ← 输入区、麦克风/发送/停止、错误横幅 token 化
│       └── Microphone.vue          ← 语音栏容器 token 化
```

**所有权**：`simpleBg` 状态在 `ChatWindow`（唯一需要它的地方），**不**提到 `ChatIndex`。理由：`:key="friend.character.id"` 已保证切角色即重建，状态自然隔离；提到上层反而要处理"切换时旧值残留"。

### 3.3 色板与对比度（**全部数值已实算**，非估算）

浅色族（暖石白 `stone` 系）：

| 语义 | token | 值 | 用途 |
|------|-------|-----|------|
| 舞台底 | （**不立变量**，直接字面量 `#e7e5e4`） | `#e7e5e4` | 舞台纯色（替代模糊图 + 压暗）。实现在 `.chat-stage-root.stage-simple .stage-dim { background: #e7e5e4 }`——单值且只有一个消费者，**不声明 CSS 变量**（故计划里也没有 `--cbg-stage`，这是有意的） |
| 窗口底 | `--cbg-window` | `#fafaf9` | 角色之窗背景 |
| 气泡底（AI） | `--cbg-bubble-ai` | `#ffffff` | AI 消息气泡 |
| 气泡描边（AI） | `--cbg-bubble-ai-border` | `#e7e5e4` | 与窗口底区分（白底白窗时唯一分界） |
| 表面底（头部/输入/弹层） | `--cbg-surface` | `#ffffff` | 头部条、输入栏、设置弹层 |
| 表面描边 | `--cbg-surface-border` | `#e7e5e4` | 同上（浅色下必需，见 §3.5） |
| 浮层底（chip/pill/胶囊） | `--cbg-float` | `#f5f5f4` | 引用 chip、示例问题、日期胶囊 |
| 代码块 hover | `--cbg-code-block-hover` | 沉浸 `rgba(0,0,0,0.75)`（= 现状 `Message.vue:171` 原值）/ 简约 `rgba(28,25,23,0.14)` | 代码块复制按钮 hover（浅底上压深） |
| 浮层底（强调，名字 pill） | `--cbg-float-strong` | `#e7e5e4` | 名字 pill 底衬 |
| 主文字 | `--cbg-text` | `#1c1917` | 正文、名字、消息 |
| 次要文字 | `--cbg-text-2` | `#57534e` | 时间戳、日期胶囊、引用 chip、空态 introduction |
| 三级文字 | `--cbg-text-3` | `#78716c` | 占位符（`#ffffff` 底上 4.80:1 达标） |
| 悬停底 | `--cbg-hover` | `rgba(28,25,23,0.06)` | 图标按钮 hover（浅底上压深） |
| 开关轨道 OFF | `--cbg-switch-off` | 沉浸 `rgba(255,255,255,0.40)`（= 现状字面量）/ 简约 `#78716c`（= `--cbg-text-3`） | 设置弹层开关；简约态白滑块 vs 该轨道 **4.80:1** ✓ |
| 开关轨道 ON | `--cbg-switch-on` | 沉浸 `var(--accent)`（= 现状）/ 简约 `#0b825a`（= 用户气泡那枚 accent 70%+黑，色板内已有） | 白滑块 vs 该轨道 **4.82:1** ✓；**不得**用裸 `var(--accent)`（白滑块仅 2.54:1，低于 WCAG 1.4.11 的 3:1） |
| 头部胶囊底（0.50 那枚） | `--cbg-glass-btn` | 沉浸 `rgba(0,0,0,0.50)`（= `VoiceToggle`/`CharacterPhotoField` 现状字面量）/ 简约 `#f5f5f4` | 头部两个胶囊（语音开关、头像 pill）——**不得复用 `--cbg-float`(0.25)**，那是引用 chip 的值 |
| 头部胶囊 hover | `--cbg-glass-btn-hover` | 沉浸 `rgba(0,0,0,0.60)`（= `VoiceToggle` 现状 hover）/ 简约 `#e7e5e4` | 同上（头像 pill 现状无 hover，保持不变） |
| 引用浮层底 | `--cbg-modal-bg` | 沉浸 `rgba(23,23,23,0.95)`（= 现状 `bg-neutral-900/95`）/ 简约 `#ffffff` | 引用原文浮层面板——**不得复用 `--cbg-surface`(0.40)**，那会让面板从近乎实心变成 40% 玻璃 |
| 引用浮层描边 | `--cbg-modal-border` | 沉浸 `rgba(255,255,255,0.10)`（= 现状 `border-white/10`）/ 简约 `#e7e5e4` | 同上 |
| 骨架渐变（暗色） | `--cbg-skeleton-a` | 沉浸 `rgba(255,255,255,0.08)`（= 现状）；简约 `rgba(28,25,23,0.06)` | shimmer 三停点 `a → b → a` 的第 1、3 停点 |
| 骨架渐变（亮色） | `--cbg-skeleton-b` | 沉浸 `rgba(255,255,255,0.18)`（= 现状）；简约 `rgba(28,25,23,0.14)` | 同上的第 2 停点（沉浸=白系提亮、简约=黑系压深，与现状同构） |
| 代码底（行内） | `--cbg-code` | 沉浸 `rgba(0,0,0,0.40)`（= `Message.vue:151`）；简约 `rgba(28,25,23,0.06)` | 行内 `code` |
| 代码底（块） | `--cbg-code-block` | 沉浸 `rgba(0,0,0,0.45)`（= `Message.vue:152`）；简约 `rgba(28,25,23,0.08)` | `pre` 与复制按钮底 |
| 危险文字 | `--cbg-danger` | 沉浸 `#fca5a5`（= 现状 `text-red-300` 系）；简约 `#b91c1c` | 语音错误横幅 |
| 链接 | `--cbg-link` | 沉浸 `#7dd3fc`（= 现状 `Message.vue:155`）；简约 `#0f766e` | markdown 链接 |
| 表面底（次级） | `--cbg-surface-2` | 沉浸 `rgba(0,0,0,0.35)`（= 现状 `bg-black/35`）；简约 `#ffffff` | 输入栏、语音栏（与头部条 0.40 区分） |
| 弹层/窗口投影 | `--cbg-shadow` | 沉浸 `0 24px 64px rgba(0,0,0,0.45)`（= 现状）；简约 `0 24px 64px rgba(28,25,23,0.18)` | 窗口与弹层 |
| 焦点环 | `--cbg-ring` | 沉浸 `rgba(255,255,255,0.40)`（= 4A 的 `ring-white/40`，交接一致）；简约 `rgba(28,25,23,0.30)` | `focus-visible` 环 |
| 强调色本地绑定 | `--cbg-own-accent` | 两模式均 `var(--accent)` | **实现细节**：`1px` 与全局 accent 绑定，便于日后按角色覆盖（`.chat-icon-btn-active` 内部使用） |
| 开关滑块 | `--cbg-switch-knob` | 沉浸 `#ffffff`（= 现状）/ 简约 `#ffffff` | 设置弹层开关滑块（白滑块 vs 两种轨道分别 4.80 / 4.82:1，均 ≥3:1） |


**对比度实算结果**（WCAG 2.x，sRGB 分量空间合成）：

| 文字 | 底色 | 比值 | 要求 | 结论 |
|------|------|------|------|------|
| `#1c1917` 正文 | `#fafaf9` 窗口 | **16.74:1** | ≥4.5 | ✓ |
| `#1c1917` AI 正文 | `#ffffff` 气泡 | **17.49:1** | ≥4.5 | ✓ |
| `#57534e` 次要 | `#fafaf9` 窗口 | **7.30:1** | ≥3（次要）/ ≥4.5（正文） | ✓ 均满足 |
| `#78716c` 三级/占位 | `#ffffff` 输入底 | **4.80:1** | ≥3 | ✓ |
| `#1c1917` 名字 | `#e7e5e4` pill 底 | **13.93:1** | ≥4.5 | ✓ |
| `#44403c` 引用 chip 文字 | `#f5f5f4` chip 底 | **9.42:1** | ≥4.5 | ✓ |
| `#57534e` 时间戳 | `#fafaf9` 窗口 | **7.30:1** | ≥3 | ✓ |
| `#57534e` 引用 chip | `#f5f5f4` chip 底 | **6.99:1** | ≥4.5 | ✓（7.30 是它在窗口底上的值，chip 底更暗故略低；**评审实测更正**） |
| `#0b825a`（accent 70% + 黑）白字 | 用户气泡 | **4.82:1** | ≥4.5 | ✓（沿用现状，D4B-7） |

**最坏档 = 4.80:1（占位符）**，全部达标。**无需任何"档位阶梯"或运行时解析**——这是与前两版最大的复杂度差异：浅色下底色确定，色值可写死。

> **两处曾被写错的地方（留档，均为评审实测发现）**：
> 1. 初稿把引用 chip 的对比度写成「9.42:1，用 `#44403c` 档」。`9.42:1` 确是 `#44403c` 在 `#f5f5f4` 上的值，但设计选定的 token 是 `--cbg-text-2 = #57534e`——**数字必须与选定的 token 同源**。
> 2. 随后我把 `#57534e` 在 chip 底上的值写成 **7.30:1**，那实际是它在**窗口底 `#fafaf9`** 上的值；在 chip 底 `#f5f5f4` 上是 **6.99:1**（评审脚本复算，本机复现一致）。
>
> 两处都达标（≥4.5:1），结论不变：**chip 用 `--cbg-text-2`，不使用 `#44403c`**。留档的原因正是——上一轮两次翻车的根因是"数字与口径不同源"，本批再犯两次，必须记录。

> **口径声明**（吸取教训）：以上数值由 WCAG 相对亮度公式实算，alpha 合成为 **sRGB 分量空间线性混合**（CSS 语义）。**不是**线性亮度空间混合。上一轮曾两次搞错这个口径，本批所有数值均以公式输出为准。

### 3.4 token 架构（如何做到"零视觉回归"同时让浅色接管）

**做法：在 `.chat-window` 根节点定义一套 `--cbg-*` token，默认值 = 当前沉浸模式的**逐字原值**；`.chat-window.chat-simple` 覆盖为浅色值。** 所有子组件只写 `var(--cbg-*)`，不写死颜色。

```css
/* 沉浸模式（默认）：值 = 现状 main.css 逐字原值，确保零回归 */
.chat-window {
  --cbg-window: transparent;                       /* 现状：图铺满，无纯色底 */
  --cbg-bubble-ai: rgba(0, 0, 0, 0.35);
  --cbg-bubble-ai-border: transparent;
  --cbg-text: #ffffff;
  --cbg-text-2: rgba(255, 255, 255, 0.70);
  --cbg-text-3: rgba(255, 255, 255, 0.40);
  --cbg-surface: rgba(0, 0, 0, 0.40);
  --cbg-surface-border: transparent;
  --cbg-float: rgba(0, 0, 0, 0.25);
  --cbg-float-strong: rgba(0, 0, 0, 0.30);
  --cbg-hover: rgba(0, 0, 0, 0.20);
  --cbg-glass-btn: rgba(0, 0, 0, 0.50);
  --cbg-glass-btn-hover: rgba(0, 0, 0, 0.60);
  --cbg-modal-bg: rgba(23, 23, 23, 0.95);
  --cbg-modal-border: rgba(255, 255, 255, 0.10);
  --cbg-skeleton: rgba(255, 255, 255, 0.08);       /* 渐变三停点见实现（实施时拆 a/b 两停点，见计划 Task 2） */
  --cbg-ring: rgba(255, 255, 255, 0.40);
  --cbg-shadow: 0 24px 64px rgba(0, 0, 0, 0.45);
}

/* 简约模式（浅色） */
.chat-window.chat-simple {
  --cbg-window: #fafaf9;
  --cbg-bubble-ai: #ffffff;
  --cbg-bubble-ai-border: #e7e5e4;
  --cbg-text: #1c1917;
  --cbg-text-2: #57534e;
  --cbg-text-3: #78716c;
  --cbg-surface: #ffffff;
  --cbg-surface-border: #e7e5e4;
  --cbg-float: #f5f5f4;
  --cbg-float-strong: #e7e5e4;
  --cbg-hover: rgba(28, 25, 23, 0.06);
  --cbg-glass-btn: #f5f5f4;
  --cbg-glass-btn-hover: #e7e5e4;
  --cbg-modal-bg: #ffffff;
  --cbg-modal-border: #e7e5e4;
  --cbg-skeleton: rgba(28, 25, 23, 0.08);
  --cbg-ring: rgba(28, 25, 23, 0.30);
  --cbg-shadow: 0 24px 64px rgba(28, 25, 23, 0.18);
}
```

**舞台**同理，但作用域在窗口的**兄弟**节点上（`ChatWindow.vue:88-96`）：

```css
.chat-stage-root .stage-blur { /* 保持现状：图 + blur */ }
.chat-stage-root .stage-dim  { background: rgba(0, 0, 0, 0.35); }

.chat-stage-root.stage-simple .stage-blur { display: none; }        /* 不显示图 */
.chat-stage-root.stage-simple .stage-dim  { background: #e7e5e4; }  /* 纯色舞台 */
```

**为什么 CSS 变量能穿透 scoped 样式**：CSS 自定义属性**继承**，Scoped CSS 只加属性选择器、不隔离变量继承。`Message.vue` 等子组件在 scoped 规则里写 `var(--cbg-text)` 即可取到由 `.chat-window` 注入的值。**已验证该机制在本项目生效**：Phase 1 起 `.session-active` 就在用 `var(--accent)`（定义于 `:root`），而 `SessionItem.vue` 是 scoped 组件。

**为什么不用 Tailwind 任意值语法**（如 `text-[var(--cbg-text)]`）：可读性差、且 38 处替换后模板会更吵。统一进 `main.css` 的语义类（`.msg-bubble-ai` 等已存在），改动面更小。

**硬性约束一（CSS 层级）**：`main.css` 目前**完全不使用 `@layer`**（`grep -c "@layer" frontend/src/assets/main.css` → `0`），因此其中的自定义类处于**未分层**状态，能压过 Tailwind utilities——本批的 token 与语义类依赖这一机制。**实施时不得为了"整洁"给它们套 `@layer`**：一旦落到 `components` 层，就会被 utilities 层压过，浅色模式静默失效（评审的产物核对已确认现状：`@layer` 仅出现在 daisyUI/theme/properties，不含这些自定义类）。

**硬性约束二（零回归）**：token 化改造后，沉浸模式下的**每个**声明必须与改造前逐字等价。做法是逐个类对照 `git show master:frontend/src/assets/main.css` 校验；构建产物比对见 §6-断言 B8。

**一处必须补偿的盒模型变更**：浅色模式下 AI 气泡需要 `1px` 描边才能与窗口底（`#ffffff` vs `#fafaf9`）区分，而沉浸模式下该描边取 `transparent`。但**加边框会改变盒模型**——`.msg-bubble` 现为 `padding: 8px 12px`（`main.css:59-68`），加 `1px` 边框后气泡外尺寸宽高各 +2px，破坏"零视觉回归"。

**补偿方案**：`.msg-bubble` 统一加 `border: 1px solid transparent`，并把 `padding` 改为 `7px 11px`，使**外尺寸逐像素不变**。验收见 §6-断言 B6（截图对照）与 B8（产物核对）。

> 这是本批唯一需要动几何值的地方，**必须用截图逐项确认**，不得凭推理认为"应该没问题"。

**覆盖口径（R-4 机制性修复）**：本设计的"逐元素清单"（§3.5）按**文件**枚举，而不是按 token 正则统计。

原因：初稿用「Tailwind 工具类正则」统计硬编码，`Message.vue` 命中 6 处；但该文件 scoped `<style>` 里还有 4 处 `rgba()`/十六进制字面量（`第N段` span、`blockquote`、复制按钮、链接）**正则匹配不到，全部漏检**（评审 R-4 实测）。教训：**颜色字面量有两类写法，统计时必须双查**。

故 4B 计划新增一条机制性断言：对 6 个聊天窗口相关文件，扫描 **工具类 + CSS 颜色字面量** 双模式，任何未 token 化的残留即失败（白名单仅 `text-white`——己方气泡绿底白字两模式通用）。该断言把"漏检"从人工纪律变成自动化门禁。

### 3.5 组件级规格（浅色模式的逐项反转）

下表是"深玻璃 + 白字"→"浅面 + 深字"的完整清单。**沉浸列的现有实现不动**（走 §3.4 的默认 token）。

| 元素 | 现状（沉浸） | 简约模式 | 依据 |
|------|--------------|----------|------|
| 窗口背景 | 角色图 cover | `#fafaf9` 纯色 | D4B-1 |
| 窗口蒙层 `.window-scrim` | 渐变 `rgba(0,0,0,0.25→0.60)` | `display: none` | 无图即无承托需求 |
| 窗口阴影 | `0 24px 64px rgba(0,0,0,.45)` | `0 24px 64px rgba(28,25,23,.18)` | 浅底上重阴影显脏 |
| 舞台 | 模糊图 + `rgba(0,0,0,.35)` | `#e7e5e4` 纯色 | D4B-2 |
| 头部条 | `bg-black/40 backdrop-blur`（无边框） | `--cbg-surface` + `1px` `--cbg-surface-border` | 浅底上白条需描边才有边界（PR #37 评审 M3 同一结论） |
| 头部图标（☰/✕/⚙） | 透明（无托盘） | **`.chat-icon-btn-solid`**（与语音开关/头像 pill 同一托盘） | 验收反馈：同排「喇叭有底、齿轮没有」不协调；三个按钮统一为 0.50 胶囊族，观感一致（复审追加，详见 §3.5.2） |
| 头部图标（☰/✕） | `text-white`，hover `bg-black/20` | `--cbg-text`，hover `--cbg-hover` | |
| 语音开关 | `bg-black/50`（0.50），图标白，hover `bg-black/60` | `--cbg-glass-btn` + `--cbg-text`；hover `--cbg-glass-btn-hover` | 实现用 `.chat-icon-btn-solid` 一个类同时给底与字色。**不得**用 `--cbg-float`(0.25)：那会让胶囊暗度减半（评审 N5）；`SpeakerIcon` 改 `currentColor`（F10） |
| 设置弹层开关（轨道/滑块） | OFF 轨道 `rgba(255,255,255,0.40)`；ON 轨道 `var(--accent)`；滑块 `#ffffff` | OFF `--cbg-switch-off`；ON `--cbg-switch-on`；滑块 `--cbg-switch-knob`（`#ffffff`，两模式同值） | **简约态必须换色**：`#f5f5f4` 轨道贴在 `#ffffff` 头部上仅 **1.09:1**，OFF 状态几乎不可见（评审 R6-1 实算）；ON 态白滑块 vs 裸 accent 仅 **2.54:1**，低于 WCAG 1.4.11 的 3:1。改用 `#78716c` / `#0b825a` 后为 **4.80:1 / 4.82:1**。**沉浸态按零回归不变**（其白滑块 vs OFF 轨道 1.78:1 亦偏低，属既有观感，本批不动） |
| 头像 pill（`CharacterPhotoField`） | `bg-black/50`（0.50） | **`--cbg-glass-btn`**（0.50，保真） | **不得**用 `--cbg-float`(0.25)：会让头部件两个 0.50 胶囊同时变浅（评审 N5） |
| 名字 pill | `bg-black/30` + `white/70` | `--cbg-float-strong` + `--cbg-text` | 13.93:1 |
| AI 气泡 | `bg-black/35` + blur + 白字 | `--cbg-bubble-ai` + `1px` 描边 + `--cbg-text` | 白底白窗，靠描边分界 |
| 用户气泡 | `#0b825a` + 白字 | **不变**（同色同字） | 4.82:1 已达标；D4B-7 |
| 时间戳 / hover | `text-white/60` | `--cbg-text-2` | 7.30:1 |
| 日期胶囊 | `bg-black/25` + `white/60` | `--cbg-float` + `--cbg-text-2` | |
| 引用 chip | `bg-black/25` + `white/90` | `--cbg-float` + `--cbg-text-2` | 浮层底上 **6.99:1**（`#57534e` on `#f5f5f4`，实算）；标题的 0.90 → 0.70 属**归并**（见下方归并清单） |
| markdown 行内 code | `bg-black/.4` + 白字 | `rgba(28,25,23,0.06)` + `--cbg-text` | 浅底上"更深一点" |
| markdown `pre` | `bg-black/.45` | `rgba(28,25,23,0.08)` | 代码块底 |
| markdown 链接 | `#7dd3fc` | `#0f766e` | 深青，浅底上可读（与"深色底上亮青"同源的明度反转） |
| 输入栏 | `bg-black/35 backdrop-blur` + 白字 | `--cbg-surface` + `1px` 描边 + `--cbg-text` | |
| 输入占位符 | `white/40`（未显式设） | `--cbg-text-3`（4.80:1） | |
| 麦克风/发送键 | 白图标，未激活 `bg-neutral-700` | 图标 `--cbg-text`；未激活 `--cbg-hover`（`.chat-btn-idle`） | **激活态必须用 `.chat-icon-btn-active` 类**，不得在元素上写 `bg-[var(--accent)]`/`text-white` 工具类——未分层语义类会压掉 utilities，绿底会静默消失（评审 R-4） |
| 错误横幅（语音） | `text-red-300` | `#b91c1c` | 浅底上红字可读 |
| 骨架 shimmer | 白 8%→18% 渐变 | 深 8%→14% 渐变 | 浅底上压深 |
| 空态 introduction | `text-white/90` | `--cbg-text-2` | 7.30:1 |
| 示例问题胶囊 | `bg-black/25` + `white/90` | `--cbg-float` + `--cbg-text` + 描边 | |
| 思考中气泡 | 同 AI 气泡（白点） | 同 AI 气泡（深点） | `.thinking-dot` 用 `currentColor`（4A 已引入该类） |
| 引用浮层（`ChatWindow` 内 modal） | `bg-neutral-900/95` + `border-white/10` + 白字 | **`--cbg-modal-bg` + `--cbg-modal-border`** + `--cbg-text`/`--cbg-text-2` | 用专属 token 而**不是** `--cbg-surface`(0.40)：后者会让面板从近乎实心变成 40% 玻璃且失去描边（评审 N5） |
| `focus-visible` 环 | `ring-white/40`（**四处**：`ChatHistory`/`InputField`，加 4A 新增的 `VoiceToggle`/`CharacterPhotoField`；`.btn` 元素由 daisyUI 自带，不加） | `--cbg-ring`（同样只加在非 `.btn` 元素上；沉浸态 `rgba(255,255,255,0.40)` 与 `ring-white/40` 同色 → 零回归，简约态自动变深可见） | **必须 token 化**：保留字面量会让 4A 的无障碍收益在简约模式静默失效（评审 R3-2） |

#### 3.5.2 验收反馈修复（2026-09-14，B 端实测）

**① 简约模式下输入区图标几乎不可见** —— 根因是三个图标组件（`MicIcon`/`SendIcon`/`StopIcon`）
内部写死 `class="text-white"`，**压过**父级按钮 `.chat-icon-btn/.chat-btn-idle` 的 color token；
而 `text-white` 在颜色门禁的白名单里（依据是"己方气泡绿底白字"），**门禁因此放行**。

> 教训：白名单只对"它自己的适用场景"成立。同一类名在别处可能正是缺陷根源——门禁的
> 白名单机制天然有盲区，需配合"组件级行为断言"补位（已加 `iconColor.test.js` 四条）。

处置：三个图标去掉写死的 `text-white`（改继承父级 color）；`InputField` 的发送按钮
去掉无条件的 `text-white`（它压过 `.chat-btn-idle`）。简约模式下图标取 `--cbg-text-3`
深灰，可见。

**② 头部件图标托盘不一致** —— 语音开关与头像 pill 用 0.50 胶囊底，而 ☰/✕/⚙ 透明，
同排观感不协调。处置：三个按钮统一改用 `.chat-icon-btn-solid` + `chat-focus`。
- 沉浸模式：托盘同为 `rgba(0,0,0,0.50)`，与语音开关一致（**属有意变更**，非回归）
- 简约模式：托盘 `#f5f5f4`，与头像 pill 一致

#### 3.5.1 允许的观感归并清单（评审 N5 的处置）

`--cbg-*` 的沉浸默认值**大部分取自被替换元素的现状字面量**，因此是逐字等价；但有 **7 处文字不透明度**是"归并到已建立的档位"，**确实会改变沉浸模式的观感**。本版**明确采用归并**并逐条列出，作为门 4 截图对照的约定基线——**不让实施者遇到"文档让我改、验收说这是回归"**：

| 元素 | 现状（沉浸） | 计划值 | 变化 | 归并去向 |
|------|--------------|--------|------|----------|
| 时间戳（Message） | `text-white/60` | `--cbg-text-2` = 0.70 | +10% | 次要文字档 |
| 日期胶囊（`main.css`） | `white/60` | `--cbg-text-2` = 0.70 | +10% | 次要文字档 |
| chip「第N段」（Message:122） | `text-white/75` | `--cbg-text-2` = 0.70 | −5% | 次要文字档 |
| 引用浮层 关闭按钮 | `text-white/70` | `--cbg-text-2` = 0.70 | 不变 | 次要文字档 |
| 引用 chip 标题（Message:121） | `text-white/90` | `--cbg-text-2` = 0.70 | −20% | 次要文字档 |
| 空态 introduction（ChatHistory:186） | `text-white/90` | `--cbg-text-2` = 0.70 | −20% | 次要文字档 |
| 示例问题（ChatHistory:192） | `text-white/90` | `--cbg-text` = 1.00 | +10% | 主文字档（它本质是"可点的正文"） |
| 引用浮层面板（ChatWindow） | `text-white/90`（标题）、`/80`（正文） | `--cbg-text` / `--cbg-text-2` | +10% / −10% | 主/次要档 |

**为什么接受归并、而不是给每处"专属不透明度 token"**：
1. 7 处归并全部**落在已建立的文字档位**（主 1.00 / 次 0.70），是**语义正确**的——0.90/0.75 本身没有语义，`text-white/90` 与 `text-white/70` 在同一层级里并存是历史遗留；
2. 替代方案要为 0.90/0.80/0.75/0.60 各立一个 token，token 家族从 20 个膨胀到 26+ 个，且**每个只有一个消费者**，抽象收益为负；
3. **不引入新的达标风险**：归并**让已承认不达标的沉浸最坏情况再降约 0.2~0.5**（按本设计声明的 sRGB 分量口径实算：纯白背景图 + 顶部 0.25 蒙层下，时间戳/空态 introduction 由白 90% 的 **1.74:1** 降到白 70% 的 **1.55:1**；引用 chip 标题由 **2.92:1** 降到 **2.38:1**）——这属于 §0.3 已声明的范围（那里已登记"沉浸态白 70% 名字 pill = 2.63:1 ✗"），**不是本批新引入的不达标**；浅色模式的达标结论（§3.3）完全不受影响，因为简约模式无图、底色确定。**变暗而非变亮**，方向与既有取舍一致。

**明确保真、不归并的**（用专属 token，沉浸值 = 原字面量）：`VoiceToggle`/`CharacterPhotoField` 的 0.50 胶囊底（→ `--cbg-glass-btn`）、引用浮层面板的 `rgba(23,23,23,0.95)` 与 `border-white/10`（→ `--cbg-modal-bg`/`--cbg-modal-border`）。这三处是**成对/成块**的视觉构件，整体变浅会很显眼（评审 N5 的对照表里，它们正是"面板从实心变玻璃"那两行）。

**显式不改**：会话栏全部、NavBar、消息分组间距/字号/圆角、气泡 `max-width: 75%`、窗口 3:5 几何。

> **例外（唯一一处动几何）**：`.msg-bubble` 的 `padding: 8px 12px` → `7px 11px` + `border: 1px solid transparent`。原因是 AI 气泡在浅色下需要 1px 描边才能与窗口底区分，而加边框会撑大外尺寸。详见 §3.4 的"必须补偿的盒模型变更"。**外尺寸逐像素不变**，但这是本批唯一不能靠"值等价"证明、只能靠截图证明的一处。

### 3.6 设置弹层与异常场景

#### 弹层（D4B-4）

```
┌─ 头部条 ────────────────────────────────┐
│ [头像 名字]        ⚙  🔊  ✕             │   ⚙ = 新增入口
└──────────────────────────────────────────┘
                     ↓ 点击 ⚙
        ┌───────────────────────────────┐
        │  简约背景            ●───○     │   ← toggle switch
        │  仅对「龙安洋」生效             │   ← 每角色范围说明（D4B-3 的界面交代）
        ├───────────────────────────────┤
        │  （后续设置项的位置）           │   ← 占位说明，本期无第二项
        └───────────────────────────────┘
```

**要点：**

1. **「仅对『X』生效」这行是硬性要求** —— 上次被否的原因之一正是"全局偏好但界面未说明"。范围说明必须在界面上，不能只写在文档里。
2. 开关是原生 `<button role="switch" aria-checked>` 或 daisyUI `<input type="checkbox" class="toggle">`（实现时二选一，倾向后者：语义与键盘行为由原生提供）。若用 `<input>`，其外必须包 `<label>` 提供可访问名称。
3. 键盘：`Esc` 关闭；焦点进入弹层后 `Esc` 后焦点回到 ⚙。点击外部关闭。
4. 位置：`absolute` 定位于头部条下方右对齐，`z-40`（高于气泡与头部，低于引用浮层 `z-20`? —— **实现时统一层序并记入计划**：引用浮层当前是 `z-20`，弹层需在其下或上取决于是否可能同时出现；结论：弹层 `z-30`，点开弹层时若引用浮层正打开则先关引用浮层）。
5. 图标：`⚙` 用**内联 SVG**（不用 emoji 字形——PR #40 验收反馈：emoji 各平台形状不一）。

#### 异常与边界

| # | 场景 | 处理 |
|---|------|------|
| E1 | `localStorage` 不可用（隐私模式/被禁用） | `try/catch` 包裹读写，失败则退化为"内存态 + 默认关闭"，不抛错、不影响聊天 |
| E2 | `character.background_image` 为空 | **沉浸模式**：现状渲染 `url(undefined)`（F12）→ 改为 **`.no-bg` 兜底**：不渲染背景图与 `.window-scrim`，改用**深色底 + 白色文字**（即 `.no-bg` 覆盖 `--cbg-window: #1c1917` **且**把该子树内的 `--cbg-text/-2/-3` 一并覆写为白系——**否则沿用沉浸模式的 token 会在深底上得到深字**）。**简约模式**：本就无图，不受影响 |
| E3 | 图片加载失败（URL 有效但 404/超时） | 同 E2 走 `.no-bg` 兜底。**检测方式必须用 `new Image()` 预探测**：`error` 事件不会为 CSS `background-image` 触发，挂在 `<div>` 上的 `@error` 是死代码（评审 R-5 实测）。**组合态**：`.no-bg` 与 `.chat-simple` 可同时存在，CSS 源顺序让 `.chat-simple` 的浅色取胜（§3.4 有说明） |
| E4 | 切换角色 | `:key` 重建 → 新实例按新 `character_id` 读设置；**不会**继承上一个角色的状态 |
| E5 | 移动端 | 无舞台；窗口本身按简约 token 渲染（F7），其余逻辑一致 |
| E6 | 弹层打开时切换角色 | `:key` 重建会卸载弹层与其状态（关闭）——可接受，不需额外处理 |
| E7 | 简约模式下收到引用/长代码块/markdown | 全部走 §3.5 的 token，无特例 |


### 3.7 移动端抽屉遮罩随模式反转（用户裁决 2026-09-13 纳入）

**问题**：`ChatIndex.vue:119` 的移动端会话抽屉遮罩写死 `bg-black/50`。简约模式下舞台变浅（`#e7e5e4`），纯黑遮罩会显得突兀——整页唯一的深色块。

**改动**：遮罩是移动端独有的覆盖层（`lg:hidden` 语义），属简约模式的组成部分，故跟随模式：

```html
<!-- 移动端抽屉遮罩：沉浸=黑 50%（现状不变）；简约=暖深色 40% -->
<div class="absolute inset-0"
     :class="simpleBg ? 'bg-[#1c1917]/40' : 'bg-black/50'"
     @click="drawerOpen = false"></div>
```

**为什么用 `#1c1917`@40% 而不是纯黑**：浅色模式整体更轻，遮罩也应更轻；暖黑与浅色族的暖调同源。

**实算（本机脚本，与 §3.3 同一套公式）**：

| 遮罩 | 合成色（叠在舞台 `#e7e5e4` 上） | 与舞台底对比 |
|------|-------------------------------|--------------|
| 现状 `bg-black/50` | `#747272` | **3.81:1** |
| 简约 `#1c1917`@40% | `#969392` | **2.43:1** |
| 简约 `#1c1917`@35% | `#a09e9c` | 2.13:1 |

取 **40%**：与现状同为"明显可见的压暗"，但方向与色调都更轻。遮罩上无文字，故不涉及 WCAG 文字对比度门槛；此处数值用于保证"可见但不过重"。

**`simpleBg` 的可见性**：`ChatIndex.vue` 目前不持有该状态（它在 `ChatWindow` 内）。移动端抽屉与 ChatWindow 是兄弟节点，故需要把 `useChatBg(activeCharacterId)` 也在 `ChatIndex` 用一次——同一模块级单例，两处读到**同一状态**，不会出现不一致。

---

## 4. 文件清单

| 动作 | 文件 | 职责 |
|------|------|------|
| 新增 | `frontend/src/composables/useChatBg.js` | 按 `character_id` 读/写/切换（localStorage，`try/catch`） |
| 新增 | `frontend/src/composables/__tests__/useChatBg.test.js` | 存储读写、每角色隔离、响应性、容错（E1） |
| 新增 | `frontend/src/components/character/icons/SettingsIcon.vue` | ⚙ 内联 SVG（替换 emoji 字形） |
| 修改 | `frontend/src/assets/main.css` | `--cbg-*` token 家族 + `.chat-simple` / `.stage-simple` + `.chat-popover` |
| 修改 | `frontend/src/components/chat/chat_window/ChatWindow.vue` | 持有 `simpleBg`、渲染 `stage-simple`/`chat-simple`、引用浮层 token 化 |
| 修改 | `frontend/src/components/chat/chat_window/WindowHeader.vue` | ⚙ 入口 + 设置弹层（含范围说明、Esc/点外关闭、焦点管理）+ token 化 |
| 修改 | `frontend/src/components/character/chat_field/character_photo_field/CharacterPhotoField.vue` | token 化 |
| 修改 | `frontend/src/components/character/chat_field/VoiceToggle.vue` | token 化 |
| 修改 | `frontend/src/components/character/icons/SpeakerIcon.vue` | `text-white` → `currentColor`（F10） |
| 修改 | `frontend/src/components/character/chat_field/chat_history/ChatHistory.vue` | 骨架/空态/示例问题/思考中 token 化 |
| 修改 | `frontend/src/components/character/chat_field/chat_history/message/Message.vue` | 气泡/名字/时间戳/日期/引用/markdown token 化 |
| 修改 | `frontend/src/components/character/chat_field/input_field/InputField.vue` | 输入区/按钮/错误横幅 token 化 |
| 修改 | `frontend/src/components/character/chat_field/input_field/Microphone.vue` | 语音栏容器 token 化 |
| 修改 | `frontend/src/views/chat/ChatIndex.vue` | 移动端抽屉遮罩随模式反转（§3.7，用户裁决纳入） |

**后端零改动**。**会话栏与 NavBar 不改**（D4B-6）。

---

## 5. 测试与验证方案

### 5.1 自动化（本机）

| 命令 | 期望 |
|------|------|
| `cd frontend && npx vitest run` | 现有 65 与 4A 新增 10 不回归；本批新增 25 条：`useChatBg.test.js`（7）、`chatBgTokens.test.js`（**7**，含保真 token 机检）、`ChatWindow.test.js`（5）、`WindowHeader.test.js`（4）、`chatBgLiterals.test.js`（1，颜色字面量门禁）、`chatBgScrim.test.js`（1，抽屉遮罩）；合计 **100** |
| `cd frontend && npm run build` | exit 0 |
| 产物核对 | 构建产物 CSS 含 `--cbg-window` / `.chat-simple` / `.stage-simple` / `#fafaf9` / `#e7e5e4`；沉浸模式原有值（`rgba(0,0,0,.35)`、`blur(24px)`）**仍在** |

### 5.2 手工（云端验收，本机不起服务）

1. 打开 `/chat/:id/` → 默认沉浸模式，**与改动前逐像素一致**（对照 master 截图）
2. ⚙ → 打开弹层 → 看到「简约背景」与「仅对『角色名』生效」
3. 开启 → 窗口与舞台同时变浅、同色调；消息、时间戳、引用 chip、日期胶囊、输入框、占位符、空态、示例问题全部可读
4. **刷新页面 → 仍为简约**；切换到另一个角色 → **该角色仍是沉浸**（每角色独立的核心验证）
5. 回到第一个角色 → 简约仍开启
6. 发一条消息 → 流式、引用 chip、代码块、思考中三点在浅色下均正常
7. 键盘：Tab 到 ⚙ → Enter 打开 → Tab 到开关 → 空格切换 → Esc 关闭 → 焦点回 ⚙
8. 系统"减少动态效果" → 骨架与三点静止
9. 移动端（窄视口）：简约模式下窗口铺满且为浅色，无舞台残留

### 5.3 对比度核验（**可选但推荐**）

用浏览器 DevTools 取色器抽查 §3.3 表中 4 组关键组合，确认 ≥ 表中值。数值已在设计阶段实算，此处仅作落地确认。

---

## 6. 验收断言（可勾选）

| # | 断言 | 验证方式 |
|---|------|----------|
| B1 | 开启简约后，窗口与舞台**同色调**（浅色），舞台略深于窗口 | 手工 5.2-3 |
| B2 | 浅色下 §3.3 表中 8 组文字/底色对比度全部达标（最坏 4.80:1） | 设计期实算（§3.3）+ 手工抽查 5.3 |
| B3 | 开关**每角色独立**：A 角色开启不影响 B 角色；切回 A 仍开启 | 手工 5.2-4/5 |
| B4 | 刷新后状态保持（localStorage） | 手工 5.2-4 |
| B5 | 界面明确告知生效范围（「仅对『X』生效」） | 手工 5.2-2 |
| B6 | **沉浸模式零视觉回归**：与改动前逐像素一致 | 手工 5.2-1 + 产物核对 5.1 |
| B7 | ⚙ 弹层键盘完全可用（Tab/Enter/空格/Esc/焦点回归），可访问名称与状态齐备 | 手工 5.2-7 |
| B8 | 沉浸模式关键 CSS 值在构建产物中逐字保留（`rgba(0,0,0,.35)` / `blur(24px)` / `saturate(1.35)` / `.45` 阴影） | 产物核对 5.1 |
| B9 | 无背景图 / 图片加载失败时不出现破图或亮底白字（E2/E3） | 手工（造一个无背景图角色） |
| B10 | 现有前端单测不回归 | `npx vitest run` |
| B11 | 简约模式下移动端抽屉遮罩为暖深色 40%（非纯黑 50%），沉浸模式保持现状 | 手工（窄视口开抽屉）+ 源码核对 |

---

## 7. 范围边界（明确不做）

| 不做 | 归属 |
|------|------|
| 亮度自适应蒙层 / `--overlay-k` / canvas 采样 / 主色提取 | 已否决（§0.2） |
| 文字描边 `--msg-text-shadow` | 随 PR #40 作废 |
| 创建/编辑角色页的聊天效果预览、亮度提示 | 另一主题（创建流程） |
| 会话栏、NavBar 的配色改动 | D4B-6（它们本就是浅色） |
| 语音自动发送开关、`useChatSettings` 单例 | 与"每角色独立"冲突；另行立项（§3.1 已登记） |
| 深色简约 / 跟随系统深色 | 用户已选浅色 |
| 切换过渡动画 | D4B-8 |
| 会话列表最后消息预览（spec §11 可选项） | 后端增强，另一主题 |

---

## 8. 风险与回滚

| 风险 | 缓解 |
|------|------|
| **token 化改造破坏了沉浸模式**（最重的风险） | §3.4 硬性约束 + 断言 B8 产物逐字核对 + 截图对照 B6 |
| 38 处替换漏改某处，浅色下出现"白字白底" | §3.5 清单逐项对照 + 手工 5.2-3 覆盖全部元素 |
| 未达"整体观感"预期（第三次被否） | 本轮已把方向决策交给用户（§0.2 四项）；**云端验收时若仍不满意，回滚代价 = 一个分支**，master 不受污染 |
| `localStorage` 权限异常导致聊天页白屏 | E1 容错 + 单测 |
| 弹层层序与引用浮层冲突 | §3.6-4 明确层序策略，实现时写入计划并验证 |

**回滚**：纯前端，无迁移/数据/接口。`git revert` 分支或直接弃用分支即可（生产走 master 镜像）。

---

## 9. 待决问题与裁决结果（2026-09-13 已全部拍板）

| # | 问题 | 我的建议 |
|---|------|----------|
| Q-4B-1 | ~~① 会话栏是否跟着变？② 抽屉遮罩是否跟着变？~~ | ✅ **用户裁决（2026-09-13）：① 会话栏不动；② 抽屉遮罩纳入**（按 Agent 倾向）。具体值与实算见 §3.7 |
| Q-4B-2 | ~~E2/E3（无背景图 / 加载失败）是否纳入本批？~~ | ✅ **用户裁决（2026-09-13）：纳入**（本批必然碰到同一处代码路径） |
| Q-4B-3 | ~~窗口底色 `#fafaf9` vs spec 原文 `#f5f5f4`？~~ | ✅ **用户裁决（2026-09-13）：`#fafaf9`**（更接近"纯白"且保留暖调） |
| Q-4B-4 | ~~弹层里是否顺带做"语音自动发送"开关？~~ | ✅ **用户裁决（2026-09-13）：不做**（全局偏好与每角色偏好语义打架，另行立项） |
| Q-4B-5 | ~~移动端是否需要额外处理？~~ | ✅ **用户裁决（2026-09-13）：逻辑无需额外处理**，但**抽屉遮罩除外**——移动端独有的覆盖层，见 §3.7 |

---

## 10. 与既有文档的关系（实施时按此清单回写，**动手前先向你确认**）

| 文档 | 拟回写内容 |
|------|------------|
| `spec-for-llm.md` §6.1 | `--chat-bg` 行：`#f5f5f4`（浅色）/ `#1c1917`（深色跟随系统）→ 明确为**仅浅色**，删去"跟随系统"（与全站单一 light 主题矛盾） |
| `spec-for-llm.md` §6.6 | 补：生效范围为**每角色**；舞台由 `base-200` 改为 `#e7e5e4`（与本设计 §3.3 一致） |
| `spec-for-llm.md` §13-Phase 4 | 断言 1/3（自适应、创建页预览）标注"已砍，见 4B 设计 §0.2"；断言 2 补充"每角色" |
| `logic-design.md` §3.5 | 弹层内容增补"仅对『X』生效"一行 |
| `logic-design.md` §10 | Phase 4 表按本设计改写（4A/4B 两批） |

> 以上均为**事实变更回写**。契约 §4 要求：改既有文档前先列出"改哪几处、为什么"并获你同意 —— 故本清单在门 2 提请批准，实施时不擅自扩大。
