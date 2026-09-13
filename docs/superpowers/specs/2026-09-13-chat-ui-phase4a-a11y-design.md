# 聊天界面改版 Phase 4A —— 无障碍修复 · 设计文档

> 状态：**待门 1/门 2 批准**（2026-09-13 起草）
> 分级：**L**（跨 8 个前端文件 + 全局 CSS；含 1 项行为变更——对话区思考指示器换实现）
> 上游事实源：`2026-09-07-chat-ui-redesign-spec-for-llm.md` §12（无障碍硬性规格）、`2026-09-07-chat-ui-redesign-logic-design.md` §3.5
> 关联批次：`2026-09-13-chat-ui-phase4b-simple-background-design.md`（4B 在其后独立走门；两份**不合并交付**）
> 上一轮同类工作的处置：PR #37 / PR #40 **均被 owner 作废**，本文件为第三次起草，非延续。

---

## 0. 为什么有这一批

Phase 3 交付语音与输入后，聊天页留下了**三类与观感无关的真实缺陷**：键盘用户无法操作两个核心控件、图标按钮无可访问名称、`prefers-reduced-motion` 在对话区未生效。

它们**不改变任何颜色与布局**，因此不受"简约背景该是什么样"这一审美争议牵连 —— 上一次（PR #40）它们与深色简约背景捆在同一 PR 内一起被否，属于**连坐**。本批独立交付，正是为了把这个连坐关系切掉。

**本批不含任何视觉变更。** 若验收时发现观感有变，即视为回归缺陷。

---

## 1. 事实核查（实施前基线，均已在本机 master `7279335` 核实）

| # | 事实 | 证据 | 影响 |
|---|------|------|------|
| F1 | `VoiceToggle` 是 `<div @click>`，无 `tabindex`、无 `role`、无 `aria-label`，仅 `:title` | `frontend/src/components/character/chat_field/VoiceToggle.vue:7-12` | **键盘用户无法开关语音**（Tab 不到，Enter/空格无效） |
| F2 | `CharacterPhotoField` 是 `<div @click>`，内嵌 `<img alt="">`（空 alt） | `character_photo_field/CharacterPhotoField.vue:15-18` | **键盘用户无法打开角色详情**；头像无替代文本 |
| F3 | `UserMenu` 触发器是 `<div tabindex="0" role="button">`，**无 `aria-label`** | `components/navbar/UserMenu.vue:41` | 可聚焦但无可访问名称；读屏播报为空 |
| F4 | 对话区"思考中"用 daisyUI `<span class="loading loading-dots loading-sm">` | `chat_history/ChatHistory.vue:205` | **CSS 停不掉**：daisyUI 5.5.17 的 `.loading-*` 是 `mask-image` 内嵌 SVG 的 SMIL 动画（`frontend/node_modules/daisyui/components/loading.css`，文件内无 `animation`/`@keyframes`/`::before`/`::after`）。SMIL 不响应 `prefers-reduced-motion` |
| F5 | 语音栏的六个小点**已**受 `preferReduced` 控制 | `input_field/Microphone.vue:25`（`matchMedia`）、`:266-289`（`animate-pulse-dot` 条件绑定） | 这部分**已达标**，本批不重复处理，仅作回归基线 |
| F6 | 波形高度在 reduce 时固定为 8px | `Microphone.vue:159` | 已达标，同上 |
| F7 | 骨架 shimmer **未**受 reduce 控制 | `assets/main.css:110-118`（`.skeleton-shimmer` + `@keyframes shimmer`，无 `prefers-reduced-motion`） | 遗漏项，本批补齐 |
| F8 | 会话栏 `SessionItem` / `SessionList` 已是 `<button>` 或 `RouterLink` | `components/chat/SessionItem.vue`、`SessionList.vue`（`aria-label` 齐备） | 已达标，不动 |
| F9 | 聊天页图标按钮（麦克风/发送/停止/☰/✕）均有 `aria-label` + `focus-visible:ring` | `InputField.vue:397,431,442`、`WindowHeader.vue` | 已达标，不动 |
| F10 | 全局仅有 2 处 `@keyframes`：`shimmer`（main.css）与 `pulse-dot`（Microphone.vue scoped） | `grep -rn "@keyframes" frontend/src` | 自定义动画可控，daisyUI 的不可控（F4） |

### 1.1 与 commit message 不符的历史欠账（登记）

