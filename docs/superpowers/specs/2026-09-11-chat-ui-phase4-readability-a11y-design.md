# 聊天界面改版 Phase 4 — 可读性修复与无障碍（2026-09-11）

> 状态：**已评审通过（门 1）**，待门 2 出实施计划
> 上游：`2026-09-07-chat-ui-redesign-spec-for-llm.md`（spec）、`2026-09-07-chat-ui-redesign-logic-design.md`（LD）
> 前置：Phase 1（PR #34）/ Phase 2 + 后端批次（PR #35）/ Phase 3（PR #36）均已合并 master
> 本文档产出：Phase 4 的最终范围、三项用户决策、可读性修复方案与实测依据、明确砍掉项及理由、文件清单

---

## 1. 背景：这一轮的目标被两个决定改写了

spec §13 的 Phase 4 原名"自适应与质感"，内容为：背景图亮度自适应蒙层、主色提取（accent）、用户降级开关、创建页预览、无障碍细节。

设计过程（2026-09-11）中产生两个用户决策，使自适应那部分整体失去必要性：

1. **颜色固定**：用户否决"界面主色随角色背景图变化"。理由：换一个好友按钮就换一次颜色、整个页面一直在变色，观感混乱不稳定。accent 固定为现有绿色 `#10b981`，己方气泡 / 发送键 / 会话栏选中行三处一致。
2. **可读性问题另有所属**：实测发现真正的可读性缺陷不是"蒙层不够深"，而是**文字没有描边**（见 §3）。而描边方案不依赖背景亮度，于是"亮度采样 → 动态算蒙层浓度"这条链整体不需要了。

**因此 Phase 4 的目标改写为**：用固定的视觉语言（不变的颜色 + 文字描边 + 深色纯色降级背景），保证任意背景图下文字可读，并补齐无障碍缺陷。

---

## 2. 三项用户决策（决策记录）

| # | 决策 | 结论 | 理由 |
|---|------|------|------|
| P4-D1 | 界面主色 | **固定 `#10b981`，不做背景图主色提取**；己方气泡、发送键、会话栏选中行三处同色 | 用户："不要随意改变颜色，不然感觉很乱" |
| P4-D2 | 创建页"聊天效果预览" | **不做**；同步回写 spec §13 Phase 4 断言 3 为"本期不做" | 用户："先不做了"。可读性已由描边兜底，预览的"救火"价值消失 |
| P4-D3 | 己方气泡对比度 | **加同款深色文字描边，气泡颜色不动** | 用户选"颜色一点都不动"。当前绿底白字 3.45:1 低于 4.5，但补描边后白字对比度达标且绿色保持原样 |

补充决策（本文档追加，已获用户确认）：

| # | 决策 | 结论 |
|---|------|------|
| P4-D4 | 无障碍两件事 | **都做**（用户："如果不复杂的话可以都做"）。且经核查后，5.1 修 `<div>` → `<button>` 由"细节"升格为**功能缺陷修复**（键盘用户当前无法触及） |
| P4-D5 | 审核文档归档 | 评审记录归位 `reviews/`；仅碰评审文档，工作区其他杂物不动 |

> 流程附记：PR #39（流程契约）已由用户于 2026-09-11 合并（`7279335`），即门 3 已通过。契约未写明"合并动作 = 门 3 结论"，属契约措辞缺口，**不在本轮修改**，已登记为长期待办。

---

## 3. 可读性修复方案（本轮核心）

### 3.1 现状实测（问题确认）

合成链：背景图亮度 →（窗口渐变蒙层 `rgba(0,0,0,.25)`→`.60`）→ 蒙层后底色 →（AI 气泡 `rgba(0,0,0,.35)`）→ 气泡底色 → 白字。

| 背景图亮度 | 位置 | 气泡底色亮度 | 白字对比度 | 判定 |
|-----------|------|-------------|-----------|------|
| 1.0（纯白） | 顶部 25% | 0.488 | **1.95:1** | 不达标 |
| 1.0 | 中部 50% | 0.374 | **2.48:1** | 不达标 |
| 1.0 | 底部 75% | 0.260 | **3.39:1** | 偏低 |
| 0.7（中灰） | 顶部 25% | 0.341 | **2.68:1** | 不达标 |
| 0.4（深图） | 底部 75% | 0.104 | 6.82:1 | 达标 |

