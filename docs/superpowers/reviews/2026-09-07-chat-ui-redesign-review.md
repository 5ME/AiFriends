# 聊天界面改版设计链 Review 报告（2026-09-07）

> 修订状态：三份文档已按本报告完成两轮修订；R1~R8 全部关闭（见 7.4）。剩余 N1 为最后一个对比度数学缺口，建议在 Phase 2/4 实现前拍板；N2~N4 为措辞级修正。
>
> 评审对象：
> - `2026-09-07-chat-ui-redesign-design.md`（评审版设计）
> - `2026-09-07-chat-ui-redesign-spec-for-llm.md`（设计事实源）
> - `2026-09-07-chat-ui-redesign-logic-design.md`（逻辑层设计，LD）
>
> 评审方法：将三份文档的 15+ 条关键论断逐一与代码核对（后端 5 个视图/模型 + 前端 8 个组件/配置文件），并交叉核对三份文档间的数值一致性。
>
> 总体结论：**设计链质量高，LD §1 事实核查表全部属实，可作为实施基线；但存在 1 个必须修正的设计错误（蒙层公式）、1 个不可达成的验收断言（气泡对比度）、2 个必须补齐的规格漏洞（断连落库覆盖、spec 未回写后端批次），建议在进入 Phase 1 前处理。**

---

## 一、代码事实核查结论（逐条验证）

| # | 论断 | 验证结果 |
|---|------|----------|
| F1 | get_or_create 只接受 `character_id`，无按 friend_id 查单个好友的接口 | ✅ `get_or_create.py:20`；Q1 改用 character_id 作 URL 参数是正确解法 |
| F2 | get_history 只返回 `{id, user_message, output}` | ✅ `get_history.py:26-30`，无 created_at / citations |
| F3 | 滚动位置补偿算法已存在 | ✅ `ChatHistory.vue:55-76`（`oldTop + newHeight - oldHeight`） |
| F5 | footer 在 NavBar.vue 内、搜索在 navbar-center | ✅ `NavBar.vue:53,80` |
| F6 | citations 仅 `{index,title,chunk_index}`，无原文 | ✅ `chat.py:437-441, 559-563` |
| F7 | ChatField 仅 2 处引用 | ✅ 仅 `Character.vue`、`CharacterDetail.vue` |
| — | CITATION_RE 两处重复提取 | ✅ `chat.py:436`（tts_sender）、`:558`（_stream_llm_only） |
| — | migration 编号 0022 | ✅ 最新为 `0021_add_api_usage_daily.py`，0022 正确 |
| — | get_list `items_count` 分页 + last_active 排序 | ✅ `get_list.py:20-25` |
| — | get_or_create 响应含 `character.background_image` URL | ✅ `get_or_create.py:45`（ChatWindow 数据源成立） |
| — | InputField `handleSend(eventOrMsg, audioMsg)` 签名 / processId / KeepAlive | ✅ `InputField.vue:119,137,223` |
| — | Message.vue `chat-bubble-success` + `break-all` + collapse 引用 | ✅ `Message.vue:22,28-40,53` |
| — | BackgroundImage 300×500 视口 | ✅ `BackgroundImage.vue:24` |
| — | 前端无 vitest / marked / dompurify / @vueuse | ✅ `package.json` 全无 |

**事实层零差错。** 这是这套文档链最值钱的部分。

---

## 二、必须修正的问题

### P0-1 亮度自适应蒙层公式方向反了，且三份文档数值互相矛盾

直接影响核心卖点（沉浸模式可读性）与 Phase 4 验收。四个位置的公式/注释/期望值两两矛盾：

