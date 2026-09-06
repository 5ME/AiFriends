# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Friends — a full-stack web app where users create AI characters ("friends") and chat with them. Supports text + voice input/output, long-term memory summarization, and RAG-based knowledge retrieval.

- **Backend:** Django 6.0 + Django REST Framework + JWT auth (PostgreSQL 17 + pgvector 0.8)
- **Frontend:** Vue 3 (Composition API) + Vite 7 + Pinia + Vue Router 5 + Tailwind CSS 4 + daisyUI 5
- **AI:** Alibaba DashScope via OpenAI-compatible API (Chat/Memory: deepseek-v4-flash, TTS: cosyvoice-v3-flash, ASR: gummy-realtime-v1, Embedding: text-embedding-v4). LangChain/LangGraph for orchestration. pgvector for vector storage.
- **Voice:** DashScope TTS (WebSocket streaming) + ASR (WebSocket). Browser-side VAD via `@ricky0123/vad-web` (Silero VAD on ONNX).

## Commands

### Backend (Python/Django)

Uses conda environment at `D:\MyWork\Miniconda3\envs\py312`. Activate with `conda activate py312` before running commands.

```bash
cd backend
pip install -r ../requirements.txt      # requirements.txt 在项目根目录
# DEBUG / SECRET_KEY 等通过 .env 环境变量控制，无需手动改 settings.py
python manage.py runserver              # Dev server on :8000
python -m pytest web/tests/ -v         # Run all backend tests (209 tests)
# PostgreSQL & Redis: Docker Compose 一键启动（见下方 Infrastructure）
# .env 模板: cp .env.example .env
python manage.py clean_dirty_characters --all  # Clean test residue data
# 部署到云服务器时 DEBUG = False
python manage.py collectstatic          # Collect static files for production
```

### Frontend (Node/Vue/Vite)

```bash
cd frontend
npm install
npm run dev         # Vite dev server with HMR on :5173
npm run build       # Production build → ../backend/static/frontend/
npm run preview     # Preview production build locally
```

### Infrastructure

**Docker Compose** (`docker-compose.yml` at project root):

```bash
wsl docker compose up -d   # 启动 PostgreSQL 17 + pgvector + Redis 7
```

**Celery Worker:**

```bash
cd backend
celery -A backend worker --loglevel=info --pool=solo
```

### Production Deployment

部署走「本地 build 镜像 → push 阿里云 ACR → 服务器 pull」的 registry 流程，完整步骤见 `服务器部署.md`：

1. 本地构建机：`ACR_IMAGE=<镜像名> ./deploy/build.sh`（多阶段 build：前端打进镜像 + collectstatic → push 到 ACR）
2. 服务器：`docker compose pull && docker compose up -d`（5 容器，不 build、不 scp）

**前端 platform 自动切换：**

| 场景 | 命令 | 使用的 API 地址 |
|------|------|----------------|
| 开发热更新 | `npm run dev` | `http://127.0.0.1:8000` |
| 本地打包测试 | `$env:VITE_PLATFORM='django'; npm run build` | `http://127.0.0.1:8000` |
| 生产部署 | 镜像内自动 `VITE_PLATFORM=docker` build | 同源 `''` |

## Architecture

### Testing (pytest)

- Tests in `web/tests/`, run with `python -m pytest web/tests/ -v` (209 tests)
- `pytest.ini` 配置默认 `-m "not slow"` 跳过需真实 API_KEY 的慢测试（`test_tool_calling.py` 中 3 个）
- `conftest.py` provides global fixtures: `api_client`, `user`, `auth_client`, `character`, `friend`, `_disable_rate_limit_for_tests` (autouse), `media_root` (session, autouse), `pgvector_extension` (session, autouse), `mock_asr_ws`, etc.
- `media_root` fixture (autouse, session-scoped) redirects test uploads to a temp directory — test files never touch real `media/`
- `_disable_rate_limit_for_tests` fixture (autouse) globally patches rate limit for all tests; `test_rate_limit.py` overrides it with its own `@patch`
- Tests use `model_bakery` (baker.make) + `pytest-django` transaction rollback
- **Dual-DB strategy:** tests run on PostgreSQL `aifriends_test` database (auto-detected via `sys.argv`), separated from the development `aifriends` database. Avoids polluting development data during tests.

### GitHub Actions CI

