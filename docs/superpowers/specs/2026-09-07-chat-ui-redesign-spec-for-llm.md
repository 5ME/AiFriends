# AI Friends 聊天界面改版设计规格（纯文本版，供文本型 LLM 阅读）

> 文档性质：**设计事实源（Design Source of Truth）**。本文档不依赖任何图片/截图，所有空间关系、尺寸、颜色、状态均以文字与数值精确描述。
> 下游用途：由无视觉能力的 LLM（deepseek-v4-pro）在此文档基础上进行整体逻辑、状态管理、组件契约、错误处理等架构设计。
> 配套文档：`2026-09-07-chat-ui-redesign-design.md`（同主题评审版，含讨论背景，可忽略重复内容，以本文档为准）。

---

## 0. 阅读指引

- 本文档第 1~2 节交代事实约束（现状代码事实 + 产品约束），第 3 节为已拍板决策。
- 第 4~13 节为完整设计规格：先布局（几何）、再组件契约、视觉 token、状态机、数据流、边界情况、无障碍。
- 第 14 节为分阶段实施与**可验证的验收断言**。
- 所有"必须/不得"为硬性规格；"建议"为非阻断性优化。

---

## 1. 现状代码事实（改造前基线）

1. **聊天载体**：`frontend/src/components/character/chat_field/ChatField.vue` 是一个 `<dialog class="modal">`，内含 `modal-box w-90 h-150`（360×600px，比例 3:5）。由 `Character.vue`（每张角色卡片）和 `CharacterDetail.vue` 各自内嵌实例化。
2. **内部布局**：`ChatField.vue` 内头部（`absolute left-3 top-3`）、历史列表（`absolute top-18 left-0 w-90 h-112`）、输入栏（`absolute bottom-4 left-2 h-12 w-86`）全部为绝对定位堆叠。
3. **背景图**：`ChatField.vue` 以 `style.backgroundImage = friend.character.background_image`（cover/center）铺满弹窗，无蒙层。
4. **头像条**：`character_photo_field/CharacterPhotoField.vue`（黑底 50% 圆形 pill：36px 头像 + 名字），点击可打开 `CharacterDetail` 弹窗（`mode="chat"`）。
5. **语音开关**：`VoiceToggle.vue`（40px 圆形，`bg-black/50`，切 `useVoiceToggle` 全局状态，仅 title tooltip）。
6. **历史加载**：`ChatHistory.vue` 用哨兵 + IntersectionObserver 上滑加载 `GET /api/friend/message/get_history/?last_message_id=&friend_id=`（每次 10 条，返回 `{id, user_message, output}`，按 id 倒序）。`handlePushFrontMessage` 把一条历史拆成 role=ai + role=user 两条推入前端数组。
7. **消息渲染**：`Message.vue`——每条消息都显示头像 + 名字 + 气泡；用户气泡 `chat-bubble-success`（daisyUI 绿）；AI 气泡默认 `chat-bubble`；文本 `whitespace-pre-wrap break-all`；RAG 引用以 `collapse` 手风琴展在气泡下方（`message.citations`）。
8. **输入**：`InputField.vue`——单行 `<input>` + `pr-20` 内绝对定位两个图标（发送、麦克风）；`handleSend` 先 push 用户消息 + 空 AI 消息，再 `POST /api/friend/message/chat/` SSE 流式（`@microsoft/fetch-event-source`）；`onmessage` 处理 `data.content / data.audio / data.citations / data.error`；`processId` + `abortController` 已支持"中断上一个流"与"组件卸载时 abort"；TTS 音频经 MediaSource 播放。
9. **麦克风**：`Microphone.vue`——点麦克风后**替换**整个输入栏；`@ricky0123/vad-web`（Silero VAD, onnx/wasm, 缓存于 Cache API）；`onSpeechEnd` 直接把 PCM 发 `POST /api/friend/message/asr/asr/`，收到文本后 `emits("send", null, text)` **立即发送**；`vadReady` 初始化失败时永久停在"语音初始化中..."，无错误态。
10. **导航**：`App.vue` 中 `NavBar`（64px 高，sticky，含 logo/搜索/创作/用户菜单）包裹 `RouterView`，底部有全局 footer。路由表在 `frontend/src/router/index.js`，`meta.needLogin` 由 beforeEach 校验。
11. **好友列表**：`GET /api/friend/get_list/?items_count=`（分页 20/次，`select_related`，已按 `last_active=Max(message.created_at)` 排序），返回 `{id, character:{id,name,introduction,photo,background_image,author}}`，**不包含**最后一条消息内容。
12. **角色创建**：`BackgroundImage.vue` 用 Croppie 固定视口 **300×500（3:5 竖版）** 裁剪聊天背景；`Character.photo`/`background_image` 有安全属性 `photo_url`/`background_image_url`。

