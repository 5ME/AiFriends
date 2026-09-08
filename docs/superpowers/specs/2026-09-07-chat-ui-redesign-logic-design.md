# AI Friends 聊天界面改版 — 逻辑层设计（deepseek-v4-pro）

> 状态：**已定稿**（Q1~Q8 于 2026-09-07 全部拍板；§13 已转为决策记录，§14 为决策汇总与后端批次明细；可按 §10 进入 Phase 1 实施）
> 上游事实源：`2026-09-07-chat-ui-redesign-spec-for-llm.md`（视觉/交互规格，本设计不得违背；若存在冲突，以本文件 §1 事实核查结论 + §13 拍板结果为准）
> 本文档产出：组件契约、状态与数据流、事件时序、资源生命周期、错误处理、性能结论、样式落地、测试设计、文件级实施清单
> 术语：spec 简称 S（引用其章节号），本文件简称 LD

---

## 1. 事实核查：spec 假设 vs 代码现实（实施前必读）

| # | spec 假设 | 代码现实（已核实） | 结论 |
|---|-----------|--------------------|------|
| F1 | 路由 `/chat/:friend_id/`，页面用 get_or_create 取 friend | `get_or_create` **只接受 `character_id`**；且不存在"按 friend_id 查单个好友"的接口（`get_list` 是分页列表、`get_history` 只返回消息） | 直达/刷新时无法用 friend_id 恢复 friend 数据 → **Q1 必须拍板**（本设计按推荐方案 A：路由参数用 character_id 撰写） |
| F2 | get_history "返回 {id,user_message,output}"（S §1.11） | 属实；**不含 created_at、不含 citations** | 历史消息无时间戳 → 日期分隔线、hover 时间、历史引用 chips 均无数据源 → **Q3** |
| F3 | S §8.3 "前置插入历史保持滚动位置（现有算法保留）" | 属实：`ChatHistory.vue:55-76` 已有 `oldTop + newHeight - oldHeight` 算法 | 无需新增，仅迁移 |
| F4 | S §9 语音状态机"6 态" | 现状 Microphone 无状态机（init 失败永久卡死），emits 只有 close/send/stop | 状态机全新实现（LD §6），Microphone 职责收缩 |
| F5 | S §5.1 meta `hideSearch/hideFooter` | 搜索框在 `NavBar.vue` navbar-center；**footer 在 NavBar.vue 内**（`drawer-content` 底部）；汉堡抽屉也在 NavBar | 三者都在 NavBar 组件内通过 `route.meta` 控制；汉堡是否隐藏 spec 未写入 meta → **Q7** |
| F6 | 引用 chips "点击展开该条来源文本" | 后端 SSE citations 事件仅含 `{index,title,chunk_index}`（`chat.py` CITATION_RE 提取），**无原文**；现有 Message.vue collapse 也只显示标题列表 | "展开来源文本"无数据 → **Q4** |
| F7 | ChatField 引用面 | 仅 `Character.vue`、`CharacterDetail.vue` 两处内嵌（grep 已核实） | 下线影响面受控 |
| F8 | S §5.3 ChatIndex 负责 resize 重算窗口尺寸 | 窗口 3:5 公式可由纯 CSS `min()/calc()/aspect-ratio` 实现 | 实现为纯 CSS，**不需要 JS resize 监听**（LD §8，与 spec 意图一致，实现更优） |
| F9 | S §7 "会话切换不新开路由跳转" | 若不更新 URL，刷新/分享会回到进入页时的会话 | 与"刷新/分享天然可用"目标冲突 → **Q2**（本设计按推荐方案：`router.replace` 同步 URL） |
| F10 | 消息时间戳 | Message 模型有 created_at，但 get_history 不下发 | 同 F2 → Q3 |

---

## 2. 架构决策（LD 决策，编号 D-L1~D-L8）

| # | 决策 | 内容与理由 |
|---|------|-----------|
| D-L1 | **history 数组所有权 = ChatWindow** | 每个会话一个 ChatWindow 实例（`:key` 重建即隔离），沿用现有 ChatField 的 push/append 模式，迁移成本最小；ChatIndex 不持有 history |
| D-L2 | **friend 数据唯一入口 = `POST get_or_create(character_id)`** | 幂等接口；卡片点击、直达/刷新、会话切换三条路径统一走它，一次请求即得 friend（含 character 全部字段）。SessionList 的列表数据仅作选择 UI，不作为 ChatWindow 数据源 |
| D-L3 | **发送统一入口 = ChatWindow.sendMessage(text)** | ChatWindow 持 `inputFieldRef`，`sendMessage` 转发 `inputFieldRef.handleSend(text)`（现有 handleSend 已支持字符串参数，SSE 逻辑零改动）；空态示例问题由 ChatHistory `emit('quickSend', text)` → ChatWindow 转调 |
| D-L4 | **资源生命周期 = 组件卸载 + :key 重建** | 切换会话：更新 `activeCharacterId` → ChatWindow `:key` 变化 → 旧树整体卸载 → `InputField.onUnmounted`（现有：abort + stopAudio）与 `Microphone.onUnmounted`（现有：vad destroy）自动释放 → 新树挂载重新加载。**无需新增手动释放代码**；生成中切换会话由后端 C2 断连路径兜底落库（现有机制） |
| D-L5 | **markdown 渲染时机 = 边流边渲染**（✔ 2026-09-08 实测修订） | 原"流式结束才渲染"在 TTS 音频尾巴期间产生"文字已吐完仍裸文本、随后突然渲染"的明显延迟（用户实测反馈）；实测 marked+DOMPurify 对增量文本 <2ms/次、无性能影响。实现：Message.vue 始终渲染 markdown（`renderedHtml` 常算），复制按钮按 content 变化重挂（幂等） |
| D-L6 | **滚动节流，内容更新不节流** | 每 SSE chunk 更新 content（Vue 局部 patch 开销可忽略）；`scrollToBottom` 改为 `requestAnimationFrame` 合并执行（每帧最多一次）。理由与虚拟列表结论见 LD §7 |
| D-L7 | **用户级设置 = useChatSettings 模块级单例** | 仿照 `useVoiceToggle` 模式：`simpleBackground`（默认 false）、`autoSendVoice`（默认 false），localStorage 持久化（key：`chatSimpleBg` / `chatAutoSendVoice`）。WindowHeader 与 InputField 共享 |
| D-L8 | **ChatField.vue 下线（删除文件）** | 其内部逻辑分别迁移：布局壳 → ChatWindow；历史 → ChatHistory（改造）；输入/音频 → InputField（改造）。删除文件而非保留死代码 |

