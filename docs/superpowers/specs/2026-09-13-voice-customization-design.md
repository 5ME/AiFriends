# 音色自定义（一期）设计文档

**日期**：2026-09-13
**分级**：L（跨层：DB + 后端 + 前端；含新接口与新外部依赖）
**状态**：门 1 已通过（2026-09-13）。本文档待用户评审，通过后进入 writing-plans 出实施计划。
**范围**：一期。二期（公开共享）不在本文档内，且被合规工单结论阻塞。

---

## 1. 背景

### 1.1 现状

音色是平台级预置资源。`Voice`（`backend/web/models/character.py:21`）只有 `name` / `voice_id` / `profile` / `is_builtin` 四个业务字段；`Character.voice`（同文件 `:39`）是一个可空外键。音色来源只有两条：`seed_builtins` 内置的两个（`longanyang` 龙安洋、`longanhuan` 龙安欢，`backend/web/management/commands/seed_builtins.py:25-28`，落库在 `:91-94`），以及管理员在 Django Admin 手工录入（`backend/web/admin.py:21` 是裸注册，无校验）。

创建角色时前端拉全量音色列表（`backend/web/views/create/character/voice/get_list.py:18`，无条件 `order_by('id')`），下拉框默认选中第一项，提交的是 **`Voice` 表主键**。音色真正被消耗只有一处：聊天时读出阿里云音色标识透传给 TTS（`backend/web/views/friend/message/chat/chat.py:233` → `:422`）。

线上实查：3 个音色（2 个内置 + 1 个管理员录入的「观音菩萨」）、3 个角色、无音色为空的角色。那个音色已用 `action=query_voice` 实测确认：`status` 为 `OK`、`target_model` 为 `cosyvoice-v3-flash`、创建于 2026-04-19；而同一个接口对内置音色 `longanyang` 返回 `BadRequest.ResourceNotExist` —— **该接口只覆盖复刻音色，所以"观音菩萨"能被查到这件事本身就证明了它是复刻产物**，先前只能算推断。同时这也证实 `VOICE_URL` + `API_KEY` 两个环境变量已经可用（`.env.example:7,9,10`），阿里云侧调用不需要新增配置。

### 1.2 已发现的问题

| 类别 | 具体问题 | 影响 |
|---|---|---|
| 数据完整性 | `Character.voice` 的 `on_delete=CASCADE` | 删一个正被使用的音色会**级联删除所有用它的角色**。用户自建音色上线后，这会变成用户可触发的破坏 |
| 数据完整性 | `Voice.voice_id` 无格式校验 | 管理员填错只能等到聊天时静默降级为纯文本 |
| 错误语义 | `create.py:44` / `update.py:43` 的 `Voice.objects.get(id=...)` 在 try 块内 | 非法或缺失的音色标识返回 **500** 而非 400 |
| 错误语义 | `update.py:31` 用 `request.data['voice_id']` 直接下标 | 缺字段抛 KeyError → 500 |
| 空值处理 | `backend/web/views/create/character/get_single.py:41` 的 `character.voice.id` 无判空 | 角色音色为空时 **500**（对比 `chat.py:233` 有判空） |
| 命名 | API 参数 `voice_id` 指 `Voice` 主键，DB 字段 `Voice.voice_id` 指阿里云标识 | 一名两义，后续功能会持续踩 |
| 可用性 | 列表返回 `profile` 但前端从不渲染（`frontend/src/views/create/character/components/Voice.vue:21` 只显示 `name`）；**没有试听** | 选音色只能靠名字猜。本期补试听**并补 `profile` 渲染** |
| 重复代码 | `voice/get_list.py:18-25` 与 `create/character/get_single.py:24-31` 有 8 行逐字节相同的序列化逻辑 | 改一处漏一处 |

### 1.3 已登记但不在范围内的相邻问题

- `backend/web/views/create/character/voice/custom/` 下三个文件是阿里云声音复刻（voice-enrollment）接口的封装，来自 2026-04-21 的提交 `a10e60e`，**从未接线**（无 import、无 URL 路由、无前端）。本期以正式实现替代它们，**这三个文件在 D 批删除**。
- `create.py:21` 的 `request.data.get('name').strip()` 与 `update.py:20` 的 `request.data['character_id']` 是同类 500 风险，但不属音色范围，本期不修。

---

## 2. 目标与非目标

### 2.1 目标

让用户能创建（复刻）属于自己的音色并用在**自己的**角色上；同时消除 §1.2 的全部问题，补上试听与音色描述（`profile`）的展示。

### 2.2 非目标（一期明确不做）