`.github/workflows/test.yml` — 209 tests auto-run on push/PR to master:
- `ubuntu-latest` + Python 3.12 + `pgvector/pgvector:pg17` service container
- Creates `aifriends_test` database, runs `pytest web/tests/ -v`
- No Redis/Celery service — rate limit & health check tests rely on mock/patch in CI

### How the stacks connect

The frontend is built into `backend/static/frontend/`. Django serves the SPA via a catch-all route: `web/views/index.py` reads the built `frontend/index.html` (from `STATIC_ROOT` in prod, `static/` in dev), which loads the Vite-built assets. All API routes live under `/api/` in `backend/web/urls.py`.

### Environment / platform modes

`frontend/src/js/config/config.js` 根据 Vite MODE 和 `VITE_PLATFORM` 环境变量自动切换：

| Mode | HTTP base | 触发方式 |
|------|-----------|---------|
| `vue` | `http://127.0.0.1:8000` | `VITE_PLATFORM=vue npm run dev` |
| `django` | `http://127.0.0.1:8000` | `npm run dev`（默认）|
| `cloud` | `VITE_CLOUD_BASE` 或 `https://115.190.245.146` | `npm run build`（默认）|
| `docker` | `''`（同源）| `VITE_PLATFORM=docker npm run build` |

不再需要手动改 `platform` 变量。`npm run dev` 和 `npm run build` 会自动选择合适的模式。

> 生产部署用 `docker` 模式（同源）：多阶段 Dockerfile 里固定 `VITE_PLATFORM=docker`，前端产物随镜像分发，不再用 `cloud` 模式。

### JWT auth flow

- Login/register returns `access_token` (2h TTL) in response body + `refresh_token` (7d TTL) as httpOnly cookie.
- `accessToken` is stored in memory via Pinia store (`stores/user.js`), never persisted.
- Axios request interceptor attaches `Authorization: Bearer <token>`.
- On 401, a response interceptor silently calls `/api/user/account/refresh_token/`, queues concurrent requests, and retries them with the new token. If refresh fails, user is logged out.
- Login/register endpoints are whitelisted from the 401→token-refresh interceptor (a 401 there means "wrong credentials," not "expired token").

### SECRET_KEY enforcement

`DJANGO_SECRET_KEY` 从环境变量读取：
- **DEBUG=True**: 未设置时 fallback 到 `'django-insecure-dev-only-not-for-production'`
- **DEBUG=False**: 未设置时抛出 `ImproperlyConfigured`，拒绝启动

### Backend view pattern

Each API endpoint is a single file under `backend/web/views/`, each exporting a DRF `APIView` subclass. **No DRF serializers are used** — views read `request.data` / `request.FILES` directly and return plain dicts via `Response(data, status=...)`.

**HTTP status code conventions** — never use the default 200 for error responses:
- `200` — success (only for successful operations)
- `400` — client validation error (empty fields, missing required data)
- `401` — authentication failure (wrong password, expired token)
- `404` — resource not found
- `409` — conflict (duplicate username, etc.)
- `429` — rate limit exceeded (handled by RateLimitMiddleware)
- `500` — server error (unhandled exception)
- `503` — service degraded (health check partial failure)

**Exception handling:** Never use bare `except:`. Always `except Exception as e:` with `logger.exception(...)` before the error response. Every view imports `logging` and has `logger = logging.getLogger(__name__)`.

### Data models

Models live in `backend/web/models/` — six files:

| File | Models |
|------|--------|
| `user.py` | UserProfile |
| `character.py` | Character, Voice |
| `friend.py` | Friend, Message, SystemPrompt |
| `document.py` | UserDocument, DocumentChunk (pgvector VectorField) |
| `retrieval_trace.py` | RetrievalTrace (RAG 检索 trace 落库) |
| `usage.py` | APIUsage (LLM/TTS/ASR/Embedding 用量追踪) |

### Logging

LOGGING is configured in `backend/backend/settings.py` with console (StreamHandler) + rotating file handler (`logs/web.log`, 10 MB × 5 backups). Both the root logger and the `web` logger are set to INFO level.

All view modules use `logger = logging.getLogger(__name__)`. Use `logger.exception()` on caught errors (equivalent to `logger.error(... exc_info=True)`, captures full traceback).

Log format: `[{levelname}] {asctime} [{request_id}] {module}: {message}` — `RequestIdFilter` 注入 `request_id` 到每条日志。

### Middleware

`backend/web/middleware/` 包含两个自定义中间件：