---

## 3. 组件契约（props / emits / state / 方法 / 职责）

### 3.1 `views/chat/ChatIndex.vue`【新】

- **props**：无（数据来自路由参数 + API）
- **state**：
  - `friend`：`Object | null`，get_or_create 返回体
  - `friendLoading` / `friendError`：页面级加载态与错误
  - `drawerOpen`：移动端会话抽屉开关
- **computed**：
  - `activeCharacterId`：`route.params.character_id ?? null`（Q1/Q2 已拍板：状态全部由路由参数派生，无独立内部状态）
  - `isHub = activeCharacterId === null`：无参 `/chat/` 静态会话中心态（Q7-b）
  - `isMobile`：新增 `src/composables/useMediaQuery.js`（matchMedia + resize 监听封装，约 10 行；项目无 @vueuse，review P2-3）
- **无参 `/chat/` 会话中心行为（Q7 已拍板：静态，不自动跳转）**：`isHub` 时**不调用 get_or_create**；舞台区渲染空态——文案"从左侧选择一个好友开始聊天"；`<lg` 时附加"选择好友"按钮（`drawerOpen=true` 打开会话抽屉）；SessionList 照常自加载
- **方法**：
  - `loadFriend(characterId)`：调 get_or_create；成功 `friend = res.friend`；4xx → `friendError`（E1）
  - `handleSelect(characterId)`：会话切换（时序见 LD §4.3）
  - `toggleDrawer(open)`：开时 `document.body.style.overflow='hidden'`，关时恢复（E：抽屉关闭时解锁）
- **watch**：`route.params.character_id` 变化（后退/前进/直达/切换）→ 若与 `friend.character.id` 一致则跳过 loadFriend（会话切换预取路径，N2），否则 `loadFriend`；`friend?.character.id` 变化 → `windowReady`
- **模板结构**：
  ```
  <div class="h-[calc(100dvh-64px)] flex">
    <SessionList v-if="isMobile ? drawerOpen : true" （桌面常驻，移动端进抽屉） />
    <main class="flex-1 relative overflow-hidden">  ← 舞台
      <ChatWindow v-if="friend" :key="friend.character.id" :friend="friend" @closed="handleClose" />
      <loading/error 态 v-else />
    </main>
  </div>
  ```
- **边界**：E1（friend 加载失败 → 错误态 + 返回按钮）、E14（needLogin 守卫兜底）

### 3.2 `components/chat/SessionList.vue`【新】

- **props**：`activeId`（高亮）
- **emits**：`select(characterId)`、`closeDrawer()`
- **state**：`sessions`、`loading`、`error`、`hasMore`、`itemsCount`（分页游标）
- **方法**：`loadMore()`（`GET /api/friend/get_list/?items_count=`，20/次，滚动到底触发）；`retry()`
- **模板**：搜索框（56px，本地过滤 sessions 数组）+ 列表（overflow-y auto）+ 三态（loading 骨架 2~3 条 / empty "还没有好友，去首页添加吧"+链接 / error "加载失败"+重试）
- **搜索过滤**：`keyword` computed 过滤 `character.name`（前端本地过滤，不调后端）

### 3.3 `components/chat/SessionItem.vue`【新】

- **props**：`session`（friend 对象）、`active`（bool）
- **emits**：`select`
- **模板**：64px 高、rounded-xl；头像（`character.photo`）+ 名字；选中态：`background: color-mix(in srgb, var(--accent) 40%, transparent)` + 左侧 4px accent 竖条（D10）；`aria-current="true"` 当选中
- 无预览/时间（D4）

### 3.4 `components/chat/chat_window/ChatWindow.vue`【新】

- **props**：`friend`
- **emits**：`closed`（✕ → ChatIndex 执行 router.back()）
- **state**：`history = ref([])`（D-L1 所有权）；`isStreaming = ref(false)`；`thinking = ref(false)`（发送后、首 content 前）
- **持有**：`chatHistoryRef`、`inputFieldRef`、`headerRef`；`useBackgroundAdaptive(friend.character.background_image)` 与 `useChatSettings()`
- **方法**：
  - `pushBackMessage(msg)` / `appendToLastMessage(delta)` / `pushFrontMessage(msg)`：现 ChatField 同名逻辑迁移（append 支持 `{citations}` 对象与 string delta 两种）
  - `sendMessage(text)`：`isStreaming=false && text.trim()` 时 `inputFieldRef.handleSend(text)`（D-L3）
  - `handleStreamState({streaming, thinking})`：InputField 上抛，驱动"■ 停止"显示与窗口级 isStreaming
  - `scrollToBottom`（rAF 节流版，LD §7）
- **模板**：3:5 窗口容器（LD §8.1）+ flex column：WindowHeader（56px shrink-0）→ ChatHistory（flex-1 min-h-0）→ InputField（shrink-0）
- **样式职责**：窗口背景图 + 渐变蒙层（`--overlay-k` 变量）+ 舞台背景（桌面）；`--accent`/`--overlay-k` 经 `useBackgroundAdaptive` 绑定到窗口根节点 style

### 3.5 `components/chat/chat_window/WindowHeader.vue`【新】

- **props**：`character`、`simpleBackground`（useChatSettings 注入）
- **emits**：`close`、`toggleSimple`、`toggleAutoSend`
- **结构**：`[CharacterPhotoField(复用)] [VoiceToggle(复用)] [⚙设置] [简约背景切换] [✕关闭]`，56px `bg-black/40 backdrop-blur`，`shrink-0`
- **⚙ 设置弹层**（Q6 已拍板落点；点击展开，点击外部关闭）：两个开关项——"简约背景"、"语音自动发送"
- **关闭**：`emit('close')`；ChatIndex 内：`history.state.back ? router.back() : router.replace({name:'friend-index'})`（S §7）
- **无障碍**：所有按钮 `aria-label` + `data-tip`

### 3.6 `ChatHistory.vue`【改造】