- 公开共享（发布给他人选用）—— 二期
- 举报、下架、内容审核工作台
- 使用者定义音色（每用户覆盖角色音色）
- 音色分类、标签、分页、搜索
- 演绎参数化（语速 / 音量 / 音调 / 情绪）
- 音色删除的「改绑到默认音色」流程 —— 一期用 `RESTRICT` 直接拒绝删除
- 阿里云侧音色的定期探活（见 §11 风险 3）
- 移动端专门适配

---

## 3. 关键决策

| # | 决策 | 结论 | 理由 | 代价 |
|---|---|---|---|---|
| D1 | 音色绑定层 | **创作者定义**，`Character.voice` 不动 | 角色是人格，声音是人格的一部分；且结构零改动 | 使用者不能按自己的听觉偏好换音色 |
| D2 | 一期范围 | **只做私有**，但归属字段一次立好 | 把「以后要改表」这笔债提前还掉；私有形态不涉及跨用户内容责任 | 两个一期不对外暴露的字段 |
| D3 | 删除语义 | **`RESTRICT`**（不是 `PROTECT`） | Django 文档：*Unlike PROTECT, deletion of the referenced object is allowed if it also references a different object that is being deleted in the same operation, but via a CASCADE relationship.* 用 `PROTECT` 会让「删除一个既有角色又有自建音色的用户」永远失败 | 无 —— 这是更精确的语义 |
| D4 | 命名统一 | 接口字段 `voice_id` → `voice`；DB 字段 `Voice.voice_id` 保持不变 | 消除一名两义；DB 字段确实指阿里云标识，语义本身没错 | 前端三处联动改动 |
| D5 | 样本存储 | **阿里云 OSS 私有 bucket + 短期签名 URL** | 复刻接口要求样本公网可访问，而自有服务器是自签证书（实测 `issuer=CN=8.153.201.12`），阿里云侧拉取会因证书不可信失败；走明文 HTTP 会让生物特征数据裸传；买域名配有效证书在大陆服务器需 ICP 备案，是数周流程 | **项目第一个新外部依赖**（`oss2` + 一组凭据 + 部署环境变量） |
| D6 | 样音生成 | **懒生成 + 永久缓存到 MEDIA** | 内置音色没有现成样音；生成一次后零成本。复用与聊天完全相同的 TTS 参数，保证「试听到的」等于「聊天听到的」 | 首次试听有 1~2 秒延迟。**文案里对音色名截断到 20 字符**，否则 TTS 成本随用户输入膨胀 |
| D7 | 复刻状态刷新 | **Celery Beat 周期任务**（每 5 分钟扫 `status='deploying'` 的行） | `CELERY_TASK_SOFT_TIME_LIMIT=120` / `TIME_LIMIT=180`（`backend/backend/settings.py:305-306`）叠加单并发 worker（`docker-compose.yml:65`，`-c 1` 且嵌入式 `-B`，文档处理与记忆总结共用这一个 slot）**不允许任何长时间轮询任务**；仓库已有 `CELERY_BEAT_SCHEDULE`（`settings.py:311`，每日 usage 清理）可直接沿用同一机制 | 状态最长有 5 分钟可见延迟 |
| D8 | 删除音色必须同步删阿里云侧 | **`remove` 先调 `action=delete_voice`，成功才删本地行** | 1000 个音色是**账号级共享**配额，阿里云不自动淘汰最早的，只删本地行会让配额只增不减；而 `voice/custom/delete_voice.py` 恰好是仓库里唯一的调用样板，它将在 D 批被删除 | 阿里云不可用时用户暂时删不掉（返回 503，可重试）。不采用"先删本地再补删"——那会在网络失败时静默泄漏配额，且丢掉 `voice_id` 再也补不回来 |

---

## 4. 数据模型

### 4.1 迁移 0023（A 批）

```python
# Character.voice
voice = models.ForeignKey(Voice, default=None, on_delete=models.RESTRICT,
                          blank=True, null=True)

# Voice.voice_id
voice_id = models.CharField(
    max_length=100,
    help_text="阿里云音色ID",
    validators=[RegexValidator(
        r'^[A-Za-z0-9][A-Za-z0-9_-]*$',
        '音色 ID 只能是字母、数字、下划线或连字符',
    )],
)
```

无数据迁移。字符集按线上三个真实标识反推（`longanyang`、`longanhuan`、`cosyvoice-v3-flash-guanyin-...` 均通过）。

校验器**只在表单 / Admin 路径生效**（`objects.create()` 不调用 `full_clean()`），而这正是要防的路径 —— 管理员手填。

### 4.2 迁移 0024（C 批）

```python
class Voice(models.Model):
    owner = models.ForeignKey('UserProfile', null=True, blank=True,
                              on_delete=models.CASCADE)
    visibility = models.CharField(max_length=10, default='private',
                                  choices=[('private', '私有'), ('public', '公开')])
    status = models.CharField(max_length=12, default='ready', choices=[
        ('ready', '可用'), ('deploying', '审核中'), ('rejected', '审核未通过'),
    ])
```

