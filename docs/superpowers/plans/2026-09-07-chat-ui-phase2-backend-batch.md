# 聊天改版 Phase 2 + 后端批次（Q3/Q4）Implementation Plan

> 状态：待执行
> 前置：PR #34 已合并 master（71e941a）；本计划从 master 切 `feature/gqyin/chat-ui-redesign-phase2`
> 事实源：`2026-09-07-chat-ui-redesign-spec-for-llm.md`（spec）+ `2026-09-07-chat-ui-redesign-logic-design.md`（LD §14.2/§10/§9）+ `2026-09-07-chat-ui-redesign-review.md`（P1-3/P1-4/R2/N1 细节）
> 顺序：**Step A（后端批次）先行**（Phase 2 前端消费 created_at/citations 新字段），A 部署验证后再上 B；A/B 均为向后兼容改动，必要时可合并一次部署。

---

## Step A — 后端批次（Q3/Q4）

### Task A1：Message.citations 字段 + migration 0022

**Files:**
- Modify: `backend/web/models/friend.py`

- [ ] **Step 1：Message 增加字段**

在 `Message` 模型中 `total_tokens` 之后增加：

```python
citations = models.JSONField(default=list, blank=True,
                             help_text='RAG 引用来源: [{index,title,chunk_index,content}]')
```

- [ ] **Step 2：生成迁移**

Run: `cd backend && python manage.py makemigrations web --name add_message_citations`
Expected: 生成 `0022_add_message_citations.py`，仅含 AddField citations。

- [ ] **Step 3：提交**

```bash
git add backend/web/models/friend.py backend/web/migrations/0022_add_message_citations.py
git commit -m "feat(message): Message 增加 citations JSONField（Q3/Q4 后端批次）"
```

### Task A2：chat.py citations 提取/收集/落库/下发 + 降级路径修复

**Files:**
- Modify: `backend/web/views/friend/message/chat/chat.py`

- [ ] **Step 1：抽取 `extract_citations(tool_content)`**

模块级纯函数，替换 `tts_sender` 与 `_stream_llm_only` 两处重复的 CITATION_RE 提取：

```python
def extract_citations(tool_content: str) -> list[dict]:
    """从 ToolMessage 内容解析 [来源N: 标题 第M段] 块，返回四元组列表（含原文）。"""
    citations = []
    for block in re.split(r'\n(?=\[来源\d+: )', tool_content):
        block = block.strip()
        if not block:
            continue
        m = CITATION_RE.search(block)
        if not m:
            continue
        content = block[m.end():].strip()          # 标记行之后的正文 = 检索 chunk 原文
        citations.append({
            'index': int(m.group(1)),
            'title': m.group(2),
            'chunk_index': int(m.group(3)),
            'content': content,
        })
    return citations
```

- [ ] **Step 2：`_collect_citations(msg)` 无条件收集（review P1-3）**

`MessageChatView` 内方法（或直接内联两处）：`self._citations = extract_citations(msg.content)`——**不受 cancel_event 门控**，断连路径也必须可用。

- [ ] **Step 3：SSE citations 事件携带 content**

`tts_sender` 与 `_stream_llm_only` 中，`mq.put_nowait({'citations': citations})` 的 citations 改为四元组（Step 1 产物），向后兼容（旧前端忽略 content 字段）。

- [ ] **Step 4：正常路径落库**

`event_stream` 的 `Message.objects.create(...)` 增加 `citations=getattr(self, '_citations', [])`（worker 线程已先写成员变量，queue None 哨兵保证 happens-before）。

- [ ] **Step 5：断连路径落库（C2）**

`work()` 断连分支的 `Message.objects.create(...)` 同样增加 `citations=getattr(self, '_citations', [])`。

- [ ] **Step 6：修复 _stream_llm_only 断连丢消息既有缺陷（review P1-3）**

`_stream_llm_only` 补成员收集（与 tts_sender 对齐）：循环前 `self._output_buffer = []`、`self._output_usage = {}`、`self._has_error = False`；每个 `BaseMessageChunk` 无条件 `self._output_buffer.append(msg.content)`、usage_metadata 写入 `self._output_usage`。使 TTS 配额耗尽降级路径在断连时消息仍可落库（work() 的 `if output and friend and message` 分支生效）。

- [ ] **Step 7：提交**

```bash
git add backend/web/views/friend/message/chat/chat.py
git commit -m "feat(chat): citations 四元组提取/无条件收集/双路径落库；修复降级路径断连丢消息"
```

### Task A3：get_history 返回 created_at + citations

**Files:**
- Modify: `backend/web/views/friend/message/get_history.py`

- [ ] **Step 1：序列化补字段**