1. **`request_id.py`** — `RequestIdMiddleware` + `RequestIdFilter`
   - 每个请求生成 `uuid.uuid4().hex` 唯一 ID，通过 `threading.local()` 传递
   - 响应头设置 `X-Request-ID`
   - 记录每个请求的 `METHOD /path -> STATUS, duration=X.Xms`

2. **`rate_limit.py`** — `RateLimitMiddleware`
   - Redis Lua 原子脚本实现滑动窗口日志算法
   - 区分认证用户（`user:{id}`）和匿名用户（`ip:{ip}`）限流
   - 仅限制写方法（POST/PUT/PATCH/DELETE），GET/HEAD/OPTIONS 放行
   - Fail-open: Redis 不可达时放过请求并记录异常
   - 6 条规则: login(5/60s), register(3/60s), chat(20/60s), asr(10/60s), upload(10/60s), default(60/60s)
   - 跳过路径: `/api/health/`, `/api/user/account/refresh_token/`, `/static/`, `/media/`, `/admin/`
   - 返回 HTTP 429 + `Retry-After` 头

### Character fields

`Character.profile` has been split into two independent fields:

- **`introduction`** (`max_length=500`) — public intro shown on cards and the `CharacterDetail` modal. Frontend display uses this directly.
- **`system_prompt`** (`max_length=10000`) — full character personality prompt sent to the LLM via `chat/graph.py` and `chat/chat.py`.

The two fields are completely independent — `system_prompt` does NOT include `introduction`. Only `system_prompt` enters the LLM context.

### Character.photo_url / background_image_url

Use `character.photo_url` and `character.background_image_url` properties instead of `.photo.url` / `.background_image.url`. These safe properties return `''` when no file is associated, preventing `ValueError` crashes.

### Voice.is_builtin

System built-in voices (longanyang/longanhuan) have `is_builtin=True`. The cleanup command skips them. Never delete a voice with `is_builtin=True`.

### Character detail → chat flow

On the homepage, clicking a character card opens `CharacterDetail.vue` (a modal) rather than jumping straight to chat. The component:
1. Calls `GET /api/friend/is_friend/?character_id=X` to check friendship status
2. Shows "添加好友" or "开始聊天" button accordingly
3. On button click, calls `POST /api/friend/get_or_create/` then opens `ChatField`

`Character.vue` accepts a `showDetail` prop — when true, the card click opens the detail modal first; when false (friend list page, user space), the old direct-to-chat behavior is preserved.

### LangGraph agent architecture

Two separate LangGraph state graphs:

1. **Chat agent** (`web/views/friend/message/chat/graph.py`) — `deepseek-v4-flash` model with tools: `get_time` and `search_knowledge_base` (pgvector 余弦向量检索，JOIN UserDocument 获取标题，按 `owner_id` 过滤召回全局知识库 + 用户个人文档)。Streams tokens via SSE. Also streams TTS audio chunks (base64 mp3) over the same SSE connection using a separate DashScope WebSocket.

2. **Memory agent** (`web/views/friend/message/memory/graph.py`) — `deepseek-v4-flash` model. 通过 Celery 异步任务 (`web/views/friend/message/memory/tasks.py`) 每 10 条消息触发一次，摘要写入 `Friend.memory` 字段。`last_summarized_count` 字段防止失败重试时遗漏消息。

### SystemPrompt 3 层架构

`chat.py` 的 `add_system_prompt()` 构建 3 层独立的 SystemMessage 栈：

| 层级 | 来源 | 内容 |
|------|------|------|
| **Layer 1** (最高优先级) | 代码常量 `TOOL_RULES` | 工具调用规则（何时必须/禁止调用 `search_knowledge_base`）|
| **Layer 2** | `Character.system_prompt` + `Friend.memory` | 角色性格 + 长期记忆 |
| **Layer 3** (框架) | DB `SystemPrompt` (title=REPLY) | 系统级框架约束，管理员可配置 |

三层独立注入，互不耦合。Memory Agent 使用 `SystemPrompt` (title=MEMORY) 按 `order_number` 排序拼接。

### Celery async tasks

`web/tasks/` 包（`__init__.py`）是 Celery `autodiscover_tasks()` 的入口，所有异步任务通过此包注册导入：

```python
from web.views.friend.message.memory.tasks import update_memory_task    # Memory Agent
from web.views.document.tasks import process_document_task              # 文档处理
from web.tasks.cleanup_usage import cleanup_usage_task                # 用量数据清理
```