- **props**：`friendId`、`character`、`history`、`isStreaming`、`thinking`（后两个用于尾部指示）
- **emits**：`pushFrontMessage`、`quickSend(text)`（空态示例问题）
- **保留**：哨兵 + IntersectionObserver 上滑加载、`loadMore` 全逻辑、滚动位置保持算法（F3）、`scrollToBottom`（改 rAF 节流）
- **state 新增**：`initialLoading`（首次加载骨架）、`loadError`（已有，补重试按钮）
- **新增状态渲染**：
  - 骨架：`initialLoading && history.length===0` → 2 组左右 shimmer 气泡
  - 空态：`!initialLoading && !hasMessages && history.length===0` → 居中 introduction + 3 示例问题（点击 `emit('quickSend', q)`）（D7 文案）
  - 错误重试：`loadError` → 居中"加载失败" + 重试按钮（重放 `loadMore`）
  - 思考中：`thinking` → 列表尾部三点动画气泡
- **分组/日期/时间渲染**：由 Message.vue + 纯函数 `groupMessages` 计算（LD §6.4），ChatHistory 只传 `showHeader`/`dateLabel` 等派生 props
- **布局**：`flex:1 min-h-0 overflow-y-auto`，`px-4 py-3`

### 3.7 `Message.vue`【改造】

- **props**：`message`、`character`、`showHeader`、`dateLabel`、`isLastOfGroup`、`streaming`（该消息是否正在流式）
- **渲染**：
  - 组首：头像 36px + 名字（AI=角色名 / user=store 用户名）
  - 气泡：AI 左对齐 `--bubble-ai`；用户右对齐 `--bubble-user`；`break-words whitespace-pre-wrap`；max-w 75%
  - markdown（D-L5 已修订为边流边渲染）：AI 消息 `computed(() => DOMPurify.sanitize(marked.parse(content)))` 常算（增量全量重解析 <2ms/次），无 `rendered` 触发；用户消息不走 markdown（纯文本 `pre-wrap`），S §5.3 仅要求 AI 回复；白名单 S §5.3；代码块复制按钮（navigator.clipboard，按 content 变化重挂、幂等）
  - 引用 chips：`message.citations` 非空 → 气泡下横排 chips，点击弹浮层（内容取决于 Q4 结果：原文 / 标题+段落号）
  - hover 时间：`message.time`（格式 `HH:mm`，数据源取决于 Q3）→ `group-hover` 显示
  - 日期分隔：`dateLabel` 非空 → 该消息前插入胶囊分隔线
- **XSS**：markdown 路径必须过 DOMPurify（Phase 2 验收断言 4）

### 3.8 `InputField.vue`【改造（最大）】

- **props**：`friendId`
- **emits**（保持现有 `pushBackMessage/appendToLastMessage`，新增）：`streamState({streaming, thinking})`
- **保留**：`processId` 打断、`abortController`、SSE 消费（content/audio/citations/error）、MediaSource 音频播放、`stopAudio`、`onUnmounted` 清理、`handleSend(eventOrMsg, audioMsg)` 签名
- **结构**：`[🎤36] [textarea flex-1] [➤/■ 36]`，容器 `bg-black/35 backdrop-blur rounded-xl px-2 py-2`，底部 12px 内距
- **textarea**：
  - auto-grow：`rows=1` + `@input` 读 `scrollHeight`，1~4 行（超过内部滚动）；`max-height` 对应 4 行
  - `@keydown.enter`：`if (e.isComposing || e.keyCode === 229) return;`（E8 硬性）；`e.shiftKey ? 换行 : (preventDefault + handleSend())`
  - 发送键 disabled：`!message.trim() || micState==='listening' || micState==='transcribing'`
- **语音状态机**：见 LD §6（状态由 InputField 持有，Microphone 只出事件）
- **暴露**：`handleSend`（供 ChatWindow.sendMessage）、`focus()`、`closeMic()`（迁移自现 ChatField）
- **流式状态上抛**：`thinking=true`（发送前）→ 首 content 后 `thinking=false, streaming=true` → done/error 后 `streaming=false` → `emit('streamState', ...)`

### 3.9 `Microphone.vue`【改造】

- **props**：无（改为受控：由 InputField 通过 ref 调用）
- **emits**：`started`、`speechEnded`、`transcript(text)`、`error(kind)`、`cancel`（**不再 emits('send')**，F4/D6）
- **保留**：VAD 初始化（Cache API 缓存 WASM）、PCM16 转换、`POST /api/friend/message/asr/asr/`、KeepAlive 相关（注意：迁移后可能不再需要 KeepAlive，见下）
- **暴露方法**：`start()`（initVAD 惰性 + `vad.start()`）、`pause()`、`destroy()`、`retry(kind)`
- **波形**：AnalyserNode 真实音量驱动（getUserMedia 流同时喂 VAD 与 Analyser）；`prefers-reduced-motion` 时柱高固定 8px
- **KeepAlive 说明**：现 InputField 用 `<KeepAlive>` 保活 Microphone 避免重复加载 WASM。改造后 Microphone 常驻 InputField 内（聆听态只是容器内状态切换，不再 v-if 挂载/卸载）→ **KeepAlive 可移除**，VAD 实例随 InputField 生命周期（每会话一个），WASM 由 Cache API 缓存保证二次加载快
- **错误映射**：`vad_init_failed` / `mic_permission_denied` / `asr_failed` → `emit('error', kind)`，由 InputField 渲染内联提示（不卡死）

### 3.10 `useBackgroundAdaptive.js`【新】

- **签名**：`useBackgroundAdaptive(imageUrl)` → `{ overlayK, accent, userBubbleBg, ready }`（均为 ref）；`userBubbleBg = resolveUserBubble(accent)`（见 §8.2，review P0-2）
- **流程**（S §6.5 公式）：
  1. `seq = ++loadSeq`；`ready=false`
  2. `new Image()`，`crossOrigin='anonymous'`，src=imageUrl
  3. onload：若 `seq !== loadSeq` 丢弃（**竞态防护**，D 切换会话场景）；否则 16×16 canvas → `avg`、`dominant`
  4. `overlayK = clamp(0.6 + (avg - 0.5) * 1.8, 0.6, 1.5)`（K 随 avg 单调递增——白字需要：白图深蒙层、黑图浅蒙层，review P0-1，最终数值以 spec §6.5 为准）；accent 亮度不在 [0.15, 0.85] → fallback `#10b981`
  5. onerror/跨域：`overlayK=1, accent=#10b981, ready=true`（E2，不阻塞渲染）
  6. 空 imageUrl（无背景图）：同失败分支