| 位置 | 公式或期望 | 代入 avg=0.9（白图） | 代入 avg=0.1（黑图） |
|------|-----------|---------------------|---------------------|
| design.md §6.2 公式 | `clamp(0.35 + (0.6 - avg) * 0.8, 0.35, 0.7)` | 0.11 → clamp **0.35** | 0.75 → clamp **0.7** |
| design.md §6.2 注释 | "白图→0.7 深蒙层；黑图→0.4 浅蒙层" | **0.7** | **0.4** |
| spec §6.5 公式 | `K = clamp(0.6 + (0.6 - avg) * 1.5, 0.6, 1.5)` | **0.6**（最浅） | **1.35**（最深） |
| spec §6.5 注释 | "蒙层浓度随图变亮而变深" | 与公式值相反 | 与公式值相反 |
| LD §9.2 单测期望 | avg=0.9→0.6；avg=0.1→1.5 | 0.6 | 1.5 |
| spec §13 Phase 4 断言 1 | "白图浓度 ≈0.7；黑图 ≈0.4" | 0.7 | 0.4 |

- design.md：公式输出与自身注释连数值都对不上；
- spec：公式本身与"注意"句相反，且与 design.md 注释方向相反；
- LD：单测跟随 spec 公式，但 spec 验收断言跟随 design.md 注释——**验收会失败**。

**物理上正确的方向**：窗口内文字一律白色系（spec §6.4），白字 + 白底图 → 蒙层须**更深**，即 K 应随 avg **单调递增**。按 LD 现行公式，白底图拿到最浅蒙层 K=0.6，Phase 4 断言 7（对比度 ≥4.5:1）必然失败。

**修正建议**：统一为单调递增公式，例如 `K = clamp(0.6 + (avg - 0.5) * 1.8, 0.6, 1.5)`，并同步修改四处：design.md §6.2 公式+注释、spec §6.5 公式+注释+示例值、spec §13 Phase 4 断言 1、LD §9.2 单测期望。

### P0-2 己方气泡白字对比度达不到 4.5:1，验收断言不可达成

`--bubble-user = color-mix(in srgb, var(--accent) 85%, black)`，fallback accent `#10b981`。按 WCAG 相对亮度公式计算：

| 背景 | 相对亮度 L | 白字对比度 | 达标？ |
|------|-----------|-----------|--------|
| `#10b981`（不 mix） | ≈0.364 | ≈**2.5:1** | ❌ |
| `color-mix(85% toward black)` ≈ `rgb(14,157,110)` | ≈0.254 | ≈**3.4:1** | ❌ |
| 15px 正文 AA 要求 | — | 4.5:1 | — |

**修正建议（二选一）**：
1. 己方气泡加深到 `color-mix(in srgb, var(--accent) 70%, black)`（约 4.7:1，达标），或
2. 将己方气泡验收标准降为 3:1（AA 大字号/UI 组件标准），并在 spec §12 无障碍节明确哪些元素按 4.5:1、哪些按 3:1。

当前 spec §6.1"保证 ≥4.5:1"是**不可测量的错误断言**，必须改写。

### P1-3 Q4 后端批次的"断连路径落库 citations"在代码上覆盖不全

LD §14.2 声称正常/断连两条保存路径都写入 `self._citations`，但代码现实：

1. `tts_sender` 中 citations 只在 `not cancel_event.is_set()` 时 `mq.put`（`chat.py:442`），**从不收集到成员变量**——断连时 ToolMessage 分支整体跳过，work() 落库时无 citations 可写；
2. `_stream_llm_only`（TTS 配额耗尽降级路径）**没有 cancel_event，也没有 `_output_buffer`**——TTS 配额用完 + 用户停止生成/断连时，work() 的 `if output and friend and message`（`chat.py:323`）因 output 为空而**整条消息不落库**。这是现状既有缺陷，但 Q4 要宣称"断连路径落库 citations"就必须顺带修它。

**修正建议（写入 LD §14.2）**：
- 抽 `_collect_citations()` 为 tts_sender / _stream_llm_only 两路径共用，**无条件**（不受 cancel_event 门控）写入成员变量；
- `_stream_llm_only` 接入 `_output_buffer` / `_output_usage` 收集（顺带修复现状丢消息缺陷）；
- 补一条"断连路径 citations 落库"的测试用例（LD §14.2 第 5 条测试清单）。

### P1-4 spec（设计事实源）没有记录 Q3/Q4 引入的后端批次