`a9cd6b7` 的提交信息写「reduced-motion 覆盖三点动画（spec §12）」，但其 diff **只改了 `Microphone.vue` 的初始化/识别中小点**（`git show a9cd6b7 --stat` → 仅 `logic-design.md` + `Microphone.vue`）。对话区"思考中"三点（F4）从未被处理。

- 该 commit 已在 master（`git merge-base --is-ancestor a9cd6b7 master` → YES）
- **不追溯修改历史提交信息**；本批以 T4 补齐，并在下方验收断言 A4 中锁定

### 1.2 本批明确不碰的东西

| 项 | 归属 |
|---|---|
| 一切颜色、透明度、字体、间距、圆角 | 4B（若涉及） |
| `--msg-text-shadow` 文字描边 | **不采用**（PR #40 方案，随该 PR 一并作废） |
| 亮度自适应蒙层、canvas 采样、主色提取 | **不采用**（PR #37 方案，已作废） |
| 设置弹层（⚙）自身 | 不存在于 master —— 属 4B 的新增件 |
| `CharacterPhotoField` 名字 pill 的底衬/字号 | 4B 按浅色模式统一处理 |

> **F3 的边界**：`UserMenu` 属全站 NavBar，与聊天改版无关。之所以并入本批，是因为它是同一轮 aria 扫描发现的同类缺陷，且改动仅一行。若你希望严格限定在聊天页，可从本批删除（见 §8 待决 Q-4A-1）。

---

## 2. 决策记录

| # | 决策 | 来源 |
|---|------|------|
| D4A-1 | 键盘可达性优先于"看起来像不像按钮"：`<div @click>` 一律改真 `<button type="button">`，**不**用 `role="button"` + 手工键盘事件兜底 | 用户 2026-09-13 拍板范围 |
| D4A-2 | 可访问名称用 `aria-label`；已有的 `:title` / `data-tip` 保留（tooltip 是视觉提示，不替代名称） | 同上 |
| D4A-3 | reduced-motion 只覆盖**我们自己可控**的动画。daisyUI 内部 SMIL 不试图用 CSS 关闭，改为**替换实现**（F4 → `loading-dots` 换成自绘三点） | 同上 |
| D4A-4 | 本批**零视觉变更**：改 `div`→`button` 必须保持原尺寸/间距/圆角/悬停观感逐像素一致 | 用户 2026-09-13：「拆两批，4A 无障碍 → 4B 简约背景」 |
| D4A-5 | 不引入依赖（不装 `axe-core`、不装 `eslint-plugin-vuejs-accessibility`）；验证靠真实浏览器键盘走查 + 产物核对 | YAGNI；项目当前无前端 lint 链 |

### 2.1 已否决的替代方案

| 方案 | 否决理由 |
|------|----------|
| 用 `role="button"` + `@keydown.enter/space` 保留 `div` | 语义与行为都要手写（含空格键的 `keyup` 触发约定），且丢失原生 `disabled`/`type` 语义；改真按钮成本更低 |
| 保留 `loading-dots`，用 CSS 覆盖其 SMIL | **物理上不可能**（F4）；SMIL 不受 CSS 控制 |
| 引入 `eslint-plugin-vuejs-accessibility` 做静态检查 | 项目无前端 lint 链，为 3 处修复引入整套工具链不划算；且静态规则查不出"SMIL 停不掉"这类问题 |
| 顺手统一全站按钮的 `aria-label` | 超出 4A 边界（原则），且会让 PR 变大、评审焦点模糊 |

---

## 3. 详细设计

### 3.1 `VoiceToggle` → 真按钮（T1）

**改动前**（`VoiceToggle.vue:6-12`）：

```html
<div class="h-10 w-10 rounded-full bg-black/50 flex items-center justify-center
            cursor-pointer hover:bg-black/60 transition-colors shrink-0"
     :title="voiceEnabled ? '语音已开启' : '语音已关闭'"
     @click="toggle">
  <SpeakerIcon :enabled="voiceEnabled" />
</div>
```

**改动后**：

```html
<button type="button"
        class="h-10 w-10 rounded-full bg-black/50 flex items-center justify-center
               cursor-pointer hover:bg-black/60 transition-colors shrink-0
               focus-visible:ring-2 ring-white/40 outline-none"
        :title="voiceEnabled ? '语音已开启' : '语音已关闭'"
        :aria-label="voiceEnabled ? '关闭语音播报' : '开启语音播报'"
        :aria-pressed="voiceEnabled"
        @click="toggle">
  <SpeakerIcon :enabled="voiceEnabled" />
</button>
```