---

## 2. 产品约束（不可更改）

- **C1 背景图由角色创建者设定**：聊天背景是创建者的品牌资产，UI 不得改变其 3:5 构图（不得用桌面 16:9 全屏 cover 裁剪）。
- **C2 创建者非设计师**：背景图内容不可预知（全白/全黑/高饱和/低清均可能），文字可读性不得依赖图片本身，必须落在确定性蒙层上。
- **C3 用户须能降级**：背景非用户所设，用户应能切换"简约背景"模式（无障碍兜底）。
- **C4 技术栈固定**：Vue 3 Composition API + Tailwind CSS 4 + daisyUI 5 + Pinia + Vue Router 5；后端 Django/DRF 不改主体（仅可选项，见 §11）。
- **C5 移动端兼容**：本项目有移动端使用，改版必须兼顾 `<lg`（1024px）以下。

---

## 3. 已拍板决策（评审结论）

| # | 决策 | 结论 |
|---|------|------|
| D1 | 角色之窗宽度 | **420px**（封顶），高度按 3:5 比例并受视口高度约束（见 §4.3） |
| D2 | 移动端形态 | **聊天页全屏窗口 + 会话栏抽屉化**；废弃 dialog 弹窗（ChatField 下线） |
| D3 | 首页卡片行为 | 保留 `showDetail` 两级流程：`showDetail=true` 卡片 → 详情弹窗 → "开始聊天" → 跳转聊天页；`showDetail=false` 卡片 → 直接跳转聊天页 |
| D4 | 会话栏预览 | **P1 仅显示头像+名字**（排序复用 get_list 的 last_active）；最后消息预览列为 P2 可选后端增强 |
| D5 | NavBar 搜索 | **聊天页隐藏搜索框**（通过路由 meta 标记） |
| D6 | 语音自动发送 | **默认关闭**（识别结果回填输入栏，用户确认后发送；设置项开关可开） |
| D7 | 示例问题 | **前端通用兜底文案**；创建者自定义示例问题列为后续增强 |
| D8 | 宽版横幅图 | **本期不做**；桌面舞台用同一张 3:5 图模糊延展兜底 |
| D9 | 全局 footer | **聊天页隐藏**（路由 meta 标记），保证沉浸式全高 |
| D10 | 会话选中态 | 当前会话在列表中以 accent 色高亮（背景 `--accent`/40，左侧 4px accent 竖条） |

---

## 4. 全局布局规格（几何描述）

### 4.1 页面结构（桌面端，viewport ≥ 1024px）

```
┌────────────────────────────────────────────────────────────────────┐
│ NavBar: 高 64px，sticky top-0，z-50；含 logo(32px)+"AI Friends"(左)、│
│        搜索框(本期聊天页内隐藏)、"创作"、用户菜单(右)                    │
├──────────────┬─────────────────────────────────────────────────────┤
│ 会话栏 280px  │ 聊天区（舞台）: flex-1，相对定位，overflow-hidden        │
│ 白底可滚动     │   ├─ 舞台背景层（absolute inset-0，blur+压暗，见 §6.2）│
│              │   └─ 角色之窗（absolute 居中，见 §4.3）                 │
└──────────────┴─────────────────────────────────────────────────────┘
总高度 = 100vh - 64px（导航栏）；聊天页不产生页面级滚动条（滚动发生在内部）
```

坐标（相对视口，px 基准，Tailwind 4 原生 spacing 单位换算）：
- 会话栏：`width: 280px`，左侧贴导航栏下方，竖向占满剩余高度；`background: base-200（浅灰）`，`border-right: 1px solid base-300`。
- 舞台：占据 `viewport 宽 - 280px`，`overflow: hidden`。

### 4.2 会话栏内容（由上至下）

1. 搜索区：高 56px，内含圆形输入框（placeholder"搜索好友"，通用图标）。
2. 会话列表：`overflow-y: auto`，隐藏滚动条（现有 `.no-scrollbar` 模式）；每条 `SessionItem` 高 64px，`rounded-xl` 内边距 8px，垂直排布；列表内边距 8px。
3. 列表状态：loading（骨架 2~3 条）/ empty（"还没有好友，去首页添加吧" + 链接）/ error（"加载失败" + 重试按钮）。
4. 移动端（<1024px）：会话栏整体转为左侧抽屉（`fixed left-0 top-0 h-full w-280px`，覆盖 NavBar 层，带半透明遮罩 + 点击遮罩关闭；由聊天页头部"菜单"按钮打开，或路由进入时不自动打开）。

### 4.3 角色之窗（核心容器，3:5 竖版）

