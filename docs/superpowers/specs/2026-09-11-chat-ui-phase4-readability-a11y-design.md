# 聊天界面改版 Phase 4 — 可读性修复与无障碍（2026-09-11）

> 状态：**门 1 已通过**；**门 2 方案评审修订 v2**（按 2026-09-11 两轴评审报告重导数值与论证）
> 定档：**L**（用户确认 2026-09-11）
> 上游：`2026-09-07-chat-ui-redesign-spec-for-llm.md`（spec）、`2026-09-07-chat-ui-redesign-logic-design.md`（LD）
> 前置：Phase 1（PR #34）/ Phase 2 + 后端批次（PR #35）/ Phase 3（PR #36）已合并 master；流程契约 PR #39 合并点 `7279335`
> 本文档产出：Phase 4 最终范围、七项用户决策、可读性修复方案与**修正后的实测依据**、明确砍掉项、文件清单

---

## 0. v1 → v2 修订说明（必读）

v1 版本文档的对比度计算使用了**错误的颜色空间**：把 CSS alpha 合成当成"亮度空间线性混合"来算。

**CSS 的 alpha 合成发生在 sRGB（gamma）分量空间**，正确做法是**先在 sRGB 分量空间混合，再线性化**求 WCAG 相对亮度。用错空间使 v1 的结论整体偏悲观约一倍：

| 场景 | v1（错，线性混合） | v2（对，sRGB 混合） |
|---|---|---|
| 纯白图·顶部 无描边 | 1.95:1 "基本不可读" | **4.16:1**（仅略低于 4.5） |
| 纯白图·中部 无描边 | 2.48:1 | **6.36:1 已达标** |
| 纯白图·底部 无描边 | 3.39:1 | **10.00:1 已达标** |
| 己方气泡 绿底白字 | 3.45:1 "不达标" | **4.85:1 已达标** |
| 蒙层 K=1.5 顶部 | "救不回来" | **5.61:1 达标** |
| 描边后 4 档 | 19.80/18.63/16.92/15.08 | **19.80 / 19.26 / 16.92 / 15.08** |

**连带作废的结论**：①"现状 2:1 基本不可读"被夸大（真实最坏 4.16:1）；②"单改蒙层或单改气泡都救不回来"**不成立**——两条路各自都能达标（见 §3.5）；③ v1 计划拟写回 spec 的"原文在数学上不成立"**撤回**——那是用错模型否定了一个可能正确的论断。

**未受影响的部分**：描边方案本身（不依赖图片亮度、不压暗构图、成本低）；用户决策；砍掉项范围；文件清单主体。

> 口径统一约定（全文适用）：`LinS(x)` = sRGB 分量 x（0~255）→ WCAG 相对亮度；alpha 合成一律在 sRGB 分量空间进行。

---

## 1. 背景：这一轮的目标被两个决定改写了

spec §13 的 Phase 4 原名"自适应与质感"，内容为：背景图亮度自适应蒙层、主色提取（accent）、用户降级开关、创建页预览、无障碍细节。

设计过程（2026-09-11）中产生两个用户决策，使自适应那部分整体失去必要性：

1. **颜色固定**：用户否决"界面主色随角色背景图变化"。理由：换一个好友按钮就换一次颜色、整个页面一直在变色，观感混乱不稳定。accent 固定为现有绿色 `#10b981`，己方气泡 / 发送键 / 会话栏选中行三处一致。
2. **可读性问题改由文字描边解决**：最坏情况（纯白背景图顶部）白字对比度为 4.16:1，略低于 4.5:1 标线。描边方案与图片亮度完全解耦，且不压暗创作者构图（见 §3）。

**因此 Phase 4 的目标改写为**：用固定的视觉语言保证任意背景图下文字可读，并补齐无障碍缺陷。

---

## 2. 用户决策（决策记录）