- design.md 原则为"后端零依赖起步"，spec §10 API 表全部写"无变更"；
- 但 LD 经 Q3/Q4 拍板了后端批次（migration 0022 + `get_history` 增字段 + `chat.py` 重构），且 **spec §13 Phase 2 断言 3/5（日期分隔、引用展开）依赖这批字段**；
- 下游只读 spec 会误判 Phase 2 零后端可完成，与 LD §14.3 实施顺序冲突。

**修正建议**：向 spec 回写一节"后端批次（Q3+Q4 结论回写）"，并更新 §10 API 表与 §13 Phase 2 断言的前置条件说明。design.md 作为评审版可不动，但 spec 必须与 LD 对齐。

---

## 三、建议处理（P2，进入 Phase 1 时拍板）

1. **路由直接拆两条**：vue-router 4 起已移除 `:param?` 可选参数语法（[issue #2525](https://github.com/vuejs/vue-router/issues/2525)），项目为 vue-router 5.0.1 未证实恢复。LD 已标注"实现时验证"，不如直接定为 `/chat/`（hub）+ `/chat/:character_id/` 两条，消除不确定性。
2. **dev 模式 canvas 采样跨域**：`CORS_ALLOWED_ORIGINS` 默认仅含 `http://localhost:5173`（`settings.py:199-203`）。经 `127.0.0.1:5173` 访问时，`crossOrigin='anonymous'` 的采样图加载失败 → K 恒为 fallback，Phase 4 自适应验收在 dev 无法观测（生产 docker 同源无问题）。补一条约定：dev 必须经 localhost 访问，或把 `http://127.0.0.1:5173` 加入白名单。
3. **`useMediaQuery` 未列入文件清单**：LD §3.1 使用了它，但 §10 Phase 1 清单没有新增（项目无 @vueuse）。要么补进清单（约 10 行 matchMedia 封装），要么改用纯 CSS 双渲染，否则 Phase 1 验收断言 5 无法实现。
4. **`.no-scrollbar` 是 scoped 样式**（定义在 `ChatHistory.vue:126-131`），SessionList 拿不到，需全局化到 main.css。
5. **几何公式本身正确（已复核）**：`W = min(420, (vh-112)*0.6)` ⇒ `H = 5W/3 ≤ vh-112` 恒成立，`max-height` 是冗余保险，3:5 不会破；移动端宽高双定值时 aspect-ratio 自动失效，无冲突。LD §8.1 实现可行 ✅

---

## 四、文档间小漂移（spec 已声明为事实源，记录备查）

| 项 | 差异 | 处理 |
|----|------|------|
| 窗口高度公式 | design.md §3 `min(85vh,700px)` vs spec §4.3 精确公式 | 以 spec 为准 ✅ |
| 引用展示形态 | design.md §7 双形态（内联胶囊 + 尾部 chips）vs spec 仅 chips | 以 spec 为准 ✅ |
| 舞台叠加浓度 | design.md §6.2 `.4~.6` vs LD §8.2 实际 `0.5*K ∈ [0.3, 0.75]` | 以 LD 为准，建议 design.md 不改（评审版） |
| 停止生成措辞 | spec §5.3"追加（已停止生成）标记**或**保持已有文本"两可 vs Q8 已拍板不加标记 | spec §5.3 应同步为单一定论 |
| Phase 4 断言 1 星号 | spec §13 "0.7\* / 0.4\*" 星号无脚注，疑似残留 | 随 P0-1 公式修正一并清理 |

---

## 五、值得肯定的决策（无需改动）

- **Q1**：用 character_id 作 URL 参数，绕开"无 friend_id 单查接口"的约束，get_or_create 幂等且返回 character 全字段，三条进入路径统一；
- **Q2**：会话切换 `router.replace` 同步 URL，同时满足"刷新/分享可用"与"不污染历史栈"；
- **`:key` 重建 + processId 双保险**：会话切换竞态防护符合 Vue 惯用法；
- **"虚拟列表不需要"**：论证有依据（个人陪伴场景百级消息 + 哨兵分页 + 轻量 Message 组件）；
- **D-L5**：markdown 流式结束后一次性渲染，避免逐 token 解析闪烁；
- **D6**：语音识别结果回填确认，取代"识别即发送"，修复 ASR 误识别不可挽回的现状问题；
- **rAF 滚动节流 + seq 令牌防采样竞态**：实现点正确；
- **Q4**：citations 四元组携带原文，顺带修掉"前端未消费 citations"的已知技术债。

---

## 六、后续动作建议

1. **立即**（进入 Phase 1 前）：修正 P0-1 蒙层公式（四处同步）、P0-2 对比度断言（二选一）；
2. **Phase 1 前**：P2 五项拍板（路由拆两条、dev 跨域约定、useMediaQuery 落地方式、no-scrollbar 全局化）；
3. **后端批次开发前**：P1-3 断连落库覆盖方案写入 LD §14.2、P1-4 spec 回写后端批次；
4. 其余内容可按 LD §14.3 实施顺序推进。

---

## 七、修订后复核记录（2026-09-07 二次评审）

### 7.1 修复确认表（逐项验算通过 ✅）

| 原问题 | 修订位置 | 验算结论 |
|--------|----------|----------|
| P0-1 公式方向 | design.md §6.2、spec §6.5、spec §13 Phase 4 断言 1、LD §3.10、LD §9.2 | `K = clamp(0.6 + (avg-0.5)×1.8, 0.6, 1.5)`：avg=0.9→1.32、avg=0.1→0.6、avg=0.5→0.6，五处数值一致、方向正确 ✅ |
| P0-2 气泡对比度 | spec §6.1/§6.6、LD §3.10/§8.2/§9.2 | `resolveUserBubble` 阶梯寻档机制成立；引用数值验算：#10b981 白字 2.54 ✓、#10b981@70% 4.82（文档 4.85，量级一致 ✓） |
| P1-3 断连落库 | LD §14.2 | `_collect_citations` 无条件收集 + `_stream_llm_only` 补 `_output_buffer/_output_usage/_has_error` + 新增降级路径断连测试，覆盖完整 ✅ |
| P1-4 spec 回写 | spec §10 表 + §10.1 + Phase 2 断言 3/5 | 回写完整，断言已标注依赖 §10.1 ✅ |
| P2-1 路由拆两条 | LD §3.12/§13 Q7/§14.1 | `/chat/` + `/chat/:character_id/`，不再依赖可选参数语法 ✅ |
| P2-2 dev 跨域 | LD §11 风险表 | 约定 + `DJANGO_CORS_ORIGINS` 白名单方案 ✅ |
| P2-3 useMediaQuery | LD §3.1 + §10 Phase 1 清单 | 新增 `useMediaQuery.js`（matchMedia 封装）✅ |
| P2-4 no-scrollbar | LD §10 全局节 | 迁移至 main.css 全局 ✅ |
| 停止生成措辞 | spec §5.3 | 统一为"保持已有文本、不加标记" ✅ |
| Phase 4 断言星号残留 | spec §13 | 已重写为公式值断言 ✅ |

### 7.2 残留问题（修订后新发现）

**R1【P1】spec 路由口径未同步 Q1/Q2，全文仍是 friend_id**

LD 已拍板：路由参数 = `character_id`（两条路由）、会话切换 `router.replace` 同步 URL、状态全由路由参数派生。但 spec（设计事实源）仍是旧口径：§5.1 `path: /chat/:friend_id/`、§5.3 `activeFriendId（路由参数）`、§7 `router.push('/chat/'+friend.id)` 与"`friend_id` 变化时重建 ChatWindow（`:key="friend.id"`）"、§13 Phase 1 断言 1 `/chat/:friend_id/`、E1"friend_id 无效"。下游以 spec 实施会实现错参数（friend_id 无法直达恢复，正是 F1 发现的约束）。**修复：spec 全文 friend_id → character_id，并补两条路由与 replace 语义。**

**R2【P1】"蒙层保证 ≥4.5:1"的全域断言仍未成立（AI 气泡是短板）**

spec §12 / E3 仍承诺窗口内文字全域 ≥4.5:1。按新公式对纯白图（K=1.32）验算：
- 顶部渐变停点 alpha = 0.25×1.32 = 0.33，白图压暗后 bg≈rgb(171)，白字对比度 ≈2.3:1；
- 消息区顶部（头部条下方第一屏）≈2.6:1；
- 中下部（alpha≈0.56）≈4.9:1 ✅——**只有中下部达标**；
- 更糟的是 AI 气泡是 `rgba(255,255,255,0.15)` **增亮**玻璃：叠在白图顶部区域 ≈**2.0:1**。

建议二选一：
1. **推荐**：AI 气泡玻璃由 white/15 改为 `rgba(0,0,0,0.35)+blur`（黑色乘法合成，叠在渐变蒙层之上）：纯白图顶部 ≈5.0:1、中下部 ≥7:1，全域达标，且无需加深顶部渐变、不损人像构图；
2. 或将 spec §12/E3 断言改写为分级承诺："头部/输入栏/己方气泡 ≥4.5:1；AI 气泡+蒙层 ≥3:1，极端亮图以简约模式兜底"。

**R3【P2】spec §6.1 `--overlay` 数值与命名残留**

`--overlay | 0.35~0.70` 是旧公式的范围（新范围 0.6~1.5）；且 spec §6.1/§6.2 用 `--overlay`、§6.3 与 LD 用 `--overlay-k`，双命名并存。统一为 `--overlay-k`（0.6~1.5）。

**R4【P2】spec §8.2 用户气泡残留旧描述**

仍写"`--bubble-user`（accent 85% + 黑）+ 白字"，与 §6.1 的 `resolveUserBubble` 阶梯机制矛盾。改为"`--user-bubble-bg`（resolveUserBubble 解析结果，§6.1）"。

**R5【P2】LD §3.10 消费行漏注入 `--user-bubble-bg`**

`useBackgroundAdaptive` 返回了 `userBubbleBg`，LD §8.2 声称运行时注入 accent/overlay/user-bubble-bg 三者，但 §3.10 消费行只写 `:style="{'--overlay-k': ..., '--accent': ...}"`。补上第三个变量。

**R6【P2】LD §9.2 黄色用例数值错误（实现该单测会失败）**

用例断言：`rgb(250,200,50)` 在 60/50 档仍 <4.5 → 回退 `#10b981`@70%。实测（WCAG 公式）：
- @70% → 3.18:1（<4.5 ✓）
- @60% → 4.20:1（<4.5 ✓）
- **@50% → 5.66:1（≥4.5 ✗，断言与计算相反）**

且由于 accentFallback 先过滤亮度（L∈[0.15,0.85]），50% 档数学上恒达标（sRGB 半混后 L ≤ 0.19×0.85 = 0.161 < 0.183 阈值），**"全部不达标回退"分支实际不可达**。修正建议：用例改为断言"黄色 → 解析到 50% 档（≈5.66）"，并把回退分支在 spec §6.1 中标注为理论兜底。

**R7【P3】LD §4.3 残留矛盾**

步骤 2 "activeCharacterId = characterId" 与 Q2 拍板（状态全部由路由参数派生、不维护内部状态）冲突，删除该步骤。

**R8【P3】design.md 非权威残留（可接受，建议加声明）**

§4 路由仍是 friend_id、§6.2/§6.3 气泡仍是 85%、§12 开放问题未标注已拍板。建议头部加一句"评审版口径以 spec-for-llm.md 为准，§12 问题已在 LD §13 全部拍板"，避免后人误读。

### 7.3 复核结论

P0 级问题全部关闭；R1/R2 为 P1 级，建议在进入 Phase 1 前修复（R2 推荐方案仅改一行气泡玻璃色值，成本极低）；R3~R8 为文档一致性修正，可随下次编辑顺手完成。修复后三份文档可作为实施基线。

### 7.4 三次复核（2026-09-07，R1~R8 关闭确认）

| # | 修复确认 | 状态 |
|---|----------|------|
| R1 | spec §5.1 两条路由（`/chat/` + `/chat/:character_id/`）、§5.3 activeCharacterId 改 computed 派生、SessionList emits 改 characterId、§7 全表 character_id + replace、§13 Phase 1 断言 1、E1 全部同步 | ✅ 关闭 |
| R2 | spec §6.1 `--bubble-ai` 改 `rgba(0,0,0,0.35)` 深色玻璃；§12 分级断言（正文 ≥4.5 / 次要 ≥3）；LD §8.2 `--color-bubble-ai` 同步。验算：纯白图顶部区域 AI 气泡内白字 ≈5.0:1 ✓ | ✅ 关闭 |
| R3 | spec §6.1 `--overlay-k`（0.6~1.5，停点 0.25K~0.60K）；§6.2 舞台叠加统一用 `var(--overlay-k)` | ✅ 关闭 |
| R4 | spec §8.2 用户气泡改 `--user-bubble-bg`（resolveUserBubble 解析结果，§6.1） | ✅ 关闭 |
| R5 | LD §3.10 消费行注入 `--overlay-k / --accent / --user-bubble-bg` 三变量 | ✅ 关闭 |
| R6 | LD §9.2 黄色用例修正：70% 3.18 / 60% 4.20 不达标、50% 档 5.66 达标不回退；spec §6.1 回退分支标注"理论兜底（L∈[0.15,0.85] 下 50% 档恒达标）" | ✅ 关闭 |
| R7 | LD §4.3 删除 activeCharacterId 赋值步骤，切换 = replace → watch → loadFriend | ✅ 关闭 |
| R8 | design.md 头部加 ⚠️ 声明：实施口径以 spec 为准、§12 问题已在 LD §13 拍板、§4/§6.2/§6.3 数值未随修订同步 | ✅ 关闭 |

**剩余问题（三次复核新发现，均不阻塞 Phase 1）：**

**N1【P2】最后一个对比度数学缺口：组首名字与白色玻璃面在纯白图顶部区域仍不达标**

R2 修复后，**气泡内**正文已全域 ≥4.5:1。但仍有三个"无底衬/增亮玻璃"元素位于蒙层之外，纯白图（K=1.32）+ 窗口顶部区域（渐变 alpha≈0.37）下验算：

| 元素 | 最差对比度 | spec §12 要求 | 判定 |
|------|-----------|--------------|------|
| 组首名字（14px，半透明白，无底衬） | ≈2.0~2.6:1 | 正文 ≥4.5:1 | ❌ |
| 日期胶囊（bg-white/10 + text-white/60） | ≈1.7:1 | 次要 ≥3:1 | ❌ |
| 引用 chips（bg-white/15 + text-white/90） | ≈2.0:1 | 次要 ≥3:1 | ❌ |

根因与 AI 气泡同源：白色玻璃是**增亮**方向。修复（三处小改，与玻璃体系一致）：
1. 组首名字加 `bg-black/30 rounded-full px-2` pill 底衬；
2. 日期胶囊改 `bg-black/25`；
3. 引用 chips 改 `bg-black/25`。

或接受边缘场景（仅"近纯白背景 + 窗口顶部 35% 区域"触发），把 spec §12 断言收敛为"气泡内正文 ≥4.5:1；其余元素 ≥3:1，极端亮图顶部区域以简约模式兜底"。

**N2【P3】spec §5.3 与 LD §4.3 会话切换时序顺序不一致**：spec 写"select → get_or_create → replace"；LD 写"replace → route watch → loadFriend"。角色 404 时行为不同（spec 留在原会话，LD 进入新 URL 错误页）。建议统一为"get_or_create 失败则不 replace"（两者取长）。

**N3【P3】spec E3 措辞**："亮度自适应（§6.5）保证文字 ≥4.5:1" 未提及深色 AI 气泡的贡献，应与 §12 口径对齐（气泡 + 蒙层共同保证）。

**N4【P3】spec §5.3 ChatIndex 职责仍写"window.resize 时重算窗口尺寸"**，与 LD F8（纯 CSS 实现、无需 JS resize）矛盾，删去该职责。

### 7.5 三次复核结论

两轮修订全部落地且无新增数值错误；N1 是 spec §12 无障碍断言与视觉 token 之间的最后一个数学缺口（三处小改或一句断言收敛即可关闭），N2~N4 为措辞级。**三份文档现已可作为 Phase 1 实施基线；建议 Phase 2 消息打磨时一并处理 N1，Phase 1 期间仅需按 N2~N4 微调 spec 文本。**