语义映射：

| 组合 | 含义 |
|---|---|
| `owner=None` + `is_builtin=True` | 内置音色（代码拥有） |
| `owner=None` + `is_builtin=False` | 管理员录入的平台音色 |
| `owner` 有值 | 用户自建 |

- `visibility` 一期只会取两个确定值：用户自建为 `private`，平台音色为 `public`
- `status` 只对用户自建音色有意义，平台音色恒为 `ready`
- **没有 `failed` 状态，也不新增 `error_message` 字段** —— 复刻**同步失败时不建行**（见 §6.2 步骤 7）。原因是失败时根本拿不到阿里云 `voice_id`，而 `voice_id` 是非空非空白的 `CharField`，硬塞一个占位值等于让这个字段说谎；异步才可能出现的失败态只有阿里云侧的 `UNDEPLOYED`，那时 `voice_id` 已经存在，正好就是 `rejected`。这样范围冻结不被打破，用户也不会在"我的音色"里看到一堆自己没造出来的失败行
- `owner` **不加 `db_index=True`** —— Django 外键自带索引

**0024 必须包含数据迁移**：存量音色全部设为 `visibility='public'`。否则默认值 `private` 会让线上现有的「观音菩萨」从所有用户的选择列表里消失 —— 这是行为回归。`seed_builtins` 同步更新为内置音色写 `visibility='public'`。

**不新增 `target_model` 字段**：当前合成模型固定为 `cosyvoice-v3-flash`，复刻时 `target_model` 也固定为它，存下来是冗余。代价登记在 §11 风险 5。

---

## 5. 接口契约变更

| 接口 | 变更前 | 变更后 |
|---|---|---|
| `GET /api/create/character/voice/get_list/` | `voices: [{id, name, profile}]`，全量无过滤 | `voices: [{id, name, profile, is_mine, status}]`，只返回 `visibility='public' OR owner=当前用户`。**列表不带样音 URL**（原设想的 `sample_url` 已取消）：前端点试听时直接调下面的 sample 端点，缓存命中即秒回；列表里再放一份 URL 只会多出"有 URL 直接播 / 没 URL 先请求"两条代码路径。列表接口**绝不触发合成** |
| `POST /api/create/character/create/` | 表单字段 `voice_id` = `Voice` 主键 | 表单字段 **`voice`** = `Voice` 主键。服务端校验：音色不存在或不属于自己且非公开 → **404**（沿用 `create/character/get_single.py:22` 的"不存在或无权"统一 404 的惯例，不暴露他人音色的存在性）；存在但 `status != 'ready'` → **400** |
| `POST /api/create/character/update/` | 同上 | 同上 |
| `GET /api/create/character/get_single/` | `character.voice_id` = `Voice` 主键 | `character.voice` = `Voice` 主键；`voices` 列表与 get_list 同规则 |
| **新增** `GET /api/create/character/voice/sample/?voice=<id>` | — | B 批。可见性校验同 get_list；不可见 → **404**；可见但 `status != 'ready'` → **400**（"还没得听 / 永远不会响"，必须与"合成失败"区分开）。命中缓存直接返回；未命中则合成、落盘、返回 `{message, url}`；**合成超时（5 秒）或失败 → 503**；记 `APIUsage(api_type='tts')` 且 `update_quota=False`（见 §6.1） |
| **新增** `POST /api/create/character/voice/clone/` | — | D 批，multipart：`file`（样本，≤8MB，见 §11 风险 8）、`name`（必填，≤100 与 DB 对齐）、`profile`（≤500，`TextField` 的 `max_length` 只在表单层生效，必须显式校验）。流程见 §6.2。成功 → `{message, voice: {id, status}}`；**阿里云明确拒绝**（样本不合格、敏感内容）→ **400** + 透传可读原因；**阿里云不可用 / 超时 / 未知错误 → 503**。两种情况都**不建行** |
| **新增** `POST /api/create/character/voice/remove/` | — | D 批。只能删自己的音色，别人的 → **404**；被任何角色引用 → **400** + 「该音色正被 N 个角色使用，无法删除」；**先调阿里云 `action=delete_voice`，成功才删本地行**，阿里云调用失败或**超时（5 秒）** → **503** 并保留行供重试（阿里云侧"音色不存在"视为删除成功） |

范围冻结：本期除上表外**不新增任何接口或字段**（包括 `error_message`，见 §4.2）。`create.py` / `update.py` / `get_single.py` 里重复的音色序列化逻辑抽成一个共用函数（消除 §1.2 的重复代码项）。