`autodiscover_tasks()` 只扫描 `<app>.tasks` 模块，深度嵌套的 task 文件必须在此入口文件中显式导入。

**Celery 配置：**
- `CELERY_TASK_ACKS_LATE = True` — Worker 崩溃时任务自动回到队列
- `CELERY_WORKER_PREFETCH_MULTIPLIER = 1` — 一次只取一个任务（避免并发 LLM 调用）
- `CELERY_TASK_SOFT_TIME_LIMIT = 120s`, `CELERY_TASK_TIME_LIMIT = 180s`

**任务重试策略（两个 task 通用）：**
- 4xx 错误（除 429）→ 永久故障，不重试，清空 `celery_task_id`
- 5xx / 429 / 网络错误 → 临时故障，retry(countdown=10)，保留 `celery_task_id` 支持撤销

### Document processing reliability

`UserDocument.celery_task_id` 字段追踪异步任务：
- **上传：** `delay()` 成功后保存 `task.id`；投递失败（Celery broker 不可达）→ `status='failed'`
- **完成：** 成功或永久故障时清空 `celery_task_id`
- **重试中：** 保留 `celery_task_id`，支持撤销
- **删除：** `remove.py` 检查 `celery_task_id` → `app.control.revoke(task_id)` 撤销排队/等待中的任务（best-effort，失败不阻止删除）

### RAG / knowledge base

`backend/web/documents/` 三层架构：

```
documents/
├── loaders/          # 文档加载层（抽象接口 + txt/md/pdf 三种 loader）
├── services/         # 服务层（embeddings + chunker 统一切分）
└── utils/            # 系统知识库批量导入（增量更新）
```

- **向量化：** `CustomEmbeddings` 封装 DashScope `text-embedding-v4` API（1024 维）
- **切分：** `RecursiveCharacterTextSplitter(chunk_size=500, overlap=50)`
- **存储：** `DocumentChunk` 模型（pgvector VectorField，HNSW 索引）
- **用户隔离：** `DocumentChunk.owner` 字段，`search_knowledge_base` 按 `WHERE owner_id IS NULL OR owner_id = %s` 同时召回全局 + 个人文档

**系统知识库增量更新：** `insert_documents.py` 使用 `DocumentChunk.content_hash`（SHA-256）对比新旧 chunk，跳过未变内容避免重复 embedding。

**API 端点：**

| 端点 | 功能 |
|------|------|
| `POST /api/document/upload/` | 上传文档 → 魔数校验 → Celery 异步处理 |
| `GET /api/document/list/` | 用户文档列表 |
| `POST /api/document/remove/` | 删除文档 → revoke Celery 任务 → 级联删除 chunks |

**Celery 任务：** `process_document_task(doc_id)` — 文本提取 → 分块 → embedding → 批量写入 DocumentChunk。注册在 `web/tasks/`。

### RAG citations & RetrievalTrace

`search_knowledge_base` 工具返回的结果带有来源标记：

```
[来源N: 文档标题 第M段]
内容文本...
```

- JOIN `UserDocument` 获取文档标题，系统知识库（`document_id=NULL`）显示为 "系统知识库"
- `RetrievalTrace` 模型记录每次检索：`user`, `query`, `document_id`, `chunk_index`, `distance`
- `chat.py` 检测 LangGraph `ToolMessage(name="search_knowledge_base")`，正则提取 citations
- SSE 流在 content 之前发送 `{"citations": [...]}` 事件

### Rate limiting & API usage tracking

**限流：** `RateLimitMiddleware`（见 Middleware 节）

**API 用量追踪：** `APIUsage` 模型记录 4 类 AI 调用：

| 类型 | 记录位置 | 记录内容 |
|------|---------|---------|
| `llm` | `chat.py`, `memory/tasks.py` | model_name, token_count, duration_ms, success |
| `tts` | `chat.py`（同步上下文写入） | character_count 作为 token_count |
| `asr` | `asr/asr.py` | duration_ms, success |
| `embedding` | `embeddings.py` | 批量 token_count, success |

`record_api_usage()` 是 fire-and-forget 函数，所有异常内部 catch+log，不阻塞业务。

### Health check

`GET /api/health/` — 三组件独立检测：