**结论**：背景图偏亮时，AI 消息是"浅灰半透明气泡上的白字"，2:1 左右，基本不可读；越靠窗口上方越差（蒙层顶部最薄）。

**spec 的断言不成立**：spec §11 E3 称"亮度自适应蒙层（§6.5）+ 深色 AI 气泡（R2）共同保证正文 ≥4.5:1"。该数值关系经计算不成立——**单改任一项都救不回来**：

- 只加深气泡（蒙层不动）：需气泡不透明度约 **0.77**（现状 0.35），已非玻璃气泡而是纯黑药丸；
- 只加深蒙层（气泡不动）：需顶部蒙层约 **0.57**（现状 0.25），背景图上半部分基本不可见，直接违背 C1（尊重创作者构图）。

### 3.2 方案：文字描边（不依赖背景亮度）

```css
/* AI 气泡与己方气泡共用同一套 */
text-shadow: 0 0 1px rgba(0, 0, 0, .85),    /* 实心圈：紧贴字形，构成"紧邻背景" */
             0 0 2px rgba(0, 0, 0, .55),
             0 1px 2px rgba(0, 0, 0, .45);  /* 最外层柔和下落影 */
```

- 气泡底色、不透明度、圆角、内边距、布局**全部不变**
- 己方气泡颜色 `color-mix(in srgb, #10b981 70%, black)` **不变**
- 落地位置：`.msg-markdown` 与 `.msg-markdown-plain`（文字容器），不是气泡容器

**为什么它比"加深蒙层"可靠**：描边自身即深色，成为文字紧邻的背景，**不依赖其下垫层有多亮**。

### 3.3 压力测试（含现实中不存在的极限）

| 描边之下的底色亮度 | 场景 | 白字 vs 描边像素 | 判定 |
|---|---|---|---|
| 0.260 | 气泡本色（中灰图中部） | 19.80:1 | 达标 |
| 0.375 | 纯白图 + 蒙层 0.25 + 气泡 0.35（最坏实际） | 18.63:1 | 达标 |
| 0.750 | 纯白图 + 蒙层 0.25，气泡全透明 | 16.92:1 | 达标 |
| 1.000 | 纯白 + 零蒙层（理论极限） | 15.08:1 | 达标 |

对比度按 WCAG 相对亮度公式计算（相对亮度函数 `L`，比值 `(1.05)/(L+0.05)`）。**三档模糊层叠加后的保守值 9.88:1** 仍远超 4.5:1 标线。

### 3.4 例外：代码块不参与描边

markdown 渲染的 `pre` / `code` 自带深色底（`rgba(0,0,0,.45)` / `.40`），再叠描边会显脏。处理：对 `.msg-markdown :deep(pre)`、`:deep(code)` 显式 `text-shadow: none`（`none` 是绝对重置，可覆盖继承值）。

---

## 4. 明确砍掉（防蔓延，含理由备查）

| 砍掉项 | 原属 | 理由 | spec 影响 |
|---|---|---|---|
| 亮度采样（`new Image` + 16×16 canvas + `crossOrigin` + `seq` 竞态令牌） | spec §6.5 / LD §3.10 | 描边已独立解决可读性 | §6.5 整节、§13 断言 1 |
| 蒙层浓度自适应 `--overlay-k` | spec §6.1/§6.3/§13 | 同上；蒙层保持固定 0.25→0.60 | §13 断言 1 |
| 主色提取 `dominantColor` + `accentFallback` | spec §6.1/§6.5 | P4-D1：颜色固定 | §6.1 `--accent` 行 |
| 三档对比度阶梯 `resolveUserBubble` | spec §6.1 / LD §8.2 | 己方气泡是固定不透明色，无需按 accent 解析 | §6.1 `--bubble-user` 行 |
| 创建页聊天效果预览 + 亮度提示 | spec §13 断言 3 | P4-D2 | §13 断言 3 |
| `main.css` 中 3 处"Phase 4 落地后…"过时注释 | — | 避免后人照此实施 | — |