- **消费**：ChatWindow 根节点 `:style="{'--overlay-k': overlayK, '--accent': accent, '--user-bubble-bg': userBubbleBg}"`（R5：三变量齐注入）
- **单元可测**：核心计算抽纯函数 `frontend/src/utils/backgroundAdaptive.js`（LD §9）

### 3.11 `useChatSettings.js`【新】

- 模块级单例（仿 useVoiceToggle）：`simpleBackground`、`autoSendVoice` 两个 ref + localStorage watch 持久化；返回 `{ simpleBackground, autoSendVoice, toggleSimple, toggleAutoSend }`

### 3.12 删除/改造的既有文件

| 文件 | 动作 |
|------|------|
| `components/character/chat_field/ChatField.vue` | **删除**（D-L8） |
| `components/character/Character.vue` | 删 ChatField 引用；`openChatField()` 改为：登录校验 → get_or_create → `router.push({name:'chat-index', params:{character_id}})`；`friendError` 保留（toast 或内联提示） |
| `components/character/CharacterDetail.vue` | 删 ChatField 引用；`handleAction()`：get_or_create → 关闭弹窗 → `router.push`（同 D3） |
| `components/navbar/NavBar.vue` | `useRoute()` 读 meta：`hideSearch` 隐藏 navbar-center；`hideFooter` 隐藏 footer；**汉堡保留**（Q7）；抽屉新增"聊天"入口（`ChatIcon` → `/chat/`，Q7 已拍板） |
| `router/index.js` | 新增**两条路由**（同 name/meta，review P2-1）：`{path:'/chat/', ...}`（会话中心）与 `{path:'/chat/:character_id/', ...}`（具体会话）；meta：needLogin/hideSearch/hideFooter；不依赖可选参数语法 |
| `components/character/chat_field/input_field/Microphone.vue`、`InputField.vue`、`chat_history/ChatHistory.vue`、`message/Message.vue` | 按 3.6~3.9 改造，路径不变（迁移成本最低） |
| `VoiceToggle.vue`、`CharacterPhotoField.vue` | 微调：补 `aria-label` |

---

## 4. 事件流（时序）

### 4.1 卡片 → 聊天页

```
用户点击卡片（showDetail=false）
 → Character.openChatField()
 → user.isLogin()? 否 → push 登录页（现状）
 → POST get_or_create(character_id)
    ├─ 失败 → friendError 提示（不跳转）
    └─ 成功 → router.push({name:'chat-index', params:{character_id}})
ChatIndex onMounted
 → loadFriend(character_id)   // 再次 get_or_create（幂等，拿到最新 friend）
 → friend 就绪 → ChatWindow :key=character_id 挂载
 → ChatHistory onMounted → loadMore() 首批历史（10 条）
 → scrollToBottom
```

### 4.2 直达 / 刷新恢复

```
URL /chat/:character_id/ 直接进入（needLogin 守卫先行）
 → ChatIndex onMounted → loadFriend → 后续同 4.1
浏览器后退/前进（route.params 变化）
 → watch → loadFriend → ChatWindow 按 :key 重建
```

`/chat/`（无参，会话中心，Q7-b 静态）：
 → `isHub=true` → 不调 get_or_create；SessionList 自行加载；舞台渲染空态
 → 用户点击会话 → 走 §4.3 切换流程（replace 到 `/chat/:character_id/`）

### 4.3 会话切换（含资源释放时序）

```
SessionList → emit('select', characterId)
ChatIndex.handleSelect:
 1. drawerOpen=false（移动端收抽屉，body 解锁）
 2. friend = await get_or_create(characterId)
    ├─ 失败 → 错误提示（toast/内联），**不 replace，留在原会话**（N2 拍板）
    └─ 成功 → 写入 friend ref → router.replace({name:'chat-index', params:{character_id: characterId}})
 3. route watch：新 character_id === friend.character.id → 跳过 loadFriend（已预取）；否则（直达/刷新/后退）→ loadFriend
渲染层：
 5. ChatWindow :key 变化 → 旧树卸载：
    - InputField.onUnmounted → abortController.abort()（后端 C2 断连路径保存已生成内容）
    - stopAudio()（pause + endOfStream + revokeObjectURL）
    - Microphone.onUnmounted → vadInstance.destroy()
 6. 新树挂载 → ChatHistory 重新 loadMore（lastMessageId=0）
```

### 4.4 发送 → SSE → 渲染 → 滚动

```
sendMessage(text)（统一入口，D-L3）
 → InputField.handleSend(text)
 → history.push(user 消息)、push(空 ai 消息)；thinking=true（emit streamState）
 → initAudioStream()（voiceEnabled 时）
 → abort 上一个流 → 新 AbortController
 → streamApi POST /chat/
   onmessage:
   ├─ citations → appendToLastMessage({citations})   // 后端保证先于 content
   ├─ content   → 首片时 thinking=false, streaming=true；appendToLastMessage(delta)；rAF 调度 scrollToBottom（D-L6）
   ├─ audio     → handleAudioChunk（MSE 队列，现有）
   ├─ error     → appendToLastMessage(error 文案)；stopAudio()；streaming=false
   [DONE]/isDone → streaming=false；scrollToBottom（markdown 已边流边渲染，无 rendered 触发，D-L5）
停止生成（■ 按钮）：
 → abortController.abort() + stopAudio()；streaming=false；
   停止后不加标记、保留已有文本（Q8 已拍板）
```

### 4.5 历史加载（哨兵）

现有逻辑整体保留（F3）：`sentinel + IntersectionObserver → loadMore → pushFrontMessage ×2（每条历史拆 ai+user）→ 滚动位置补偿`。新增：历史消息 `rendered=true`、`time=created_at`（Q3 方案 A）、`citations`（Q3/Q4 方案 A）。

### 4.6 语音流程（重构后）