| # | 决策 | 结论 | 理由 |
|---|------|------|------|
| P4-D1 | 界面主色 | **固定 `#10b981`，不做背景图主色提取**；己方气泡、发送键、会话栏选中行三处同色 | 用户："不要随意改变颜色，不然感觉很乱" |
| P4-D2 | 创建页"聊天效果预览" | **不做**；同步回写 spec §13 Phase 4 断言 3 为"本期不做" | 用户："先不做了" |
| P4-D3 | 己方气泡对比度 | **不修复**（v2 修订） | v1 基于错误的 3.45:1 判定其不达标而拟加描边；**v2 实测为 4.85:1，本就达标**，无需任何改动 |
| P4-D4 | 无障碍 | **键盘可达性修复与 reduced-motion 都做**（用户："如果不复杂的话可以都做"）。经核查，`<div>` → `<button>` 属**功能缺陷**（键盘用户当前完全不可达），非细节 | — |
| P4-D5 | 审核文档归档 | 评审记录归位 `reviews/`；仅碰评审文档 | — |
| P4-D6 | **C2 条款裁决**（v2 新增） | **认可"确定性深色文字描边"等效满足 C2**；C2 表述回写为"确定性深色承托（蒙层或文字描边）" | 描边色彩固定、与图片内容完全无关，其"确定性"强于蒙层（蒙层的浓度收益恰是受图亮度影响的）。用户 2026-09-11 拍板"按你觉得更好的方案来" |
| P4-D7 | 定档 | **L 档** | 源码文件 12 个（> M 的 ≤5），跨 utils / composables / 全局 CSS / 组件 / 文档多层 |

> 流程附记：PR #39（流程契约）已由用户于 2026-09-11 合并（`7279335`），即门 3 已通过。契约未写明"合并动作 = 门 3 结论"，属契约措辞缺口，**不在本轮修改**，已登记为长期待办。

---

## 3. 可读性修复方案（本轮核心）

### 3.1 现状实测（sRGB 合成口径，问题确认）

**合成链**：背景图 sRGB 分量 →（窗口渐变蒙层 `rgba(0,0,0,0.25→0.60)`）→ 蒙层后底色 →（AI 气泡 `rgba(0,0,0,0.35)`）→ 气泡底色 → 白字。

纯白背景图（sRGB 255）在各高度的气泡底色与白字对比度：

| 位置 | 蒙层浓度 | 气泡底 sRGB | 白字对比度 | 判定 |
|------|---------|------------|-----------|------|
| 顶部（渐变起点） | 0.25 | 124.31 | **4.16:1** | 略低于 4.5 |
| 中部 | 0.425 | 95.31 | 6.36:1 | 达标 |
| 底部（渐变终点） | 0.60 | 66.30 | 10.00:1 | 达标 |

**结论（v2 修正）**：问题**没有 v1 描述的那么严重**，且**只集中在窗口顶部**——白字在纯白图顶部为 4.16:1，差 0.34 到标线；窗口中部以下早已达标。深色背景图无问题。

**采样口径说明**：上表"顶部/底部"取的是渐变**端点**（0% / 100% 处）。窗口头部条占 56px，消息区实际从更靠下的位置开始，对比度高于表中"顶部"值——即 4.16:1 是**偏保守**的下界。

### 3.2 方案：文字描边

```css
--msg-text-shadow:
  0 0 1px rgba(0, 0, 0, .85),    /* 实心圈：紧贴字形 */
  0 0 2px rgba(0, 0, 0, .55),
  0 1px 2px rgba(0, 0, 0, .45);  /* 最外层柔和下落影 */
```

- 气泡底色、不透明度、圆角、内边距、布局**全部不变**
- 落在 `.msg-markdown` 与 `.msg-markdown-plain`（文字容器），不是气泡容器
- 适用对象：**仅 AI 气泡**（己方气泡 4.85:1 已达标，见 P4-D3）

**为什么它比"加深蒙层"更符合约束**：描边色彩固定，与背景图内容**完全解耦**；而蒙层的浓度收益取决于图有多亮——正是 spec C2 所警惕的"依赖图片本身"。因此 ≥ C2 所要求的确定性。

### 3.3 描边后的对比度（sRGB 口径）

描边像素 = 底色 × (1 − 0.85) = 底色 × 0.15（sRGB 分量空间）：