几何规格：
- 水平：在舞台内上下左右居中（`absolute` + `margin: auto`，或 flex 居中）。
- 尺寸公式：`W = min(420px, (100vh - 64px - 48px) * 0.6)`；`H = W * 5/3`；再叠加 `H = min(H, 100vh - 64px - 48px)`（若 H 被压，W 按比例回调，**任何情况下保持 3:5**）。
  - 说明：3:5 → H = W×1.6667；反之 W = H×0.6。48px = 上下安全边距合计。
- 形态：`border-radius: 24px`；`box-shadow: 0 24px 64px rgba(0,0,0,0.45)`；`overflow: hidden`。
- 背景：角色背景图 `background-size: cover; background-position: center;` + **窗口内渐变蒙层**（线性渐变 180°，`rgba(0,0,0,0.25)` 0% → `rgba(0,0,0,0.60)` 100%，蒙层浓度系数受亮度自适应调节，见 §6.5）。
- 内部布局：**flex column**（严禁 absolute 堆叠，替代现状的问题 3）：
  - `WindowHeader`：固定高 56px，`shrink-0`；
  - `ChatHistory`：`flex: 1 1 0; min-height: 0; overflow-y: auto`；
  - `InputField`：`shrink-0`，底部内边距 12px。

### 4.4 移动端（<1024px）窗口形态

- 宽高：`100vw × (100vh - 64px)`（导航栏保留），无圆角（`border-radius: 0`），无外部投影。
- 窗口内部结构、状态机与桌面端完全一致（同一组件，仅布局类差异）。

---

## 5. 页面与组件契约

### 5.1 路由

```
path: /chat/                       name: 'chat-index'       meta: { needLogin: true, hideSearch: true, hideFooter: true }   （会话中心，Q7-b）
path: /chat/:character_id/        name: 'chat-index'       meta: { needLogin: true, hideSearch: true, hideFooter: true }   （Q1：URL 参数=角色 id）
```

- `hideSearch` / `hideFooter`：`NavBar.vue` / `App.vue` 根据 `route.meta` 渲染条件控制（全局组件内使用 `useRoute()` 判断）。
- 进入方式（改造后）：`Character.vue` 与 `CharacterDetail.vue` 中**删除内嵌 ChatField**，"开始聊天/直接聊天"改为 `router.push({name:'chat-index', params:{character_id: character.id}})`（Q1 拍板）；进入页面由 ChatIndex 调 `POST /api/friend/get_or_create/` 拿 `friend`（幂等，含 character 全字段）。
- 汉堡保留（Q7）；全局抽屉新增"聊天"入口（ChatIcon）→ `/chat/`。
- 会话切换 = `router.replace` 同步 URL（Q2 拍板：状态全部由路由参数派生，不新增历史栈）。

### 5.2 组件树

```text
views/chat/ChatIndex.vue                     （页面壳：布局 + 会话状态）
├─ components/chat/SessionList.vue           （会话栏：数据加载 + 列表 + 状态）
│  └─ components/chat/SessionItem.vue        （单项：头像/名字/选中态/点击）
├─ components/chat/chat_window/ChatWindow.vue（角色之窗：flex column + 背景与蒙层）
│  ├─ components/chat/chat_window/WindowHeader.vue （56px 玻璃条）
│  │   ├─ CharacterPhotoField.vue（复用，36px 头像 + 名字，点击开 CharacterDetail）
│  │   ├─ VoiceToggle.vue（复用，加 aria-label）
│  │   └─ CloseButton（✕ → router.back()；失败回退 {name:'friend-index'}）
│  ├─ ChatHistory.vue（改造：flex-1、分组、日期分隔、空态、骨架、错误重试）
│  │  └─ Message.vue（改造：分组渲染、markdown、引用 chips、hover 时间）
│  ├─ InputField.vue（改造：textarea 自动增高、停止生成、语音回填确认）
│  │  └─ Microphone.vue（改造：错误态 + 音量驱动波形）
│  └─ useBackgroundAdaptive.js（composable：亮度/主色采样 + 蒙层/accent 计算）
```

### 5.3 关键组件契约

**ChatIndex.vue**
- state：`friend`（对象，来自 get_or_create 响应）、`friendLoading`/`friendError`、`drawerOpen`；`activeCharacterId` 为 **computed**（路由参数派生，Q2）；`isHub`（无参会话中心态）。
- 职责：渲染布局（窗口尺寸纯 CSS 实现，无需 JS resize，LD F8）；移动端抽屉开关状态；将 `friend` 传给 ChatWindow。
- 边界：`character_id` 无效（get_or_create 404/错误）→ 页面级错误态（"该角色不存在或已删除" + 返回按钮）。