```
idle → 点🎤 → micRef.start()
 ├─ VAD 未初始化 → initVAD()（首次，含权限申请）
 │   ├─ 失败 → error('vad_init_failed' / 'mic_permission_denied') → 内联提示+重试
 │   └─ 成功 → listening（🎤 accent 高亮，波形 AnalyserNode，Esc/✕ 可取消）
 → onSpeechStart → emits('stop')（打断 TTS，现状保留）→ listening 继续
 → onSpeechEnd(audio) → transcribing（🎤 禁用，E6）
    POST asr → transcript(text)
    ├─ 空文本 → error('asr_failed')（"未听清，请重试"）
    └─ 成功 → textarea.value = text → confirm
         ├─ autoSendVoice=true → 800ms 后 handleSend()（Q6 开关位置）
         └─ 默认 → 用户编辑后 Enter/➤ 发送；点🎤 再录 → 覆盖重录（回 listening）
取消：Esc / ✕ / 再点🎤 → micRef.pause() → idle（丢弃音频）
```

### 4.7 设置开关

```
WindowHeader ⚙ → toggleSimple / toggleAutoSend → useChatSettings 单例 → localStorage 持久化
simpleBackground=true → ChatWindow 应用简约样式（S §6.6）；InputField 读 autoSendVoice（语音 confirm 分支）
```

---

## 5. 消息区与窗口状态矩阵（细化）

| 状态 | 条件 | 组件表现 | 数据标记 |
|------|------|----------|----------|
| 会话中心（/chat/ 无参） | `isHub && !friendLoading && !friendError` | 舞台空态："从左侧选择一个好友开始聊天" + 移动端"选择好友"按钮（开抽屉） | `friend=null` |
| 页面加载中 | `friendLoading && !friend` | 舞台中央 loading spinner | — |
| 页面错误 | `friendError` | 居中"该好友不存在或已解除关系" + 返回按钮（E1） | — |
| 历史骨架 | `initialLoading && history.length===0` | 2 组 shimmer 气泡 | — |
| 空态 | 首批返回 0 条 | introduction + 3 示例问题（D7） | `hasMessages=false` |
| 历史错误 | loadError | 居中"加载失败" + 重试 | — |
| 思考中 | `thinking` | 尾部三点气泡 | — |
| 流式中 | `streaming` | 输入栏显示 ■ 停止；输入禁用发送但可编辑 | — |
| 流式结束 | done/error/abort | 停止按钮消失；滚动到底 | —（markdown 边流边渲染，无需标记，D-L5） |
| 上滑加载 | 哨兵可见 | 前置插入 + 滚动补偿（F3） | — |

---

## 6. 语音状态机（细化 spec §9，实现为有限状态 + 转移表）

状态集合：`idle | listening | transcribing | confirm | vad_failed | mic_denied | asr_failed`

| 当前态 | 事件 | 次态 | 副作用 |
|--------|------|------|--------|
| idle | CLICK_MIC | listening* | `micRef.start()`；首次含 initVAD（可能转 vad_failed/mic_denied） |
| listening | SPEECH_END | transcribing | 传 PCM → ASR |
| listening | CANCEL（Esc/✕/再点🎤） | idle | `micRef.pause()`，丢弃音频 |
| listening | SPEECH_START | listening | emits('stop') 打断 TTS（现状保留） |
| transcribing | TRANSCRIPT(text≠'') | confirm | 回填 textarea；autoSend 开 → 800ms 定时器触发 SEND |
| transcribing | TRANSCRIPT('') / ASR_ERROR | asr_failed | 内联提示"未听清，请重试" |
| transcribing | CANCEL | idle | 忽略结果（丢弃） |
| confirm | SEND（Enter/➤/自动定时器） | idle | handleSend(text) |
| confirm | CLICK_MIC | listening | 覆盖重录（清空回填文本） |
| confirm | EDIT_TEXT | confirm | 用户自由编辑，无状态变化 |
| vad_failed / mic_denied / asr_failed | RETRY | listening* | 分别：重新 initVAD / 重新申请权限（含指引文案）/ 重新录音 |
| 任意非 idle | 会话切换（组件卸载） | （销毁） | onUnmounted 全量释放（D-L4） |

\* initVAD/权限失败时实际进入对应错误态。

**实现方式**：`const state = ref('idle')` + `transition(event, payload)` 方法（内部 switch 表，便于单测——抽纯 reducer 见 LD §9）。

---

## 7. 性能结论与实现点