每条消息 dict 增加：

```python
'created_at': message.created_at.isoformat(),
'citations': message.citations,
```

- [ ] **Step 2：提交**

```bash
git add backend/web/views/friend/message/get_history.py
git commit -m "feat(history): get_history 返回 created_at 与 citations（向后兼容）"
```

### Task A4：后端测试

**Files:**
- Modify: `backend/web/tests/test_chat_agent.py`、`backend/web/tests/test_retrieval_trace.py`、`backend/web/tests/test_friend.py`（或新建 `test_message_citations.py`）

- [ ] **Step 1：extract_citations 单测**

用例：多块解析（2 个来源块 → 2 条四元组，content=标记行后正文）；无标记文本 → []；空串 → []；块间空行不影响；标题缺省时 title 为空串（沿用现状）。

- [ ] **Step 2：SSE citations 事件含 content**（现有 mock 流扩展断言）

- [ ] **Step 3：保存路径落库断言**

正常路径：mock astream 产出含 ToolMessage 的流 → 断言 `Message.citations == extract_citations(工具内容)`；断连路径（cancel_event set）→ 同样断言。

- [ ] **Step 4：降级路径断连落库（review P1-3 新增用例）**

TTS 配额耗尽（check_quota 返回 False）+ 断连 → 断言消息仍落库且含 citations。

- [ ] **Step 5：get_history 序列化断言**

创建带 citations 的 Message → 调 get_history → 断言 created_at ISO 与 citations 返回。

- [ ] **Step 6：全量回归**

Run: `cd backend && python -m pytest web/tests/ -v`
Expected: 全部 PASS（221 + 新增）。

- [ ] **Step 7：提交**

```bash
git add backend/web/tests/
git commit -m "test(chat): citations 落库/提取/降级路径断连 + get_history 新字段用例"
```

### Task A5：部署与验收

- [ ] **Step 1：镜像构建 + 推送**

Run: `ACR_IMAGE=crpi-2ltqkeifvac3nlun.cn-shanghai.personal.cr.aliyuncs.com/gqyin-sh/gqyin-docker:latest ./deploy/build.sh`

- [ ] **Step 2：服务器升级 + 验收**

服务器 `./deploy/server-deploy.sh` → 浏览器聊天产生 RAG 引用 → 刷新页面 → 历史消息"📖 N 条参考来源"仍在；`docker compose exec django python manage.py shell` 验证 `Message.objects.first().citations` 非空。验收通过后合并 `feature/gqyin/chat-ui-redesign-phase2` 到 master（PR #35）。

---

## Step B — Phase 2 前端（消息打磨）

> 依赖 Step A 已部署（否则历史消息无 created_at/citations，仅新会话消息有引用）。本地开发可直接对 A 的本地后端验证。

### Task B1：vitest 基建（Q5）

**Files:**
- Modify: `frontend/package.json`、`package-lock.json`
- 新增: `frontend/vitest.config.js`（或零配置）、`frontend/src/utils/__tests__/`

- [ ] **Step 1：安装依赖**（在 frontend/）

Run: `npm install -D vitest jsdom`
（npmmirror 已配 Dockerfile；本地 npm 走你现有网络）

- [ ] **Step 2：package.json scripts 增加** `"test:unit": "vitest run"`