| 描边之下的底色 sRGB | 场景 | 描边 sRGB | 白字 vs 描边像素 | 判定 |
|---|---|---|---|---|
| 0.260 | 气泡本色（中灰图中部） | 9.94 | 19.80:1 | 达标 |
| 0.375 | 纯白图 + 蒙层 0.25 + 气泡 0.35（最坏实际） | 14.34 | 19.26:1 | 达标 |
| 0.750 | 纯白图 + 蒙层 0.25，气泡全透明 | 28.69 | 16.92:1 | 达标 |
| 1.000 | 纯白 + 零蒙层（理论极限） | 38.25 | 15.08:1 | 达标 |

### 3.4 措辞边界（重要，防止过度声称）

**描边不改变 WCAG 意义上的对比度。** WCAG 2.x 量的是**文字色 vs 其声明背景色**的比值；`text-shadow` 的光圈是渲染层效果，不构成"背景色"。因此：

- 白字 vs AI 气泡底（纯白图顶部）**仍然记为 4.16:1**，不因加描边而变成 15:1
- 描边的作用是**感知层面的可读性改善**（压掉文字周围的高频亮度起伏，使字形边缘稳定）
- 因此**不得**把"加描边后对比度达标"写进 spec。spec 的 4.5:1 若要严格满足，须走 §3.5 的乙或丙

本节措辞经 2026-09-11 评审指出后确立，与 P4-D6 的 C2 裁决配套：C2 认可的是"确定性深色承托"，不宣称 WCAG 数值达标。

### 3.5 若日后要严格满足 4.5:1（备选，本期不做）

本轮选描边，代价是窗口顶部停在 4.16:1。若日后要求严格的 4.5:1，两条路都成立（v2 修正：v1 曾错误声称"单改任一项都救不回来"）：

| 选项 | 动作 | 结果 |
|---|---|---|
| 乙 | 窗口蒙层顶部由 `0.25` 加深至 `0.375`（K=1.5，在 spec §6.5 允许上限内） | 顶部 5.61:1；代价是背景图上半部分压暗 |
| 丙 | AI 气泡由 `rgba(0,0,0,.35)` 提到 `.45` | 顶部 5.47:1；代价是气泡玻璃感减弱、趋向实心 |

### 3.6 例外：代码块的处理

`pre` 代码块自带 `rgba(0,0,0,.45)` 深色底，叠描边会显脏 → `text-shadow: none`。

**行内 `code` 保留描边** —— 这一处**偏离 spec §3.4 的字面要求**（原文要求 `pre` 与 `code` 都排除），理由：行内 `code` 背景仅 `rgba(0,0,0,.4)`，叠加在气泡上后最亮处 ≈0.29（sRGB），白字约 3.06:1，**去掉描边会让行内代码成为气泡里最难读的部分**。该偏离登记于 W8。

---

## 4. 明确砍掉（防蔓延，含理由备查）

| 砍掉项 | 原属 | 理由 | spec 影响 |
|---|---|---|---|
| 亮度采样（`new Image` + 16×16 canvas + `crossOrigin` + `seq` 竞态令牌） | spec §6.5 / LD §3.10 | 描边已提供与图无关的确定性承托 | §6.5、§13 断言 1 |
| 蒙层浓度自适应 `--overlay-k` | spec §6.1/§6.3/§13 | 同上；蒙层保持固定 0.25→0.60 | §13 断言 1 |
| 主色提取 `dominantColor` + `accentFallback` | spec §6.1/§6.5 | P4-D1：颜色固定 | §6.1 `--accent` 行 |
| 三档对比度阶梯 `resolveUserBubble` | spec §6.1 / LD §8.2 | 己方气泡是固定不透明色且**已达标**（4.85:1） | §6.1 `--bubble-user` 行 |
| 创建页聊天效果预览 + 亮度提示 | spec §13 断言 3 | P4-D2 | §13 断言 3 |
| **背景图加载失败的自适应回退**（E2 的 `K=1.0` 分支） | spec §11 E2 | 随 §6.5 一并砍掉；**但 E2 条款本身保留**，改由 §5.4 的静态深色兜底承接 | §11 E2 |

---