**副产物**：本轮新增文件从原计划的 4 个降至 3 个（对比度纯函数 + 其单测 + 用户设置 composable），改动主体为 CSS 与模板。

---

## 5. 三项开关/修复的实施口径

### 5.1 简约背景开关（spec C3 硬要求：用户降级通道）

- 入口：`WindowHeader` 的 ⚙ 设置弹层；状态在 `useChatSettings`（模块级单例，仿 `useVoiceToggle`），localStorage key `chatSimpleBg`
- 开启后：窗口背景由角色背景图 → 纯色 `#1c1917`；舞台同步转深
- **只做深色版，不做浅色版**：浅色底会使玻璃头部条（`bg-black/40 backdrop-blur`）、名字 pill、日期胶囊、引用 chips 等一批"白字系"元素集体失效，需连带重做，与"用户降级兜底"的收益不成比例。深色底可让现有全部元素继续成立
- 气泡与描边不变 → 从"图上看字"变为"纯深底看字"

### 5.2 语音自动发送开关（Phase 3 遗留）

- 同一 ⚙ 弹层；localStorage key `chatAutoSendVoice`；**默认关**（spec D6）
- 行为：语音识别完成 → 回填 textarea → **800ms 后自动发送**
- 实现：`InputField` 内部 watch 语音状态机的 `transcribing → confirm` 转换起定时器，回调 `handleSend(message.value)`；**不新增任何对外接口**（Phase 3 清理 `closeMic` 时特意留下的内部钩子）
- 该窗口期内用户点 🎤 重录（`confirm → listening`）或卸载组件 → 定时器取消
- ASR 空文本走 `asr_failed`，不进入 `confirm`，不会被自动发送

### 5.3 无障碍

**5.3.1 两个 `<div>` 改为真 `<button>`（功能缺陷修复，必须项）**

| 文件 | 现状 | 问题 | 改后 |
|---|---|---|---|
| `VoiceToggle.vue` | `<div class="... cursor-pointer" @click="toggle">` | 非可聚焦元素：键盘用户 Tab 不到，无法开关语音 | `<button type="button" aria-label="语音开关">`，保留现有 class |
| `CharacterPhotoField.vue` | `<div class="... cursor-pointer" @click>` + `<img alt="">` | 同上：键盘用户无法打开角色详情；头像无替代文本 | `<button type="button" aria-label="查看角色详情">` + `:alt="character.name"` |

写法沿用 `InputField` 麦克风按钮既有模式（纯 Tailwind + `focus-visible:ring-2 ring-white/40`），**不使用 daisyUI 的 `btn` 类**，避免预设样式与现有尺寸类冲突。两个组件均仅被 `WindowHeader` 引用（已 grep 核实），影响面受控。

**5.3.2 `prefers-reduced-motion` 补漏**

现状覆盖：`Microphone.vue` 已处理（Phase 3）；`ChatHistory.vue`、`SessionList.vue`、`main.css` 未处理。

补：`.skeleton-shimmer`（会话列表骨架 + 聊天记录骨架共用，定义在 `main.css`）、思考中三点跳动，在 reduce 下 `animation: none`。

---

## 6. 文档收拾（P4-D5）

- `docs/superpowers/specs/2026-09-07-chat-ui-redesign-review.md` → 移入 `docs/superpowers/reviews/`（评审记录归位；该文件原被误放在 `specs/`）
- `docs/superpowers/reviews/` 下两份未跟踪的历史评审记录 → 纳入版本控制：
  - `2026-06-28-pr31-docker-compose-review.md`
  - `2026-08-19-deployment-registry-refactor-spec-review.md`
- **范围限定**：仅评审文档。工作区另有 `.codegraph/.gitignore` 改动与 8 条 `.superpowers/brainstorm/**` 删除记录，与本轮无关，不动

---

## 7. 回写 spec 的"事实变更"清单

同一个 PR 内回写 `2026-09-07-chat-ui-redesign-spec-for-llm.md`，并在该文件末尾登记变更理由：