**状态码口径**（测试按此写断言，不要用"404/403"这类二选一的写法）：

- **404** 用于"这个音色对你来说不存在"——不存在、他人的私有音色。这是本仓库既有的惯例：`update.py:24` 对既不在你名下也不存在的 `character_id` 就返回 404。配套要求：**"不存在"与"无权"必须返回完全相同的 message**，否则 404 本身就成了存在性探测器。
- **400** 用于"音色对你是可见的，但当下不能用"——`status != 'ready'`、参数不合法（`name`/`profile`/文件）、配额超限、被角色引用所以不能删。
- **503** 用于"上游不可用或超时"，即错误不能归因于用户的请求。

---

## 6. 关键流程

### 6.1 试听

1. 前端在音色下拉框旁渲染播放按钮；点击 → `GET .../voice/sample/?voice=<id>`
2. 后端按 §5 的可见性规则校验；不可见 → 404；`status != 'ready'` → 400（不做无谓的合成尝试）；然后查缓存文件，命中即返回 URL
3. 未命中：用与聊天**完全相同**的 TTS 参数（`cosyvoice-v3-flash`、mp3、22050Hz、volume 50、rate 1.0、pitch 1，见 `chat.py:419-428`）向 DashScope WS 合成固定文案 → 收集完整音频 → 写入 `MEDIA_ROOT/voice_samples/` → 返回 URL。**连接与读取超时 5 秒**，超时按失败处理（见下方超时纪律）
4. 文案：`你好呀，我是<音色名>，很高兴认识你。`—— 遵循 `REPLY_PROMPT` 的格式约束（无 emoji、无符号、纯中文口语）。**音色名截断到 20 字符**（`Voice.name` 上限是 100，不截断等于让 TTS 成本跟用户输入走）
5. 缓存文件名：`<阿里云voice_id>-<样本文案hash>.mp3`，hash 用 `sha256` 取前 8 位（在 plan 里定死，不要留成实现细节 —— 否则缓存键会随实现漂移）。文案或音色变化即换文件名，避免被浏览器 30 天缓存误导
6. 前端用 `<audio>` 播放；同一时刻只允许一个试听在播 —— 用**模块级小单例**（照 `frontend/src/composables/useToast.js` 的惯例）。⚠️ **不要用 `frontend/src/utils/voiceState.js`**：那是麦克风/ASR 的状态机（`idle/listening/transcribing/confirm/vad_failed/mic_denied/asr_failed`，见该文件 `:3-11`），与音频播放无关
7. 交付路径已确认：`nginx.conf:23-24` 的 `location /media/` 对外提供 `/app/media/`

**实现方式（必须新写，不能复用现有代码）**：仓库里没有"一次性合成整句、拿回完整音频"的路径 —— `tts_sender`（`chat.py:446-575`）与 LangGraph app 硬耦合，接收侧只把分片塞进队列，没有拼接落盘的先例。因此 B 批要**新增一个一次性合成函数**，只复用 `chat.py:404-432` 的连接与首帧样板。为避免 TTS 协议参数出现两份魔法数字，把 `model / format / sample_rate / volume / rate / pitch` 抽成共用常量模块；**但不去重构 `tts_sender` 本身** —— 动聊天主链路的收益不抵风险。

**超时纪律（四个阻塞外部调用都要遵守）**：`sample` 的 TTS、`clone` 的 OSS 上传、`clone` 的 `create_voice`、`remove` 的 `delete_voice` 都在**请求路径**上，而 gunicorn 只有 `--workers 3`（`docker-compose.yml:40`）—— 一个挂死的上游连接就能吃掉整个服务的并发。因此四个调用一律设 **5 秒超时**，超时按"上游不可用"归入 503（配置类错误如 OSS 凭据不对才是 500）。注意 `voice/custom/` 那两份样板是 `requests.post(url=..., headers=..., json=...)`，**都没有 timeout**（`create_voice.py:20`、`delete_voice.py:18`），照抄会把这个问题复制进正式实现。Beat 任务那条"单条 3 秒"的纪律同理。

**记账与成本上界**：合成后记 `APIUsage(api_type='tts')`，并传 **`update_quota=False`** —— 这个开关已经存在（`backend/web/utils/usage.py:12`，docstring 写明"用于系统功能…用量仍写入 APIUsage 但跳过配额更新"），所以"记账但不扣用户配额"不需要动任何基础设施。试听是平台为"可发现性"付的成本。

成本上界：文案固定 + 永久缓存 ⇒ **"用户可见音色数"是合成次数的上界**。但有个例外必须处理：**失败不落盘**，所以一个 ready 音色的合成若持续失败，每次 GET 都会重新打阿里云 —— 而 `sample` 是 GET、不在限流表内。因此失败时写一个**短 TTL 的负缓存**（复用同一缓存目录，如 `<key>.fail`，60 秒内直接返回 503 不再重试），并保留 warning 日志便于事后发现。