## 5. 实施口径

### 5.1 简约背景开关（spec C3 硬要求：用户降级通道）

- 入口：`WindowHeader` 的 ⚙ 设置弹层；状态在 `useChatSettings`（**模块级单例**，照 `useVoiceToggle.js:4` / LD D-L7），localStorage key `chatSimpleBg`
- 开启后：窗口背景由角色背景图 → 纯色 `#1c1917`；舞台同步转深（`#0c0a09`）
- **只做深色版，不做浅色版**：spec §6.6 提到浅色（`#f5f5f4`）与"跟随系统"，但浅色底会使玻璃头部条（`bg-black/40 backdrop-blur`）、名字 pill、日期胶囊、引用 chips、快捷问题按钮等一批"白字系"元素集体失效，需连带重做。用户已确认只做深色
- **气泡处置**：spec §6.6 要求简约模式下气泡改常规 daisyUI 对比色（AI=`base-200`）。本设计**不采纳**——深色底 + 白字 15.5:1 已远超标线，改气泡反而破坏与沉浸模式的一致性。登记于 W6
- **入口样式**：spec §6.6 描述为"月亮/减淡图标 + tooltip"；本设计改为**规整的 ⚙ 设置弹层**（两个开关并列，LD §3.5 / Q6 已拍板该落点）。登记于 W6

### 5.2 语音自动发送开关（Phase 3 遗留）

- 同一 ⚙ 弹层；localStorage key `chatAutoSendVoice`；**默认关**（spec D6）
- 行为：语音识别完成 → 回填 textarea → **800ms 后自动发送**
- 实现：`InputField` 内 watch 语音状态机的 `transcribing → confirm` 转换起定时器，回调 `handleSend()`；**不新增对外接口**
- 取消条件：该窗口内点 🎤 重录（`confirm → listening`）、组件卸载（切换会话）
- ASR 空文本走 `asr_failed`，不进入 `confirm`，不会被自动发送

### 5.3 无障碍

**5.3.1 两个 `<div>` 改为真 `<button>`（功能缺陷修复，必须项）**

| 文件 | 现状 | 问题 | 改后 |
|---|---|---|---|
| `VoiceToggle.vue` | `<div class="... cursor-pointer" @click="toggle">` | 非可聚焦元素：键盘用户 Tab 不到，无法开关语音 | `<button type="button" aria-label="…">`，保留现有 class |
| `CharacterPhotoField.vue` | `<div class="... cursor-pointer" @click>` + `<img alt="">` | 同上：无法打开角色详情；头像无替代文本 | `<button type="button" aria-label="查看角色详情">` + `:alt="\`${character.name}的头像\`"` |

写法沿用 `InputField` 麦克风按钮既有模式（纯 Tailwind + `focus-visible:ring-2 ring-white/40`），**不使用 daisyUI 的 `btn` 类**。两个组件均仅被 `WindowHeader` 引用（已 grep 核实）。

**5.3.2 `prefers-reduced-motion` 补漏**

现状覆盖：`Microphone.vue` 已处理（Phase 3）。遗漏两处：

1. `.skeleton-shimmer`（`main.css` 自绘，会话列表骨架 + 聊天记录骨架共用）→ `animation: none` 即可，**方案有效**
2. **思考中指示器**：`ChatHistory.vue:205` 用的是 daisyUI `<span class="loading loading-dots loading-sm">`

> **daisyUI 的 `loading-*` 无法用 CSS 停掉**（已核实 `frontend/node_modules/daisyui/components/loading.css` 5.5.17）：其动画是 `mask-image` 内嵌 SVG 里的 **SMIL**（`<animateTransform>` / `<animate>`），该文件内**没有任何 CSS animation / @keyframes / ::before / ::after**，全站构建产物里出现的 `prefers-reduced-motion` 来自 daisyUI 其他组件（skeleton / tooltip / carousel 等），**与 loading 无关**。
>
> 处理：把 ChatHistory 的思考中指示器**换为项目自绘的三点**（三个 `<span>` + 自有 `@keyframes`），使其可被 `prefers-reduced-motion` 停掉。
>
> 范围限定：全站另有 7 处 `loading-spinner`（ChatIndex / FriendIndex / CharacterDetail / DocumentCard / UploadZone / HomepageIndex / SpaceIndex）属同一机制，**本轮不处理**，登记为长期待办；因此本轮 reduced-motion 的断言口径**只覆盖"骨架 + 聊天页思考中指示"**，不声称覆盖全站。