1. **虚拟列表：不需要**。依据：单会话消息为个人陪伴场景，规模在百级；已按 10 条/次分页 + 上滑哨兵加载；DOM 节点数 = 当前已加载条数，Message 组件轻量。虚拟列表引入的滚动定位复杂度 >> 收益。**若未来单会话超千条再评估**（结论记录在案）。
2. **流式滚动节流**：`scrollToBottom` 由每 chunk 直接调用改为 rAF 合并（`scheduleScroll()`：`pending ? void 0 : (pending=true, requestAnimationFrame(()=>{scrollTop=scrollHeight; pending=false}))`）。ChatHistory 暴露 `scheduleScroll()`，ChatWindow append 后调用。
3. **content 追加**：保持每 chunk 一次 `last.content += delta`（Vue 局部 patch）；**禁止**每 chunk 触发 `nextTick + scrollHeight`（现状 `handleAppendToLastMessage` 里每 chunk 都 scrollToBottom，改由 rAF 节流后主开销消除）。
4. **markdown 边流边渲染**（D-L5 已修订）：文字自始即排版，` ` ` 标记不裸露，无"吐完再突变"；渲染为增量全量重解析（<2ms/次），极端超长回复可后续加 100ms 节流（当前不做）。
5. **背景采样**：16×16 canvas 一次性异步，`seq` 令牌防竞态（3.10）；失败走默认值不阻塞；不做二次采样（窗口尺寸变化不需要——蒙层与尺寸无关）。
6. **会话列表分页**：20/次滚动加载，无预取；搜索为前端本地过滤（数据量小）。
7. **TTS/MSE**：现有音频链路不动（队列 + SourceBuffer 已有背压逻辑）。
8. **依赖体积**：新增 `marked`（~36KB gzip）与 `dompurify`（~7KB gzip）只影响聊天页 bundle；若在意体积可后续动态 import，本期不做（简单优先）。

---

## 8. 样式落地（Tailwind CSS 4）

### 8.1 窗口 3:5（纯 CSS，无 JS resize，F8）

```css
/* ChatWindow 根 */
.chat-window {
  width: min(420px, calc((100dvh - 64px - 48px) * 0.6)); /* D1 */
  aspect-ratio: 3 / 5;
  max-height: calc(100dvh - 64px - 48px);                /* E4 兜底 */
  border-radius: 24px;
  box-shadow: 0 24px 64px rgba(0,0,0,0.45);
  overflow: hidden;
}
@media (max-width: 1023px) {
  .chat-window { width: 100vw; height: calc(100dvh - 64px);
                 border-radius: 0; box-shadow: none; }
}
```
（dvh 在旧浏览器回退：`height: calc(100vh - 64px)` 兜底行置于 dvh 行之前。）

### 8.2 Tailwind 4 `@theme` 落地建议（LD §14.6 任务）

在 `frontend/src/assets/main.css` 的 `@theme` 中注册语义 token，用 CSS 变量桥接运行时值：

```css
@theme {
  --color-accent: #10b981;          /* fallback；运行时被内联 --accent 覆盖 */
  --color-glass: rgba(0,0,0,0.35);
  --color-bubble-ai: rgba(0,0,0,0.35);   /* 深色玻璃：白字在亮图蒙层上仍 ≥4.5:1（review R2） */
  --color-bubble-user: var(--user-bubble-bg);   /* JS 解析值：resolveUserBubble(accent)，保证白字 ≥4.5:1 */
}
```
- 运行时动态值（accent/overlay/user-bubble-bg）经 ChatWindow 根节点 `:style` 注入同名 CSS 变量覆盖（CSS 变量级联天然生效于子树）。
- 己方气泡背景由纯函数 `resolveUserBubble(accent)` 解析（review P0-2 改良方案）：mix 70%→60%→50% 三档取首个白字对比度 ≥4.5:1 的档位，全部不达标 → `#10b981`@70%（对比度 ≈4.85）。固定 mix 无法覆盖任意亮色 accent（如黄色 @70% 仅 ≈3.2:1），故必须阶梯寻档。
- `--overlay-k` 用于两个渐变停点 `rgba(0,0,0,0.25*K) 0%, rgba(0,0,0,0.60*K) 100%` → 直接写 `linear-gradient(180deg, rgba(0,0,0,calc(0.25 * var(--overlay-k))) 0%, rgba(0,0,0,calc(0.60 * var(--overlay-k))) 100%)`（CSS calc 支持）。
- 舞台层：`filter: blur(24px) saturate(1.35); transform: scale(1.1);` + 叠加 `rgba(0,0,0,0.35)`（2026-09-07 实机调优值；Phase 4 自适应时以 0.35 为基准系数）。
- 复杂度评估：全部为既有 CSS 能力（color-mix/calc/自定义属性），无需新依赖；Tailwind 4 与任意值类（`w-[min(420px,...)]`）均支持，或按 8.1 用少量自定义 class 落 `main.css`（推荐后者，可读性高）。

### 8.3 玻璃/气泡类清单（落 `main.css` 或组件 scoped）

`.glass-bar`（头部/输入栏：bg + backdrop-blur 12px）、`.msg-bubble-ai`、`.msg-bubble-user`、`.date-capsule`、`.citation-chip`（S §6 色值照抄，此处不重复）。

---

## 9. 测试设计

### 9.1 现状与引入

- 前端**无任何测试基建**（无 vitest/jest）。后端 221 测试不动。
- **已拍板（Q5=A）引入 vitest**（devDependency）+ `jsdom` 环境（DOMPurify 用例需要）；`@vue/test-utils` 仅在组件级用例需要时引入。
- `package.json` scripts 增加 `"test:unit": "vitest run"`。Docker 构建影响：npm ci 会安装 devDeps（vite 本就在 devDeps），无额外构建风险。

### 9.2 纯函数抽取与用例清单

| 模块（新） | 函数 | 用例（断言） |
|------------|------|--------------|
| `src/utils/chatFormat.js` | `groupMessages(history)` | 同 role 连续 → 一组；role 变化 → 新组；同 role 但时间差 >5min → 新组；首条恒为组首 |
| | `dateLabel(prev, cur)` | 同一天 → null；昨天 → "昨天"；今天 → "今天"；跨日 → "M月D日" |
| | `formatTime(iso)` | → "HH:mm" |
| `src/utils/backgroundAdaptive.js` | `computeOverlayK(avg)` | avg=0.9 → ≈1.32（深）；avg=0.1 → 0.6（浅）；avg=0.5 → 0.6；K 随 avg 单调递增；边界 clamp [0.6,1.5] |
| | `extractDominantColor(pixels)` | 纯色图 → 该色；空输入 → null |
| | `contrastRatio(fg, bg)` | 已知对数值断言（#10b981 vs 白 ≈2.54；#10b981@70% vs 白 ≈4.85） |
| | `resolveUserBubble(accent)` | `#10b981` → 70% 档达标（≈4.8）；高亮黄（rgb(250,200,50)）→ 70% 3.18 / 60% 4.20 不达标，**50% 档达标（≈5.66，不回退）**（R6 修正）；回退分支为理论兜底；任一返回值的白字对比度断言 ≥4.5 |
| | `accentFallback(color)` | 亮度 >0.85 / <0.15 → '#10b981' |
| `src/utils/voiceState.js` | `voiceReducer(state, event)` | 覆盖 LD §6 转移表全部行（idle→listening、listening→transcribing、各 error、confirm→idle…） |
| `src/utils/inputKey.js` | `shouldSendOnEnter(e)` | `isComposing=true` → false；`keyCode===229` → false；shift → false；普通 Enter → true |
| Message.vue | markdown 渲染 | `marked.parse` 输出含 `<script>`/`<img>` → DOMPurify 后剥离（XSS 用例，Phase 2 断言 4） |

### 9.3 Phase 验收映射

- 可自动化：消息分组/日期/IME/状态机/自适应公式/XSS（上表）。
- 需手工：布局断点、滚动位置补偿、真实麦克风权限流、TTS 播放、后退/刷新行为（spec Phase 1~4 断言中交互类）。
- 每个 Phase 提交后：`npm run test:unit` + 手工清单对照 spec §13 验收断言执行。

---

## 10. 文件级改动清单（按 Phase）

### Phase 1 — 骨架（后端零改动）