**SessionList.vue**
- props：`activeId`（当前高亮的 character_id，Q1）。
- emits：`select(characterId)` → ChatIndex 执行会话切换：先 get_or_create（幂等），**成功才** `router.replace` 同步 URL；失败留在原会话（N2）。
- 数据：复用 `GET /api/friend/get_list/?items_count=`，分页 20/次；排序已由后端 last_active 保证，前端不重排（D4）。
- 状态：loading / empty / error / list。

**ChatWindow.vue**
- props：`friend`。
- 职责：窗口背景样式（图片 + 渐变蒙层，浓度来自 `useBackgroundAdaptive`）；flex column 布局；透传 friend.id 给 ChatHistory / InputField。
- 事件转发：ChatHistory 与 InputField 之间不直接通信，统一由 ChatWindow/ChatIndex 持有 `history` 数组（沿用现有 ChatField 的 push/append 模式），保证逻辑与现版本迁移成本最小。

**ChatHistory.vue（改造要点）**
- 布局：`flex:1; min-height:0; overflow-y:auto;` 内边距 `12px 16px`；`scrollToBottom` 保留（`nextTick` 后 `scrollTop = scrollHeight`）。
- 渲染：按 `history` 数组分组（见 §8.1）；哨兵 + IntersectionObserver 上滑加载保留（逻辑不变）。
- 新增状态：加载骨架（未返回首批时显示 2 组左右 shimmer 气泡）；空态（§8.3）；加载失败（`loadError` 已知，补一个"点击重试"）。

**Message.vue（改造要点）**
- props：`message, character, showHeader（组首标记）, isLastOfGroup, timestamp`。
- 分组渲染：`showHeader=false` 时隐藏头像与名字，气泡与上一气泡间距 4px；`showHeader=true` 时头像 36px、名字 14px/半透明白 + `bg-black/30 rounded-full px-2` pill 底衬（N1）、间距 12px。
- 气泡：圆角 16px，头像侧角为 4px；max-width = 窗口内容宽 75%（≈ 288px @420px 窗口）；文本 `font-size:15px; line-height:1.65; word-break: break-word;`（替换 break-all）；保留 `whitespace-pre-wrap`。
- markdown：`marked` + `DOMPurify`（白名单：strong/em/ul/ol/li/code/pre/blockquote/a/br/h1~h4；禁止 img）。代码块右上角提供"复制"按钮。
- 引用：`message.citations`（数组 `{index,title}` 或含内容）→ 气泡下方渲染横排 chips（`bg-black/25 backdrop-blur text-white/90 rounded-full px-2.5 py-1 text-xs`，深色玻璃方向，N1；点击展开该来源文本）；原 collapse 手风琴移除。
- 时间：气泡 hover 时旁边显示 `HH:mm`（绝对定位，`opacity-0 group-hover:opacity-100`）。

**InputField.vue（改造要点）**
- 结构（替换原单行 input）：`[🎤 36px] [textarea (flex-1)] [发送/停止 36px]`，容器 `bg-black/35 backdrop-blur rounded-xl px-2 py-2`，底部 12px 内距窗口边缘。
- textarea：`auto-grow`（1→4 行，rows 逻辑：`scrollHeight` 监听，超过 4 行内部滚动）；Enter = 发送，**Shift+Enter = 换行，IME 组合中（`event.isComposing === true` 或 keyCode 229）的 Enter 一律不触发发送**（中文输入法边界，硬性要求）。
- 发送键：内容为空或语音聆听中 → `disabled`（灰 50%）；流式生成中 → 显示"■ 停止"（点击 `abortController.abort()` + `stopAudio()`；**保持已有文本、不加标记**——2026-09-07 拍板）。
- 语音入口：🎤 点击进入聆听态（§9 状态机），不替换输入栏，仅切换容器内状态区。
- 原有 `processId` 中断逻辑与 SSE 消费（content/audio/citations/error）**全部保留**，仅迁移到新模板。

**Microphone.vue（改造要点）**
- 保留 VAD 初始化、Cache API 缓存、PCM16 → ASR 的全部现有逻辑。
- 新增：`error` 状态（`vad_init_failed` / `mic_permission_denied` / `asr_failed`），展示内联提示 + "重试"按钮；初始化失败不再永久卡"语音初始化中..."。
- 波形：现有 32 条 CSS 定时器动画改为 **AnalyserNode 实时音量驱动**（webkitAudioContext + getUserMedia 同一流，`getByteTimeDomainData` → 柱高映射 4~20px）；`prefers-reduced-motion: reduce` 时柱高固定为 8px。
- emits 改为：`started`、`speechEnded`、`transcript(text)`（ASR 成功后）、`error(kind)`、`cancel`。