### 5.4 背景图缺失/加载失败兜底（E2 承接）

E2 原文依赖已砍掉的 `useBackgroundAdaptive`。本设计承接方式：

- 角色无背景图（`background_image` 为空）或图片加载失败 → 窗口背景与舞台**直接按简约模式的深色渲染**（`#1c1917` / `#0c0a09`）
- 实现：`ChatWindow` 判断 `friend.character.background_image` 为空即走简约分支；图片加载失败用 `<img @error>` 兜底（实施计划中确定具体写法）
- 该承接登记于 W7

---

## 6. 文档收拾（P4-D5）

- `docs/superpowers/specs/2026-09-07-chat-ui-redesign-review.md` → 移入 `docs/superpowers/reviews/`
- `docs/superpowers/reviews/` 下两份未跟踪的历史评审记录 → 纳入版本控制：
  - `2026-06-28-pr31-docker-compose-review.md`
  - `2026-08-19-deployment-registry-refactor-spec-review.md`
- **范围限定**：仅评审文档。工作区另有 `.codegraph/.gitignore` 改动与 8 条 `.superpowers/brainstorm/**` 删除记录，与本轮无关，不动

---

## 7. 回写清单（spec + LD）

### 7.1 spec 回写（`2026-09-07-chat-ui-redesign-spec-for-llm.md`）

| # | 位置 | 变更 |
|---|------|------|
| W1 | §13 Phase 4 断言 3（创建页预览） | 标"本期不做（P4-D2）" |
| W2 | §13 Phase 4 断言 1（`overlayK` 公式单测） | 标"不做（P4-D1 + §3 描边方案）"，改由描边的确定性承托保证可读性 |
| W3 | §6.5 整节（亮度自适应算法） | 加作废声明，保留为未来备选；并注明"若日后要严格满足 4.5:1，见 design §3.5 的乙/丙" |
| W4 | §11 E3 **+ §6.1 `--bubble-ai` 行 + §12 对比度条目 + §13 Phase 1 断言 7** 四处同源论断 | **更正为 sRGB 口径实测值**（顶部 4.16:1 / 中部 6.36:1 / 底部 10.00:1）；撤回 v1 曾拟写的"原文数学上不成立"，改为"原文断言在顶部位置缺少余量，需确定性承托补足" |
| W5 | §13 Phase 4 断言 2 / 4 | 保留为必做；新增断言 5（键盘可达性） |
| W6 | §6.6（简约背景模式）+ §6.1 `--chat-bg` 行 | 登记实施偏离：只做深色版；气泡不改 daisyUI 对比色；入口改为 ⚙ 弹层 |
| W7 | §11 E2（背景图加载失败） | 承接方式改为 §5.4 的静态深色兜底（原依赖已砍模块的 `K=1.0` 回退作废） |
| W8 | §5.3 Message「引用」条目的代码块处置 | 登记偏离：仅 `pre` 排除描边，行内 `code` 保留（理由见 §3.6） |
| W9 | §2 C2 条款 | 表述改为"确定性深色承托（蒙层或文字描边）"（P4-D6 用户裁决） |

### 7.2 LD 回写（`2026-09-07-chat-ui-redesign-logic-design.md`）

v1 遗漏：LD 完全未回写，导致两份文档对已砍内容相互矛盾。补：

| # | 位置 | 变更 |
|---|------|------|
| L1 | LD §3.10（`useBackgroundAdaptive` 契约）、§8.2（`resolveUserBubble` / `--user-bubble-bg`） | 加"本期不实施"标注 |
| L2 | LD §10「Phase 4」表（含创建页预览） | 同步改写为本文档 §5 的实际范围 |
| L3 | LD §3.5（WindowHeader 契约：props 含 `simpleBackground`、emits 含 `toggleSimple`/`toggleAutoSend`） | 标注实施偏离：改为组件内直接使用 `useChatSettings()` 单例（单例下 props 传递是冗余的，且 LD D-L7 本就要求共享单例） |
| L4 | LD §13 决策表 Q6 | 补注"入口已由 ⚙ 弹层实现，与简约背景并列" |