**要点：**

1. `h-10 w-10` 显式尺寸保留 —— `<button>` 的默认 `box-sizing`/`padding` 会改变布局，显式类名可避免（D4A-4）。
2. `:aria-pressed` 暴露开关状态：这是**切换按钮**（toggle），`aria-pressed` 是正确语义，胜过把状态塞进 label。label 保持"动作导向"（"开启/关闭语音播报"）而非状态导向。
3. `focus-visible:ring-2 ring-white/40 outline-none` 与同区其它按钮（☰/✕）一致 —— 项目既有约定。
4. **`<button>` 默认 `line-height` 与字体继承**：Tailwind 的 preflight 已将 `button` 的 `font`/`line-height` 设为继承，`SpeakerIcon` 是固定 `w-5 h-5` 的 SVG，不受影响。已核实 `frontend/node_modules/tailwindcss` preflight 规则存在。
5. **不加 `disabled`**：语音开关任何时刻都可用。

> **反向依赖提示**：`SpeakerIcon.vue` 内部写死 `class="w-5 h-5 text-white"`（开启态）与 `text-white/40`（关闭态）。4B 切浅色时必须改这里（已登记在 4B 文档 §4 的清单内），4A **不动**。

### 3.2 `CharacterPhotoField` → 真按钮（T2）

**改动前**（`CharacterPhotoField.vue:15-24`）：`<div class="h-10 w-fit rounded-full bg-black/50 ..." @click>`，内含 `<img :src="character.photo" alt="">`。

**改动后**：

```html
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
```

**要点：**

1. `w-fit` 保留：按钮宽度仍由内容（头像 + 名字）决定，与现状一致。
2. `:alt` 用角色名 —— 头像**不是**装饰图（它是"这是哪个角色"的识别线索），故不设 `alt=""`。
3. 内部 `<div>` 保留（`.avatar` 是 daisyUI 组件类，层级不动，避免布局回归）。
4. **`<button>` 内不得嵌套交互元素** —— 已核实内部无按钮/链接（`CharacterDetail` 是独立 Teleport/modal 组件，不在按钮内）。若日后有人在 pill 内加次级按钮，需拆分结构（写入代码注释）。
5. `break-all` 保留 —— 微调它属观感范畴，划归 4B。

### 3.3 `UserMenu` 触发器补可访问名称（T3）

**改动**（`UserMenu.vue:41`，一行）：

```html
<!-- before -->
<div tabindex="0" role="button" class="avatar btn btn-circle w-10 h-10 mr-6">
<!-- after -->
<div tabindex="0" role="button" class="avatar btn btn-circle w-10 h-10 mr-6"
     aria-label="用户菜单">
```

**要点：**

1. **只补 `aria-label`，不改成 `<button>`** —— 该元素依赖 daisyUI `dropdown` 的 `tabindex="0"` + `:focus-within` 展开机制（`.dropdown:focus-within .dropdown-content`）。换成 `<button>` 会改变焦点模型，风险大于收益，且超出聊天改版边界。
2. 内部 `<img alt="avatar">` 是英文占位 —— **本批不改**（属全站文案统一，另议）。

### 3.4 对话区思考指示器换自绘三点（T4，本批唯一行为变更）

**问题**：daisyUI `loading-dots` 的动画在 `mask-image` 内嵌 SVG 里，是 SMIL，**CSS 无法停止**，也不响应 `prefers-reduced-motion`（F4）。这意味着开启系统"减少动态效果"的用户，对话区仍会看到永动动画。

**方案**：换成三个自绘 `<span>` + 全局 CSS 动画，与 `Microphone.vue` 既有 `animate-pulse-dot` 同构（已在用、已被 `preferReduced` 覆盖，见 F5/F6 —— 复用既有模式，不发明新机制）。

`ChatHistory.vue` 模板（替换 `:203-206`）：

```html
<!-- 思考中指示（首 token 前）：自绘三点——daisyUI loading-dots 是 SMIL，停不掉（见 4A 设计 F4） -->
<div v-if="thinking" class="flex justify-start my-2">
  <div class="msg-bubble msg-bubble-ai flex items-center gap-1">
    <span class="thinking-dot"></span>
    <span class="thinking-dot"></span>
    <span class="thinking-dot"></span>
  </div>
</div>
```