> 说明：Microphone 不再自己 `emits('send')`，而是把识别文本交给 InputField 回填（D6）。

---

## 6. 视觉设计系统（tokens，全部数值化）

### 6.1 色板

| Token | 值 | 用途 |
|-------|----|------|
| `--accent` | 背景图主色（自动提取），fallback `#10b981` | 选中态、己方气泡、语音激活 |
| `--overlay-k` | 0.6~1.5（亮度自适应系数，§6.5；实际渐变停点 = 0.25K~0.60K） | 窗口/舞台蒙层浓度 |
| `--text-primary` | `#ffffff` | 窗口内主文字 |
| `--text-secondary` | `rgba(255,255,255,0.70)` | 次要文字/时间戳 |
| `--text-disabled` | `rgba(255,255,255,0.40)` | 占位符/禁用 |
| `--glass` | `rgba(0,0,0,0.35) + backdrop-blur 12px` | 头部条/输入栏 |
| `--bubble-user` | JS 解析结果变量 `--user-bubble-bg`：`resolveUserBubble(accent)` 在 mix 70%→60%→50% 三档中取首个白字对比度 ≥4.5:1 的档位，全部不达标则回退 `#10b981`@70%（≈4.8，理论兜底——accentFallback 已保证 L∈[0.15,0.85]，50% 档数学上恒达标，该分支防御性保留，R6）；CSS 直接引用该变量 | 己方气泡（任意 accent 下白字达标） |
| `--bubble-ai` | `rgba(0,0,0,0.35) + backdrop-blur 8px` | AI 气泡（**深色玻璃**：白字在亮图上叠蒙层后仍 ≥4.5:1，R2） |
| `--chat-bg`（简约模式） | `#f5f5f4`（浅色）/ `#1c1917`（深色，跟随系统） | 用户切换的降级背景 |

### 6.2 舞台背景（桌面端）

- 同一张角色背景图，`<img>` 铺满舞台：`object-fit: cover; transform: scale(1.1); filter: blur(24px) saturate(1.35);` 叠加 `background: rgba(0,0,0, 0.35)`。（2026-09-07 实机调优：40px+0.5 过灰、失场景感；Phase 4 引入 `--overlay-k` 自适应时以 0.35 为基准系数起调。）
- 目的：大屏不空、氛围统一、不干扰窗口内容。移动端无舞台（窗口全屏）。

### 6.3 窗口渐变蒙层

`linear-gradient(180deg, rgba(0,0,0,0.25*K) 0%, rgba(0,0,0,0.60*K) 100%)`，K = 亮度系数（§6.5），K∈[0.6, 1.5]。

### 6.4 字体

- 系统字体栈（`system-ui, -apple-system, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei'`）。
- 层：窗口内名字 15px/600；消息正文 15px/1.65；会话栏名字 15px/500；预览 13px；日期分隔 12px；坐标 12px。窗口内文字一律白色系。

### 6.5 亮度自适应算法（`useBackgroundAdaptive.js`）

```text
输入：角色背景图 URL
输出：{ overlayK, accent, ready }
流程：
1. 创建 Image 对象，src = URL；`crossOrigin = 'anonymous'`（同源媒体无碍，失败不阻塞）。
2. onload：drawImage 至 16×16 canvas → getImageData → 计算：
   - avg  = 全像素均值亮度（0~1）
   - dominant = 简单直方图分桶（每桶 32 阶）取最大桶的中心色
3. overlayK = clamp(0.6 + (avg - 0.5) * 1.8, 0.6, 1.5)
   （K 随 avg 单调递增——窗口文字为白色系，图越亮蒙层必须越深：白图 avg≈0.9 → K≈1.32 深蒙层；黑图 avg≈0.1 → K≈0.6 浅蒙层）
4. accent 取 dominant，若饱和度/亮度不满足可读性下限（如亮度过高或过低），回退 #10b981。
5. 失败（onerror / 跨域被拦）：overlayK=1.0，accent=#10b981。全程不阻塞渲染，先以默认值渲染，ready 后热更新。
```

### 6.6 "简约背景"模式（C3 用户降级，用户设置，localStorage 持久化）

- 切换入口：WindowHeader 内（图标：减淡/月亮按钮，带 tooltip"简约背景"）。
- 效果：窗口背景 → `var(--chat-bg)` 纯色；消息气泡 → 常规 daisyUI 对比色（AI=base-200，用户=`--user-bubble-bg` 同沉浸模式解析结果，保证白字对比度）；舞台 → `base-200`；仍显示头像与布局不变。

---

## 7. 路由与导航细节