### 6.2 复刻

1. 前端：上传样本 + 填名称/描述 + 勾选授权声明（「我确认这是本人声音，或已获得声音权利人授权」）
2. `POST .../voice/clone/`
3. 后端校验：文件类型（magic byte，沿用文档上传的既有做法）、大小 ≤8MB（见 §11 风险 8）、`name` 必填且 ≤100、`profile` ≤500、用户配额
4. 上传到 OSS 私有 bucket（**5 秒超时**）→ 生成短期签名 URL（有效期数分钟）
5. **先生成 `prefix` 并记入日志**（字母数字、≤10 字符），再调 `voice-enrollment`：`action=create_voice`、`target_model=cosyvoice-v3-flash`、`prefix`、`url`；从响应取阿里云 `voice_id`。**5 秒超时**
6. **无论成功失败，立即删除 OSS 对象**（`finally`）；样本不在平台本地留副本
7. 成功 → 建 `Voice(owner=自己, visibility='private', status='deploying')`；**同步失败 → 不建行**，直接返回错误 + 日志（含步骤 5 的 `prefix` 与原始错误），状态码按 §5 拆开：阿里云**明确拒绝** → 400 + 透传可读原因；**不可用 / 超时 / 未知** → 503。日志里的 `prefix` 有用：万一请求发出去了但响应丢了，阿里云侧可能留下一个孤儿音色，可以靠 `action=list_voice` 按 `prefix` 找出来
8. 状态刷新：**不做长轮询任务**（会撞上 §3-D7 的 120s/180s 硬上限并堵住单并发 worker）。改为 **Celery Beat 周期任务**，每 5 分钟用 `action=query_voice` 扫一批 `status='deploying'` 且 `created_at` 在 24 小时内的行，写回 `OK → ready` / `UNDEPLOYED → rejected`。单轮上限 20 条、单条超时 3 秒（最坏 60 秒，仍在软上限 120 秒内）、失败 fail-open 保留原状态
9. 前端复用既有轮询模式（参考 `frontend/src/composables/useDocumentPolling.js`）刷新列表，展示「审核中 / 可用 / 审核未通过」
10. 只有 `status='ready'`（即阿里云 `OK`）的音色才允许被角色选用

**删除（`remove`）**：只能删自己的音色 → 本地先判是否有角色引用（有 → 400 + 「正被 N 个角色使用」）→ 调阿里云 `action=delete_voice`（`custom/delete_voice.py:11-17` 的 payload 形状与官方文档一致，是现成样板；该文件在 D 批删除时其逻辑被正式实现吸收）→ 成功才删本地行；阿里云调用失败或**超时（5 秒）** → 503 并保留行。阿里云侧返回"音色不存在"（例如已被 1 年规则自动清理）视为删除成功。

**配额**：每用户上限 **5**（提议值，可改）+ 全平台总量告警阈值 **800**（防 1000 个账号级名额被吃满）。超限 → 400 + 可读提示。同步失败不建行，因此不占配额。

---

## 7. 错误处理

| 场景 | 行为 |
|---|---|
| 样本格式/大小不合要求 | 400，message 指明具体原因（前端先校验，后端兜底） |
| `name` / `profile` 不合法 | 400 |
| 配额超限 | 400 |
| OSS 超时或不可达 | **503**，不建 `Voice` 行，样本不留存 |
| OSS 凭据 / bucket 配置错误 | **500** + ERROR 日志（给运维看），不建行 |
| `create_voice` **明确被拒**（含 2038 无复刻权限、样本不合格、敏感内容） | **400** + 透传可读原因，**不建行**，日志含 `prefix` 与原始错误 |
| `create_voice` **不可用 / 超时 / 未知错误** | **503**，同样不建行 |
| 试听：音色不可见 | **404** |
| 试听：音色可见但 `status != 'ready'` | **400** + 「该音色尚不可用（审核中 / 审核未通过）」，不去打阿里云 |
| 试听：合成失败或超时 | **503** + 明确 message，不阻塞表单其余部分；失败写 60 秒负缓存 |
| 状态长时间停在 `deploying` | Beat 任务只扫 24 小时内的行；超期后保留最后已知状态并记 warning（登记为 §11 风险 9） |
| 阿里云返回 `UNDEPLOYED` | `status='rejected'`，明确告知不可用，允许删除 |
| 删除被角色使用的音色 | 400 + 「正被 N 个角色使用」（提前判断给出可读提示，不把 `RestrictedError` 暴露成 500） |
| 删除时阿里云调用失败或超时 | 503 + 「删除失败，请稍后重试」，**保留本地行**（保住 `voice_id` 以便重试，避免静默泄漏配额） |