`frontend/src/assets/main.css` 追加：

```css
/* 思考中三点（4A：替换 daisyUI loading-dots——其动画是内嵌 SVG 的 SMIL，CSS 停不掉） */
.thinking-dot {
  width: 4px;
  height: 4px;
  border-radius: 9999px;
  background: rgba(255, 255, 255, 0.7);
  animation: thinking-bounce 1.2s ease-in-out infinite;
}
.thinking-dot:nth-child(2) { animation-delay: 0.2s; }
.thinking-dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes thinking-bounce {
  0%, 60%, 100% { opacity: 0.35; transform: translateY(0); }
  30%           { opacity: 1;    transform: translateY(-3px); }
}

/* 4A：全局动画的 reduce 兜底（骨架 shimmer 与思考三点） */
@media (prefers-reduced-motion: reduce) {
  .thinking-dot { animation: none; opacity: 0.6; }
  .skeleton-shimmer { animation: none; }
}
```

**要点（尺寸与观感对齐，D4A-4）：**

1. daisyUI `loading-sm` 的点约 4px、间距由 `gap-1`（4px）给出 —— 上述实现与之一致，**肉眼尺寸不变**。
2. 颜色：daisyUI `loading` 默认继承 `currentColor`，在 AI 气泡（白字）内即白色；故取 `rgba(255,255,255,0.7)` 作为基线，与呼吸感相符。
3. `reduce` 时三点静态显示（`opacity: 0.6`）—— **保留"进行中"的信息**，只是不动。这是 spec §12「三点动画降为静态」的字面要求，不是"隐藏"。
4. `.skeleton-shimmer` 的 reduce 覆盖补在**同一 media query** 内（F7 遗漏项）。
5. `Microphone.vue` 的 `animate-pulse-dot` / `pulse-dot` 已在作者组件内处理（F5/F6），**本文不动**，避免同一机制两个真相源。

> **验收提示**：`loading-dots` 是 daisyUI 组件类，删除后 `ChatHistory.vue` 不再引用它。构建产物中 `.loading` 相关规则仍会存在（daisyUI 全局生成），故**不能用"产物里没有 loading"当验收**；必须核对 `thinking-dot` 存在且模板不再含 `loading-dots`（见 §6 断言 A4）。

---

## 4. 文件清单

| 动作 | 文件 | 职责 |
|------|------|------|
| 修改 | `frontend/src/components/character/chat_field/VoiceToggle.vue` | 真按钮 + `aria-pressed`（§3.1） |
| 修改 | `frontend/src/components/character/chat_field/character_photo_field/CharacterPhotoField.vue` | 真按钮 + `aria-label` + `alt`（§3.2） |
| 修改 | `frontend/src/components/navbar/UserMenu.vue` | 触发器 `aria-label`（§3.3，一行） |
| 修改 | `frontend/src/components/character/chat_field/chat_history/ChatHistory.vue` | 思考指示器换自绘三点（§3.4） |
| 修改 | `frontend/src/assets/main.css` | `.thinking-dot` + `thinking-bounce` + reduce 块（§3.4） |
| 新增 | `frontend/src/utils/__tests__/a11yMarkers.test.js` | 产物级断言：模板/样式的关键标记存在（见 §6 断言 A1~A5 的可自动化部分） |

**不改动**：`InputField.vue`、`WindowHeader.vue`、`SessionList.vue`、`SessionItem.vue`、`ChatWindow.vue`、`Microphone.vue`（均已达标或属 4B）。

**后端零改动**（本批纯前端）。

---

## 5. 测试与验证方案

### 5.1 自动化（本机，可写"通过"）

| 命令 | 期望 |
|------|------|
| `cd frontend && npx vitest run` | 现有 **65 passed** 不回归；新增 `a11yMarkers.test.js` 全绿 |
| `cd frontend && npm run build` | exit 0；产物含 `thinking-dot`，**不含** `loading-dots` |