| 行为 | 规则 |
|------|------|
| 卡片点"开始聊天" | `POST /api/friend/get_or_create/` 成功 → `router.push({name:'chat-index', params:{character_id: character.id}})`（Q1）；失败 → toast 错误 |
| 聊天页头部 ✕ | `router.back()`；若历史栈为空（刷新直达）→ `router.replace({name:'friend-index'})` |
| 会话栏点击切换 | 先 get_or_create（幂等），**成功才** `router.replace` 同步 URL（Q2：刷新/分享正确、不新增历史栈；404 留在原会话，N2）；`:key` 变化重建 ChatWindow 与输入/音频状态 |
| 移动端抽屉 | 打开时锁定背景滚动（`overflow:hidden` on body），点击遮罩/选中会话后关闭 |
| 浏览器后退 | 从聊天页退到来源页（首页或好友列表）；会话内切换不产生历史记录 |

---

## 8. 消息区规格（含全部状态）

### 8.1 分组规则

- 遍历 `history`：`showHeader = (i===0) || (history[i].role !== history[i-1].role) || (同一角色但时间差 > 5min)`。
- 组内：间距 4px；组间：间距 12px。
- 日期胶囊分隔线：当与上一条消息日期不同（今天/昨天/M月D日），在两组之间插入居中胶囊（`bg-black/25 text-white/60 text-xs rounded-full px-3 py-0.5`，深色玻璃方向，N1）。

### 8.2 消息气泡规格

| 内容 | 规则 |
|------|------|
| AI 气泡 | 左对齐；`--bubble-ai`；`border-radius:16px`（左上角 4px）；名字在组首显示 |
| 用户气泡 | 右对齐；`--user-bubble-bg`（resolveUserBubble 解析结果，§6.1）+ 白字；圆角 16px（右上角 4px） |
| 头像 | 36px 圆形；仅组首显示（角色头像/用户头像） |
| 长文本 | `overflow-wrap: break-word`（**不得**用 `break-all`） |
| 代码块 | `bg-black/50 rounded-lg p-3 font-mono text-sm overflow-x-auto` + 复制按钮 |
| 错误消息 | 沿用现有模式：`data.error` 追加到最后一条 AI 消息（文本前加红色 icon），不弹窗 |

### 8.3 状态矩阵

| 状态 | 触发 | 表现 |
|------|------|------|
| 首次加载 | 进入页/切换会话 | 2 组左右交替的 shimmer 骨架（占位气泡），非白屏 |
| 空态 | 历史接口返回空 | 居中：角色 `introduction`（`text-white/90 text-lg`）+ 3 个示例问题胶囊按钮（D7）: "介绍一下你自己吧" / "讲个今天发生的故事" / "和我聊聊最近的烦恼"；点击直接发送 |
| 加载失败 | 历史接口异常 | 居中"加载失败" + 重试按钮（调用最初 loadMore 逻辑重放） |
| 上滑加载 | 哨兵可见 | 前置插入历史，保持滚动位置（现有 `oldTop + newHeight - oldHeight` 算法保留） |
| 思考中 | 发送后首个 `data.content` 前 | 最后一条 AI 气泡位置显示三点跳动动画 + "正在思考…"（或仅三点） |
| 流式中 | content 到达 | 停止按钮显示（§5.3）；TTS 音频路径不变 |
| 流式结束 | done/最后事件 | 停止按钮隐藏；输入恢复可发送；滚动到底 |
| 流式错误 | catch / data.error | 见 §8.2 错误消息；停止按钮隐藏 |

---

## 9. 语音输入状态机（核心交互）

```text
状态：idle ──点击🎤──> listening ──onSpeechEnd──> transcribing ──ASR成功──> confirm ──用户Enter/点发送──> idle
          │                 │                      │                            └─点🎤再录──> listening（覆盖）
          │                 └─Esc/再点🎤──> idle（取消，丢弃音频）
          ├─transcribing 失败──> asr_failed ──重试──> listening
          ├─vad 初始化失败─────> vad_failed ──重试──> 重新 initVAD
          └─麦克风权限被拒──────> mic_denied ──重试──> 重新申请权限（含引导文案）
```

界面表现（输入栏容器内切换，**不替换整个输入栏**）：
- `listening`：波形动画（音量驱动）+ 文字"正在聆听…"，右侧 ✕ 取消；🎤 按钮高亮为 accent。
- `transcribing`：三点跳动 + "识别中…"，输入栏内不可编辑。
- `confirm`：识别文本已填入 textarea（可编辑、可删除）；🎤 按钮恢复常规；不要求用户必须发送（停留 idle 前的中间态，用户可继续打字）。
- 错误态：内联红字提示（`text-red-300 text-xs`）+ "重试"按钮；vad/权限错误附带 `title` 说明（"请允许使用麦克风"）。
- 自动发送开关（设置项，D6 默认关）：`confirm` 后 800ms 自动触发发送；关闭时仅回填。