统一遵守项目既有约定：不裸 `except`，一律 `except Exception as e:` + `logger.exception(...)`。

---

## 8. 安全与合规

- 样本是用户的声音（个人生物特征信息）：私有 bucket、短期签名 URL、复刻提交后立即删除、平台不持久化。**但第三方侧并未删除** —— 实测 `query_voice` 仍能拿到指向原始样本的签名链接（见风险 12）。因此对用户的隐私说明必须写成"样本会被提交给语音合成服务方用于复刻"，**不能写成"全链路已删除"**
- 授权声明：前端必须勾选，后端把声明写入日志。**一期不落库** —— 私有音色不涉及第三方；二期做公开共享时需要持久化的授权记录，届时再加字段
- 阿里云侧的 `DEPLOYING / OK / UNDEPLOYED` 审核作为唯一的内容审核来源，平台照实呈现，不做二次判断
- 账号级约束（已核实）：复刻权限绑定百炼账号认证状态（错误码 2038「无复刻权限，请检查账号认证状态」）；1000 个音色是**全账号共享**配额；单个音色 1 年内未被任何合成请求使用会被阿里云自动删除、不自动淘汰最早的
- **合规待确认（阻塞二期，不阻塞一期）**：《阿里云百炼服务特别说明》中「复刻完成后仅支持为体验目的使用；体验生成内容不得商业化或提供给第三方使用」的**适用范围未能从公开文档确认** —— 协议页是 JS 渲染，抓取两次均失败。已起草工单文本，待用户提交。
- 试听音频走的是公开的 `/media/`（无鉴权、`expires 30d`），与角色照片、对话背景是同一套做法，判定为可接受。**但"文件名不可枚举"只对复刻音色成立** —— `longanyang` 这类平台音色的 `voice_id` 是公开常量、样本文案模板也固定，只要 hash 算法已知文件名就可推导；这不构成问题，因为平台音色的样音内容本就不敏感，登记在此以免被误当成论据
- `sample` 是 GET，**不在现有写入限流覆盖范围内**：`RATE_LIMIT_RULES`（`backend/backend/settings.py:268-275`）按设计只覆盖 POST/PUT/PATCH/DELETE。可接受的理由见 §6.1 末尾的成本上界分析（含失败重试的负缓存）

---

## 9. 测试策略

本地命令（**已实测可用**）：

```
cd backend && D:/MyWork/Miniconda3/envs/py312/python.exe -m pytest web/tests/ -v
```

环境：conda `py312`（Django 6.0.2 / pytest 9.0.3），PG 在 `127.0.0.1:55432`（WSL 的 `ai-friends-db`，pgvector pg17）。
**基线已实测：`236 passed, 3 deselected in 9.87s`**。实施时以此为基准，不以文档数字为准。

### A 批（新增 9）

- **A1** create 传不存在的 `voice` → **404**
- **A2** create 不传 `voice` → **400**
- **A3** update 传不存在的 `voice` → **404**
- **A4** update 不传 `voice` → **400**
- **A5** create / update 传一个可见但 `status != 'ready'` 的音色 → **400**
- **A6** create / update 传他人的私有音色 → **404**，且 message 与 A1 的"不存在"**逐字相同**（否则 404 就成了存在性探测器）
- **A7** 角色音色为空时 `get_single` → 200 且 `character.voice` 为 `None`
- **A8** 删除被角色引用的 `Voice` → 抛 `RestrictedError` 且角色仍存在；删除无人使用的 `Voice` → 成功
- **A9** **删除一个既有角色又有音色的用户必须成功**（`RESTRICT` 语义守门，防 `PROTECT` 回归）

### B 批（新增 6）

- **B1** 首次请求样音 → 触发合成并返回 URL（mock DashScope WS），且写了 `APIUsage(api_type='tts')` 并带 `update_quota=False`
- **B2** 第二次请求同一音色 → 命中缓存，**不再触发合成**（以 mock 调用次数断言）
- **B3** 请求不可见音色的样音 → **404**；请求 `status != 'ready'` 的音色 → **400**（且不调用阿里云）
- **B4** 合成失败 → **503**；负缓存窗口内再次请求 → **不再打阿里云**（mock 调用次数断言）
- **B5** 合成超时（上游挂住）→ 5 秒内返回 **503**，不无限等待
- **B6** 前端（Vitest）：试听按钮渲染与播放调用；`profile` 文本被渲染出来

### C 批（新增 7）