| 动作 | 文件 |
|------|------|
| 新增 | `frontend/src/views/chat/ChatIndex.vue` |
| 新增 | `frontend/src/components/chat/SessionList.vue`、`SessionItem.vue` |
| 新增 | `frontend/src/composables/useMediaQuery.js`（matchMedia 封装，约 10 行） |
| 新增 | `frontend/src/components/chat/chat_window/ChatWindow.vue`、`WindowHeader.vue` |
| 修改 | `router/index.js`（+chat-index 两条路由：`/chat/` + `/chat/:character_id/`，meta：needLogin/hideSearch/hideFooter） |
| 修改 | `NavBar.vue`（meta 两开关：hideSearch/hideFooter；抽屉新增"聊天"入口 ChatIcon → /chat/） |
| 修改 | `Character.vue`（删 ChatField → router.push） |
| 修改 | `CharacterDetail.vue`（删 ChatField → router.push） |
| 修改 | `ChatHistory.vue`（flex-1 布局、骨架/错误重试，逻辑保留） |
| 修改 | `InputField.vue`（布局迁移：去绝对定位；逻辑保留；暴露 handleSend/focus/closeMic；补 streamState emit） |
| 修改 | `Message.vue`（分组 props 接入；样式按 S §8.2；markdown 延后 Phase 2） |
| 删除 | `ChatField.vue` |
| 依赖 | 无新增 |
| 验收 | spec Phase 1 断言 1~8 + 新增断言 9：全局抽屉含"聊天"入口 → /chat/ 静态会话中心（列表 + 空舞台） |

### Phase 2 — 消息打磨

| 动作 | 文件 |
|------|------|
| 新增 | `frontend/src/utils/chatFormat.js` |
| 修改 | `ChatHistory.vue`（空态 + 示例问题 + quickSend） |
| 修改 | `Message.vue`（分组/日期胶囊/hover 时间/引用 chips/markdown） |
| 修改 | `ChatWindow.vue`（sendMessage 入口、thinking 尾部指示、rAF 滚动节流） |
| 依赖 | `marked`、`dompurify`（package.json + lock） |
| 验收 | spec Phase 2 断言 1~6 |

### Phase 3 — 输入与语音

| 动作 | 文件 |
|------|------|
| 新增 | `frontend/src/utils/voiceState.js`、`src/utils/inputKey.js` |
| 修改 | `InputField.vue`（textarea 自动增高/IME/停止生成/语音状态机接入） |
| 修改 | `Microphone.vue`（受控化：start/pause/destroy/retry + 音量波形 + 错误 emits；移除 KeepAlive 依赖） |
| 验收 | spec Phase 3 断言 1~6 |

### Phase 4 — 自适应与质感

| 动作 | 文件 |
|------|------|
| 新增 | `frontend/src/composables/useBackgroundAdaptive.js`、`src/utils/backgroundAdaptive.js`、`src/composables/useChatSettings.js` |
| 修改 | `ChatWindow.vue`（蒙层/accent 变量绑定、简约模式分支） |
| 修改 | `WindowHeader.vue`（设置弹层：简约背景 + 语音自动发送） |
| 修改 | `VoiceToggle.vue`、`CharacterPhotoField.vue`（aria-label） |
| 修改（可选） | `views/create/character/components/BackgroundImage.vue`（聊天效果预览 + 亮度提示） |
| 验收 | spec Phase 4 断言 1~4 |

### 全局

- `main.css`：§8.2/8.3 token 与类（Phase 1 先落布局类，Phase 4 补自适应）；`.no-scrollbar` 从 ChatHistory scoped 样式**迁移至 main.css 全局**（SessionList 复用，review P2-4）。
- 每 Phase 独立 commit；Phase 1 合入后旧弹窗路径被跳转替代，功能等价可回滚。

---

## 11. 风险与回滚

| 风险 | 缓解 |
|------|------|
| 新依赖 lock 变化 → Docker build 时 npm ci 重跑（5~6 分钟，npmmirror 已配） | Phase 2 合入时一次性引入 marked+dompurify；vitest 放 devDeps 不影响运行时镜像层缓存策略（Dockerfile 只 COPY package*.json，仍会重跑 ci，属已知成本） |
| ChatField 下线导致漏改引用 | grep 已核实仅 2 处；Phase 1 验收含 Vue DevTools 单实例断言 |
| 会话切换竞态（旧会话 SSE 回调晚到污染新会话 history） | `:key` 重建 + `processId` 双重防护：旧 InputField 已卸载，其闭包回调不会再触发 emits（组件实例已销毁）；新实例 processId 从 1 起 |
| 背景采样竞态（切会话后旧图 onload 覆盖新值） | useBackgroundAdaptive `seq` 令牌（3.10） |
| 移动端双抽屉并存（全局导航抽屉 + 会话抽屉）易混淆 | 触发位置/图标区分（全局=NavBar 汉堡，会话=页面内按钮）；会话抽屉加遮罩与标题"会话"；留待 Phase 1 手工验收确认 |
| dev 模式背景采样跨域（`127.0.0.1:5173` 不在 CORS 白名单）→ 自适应恒为 fallback | 约定：dev 经 `http://localhost:5173` 访问；确需 127.0.0.1 则在 backend/.env 的 `DJANGO_CORS_ORIGINS` 增加 `http://127.0.0.1:5173`（review P2-2；生产 docker 同源无此问题） |

---

## 12. 明确不在本期范围（防蔓延）

1. 会话栏最后消息预览/未读红点（D4，P2 可选后端增强）
2. 创建者自定义示例问题（D7）、宽版横幅图（D8）
3. 多标签页实时同步（E13）、断线自动重连（E11 维持现状）
4. 后端除 §14.2 后端批次（Q3/Q4）之外的任何改动

---

## 13. 决策记录（原开放问题，Q1~Q8 已全部拍板）