`a11yMarkers.test.js` 的定位说明：本批改动多为**模板语义**，用 jsdom 挂载整树成本高且易脆。因此该测试文件锁定的是**可静态断言的事实**——例如"三个 `.thinking-dot` 元素渲染"（此条值得真挂载）、"`thinking-bounce` 与 `prefers-reduced-motion` 同时出现在 main.css"。**键盘可达性无法自动化**（见 5.2），不得用该测试冒充。

### 5.2 手工（必须做，云端；本机不起服务）

1. 打开 `/chat/:id/`，**只用键盘** Tab 走查顺序：`NavBar 用户菜单 → 头像 pill → 语音开关 → ☰（移动端）→ ✕ → 消息区 → 输入框 → 麦克风 → 发送`
2. 在语音开关上按 **Enter** 与 **空格** → 语音图标状态切换（两种键都必须生效）
3. 在头像 pill 上按 Enter → 角色详情弹窗打开
4. 开启系统"减少动态效果" → 发一条消息 → 三点**静止显示**（保留可见，不跳动）；骨架屏同理静止
5. 浏览器无障碍面板 / 读屏：语音开关、头像 pill、用户菜单均可读出名称与状态

### 5.3 回归（防观感漂移，D4A-4）

对同一角色，**改动前后各截一张头部件与思考中态**，逐项比对：胶囊尺寸、间距、圆角、悬停底色、图标大小。**必须一致**；任何差异都算本批回归。

---

## 6. 验收断言（可勾选，每条都有验证方式）

| # | 断言 | 验证方式 |
|---|------|----------|
| A1 | 语音开关纯净键盘可达：Tab 可聚焦、Enter 与空格均可切换 | 手工 5.2-1/2 |
| A2 | 头像 pill 纯净键盘可达，Enter 打开详情 | 手工 5.2-1/3 |
| A3 | 语音开关与头像 pill 的可访问名称非空且含角色名/动作语义；用户菜单可读出"用户菜单" | 手工 5.2-5 + 源码 |
| A4 | `prefers-reduced-motion: reduce` 下，对话区三点与骨架**静止但可见** | 手工 5.2-4；产物含 `thinking-dot` 且模板无 `loading-dots`（自动） |
| A5 | 三个控件改动后尺寸/位置/悬停观感与改动前逐像素一致 | 手工 5.3 |
| A6 | 现有 65 个前端单测不回归 | `npx vitest run` |

---

## 7. 风险与回滚

| 风险 | 缓解 |
|------|------|
| `div`→`button` 引入布局偏移（默认 `padding`/`border`/`line-height`） | Tailwind preflight 已归零；显式尺寸类保留；验收 A5 逐像素比对 |
| `<button>` 在 `flex` 容器内基线对齐与 `div` 不同 | 两处父容器均为 `flex items-center`，非基线对齐；手工走查确认 |
| 换掉 `loading-dots` 后三点动画观感与 daisyUI 不同 | 尺寸/间距/颜色对齐（§3.4）；如观感不符，回滚即恢复一行模板 |
| `UserMenu` 属全站组件，改动外溢 | 仅加 `aria-label`，不动结构与焦点模型 |

**回滚**：本批 5 个文件改动均可单文件 revert；无迁移、无数据、无接口变更。

---

## 8. 待决问题（开工前需要你确认）

| # | 问题 | 我的建议 |
|---|------|----------|
| Q-4A-1 | `UserMenu`（全站 NavBar）是否并入本批？ | **并入**。同类缺陷、一行改动；但若你要求严格限定聊天页，我删除 T3 |
| Q-4A-2 | T4 换掉 daisyUI 三点属"行为变更"（动画曲线会与现在不同），是否接受？ | **接受**。现状在 reduce 下永动是硬缺陷；曲线差异肉眼极小 |
| Q-4A-3 | 是否顺带把 `<img alt="avatar">` 这类英文占位文案统一成中文？ | **不做**。属全站文案，另议 |

---

## 9. 与既有文档的关系（本次不改动任何既有文档）

| 文档 | 是否需要回写 |
|------|--------------|
| `spec-for-llm.md` §12 | **暂不回写**。本批实现的就是其字面要求（"三点动画降为静态"），无事实变更 |
| `logic-design.md` §3.5 | **暂不回写**。本批不动组件结构与暴露方法清单 |
| `WORKFLOW.md` | 不回写 |

> 若实施过程中发现既有文档存在**事实错误**（如 §1.1 那类 commit message 与实现不符），先向你列出"改哪几处、为什么"，获同意后再改（契约 §4）。