---

## 10. 数据流与 API 契约（复用，无破坏性变更）

| 接口 | 用法 | 变更 |
|------|------|------|
| `POST /api/friend/get_or_create/` | 进入聊天页前取 friend（含 character 背景/头像） | 无 |
| `GET /api/friend/get_list/` | 会话栏（分页 20/次） | 无（P1）；P2 可选加 `last_message` |
| `GET /api/friend/message/get_history/` | 历史加载（10/次） | 增加 `created_at`（ISO）与 `citations`（Q3 拍板，见 §10.1） |
| `POST /api/friend/message/chat/` | SSE 流式（content/audio/citations/error） | citations 事件升级为四元组 `{index,title,chunk_index,content}`（Q4 拍板，见 §10.1） |
| `POST /api/friend/message/asr/asr/` | 语音识别 | 无 |
| 路由 meta | `hideSearch/hideFooter` | 前端 |

客户端注意事项：
- `get_or_create` 前先 `user.isLogin()` 校验（未登录跳登录页，沿用现有）。
- SSE `AbortController` 生命周期：会话切换（`:key` 重建）、组件卸载、手动停止、新消息发送时都要正确 abort（现有 abort 逻辑保留并覆盖"切换会话"分支）。
- 会话栏与聊天区数据解耦：切换会话时 ChatHistory 重新 `loadMore`（`:key` 重建即满足）；若希望减少请求，可后续加内存缓存（非本期）。

---


### 10.1 后端批次（2026-09-07 拍板，Q3/Q4 结论回写）

> 由逻辑层设计 Q3/Q4 拍板引入（LD §14.2 为实施明细）。摘要：
>
> 1. `Message.citations` JSONField（migration 0022）+ `chat.py` 保存时落库（正常/断连双路径；提取逻辑抽 `extract_citations` 共用，`_collect_citations` 无条件收集）
> 2. `get_history` 响应每条增加 `created_at`（ISO）+ `citations`
> 3. chat SSE citations 事件携带 `content` 原文
>
> **Phase 2 断言 3（日期分隔）与断言 5（引用展开）依赖本批次字段，须在 Phase 2 合入前完成并部署。**

## 11. 边界情况清单

| # | 场景 | 处理 |
|---|------|------|
| E1 | character_id 无效（角色被删/不存在） | get_or_create 4xx → 页面错误态 + 返回 |
| E2 | 背景图加载失败/跨域被拦 | useBackgroundAdaptive fallback（K=1.0）；窗口背景回退 `rgba(0,0,0,0.75)` 深色 |
| E3 | 背景极亮/极暗 | 亮度自适应蒙层（§6.5）+ 深色 AI 气泡（R2）共同保证正文 ≥4.5:1；用户可切简约模式 |
| E4 | 视口高度不足（如 800px 高） | 窗口按公式缩放，保持 3:5；不得超出视口 |
| E5 | 无历史（新好友） | 空态 + 示例问题 |
| E6 | 连续两条语音（快速说话） | `transcribing` 期间🎤按钮禁用，避免并发 ASR |
| E7 | 生成中切换会话 | 先 abort 当前流，再重建（`:key`）；TTS stop 复用 `stopAudio` |
| E8 | 中文输入法候选 Enter | `isComposing` 判定，不发送（§5.3，硬性） |
| E9 | 麦克风权限被拒 | mic_denied 状态 + 引导文案 + 重试（不再卡死） |
| E10 | ASR 返回空文本 | 视为失败 → `asr_failed`（提示"未听清，请重试"） |
| E11 | SSE 中途断网 | 现有 catch → 错误消息；停止按钮隐藏；不自动重连（维持现状） |
| E12 | 会话栏接口失败 | 列表区错误态 + 重试；聊天区不受影响 |
| E13 | 两个标签页同时聊天 | 各自独立实例（符合现状，不处理同步） |
| E14 | 用户未登录直达 `/chat/1/` | meta.needLogin → 登录页（现有守卫） |
| E15 | 简约模式 + 移动端 | 两者正交：移动端同样可切换 |

---

## 12. 无障碍规格（基础要求）

- 所有图标按钮：`aria-label`（如"关闭对话"、"语音输入"、"停止生成"）且焦点可见（`focus-visible:ring-2 ring-white/60`）。
- 键盘：Enter 发送 / Shift+Enter 换行；Esc 取消语音聆听；Tab 顺序 = 头部 → 历史 → 输入栏。
- 对比度：正文（消息、名字）≥ 4.5:1（深色蒙层 + 深色 AI 气泡保证，R2）；次要文本（日期胶囊/时间戳/占位符）≥ 3:1；简约模式天然满足。
- `prefers-reduced-motion: reduce`：波形静止、三点动画降为静态、禁用 backdrop-blur 外的大幅度动画。
- 语言属性与语义：使用语义化 button / label（textarea 关联 label 或 aria-label"消息输入"）。