- **C1** 列表只返回 `visibility='public' OR owner=自己`
- **C2** 用户 A 不能给自己角色选用用户 B 的私有音色 → **404**（与 A6 同源，从列表/选用两侧各断一次）
- **C3** `is_mine` 字段正确
- **C4** 数据迁移：存量音色迁移后仍可见（`visibility='public'`）
- **C5** `seed_builtins` 幂等测试同步更新（内置音色 `visibility='public'`）
- **C6** `status != 'ready'` 的音色不能被选用 → **400**
- **C7** 前端（Vitest）：非 `ready` 音色的播放按钮被禁用 —— 依赖 `status` 字段，随 C 批实现

### D 批（新增 11）

- **D1** 成功路径：上传 → 建行（`deploying`）→ Beat 任务查到 `OK` → `ready`
- **D2** **同步失败不建行**：阿里云明确拒绝时库里不新增任何 `Voice` 行，且返回 **400** + 可读原因
- **D3** 上游不可用 / 超时 → **503**，同样不建行
- **D4** `UNDEPLOYED` → `rejected`（异步失败路径，行已存在）
- **D5** Beat 任务：单轮只处理 `deploying` 且 24 小时内、上限 20 条；单条失败不影响其余；查不到变化的行保持原状态
- **D6** 配额超限 → 400
- **D7** 删除自己的音色：无人引用 → 调阿里云删除并删本地行；被角色引用 → 400 + 可读提示
- **D8** 删除时阿里云调用失败或超时 → 503 且**本地行保留**（可重试）；阿里云返回"不存在" → 视为成功删除本地行
- **D9** 删除别人的音色 → **404**
- **D10** 样本上限：>8MB 被拒；`name` >100 或缺失被拒；`profile` >500 被拒
- **D11** OSS 对象在成功、失败两条路径上都被删除；校验失败时样本不落 OSS

前端另有 Vitest 用例（现位于 `frontend/src/**/__tests__/`）。

---

## 10. 验收标准（门 1 定稿）

### A 隐患修正 + 命名统一（A+B 批）

- [ ] Admin 删除一个正被角色使用的音色 → 被拒绝并显示明确提示，该角色数据完好
- [ ] 不传 `voice` → **400**；传不存在的、或他人私有的 `voice` → **404**（两者的 message 必须逐字相同）
- [ ] 可见但 `status != 'ready'` 的音色 → **400**
- [ ] 角色音色为空时 `get_single` 返回 **200**
- [ ] Admin 保存非法 `voice_id` 被拒
- [ ] **删除一个既有角色又有音色的用户必须成功**
- [ ] `pytest web/tests/ -v` 全绿（基线 236）

### B 试听（A+B 批）

- [ ] 创建/编辑角色页每个音色旁有播放按钮，可试听、可停止、切换音色可再听
- [ ] 每个音色旁能看到它的 `profile` 描述（不再是只有名字）
- [ ] 样音只生成一次并缓存 —— 第二次请求不产生新的 TTS 调用（mock 计数证明）

### C 归属模型（C 批）

- [ ] 用户能区分「我的音色」与「平台音色」
- [ ] 用户 A 无法给自己角色选用用户 B 的私有音色（伪造 `voice` → **404**）
- [ ] `status != 'ready'` 的音色不能被选用（→ **400**）
- [ ] `deploying` / `rejected` 的音色，试听按钮是**禁用**的（点了不响，也不该冒出一个"合成失败"）
- [ ] 平台音色（含存量的「观音菩萨」）对所有用户仍可见、可选

### D 复刻接线（D 批）

- [ ] 上传样本 → 复刻 → 音色出现在「我的音色」里，状态可见（审核中 / 可用 / 审核未通过）
- [ ] 复刻出的音色能用到自己的角色上，聊天时听到的确实是它
- [ ] 每用户限额生效，超限被明确拒绝
- [ ] 样本清理可查：成功与失败两条路径下 OSS 对象都已删除（以 OSS 侧对象列表为空证明）
- [ ] 删除音色后：平台侧不再可见、角色无法再选它、**阿里云侧已同步删除**（以百炼控制台音色列表、或调用 `action=list_voice` 后不再出现该 `voice_id` 证明）

---

## 11. 风险与未决项