| # | 问题 | 推荐（本设计已按推荐撰写） | 影响面 |
|---|------|---------------------------|--------|
| Q1 | ~~路由参数语义~~ ✅ **已拍板（方案 A）**：路由参数用 `character_id`（`/chat/:character_id/`），三条进入路径统一 get_or_create（幂等），零后端改动；URL 语义 = 角色链接（可分享，他人打开进入自己的会话） | — | 已定稿：影响路由命名、§4.3 时序、Phase 1 断言 1 的 URL 形态 |
| Q2 | ~~会话切换是否同步 URL~~ ✅ **已拍板（方案 A）**：切换会话执行 `router.replace({params:{character_id}})`，URL 实时指向当前会话（刷新/分享/书签正确），replace 不新增历史栈（后退直接退回来源页）；ChatIndex 状态全部由路由参数派生，不再维护独立的 activeCharacterId 内部状态 | — | 已定稿：影响 §4.3 时序、ChatIndex state 清单（去掉 activeCharacterId） |
| Q3 | ~~历史消息时间戳与引用~~ ✅ **已拍板（Q3a=A、Q3b=A）**：get_history 增加 `created_at`（ISO）；Message 增加 `citations` JSONField（migration 0022）+ chat.py 保存时写入 + get_history 返回。与 Q4-A 合并为**同一个后端批次**（一次测试、一次镜像重建、一次部署） | — | 已定稿：影响 §4.5、Phase 2 断言 3/5、后端批次范围见 §13 末 |
| Q4 | ~~引用"展开来源文本"的数据源~~ ✅ **已拍板（方案 A）**：citations 全程携带 `content` 原文（`{index,title,chunk_index,content}` 四元组）——chat.py 提取标记行下方正文、同构落库（Message.citations）、同构下发（SSE + get_history）；前端 chips 点击浮层显示原文（限高滚动）。向后兼容（增量字段） | — | 已定稿：并入 Q3 的同一后端批次（范围见 §13 末） |
| Q5 | ~~前端测试基建~~ ✅ **已拍板（方案 A）**：引入 vitest + jsdom（devDeps），仅为纯逻辑写单测（LD §9.2 清单）；不引入组件 E2E，交互类验收走 spec 手工清单 | — | 已定稿：影响 §9、package.json scripts、Phase 验收执行方式 |
| Q6 | ~~语音自动发送开关的 UI 落点~~ ✅ **已拍板（方案 A）**：放 WindowHeader"⚙ 设置"弹层，与"简约背景"开关并列；localStorage 持久化（useChatSettings） | — | 已定稿：影响 §3.5 WindowHeader、§4.6 语音流程 |
| Q7 | ~~聊天页是否隐藏汉堡 + ChatIcon 去向~~ ✅ **已拍板**：**保留汉堡（方案 B）**，并将"聊天"作为第 5 个入口加进全局抽屉（`ChatIcon` → `/chat/`）；`/chat/` 为**静态会话中心（方案 b）**：会话列表 + 舞台空态（"从左侧选择一个好友开始聊天"，`<lg` 附"选择好友"按钮打开会话抽屉），**不自动跳转** | — | 已定稿：路由拆两条（`/chat/` + `/chat/:character_id/`）、NavBar 抽屉 +1 入口、ChatIndex 增加 `isHub` 空态 |
| Q8（附带） | ~~停止生成后是否加标记~~ ✅ **已拍板（方案 A）**：不加标记，保留已生成文本 | — | 已定稿：影响 §4.4 停止分支 |

Q1~Q8 已全部拍板（2026-09-07）。本文档 §2~§12 即为实施基线，可按 LD §10 进入 Phase 1。


---

## 14. 已拍板决策汇总与后端批次实施明细

### 14.1 决策速查（Q1~Q8 最终结论）

| # | 结论 |
|---|------|
| Q1 | 路由参数 = character_id（`/chat/` + `/chat/:character_id/` 两条路由），get_or_create 统一入口，零后端 |
| Q2 | 会话切换用 `router.replace` 同步 URL；状态全由路由参数派生 |
| Q3 | get_history 增加 `created_at`；Message 增加 `citations` JSONField（migration 0022）落库并下发 |
| Q4 | citations 四元组 `{index,title,chunk_index,content}`，SSE 与历史同构下发 |
| Q5 | 引入 vitest + jsdom，纯函数单测（LD §9.2） |
| Q6 | 自动发送开关放 WindowHeader ⚙ 设置弹层（与简约背景并列） |
| Q7 | 聊天页保留汉堡；ChatIcon 进全局抽屉 → `/chat/` 静态会话中心（不自动跳转） |
| Q8 | 停止生成不加标记，保留已生成文本 |

### 14.2 后端批次（Q3+Q4 合并；可与 Phase 1 并行开发，Phase 2 合入前必须部署到生产）

文件与改动：

1. `backend/web/models/friend.py`：Message 增加 `citations = models.JSONField(default=list, blank=True)`
2. 新 migration `0022_message_citations`
3. `backend/web/views/friend/message/chat/chat.py`：
   - 抽 `extract_citations(tool_content) -> list[{index,title,chunk_index,content}]`，替换现有两处重复的 CITATION_RE 提取逻辑（tts_sender 与 _stream_llm_only）
   - 抽 `_collect_citations(msg)`：两路径共用，**无条件**写 `self._citations`（不受 cancel_event 门控——断连时 citations 也必须可落库，review P1-3）
   - SSE citations 事件携带 content
   - 正常路径（event_stream 保存）与 C2 断连路径（work 保存）均写入 `self._citations`
   - **顺带修复既有缺陷**：`_stream_llm_only`（TTS 配额耗尽降级路径）补 `_output_buffer` / `_output_usage` / `_has_error` 收集——现状该路径断连/停止时整条消息不落库（review P1-3）
4. `backend/web/views/friend/message/get_history.py`：响应每条增加 `created_at`（ISO）与 `citations`
5. 测试：历史序列化含新字段；citations 提取含原文；保存路径（正常 + 断连）落库断言；**新增用例：TTS 降级路径（_stream_llm_only）断连后消息仍落库且含 citations**（在既有 test_chat_agent / test_retrieval_trace / test_friend 体系内扩展）
6. 部署：pytest 全绿 → `./deploy/build.sh` → 服务器 `./deploy/server-deploy.sh`（registry 流程，层缓存，分钟级）
7. spec 回写：`spec-for-llm.md` §10 已增补 §10.1 后端批次、更新 API 表与 Phase 2 断言前置条件（review P1-4，本次修订已完成）

前端配套（Phase 2 内）：ChatHistory 历史映射带 `time / citations / rendered=true`；Message 引用 chips 浮层显示 content；日期分隔与 hover 时间的数据源 = created_at。

### 14.3 实施顺序

```
Phase 1（前端骨架，零后端）
  → 后端批次（14.2，Q3+Q4）
  → Phase 2（消息打磨，消费后端批次新字段）
  → Phase 3（输入与语音）
  → Phase 4（自适应与质感）
```

每个 Phase 独立 commit + 独立验收（spec §13 断言 + LD §9.3 映射 + Phase 1 新增断言 9）。