---

## 13. 实施阶段与验收断言（可验证）

### Phase 1 —— 骨架（后端零改动）
改动：路由 + ChatIndex + SessionList/Item + ChatWindow + WindowHeader；删除卡片内嵌 ChatField；NavBar/App 按 meta 隐藏搜索/footer。

验收断言：
1. 首页/好友列表点击卡片 → 跳转 `/chat/:character_id/`，聊天窗口出现。
2. 刷新页面后会话和历史仍在（URL 直达可恢复）。
3. 浏览器后退返回来源页；会话列表内切换不产生新历史记录。
4. Vue DevTools 组件树中同时最多存在 1 个 ChatWindow（原"每卡一 dialog"消除）。
5. ≥1024px 双栏（280px 会话栏 + 舞台）；<1024px 单栏 + 抽屉。
6. 窗口保持 3:5；任意视口尺寸下窗口不超出视口（E4）。
7. 背景图之上文字在亮/暗图下均可读（人工目测 + 公式校验 §6.5）。
8. 会话栏 loading/empty/error 三态可用。

### Phase 2 —— 消息打磨
改动：骨架屏、空态+示例问题、分组渲染、日期分隔、markdown（marked+DOMPurify）、引用 chips、错误重试。

验收断言：
1. 新好友首次进入显示 introduction + 3 个示例问题，点击即发送。
2. 连续同角色消息仅首条显示头像/名字；组间距 12px / 组内 4px。
3. 日期变化处出现"今天/昨天/M月D日"胶囊（依赖 §10.1 后端批次的 created_at）。
4. AI 回复中的列表/代码块正确渲染；代码块可复制；含 `<script>` 等标签被 DOMPurify 剥除（XSS 用例通过）。
5. 引用消息显示 chips，点击展开来源文本（依赖 §10.1 后端批次的 citations）。
6. 首 token 前显示"正在思考…"；流式中出现停止按钮且可中断（含 TTS 停止）。

### Phase 3 —— 输入与语音
改动：textarea 自动增高 + 停止生成；Microphone 错误态/重试/音量波形；识别回填确认；自动发送开关。

验收断言：
1. 输入 200 字不出现横向滚动条；超过 4 行内部滚动。
2. 中文输入法候选状态下按 Enter 不发送（E8 自动化用例）。
3. 停止生成后最后一条 AI 消息保留已生成文本，流不再追加。
4. 语音：识别文本回填 textarea，编辑后发送；默认不自动发送。
5. 拒绝麦克风权限 → 显示引导与重试，不再卡"语音初始化中…"。
6. ASR 空文本 → "未听清，请重试"。

### Phase 4 —— 自适应与质感
改动：useBackgroundAdaptive 全量接入（蒙层系数 + accent）；简约背景开关；创建页聊天预览 + 亮度提示；无障碍细节。

验收断言：
1. 白图（avg≈0.9）→ overlayK≈1.32（深蒙层）；黑图（avg≈0.1）→ overlayK≈0.6（浅蒙层）；K 随亮度单调递增（公式值，自动化单测）。
2. 简约模式切换后窗口背景为纯色、气泡高对比；刷新后保持（localStorage）。
3. 创建/编辑角色页可看到"聊天效果预览"。
4. 全部图标按钮存在 aria-label；reduced-motion 下动画静止。

---

## 14. 给下游 LLM（deepseek-v4-pro）的具体任务边界

本文档已固化：布局几何、组件拆分与契约、状态机、数据流、边界、验收断言。请基于此文档产出（补充下列内容时不得违背本文档）：

1. **逻辑层设计**：每个组件的 state/ref/derive 清单、事件流向图（如"发送 → SSE → 追加 → 滚动"）、`useBackgroundAdaptive` 的加载时序与竞态处理。
2. **模块间通信**：`history` 数组所有权的明确方案（ChatIndex vs ChatWindow）、`:key` 重建与 audio/VAD 资源释放的时序。
3. **错误与降级**：E1~E15 各自的组件级处理路径与用户提示文案。
4. **性能**：SSE 流式下的 DOM 更新/滚动节流策略；长历史分组渲染是否需要虚拟列表（给出结论与依据）。
5. **测试设计**：针对 Phase 验收断言的组件测试/端到端用例建议（现有 221 个后端测试不动）。
6. **样式实现方案**：给出 token 的 Tailwind 4 `@theme` 落地建议（CSS 变量命名、`color-mix` 用法、复杂度评估）。