---

## 8. 文件清单

源码 12 个 + 文档 3 类：

| 动作 | 文件 | 内容 |
|------|------|------|
| 新增 | `frontend/src/utils/contrast.js` | sRGB 空间合成 + WCAG 相对亮度/对比度纯函数 |
| 新增 | `frontend/src/utils/__tests__/contrast.test.js` | 锁定 §3.1/§3.3 全部数值 |
| 新增 | `frontend/src/composables/useChatSettings.js` | **模块级单例**：`simpleBackground` / `autoSendVoice` + localStorage |
| 新增 | `frontend/src/composables/__tests__/useChatSettings.test.js` | 默认值与持久化 |
| 改 | `frontend/src/assets/main.css` | 描边变量；`.skeleton-shimmer` 的 reduced-motion |
| 改 | `frontend/src/components/character/chat_field/chat_history/message/Message.vue` | 文字容器挂描边；代码块排除描边 |
| 改 | `frontend/src/components/character/chat_field/chat_history/ChatHistory.vue` | 思考中指示器换自绘三点（可被 reduce 停掉） |
| 改 | `frontend/src/components/chat/chat_window/ChatWindow.vue` | 简约背景分支 + 背景图缺失兜底 |
| 改 | `frontend/src/components/chat/chat_window/WindowHeader.vue` | ⚙ 设置弹层（两个开关） |
| 改 | `frontend/src/components/character/chat_field/VoiceToggle.vue` | `<div>` → `<button>` |
| 改 | `frontend/src/components/character/chat_field/character_photo_field/CharacterPhotoField.vue` | `<div>` → `<button>` + `alt` |
| 改 | `frontend/src/components/character/chat_field/input_field/InputField.vue` | 语音自动发送 800ms 定时器 |
| 改 | `docs/superpowers/specs/2026-09-07-chat-ui-redesign-spec-for-llm.md` | §7.1 的 W1~W9 |
| 改 | `docs/superpowers/specs/2026-09-07-chat-ui-redesign-logic-design.md` | §7.2 的 L1~L4 |
| 迁移/提交 | `docs/superpowers/specs|reviews/…review.md` 共 3 份 | §6 的归档整理 |

---

## 9. 验收断言（门 4 用）

**可自动化**

1. `npm run test:unit` 全绿，`contrast.test.js` 覆盖 §3.1/§3.3 全部档位
2. 后端 221 测试不受影响（本轮零后端改动）

**需人工**

3. 纯白/高亮背景图：AI 消息文字清晰（对照 master；注意实测差异是 4.16:1 vs 4.5，**肉眼差异有限，重点看字形边缘是否稳定**）
4. 深色背景图：文字清晰，且背景观感未被压死
5. 键盘 Tab：能聚焦语音开关、角色详情按钮、麦克风、发送键，Enter/空格可触发
6. ⚙ 弹层两个开关即时生效、刷新后保持
7. 语音自动发送开启后：识别回填后约 0.8 秒自动发出；期间点 🎤 重录则不发送
8. 系统开启"减少动态效果"：**骨架**与**聊天页思考中三点**静止（不声称覆盖全站 loading-spinner）
9. markdown：`pre` 代码块无描边、深色底正常、复制按钮可用；行内 `code` **有**描边（v2 有意为之，见 §3.6）
10. 无背景图的角色：窗口与舞台呈深色（§5.4 兜底），文字可读

---

## 10. 定档

**L 档**（用户 2026-09-11 确认）：源码 12 个文件，跨 utils / composables / 全局 CSS / 组件 / 文档多层，含一轮视觉与键盘人工验收。

门禁：①brainstorming ✅ → ②writing-plans ✅（**待门 2 方案批准**）→ ③用户人工评审 → ④verification-before-completion。