- [ ] **Step 3：提交**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(frontend): 引入 vitest + jsdom（Q5 拍板）"
```

### Task B2：chatFormat.js 纯函数 + 单测

**Files:**
- 新增: `frontend/src/utils/chatFormat.js`、`frontend/src/utils/__tests__/chatFormat.test.js`

- [ ] **Step 1：实现**（LD §9.2 契约）

`groupMessages(history)`（同 role 连续且时间差 ≤5min 一组，首条恒组首；无 time 的历史消息按时间差 0 处理）、`dateLabel(prev, cur)`（今天/昨天/M月D日）、`formatTime(iso)`（HH:mm）。

- [ ] **Step 2：单测**（用例见 LD §9.2 表）

- [ ] **Step 3：提交**

```bash
git add frontend/src/utils/chatFormat.js frontend/src/utils/__tests__/chatFormat.test.js
git commit -m "feat(chat): 消息分组/日期/时间纯函数 + 单测"
```

### Task B3：空态 + 示例问题（quickSend 激活）

**Files:**
- Modify: `frontend/src/components/character/chat_field/chat_history/ChatHistory.vue`

- [ ] **Step 1：空态渲染**：`!initialLoading && !hasMessages && history.length===0` → 居中 `character.introduction`（text-white/90 text-lg）+ 3 个示例问题胶囊（D7 文案："介绍一下你自己吧"/"讲个今天发生的故事"/"和我聊聊最近的烦恼"），点击 `emits('quickSend', q)`（ChatWindow 已接 `@quickSend="sendMessage"`，无需改）。

- [ ] **Step 2：验收**：新好友进入 → 空态显示；点示例问题 → 直接发送并走流式。

- [ ] **Step 3：提交**

```bash
git add frontend/src/components/character/chat_field/chat_history/ChatHistory.vue
git commit -m "feat(chat): 新会话空态 + 示例问题快捷发送"
```

### Task B4：分组/日期胶囊/hover 时间/引用 chips

**Files:**
- Modify: `frontend/src/components/character/chat_field/chat_history/ChatHistory.vue`、`chat_history/message/Message.vue`

- [ ] **Step 1：ChatHistory 接入 chatFormat**：`groupMessages(history)` 派生 `showHeader` 与 `dateLabel`（时间差规则替换 Phase 1 仅 role 变化版本；dateLabel 在组首消息前渲染胶囊）。

- [ ] **Step 2：Message 渲染**：props 增加 `dateLabel`；hover 时间（`opacity-0 group-hover:opacity-100` 显示 formatTime(message.time)，无 time 不渲染）；引用 chips 替换 collapse——横排 `bg-black/25 backdrop-blur text-white/90 rounded-full px-2.5 py-1 text-xs`（N1），点击弹出浮层显示 `content` 原文（限高 40vh 滚动 + 点击外部关闭）；`c.title || '系统知识库'` 与 `第 chunk_index+1 段` 展示。

- [ ] **Step 3：单测补充**（groupMessages 时间差规则、dateLabel 边界）。

- [ ] **Step 4：提交**

```bash
git add frontend/src/components/character/chat_field/chat_history/
git commit -m "feat(chat): 完整分组 + 日期分隔 + hover 时间 + 引用 chips（原文浮层）"
```

### Task B5：markdown 渲染（marked + DOMPurify）

**Files:**
- Modify: `frontend/package.json`、`frontend/src/components/character/chat_field/chat_history/message/Message.vue`
- 新增: `frontend/src/utils/__tests__/markdown.test.js`

- [ ] **Step 1：安装依赖**

Run: `cd frontend && npm install marked dompurify`

- [ ] **Step 2：渲染时机（D-L5 修订 2026-09-08）**：**边流边渲染**——AI 消息 `computed(() => DOMPurify.sanitize(marked.parse(content)))` 常算（`renderedHtml`），无「流式期间纯文本、结束时一次性渲染」的触发；用户消息纯文本 `pre-wrap`（仅 AI 回复走 markdown）。复制按钮按 content 变化重挂（幂等）。历史消息挂载即渲染；遗留 `rendered` 标志已无消费方，随 Phase 3 清理。

- [ ] **Step 3：白名单与代码块**：DOMPurify ALLOWED_TAGS 白名单（strong/em/ul/ol/li/code/pre/blockquote/a/br/h1~h4/p），禁止 img；pre 块右上角复制按钮（navigator.clipboard + toast 反馈）。

- [ ] **Step 4：XSS 单测**（@vitest-environment jsdom）：含 `<script>`/`<img onerror>` 的 marked 输出经 DOMPurify 后剥离。

- [ ] **Step 5：提交**

```bash
git add frontend/
git commit -m "feat(chat): markdown 渲染（marked+DOMPurify 白名单）+ XSS 单测"
```

### Task B6：验收 + 部署

- [ ] **Step 1：单测 + 构建**

Run: `cd frontend && npm run test:unit && npm run build`

- [ ] **Step 2：手工清单**（spec Phase 2 断言 1~6）：空态/示例问题、分组与 5min 规则、日期胶囊、markdown 列表/代码块/复制、引用 chips 原文、XSS 剥离、思考中/流式状态。

- [ ] **Step 3：镜像重建 + 部署 + 云上验收**（同 Task A5 流程）。

- [ ] **Step 4：合并 PR（#35 或后续 PR）→ master，删除分支。**

---

## 风险与回滚

| 风险 | 缓解 |
|------|------|
| 新依赖 lock 变化 → Docker npm ci 重跑（5~6 分钟） | B1/B5 分两次装依赖；构建层缓存策略已知 |
| citations 正则对异常 ToolMessage 内容健壮性 | extract_citations 纯函数 + 单测覆盖空/无标记/多块 |
| _stream_llm_only 收集改造引入回归 | A4 Step 4 专门断连用例 + 全量 pytest |
| 后端批次与旧前端兼容 | 全部增量字段；旧前端忽略新字段，无破坏 |
| 日期分组对无 time 历史消息的行为 | chatFormat 将 time 视为 0（同组），行为确定性单测锁定 |