| 组件 | 检测方式 | 失败时 |
|------|---------|--------|
| DB | `connections['default'].cursor()` | 字段 `"error"` |
| Redis | `redis.from_url(settings.REDIS_URL).ping()` | 字段 `"error"` |
| Celery | `app.control.inspect().ping()` | 字段 `"error"` |

- 全部通过 → `{"status": "ok", ...}` HTTP 200
- 任一失败 → `{"status": "degraded", ...}` HTTP 503

### Django Admin

`web/admin.py` 注册了所有主要模型：
- `UserDocumentAdmin` — `list_display` 含 title/owner/file_type/status/chunks_count；`readonly_fields` 含 `celery_task_id`/`error_message`；支持搜索和状态/类型过滤
- `DocumentChunkAdmin` — `exclude=('embedding',)` 避免 vector 字段撑爆 admin 页面
- `CharacterAdmin`, `FriendAdmin`, `MessageAdmin` — `raw_id_fields` 避免 N+1 查询
- 其他: `UserProfileAdmin`, `Voice`, `SystemPrompt`

### Frontend

#### Toast notification system

- **`useToast.js`** composable — 模块级 `reactive()` 单例，`readonly()` 暴露防止外部修改
- **`ToastContainer.vue`** — daisyUI alert 样式（success/error/warning/info），`<transition-group>` 动画
- 自动移除（非 error 3s）+ 手动关闭（error 永不清除），最多 5 条上限
- 挂载在 `App.vue` 中，`KnowledgeBase.vue` 是首个消费者
- alert 颜色用静态 class 对象避免 Tailwind JIT 漏生成

#### Shared composables

- **`useImageCropper.js`** — 封装 Croppie init/crop/destroy，三个组件复用（角色 Photo、用户 Photo、BackgroundImage），消除了之前 90% 重复代码
- **`useDocumentPolling.js`** — 每 3s 轮询文档列表，全部到终态自动停止，120 次兜底（6 分钟），`onUnmounted` 清理

#### Knowledge base page

`/knowledge` 路由 → `KnowledgeBase.vue`（`meta: { needLogin: true }`）：
- **UploadZone** — 拖拽/点击上传 .txt/.md/.pdf（≤10MB，前端校验格式+大小）
- **DocumentCard** — 文档卡片，状态标签（pending/processing/completed/failed）
- **useDocumentPolling** — 文档处理状态轮询
- **useToast** — 上传/删除操作的成功/失败通知

#### Frontend error handling

**200 = success.** Components no longer check `data.message === 'success'` — HTTP 200 guarantees the operation succeeded.

**4xx/5xx errors go through `catch` blocks.** Components read `e.response?.data?.message` with a fallback string:

```javascript
} catch (e) {
  errorMessage.value = e.response?.data?.message || '网络异常'
}
```

**axios 401 whitelist:** Login/register endpoints are excluded from the 401→token-refresh interceptor (`frontend/src/js/http/api.js`), since a 401 on those means "wrong credentials," not "expired token."

### SSE streaming (chat)

The frontend uses `@microsoft/fetch-event-source` (`js/http/streamApi.js`) to POST to `/api/friend/message/chat/`. The response is `text/event-stream` with JSON lines containing:
- `data.content` — text delta
- `data.audio` — base64 mp3 chunk (played through browser Media Source Extensions)
- `data.citations` — RAG 引用来源（在 content 之前到达）
- `data.error` — 错误信息

Audio is played through browser Media Source Extensions.

### Voice pipeline

- **Input:** `Microphone.vue` uses `@ricky0123/vad-web` (Silero VAD via ONNX/WASM) to detect speech end, captures PCM16 audio, sends it to `/api/friend/message/asr/asr/` → DashScope WebSocket for transcription.
- **Output:** Chat SSE stream carries interleaved text + audio chunks; `InputField.vue` feeds audio into `MediaSource` for real-time playback.

### Known technical debt

- **WSGI + threading + asyncio.run** (`chat.py:194`): Django WSGI 视图中创建裸线程跑 `asyncio.run()` 存在线程安全和连接泄漏风险
- **SSE 背压控制缺失:** `queue.Queue()` 无 `maxsize`，内存可能无界增长
- **无 API 版本化:** 32+ 端点直接挂在 `/api/` 下
- **前端未消费 RAG citations:** 后端已发送 `citations` SSE 事件，前端 `InputField.vue` 静默忽略
- **CI 无 Redis 服务:** 限流和健康检查的 Redis 路径在 CI 中依赖 mock