| # | 位置 | 变更 |
|---|------|------|
| W1 | §13 Phase 4 断言 3（创建页预览） | 标注"本期不做（P4-D2）" |
| W2 | §13 Phase 4 断言 1（`overlayK` 公式值单测） | 标注"不做（P4-D1 + 本文档 §3 描边方案），对比度改由文字描边保证"，附本轮实测数字 |
| W3 | §6.5 亮度自适应算法整节 | 标注"本期不实施"，保留作为未来备选 |
| W4 | §11 E3 的错误论断（"蒙层 + 深色气泡共同保证 ≥4.5:1"） | 更正为实测结论 + 描边方案 |
| W5 | §13 Phase 4 断言 2（简约模式）/ 断言 4（aria-label + reduced-motion） | **保留为必做**（本轮 5.1 / 5.3 覆盖） |

---

## 8. 文件清单（11 个）

| 动作 | 文件 | 内容 |
|------|------|------|
| 新增 | `frontend/src/utils/contrast.js` | WCAG 相对亮度与对比度比值纯函数（供单测锁定 §3.3 数值） |
| 新增 | `frontend/src/utils/__tests__/contrast.test.js` | 把 §3.3 压力测试表写成断言 |
| 新增 | `frontend/src/composables/useChatSettings.js` | `simpleBackground` / `autoSendVoice` 两个 ref + localStorage 持久化 |
| 改 | `frontend/src/assets/main.css` | 描边类；`.skeleton-shimmer` 的 reduced-motion；清理 3 处过时注释 |
| 改 | `frontend/src/components/character/chat_field/chat_history/message/Message.vue` | 代码块 `text-shadow: none` |
| 改 | `frontend/src/components/character/chat_field/input_field/InputField.vue` | 自动发送 800ms 定时器；思考中三点 reduced-motion |
| 改 | `frontend/src/components/chat/chat_window/WindowHeader.vue` | ⚙ 设置弹层（两个开关）+ 无障碍 |
| 改 | `frontend/src/components/chat/chat_window/ChatWindow.vue` | 简约模式背景分支 |
| 改 | `frontend/src/components/character/chat_field/VoiceToggle.vue` | `<div>` → `<button>` |
| 改 | `frontend/src/components/character/chat_field/character_photo_field/CharacterPhotoField.vue` | `<div>` → `<button>` + `alt` |
| 改 | `docs/superpowers/specs/2026-09-07-chat-ui-redesign-spec-for-llm.md` | §7 的 W1~W5 回写 |

文档类改动另计：本设计文档、实施计划文档、§6 的评审文档归位与补提交。

---

## 9. 验收断言（门 4 用）

**可自动化**

1. `npm run test:unit` 全绿，且新增 `contrast.test.js` 覆盖 §3.3 全部数值档位
2. 后端 221 测试不受影响（本轮零后端改动）

**需人工**

3. 找一张**纯白或高亮**角色背景图：AI 消息与己方消息文字清晰可读（对照当前 master 的"几乎看不见"）
4. 找一张**深色**背景图：文字依旧清晰，且背景图观感未被蒙层压死（验证"没有加深蒙层"）
5. 键盘 Tab 遍历聊天页：能聚焦到语音开关、角色详情按钮、麦克风、发送键，Enter/空格可触发
6. ⚙ 弹层：简约背景开关切换即时生效，刷新后保持；语音自动发送开关切换后刷新保持
7. 语音自动发送开启后说一句话：识别文本回填后约 0.8 秒自动发出；期间点 🎤 重录则不发送
8. 系统开启"减少动态效果"后：骨架微光与思考中三点静止
9. markdown 代码块：文字无描边、深色底正常、复制按钮可用

---

## 10. 定档

**M 档**（11 文件，但新增逻辑仅 1 个纯函数 + 1 个定时器，主体为 CSS/模板；含一轮视觉与键盘人工验收）。

门禁：①brainstorming ✅ → ②writing-plans → ③用户人工评审 → ④verification-before-completion。**S 档免门路径不适用**（超过"单文件、≤30 行"门槛）。