1. **合规工单**（阻塞二期）：适用范围未确认，已起草工单文本待提交。若结论为「不可」，二期需重新设计；一期不受影响。
2. **OSS 凭据与 bucket 尚不存在**：需要用户去阿里云控制台创建（建议私有 bucket、与 ECS 同地域）并提供 AccessKey；部署要新增环境变量。**这是开工 D 批的前置条件**。
3. **阿里云 1 年自动删除音色**：一期不做探活。理由：音色数量小、影响滞后 1 年、且 `chat.py:443` 已有 TTS 失败 warning 日志可查。二期补。
4. **`/media/` 的 `expires 30d`**：缓存文件名含样本文案 hash，文案变化即换名，不会被浏览器缓存误导。
5. **未存 `target_model`**：若将来更换合成模型，已复刻的音色会因模型不匹配而合成失败（阿里云要求 `target_model` 与合成模型一致），届时需重新复刻或迁移。
6. **样本质量无法在服务端充分校验**：时长、信噪比、是否有背景音等要求只能靠前端提示 + 阿里云返错。**D 批前置检查**：用控制台或实测确认 `cosyvoice-v3-flash` 的样本时长/大小档位，并把前端提示与之对齐 —— 官方使用指南把"推荐 10~20 秒、最长 60 秒、≤10MB、≥16kHz、WAV(16bit)/MP3/M4A"这组要求挂在 Qwen-Audio-TTS / Qwen-Audio-Realtime / **CosyVoice** 三系列之下，**未单独区分 v3-flash**（v2 系列是另一组档位），所以这条要以实测为准。
7. **`RESTRICT` 语义较微妙**：A 批的 **A9** 是它的守门，必须保留。
8. **样本体积上限与 nginx 顶格**：`nginx.conf:21` 是 `client_max_body_size 10m`，与阿里云允许的 10MB 顶格相等，multipart 边界开销可能触发 413。本方案把样本上限定为 **8MB**：常见的 16kHz 单声道 WAV 20 秒约 640KB（`16000 × 2B × 20s`）、MP3 更小，即便用 48kHz 立体声 WAV 20 秒也只有约 3.8MB，8MB 留有充裕余量，且不必动基础设施。（文档上传的 10MB 上限有同样问题，不属本期；样本格式要求以阿里云实测返错为准，见风险 6。）
9. **状态可能长期停在 `deploying`**：Beat 只扫 24 小时内的行，超期后保留最后已知状态并记 warning。二期做告警或人工介入入口；**不做**在期内伪造终态 —— 那会让界面说谎。
10. **`create_voice` 的孤儿音色**：请求发出但响应丢失时，阿里云侧可能留下一个音色而我们没有记录。已用"日志记录 `prefix`"让它可追溯，二期加 `action=list_voice` 对账任务。
11. **`clean_dirty_characters --all` 的语义变了**：D 批之后 `_clean_orphan_voices`（`clean_dirty_characters.py:117-131`）会删掉所有"非内置且无角色引用"的音色，其中将包含真实用户创建的；`_clean_orphan_users`（`:96-115`）会删掉无角色无好友的用户，级联带走其名下音色。它从"清测试残留"变成"能删真实用户数据"。好消息是 `count() == 0` 的前置判断天然兼容 `RESTRICT`（不会抛 `RestrictedError`）。**最小修复：`--all` 在 `DEBUG=False`（生产）下直接拒绝执行** —— 已确认 `deploy/` 与 `服务器部署.md` 都不调用它，这道闸不会挡住任何流程。
12. **阿里云侧保留了原始样本的副本**（实测发现）：`query_voice` 的响应里带一个 `resource_link`，指向 `.../orig/<voice_id>.mp3` 的签名 URL（带 `Expires` 参数）。也就是说 §8 里"复刻提交后立即删除样本"**只在我们这一侧成立**，第三方侧并未删除。后果有两条：① 给用户的隐私说明必须写准，不能暗示"全链路已删除"——样本确实被提交给了阿里云；② 它也是一个潜在的备用试听音源（本期不采用，因为对克隆者本人来说"听回自己的样本"没有信息量，且链接会过期）。
13. **阿里云侧音色的 1 年计时以"是否被合成使用"为准**：那个复刻音色的 `gmt_modified` 停在创建后 5 秒（2026-04-19），说明元数据没有再动过，但 `gmt_modified` 反映的是元数据变更而非合成调用，**无法据此判断它是否已临近 1 年自动删除**。一期不做探活（见风险 3），二期补。

---

## 12. 分期

- **一期**（本文档）：A 修正 + B 试听 + C 归属模型 + D 私有复刻
- **二期**（未设计）：公开共享 + 授权记录持久化 + 举报/下架 + 音色分类与分页 + 阿里云音色探活 + 「删除并把引用改绑」流程

---

## 13. PR 分批

| 批次 | 内容 | 迁移 | 可独立上线 |
|---|---|---|---|
| A+B | 隐患修正 + 命名统一 + 试听 | 0023 | 是 |
| C | 归属模型 + 列表过滤 + 数据迁移 | 0024 | 是 |
| D | 复刻接线（OSS + 阿里云 create/delete + Beat 状态刷新 + 配额）+ `clean_dirty_characters` 的 DEBUG 闸 + 删除 `voice/custom/` 未接线原型 | — | 是，但需先备妥 OSS 凭据 |

每批单独走 门 3（PR 人工评审）与 门 4（云端验收）。
